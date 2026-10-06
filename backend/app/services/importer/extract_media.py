"""Pre-extraction for screenshots and PDFs (plan §4.1 steps 2 and 4, no AI).

Each image, and each PDF page, becomes one selectable source in the import wizard (the
``sheets`` list of the import, with ``kind`` "image" or "pdf_page"). For a PDF page the
text layer is read with pdfplumber and numbered line by line, so the model can cite
the line a product came from. The rendered page goes along with it, so the model sees
the table layout the text alone loses. Scanned pages (no text layer) are sent as
images only.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pdfplumber
import pypdfium2 as pdfium
from PIL import Image

from app.services.importer.extract_xlsx import CURRENCY_MAP, CURRENCY_RE, FX_RE, PREVIEW_ROWS

IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
PDF_DPI = 150
SCANNED_MIN_CHARS = 20
# Sent as is when within these limits; otherwise downscaled and re-encoded as JPEG.
# Both providers accept larger images but cap the bytes per image and gain nothing from
# more pixels than they read.
MAX_IMAGE_EDGE = 2576
MAX_IMAGE_BYTES = 3_500_000


@dataclass
class ImageInput:
    media_type: str
    data: bytes


def media_kind(filename: str) -> str | None:
    suffix = Path(filename).suffix.lower()
    if suffix in IMAGE_TYPES:
        return "image"
    if suffix == ".pdf":
        return "pdf"
    return None


def _source(name: str, kind: str, **extra: Any) -> dict[str, Any]:
    """Same keys as a spreadsheet's SheetSummary, so the wizard handles both alike."""
    return {
        "name": name,
        "kind": kind,
        "hidden": False,
        "rows": 0,
        "columns": 0,
        "looks_like_price_table": True,
        "preselected": True,
        "header_row": None,
        "currency": None,
        "fx_rate": None,
        "preview": [],
        **extra,
    }


def image_source(name: str, path: Path) -> dict[str, Any]:
    """Raises if Pillow cannot read the file."""
    with Image.open(path) as img:
        img.verify()
    with Image.open(path) as img:
        width, height = img.size
    return _source(name, "image", file=path.name, width=width, height=height)


def page_lines(page: Any) -> list[str]:
    """Text of one pdfplumber page with its layout kept, blank edges trimmed."""
    text = page.extract_text(layout=True) or ""
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def pdf_sources(path: Path) -> list[dict[str, Any]]:
    """One source per page. Raises if the PDF cannot be opened."""
    sources = []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            lines = page_lines(page)
            text = "\n".join(lines)
            scanned = len("".join(text.split())) < SCANNED_MIN_CHARS
            fx = FX_RE.search(text)
            currency = CURRENCY_RE.search(text)
            sources.append(
                _source(
                    f"Page {number}",
                    "pdf_page",
                    file=path.name,
                    page=number,
                    scanned=scanned,
                    rows=sum(1 for line in lines if line.strip()),
                    currency=CURRENCY_MAP.get(currency.group(1).lower(), "CNY")
                    if currency
                    else None,
                    fx_rate=fx.group(1) if fx else None,
                    preview=[[line.strip()] for line in lines if line.strip()][:PREVIEW_ROWS],
                )
            )
    return sources


def numbered_lines(path: Path, page: int) -> dict[int, str]:
    """Line number (1-based, as sent to the model) -> text, for one PDF page."""
    with pdfplumber.open(path) as pdf:
        lines = page_lines(pdf.pages[page - 1])
    return {n: line for n, line in enumerate(lines, start=1)}


def render_numbered(lines: dict[int, str]) -> str:
    width = len(str(max(lines))) if lines else 1
    return "\n".join(f"L{n:0{width}d} | {text}" for n, text in lines.items())


def render_page(path: Path, page: int, dpi: int = PDF_DPI) -> bytes:
    """PNG of one PDF page."""
    pdf = pdfium.PdfDocument(path)
    try:
        bitmap = pdf[page - 1].render(scale=dpi / 72)
        image = bitmap.to_pil()
    finally:
        pdf.close()
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def page_png(path: Path, page: int) -> Path:
    """Rendered page, cached next to the PDF."""
    cached = path.with_name(f"page_{page}.png")
    if not cached.exists():
        cached.write_bytes(render_page(path, page))
    return cached


def prepare_image(data: bytes, media_type: str) -> ImageInput:
    """Downscale and re-encode only when the image is too large to send as is."""
    with Image.open(io.BytesIO(data)) as opened:
        too_big = max(opened.size) > MAX_IMAGE_EDGE or len(data) > MAX_IMAGE_BYTES
        if not too_big:
            return ImageInput(media_type, data)
        img: Image.Image = opened.copy()
    img.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
    if img.mode not in ("RGB", "L"):
        background = Image.new("RGB", img.size, "white")
        background.paste(img, mask=img.getchannel("A") if "A" in img.getbands() else None)
        img = background
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return ImageInput("image/jpeg", out.getvalue())
