"""Uploaded pictures: product photos, the company logo, the seller's signature.

Originals are kept under ``data/images/``. Documents embed a smaller copy (longest edge
``DOC_EDGE`` px), made once and cached next to the original, so a 12-megapixel phone
photo doesn't make every quote PDF 5 MB.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

from PIL import Image as PILImage
from sqlalchemy.orm import Session

from app.config import data_dir
from app.errors import ProblemError
from app.models import Image

MAX_BYTES = 15 * 1024 * 1024
DOC_EDGE = 1000
FORMATS = {
    "PNG": ("image/png", ".png"),
    "JPEG": ("image/jpeg", ".jpg"),
    "WEBP": ("image/webp", ".webp"),
}


def images_dir() -> Path:
    return data_dir() / "images"


def save_image(session: Session, filename: str | None, content: bytes) -> Image:
    if len(content) > MAX_BYTES:
        raise ProblemError(413, "image.too_large", "Images must be under 15 MB")
    try:
        with PILImage.open(io.BytesIO(content)) as img:
            img.verify()
        with PILImage.open(io.BytesIO(content)) as img:
            fmt, size = img.format or "", img.size
    except Exception as exc:
        raise ProblemError(422, "image.unreadable", "Not a readable image") from exc
    if fmt not in FORMATS:
        raise ProblemError(415, "image.unsupported", "Use PNG, JPEG or WebP", format=fmt)
    media_type, suffix = FORMATS[fmt]
    relative = f"{uuid.uuid4().hex}{suffix}"
    images_dir().mkdir(parents=True, exist_ok=True)
    (images_dir() / relative).write_bytes(content)
    image = Image(
        path=relative,
        original_name=filename,
        media_type=media_type,
        width=size[0],
        height=size[1],
    )
    session.add(image)
    session.flush()
    return image


def original_path(image: Image) -> Path:
    return images_dir() / image.path


def document_path(image: Image) -> Path:
    """A copy small enough to embed in PDFs and spreadsheets (PNG keeps transparency)."""
    source = original_path(image)
    target = source.with_name(f"{source.stem}_doc.png")
    if target.exists():
        return target
    with PILImage.open(source) as img:
        img.load()
        copy = img.convert("RGBA") if img.mode in ("P", "LA") else img.copy()
    copy.thumbnail((DOC_EDGE, DOC_EDGE), PILImage.Resampling.LANCZOS)
    copy.save(target, format="PNG", optimize=True)
    return target


def get_image(session: Session, image_id: int) -> Image:
    image = session.get(Image, image_id)
    if image is None or not original_path(image).exists():
        raise ProblemError(404, "image.not_found", "Image not found", id=image_id)
    return image
