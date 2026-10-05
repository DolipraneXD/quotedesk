"""Import orchestration: upload -> pre-extract -> extract (LLM) -> analyze -> review.

An import is either one spreadsheet or any number of screenshots and PDFs. Every sheet,
image and PDF page is a "source" the user can select; extraction sends units of work to
the model (spreadsheet chunks of 60 rows, whole images, whole pages). It runs in a
background thread with its own event loop and DB session; up to ``MAX_IN_FLIGHT`` units
call the API concurrently. All DB writes happen on that one
event-loop thread, so SQLite sees a single writer.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import active_model, data_dir, get_api_key, load_settings
from app.db import session_factory
from app.errors import ProblemError
from app.models import Brand, Category, Import, ImportRow
from app.services.importer import extract_media as media
from app.services.importer import extract_xlsx as xl
from app.services.importer.llm_parser import (
    ChunkContext,
    ClaudeExtractor,
    ExtractionError,
    Extractor,
    GeminiExtractor,
    GroqExtractor,
    InceptionExtractor,
    OutputTooLong,
    SourceKind,
    system_prompt,
)
from app.services.importer.matcher import MatchContext, SheetInfo, analyze_row, jsonable, to_decimal

log = logging.getLogger("quotedesk.import")

MAX_IN_FLIGHT = 4
MIN_SPLIT_ROWS = 4
SPREADSHEET_TYPES = {".xlsx": "xlsx", ".xlsm": "xlsx", ".csv": "csv"}


def imports_dir(import_id: int) -> Path:
    return data_dir() / "imports" / str(import_id)


# ---------------------------------------------------------------- upload


def create_import(session: Session, files: list[tuple[str, bytes]]) -> Import:
    """One spreadsheet, or any mix of images and PDFs (several screenshots = one import)."""
    if not files:
        raise ProblemError(422, "import.no_file", "No file uploaded")
    kinds = []
    for name, _ in files:
        suffix = Path(name).suffix.lower()
        if suffix == ".xls":
            raise ProblemError(
                415, "import.xls_unsupported", "Old .xls files are not supported; save as .xlsx"
            )
        kind = SPREADSHEET_TYPES.get(suffix) or media.media_kind(name)
        if kind is None:
            raise ProblemError(415, "import.unsupported_type", "Unsupported file type", type=suffix)
        kinds.append(kind)
    spreadsheet = any(k in ("xlsx", "csv") for k in kinds)
    if spreadsheet and len(files) > 1:
        raise ProblemError(
            422, "import.one_spreadsheet", "Upload spreadsheets one at a time, without images"
        )

    first = files[0][0]
    imp = Import(
        filename=first if len(files) == 1 else f"{first} (+{len(files) - 1})",
        stored_path="",
        file_type=kinds[0] if len(set(kinds)) == 1 else "media",
    )
    session.add(imp)
    session.flush()
    folder = imports_dir(imp.id)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        if spreadsheet:
            imp.sheets = _spreadsheet_sources(imp, folder, *files[0])
        else:
            imp.sheets = _media_sources(imp, folder, files, kinds)
    except ProblemError:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    except Exception as exc:  # corrupt, password-protected or truncated file
        shutil.rmtree(folder, ignore_errors=True)
        raise ProblemError(422, "import.unreadable", f"Cannot read the file: {exc}") from exc
    imp.status = "uploaded"
    return imp


def _spreadsheet_sources(imp: Import, folder: Path, name: str, content: bytes) -> list[Any]:
    path = folder / f"source{Path(name).suffix.lower()}"
    path.write_bytes(content)
    imp.stored_path = str(path)
    return [xl.summarize(grid, hidden).to_dict() for grid, hidden in xl.load_grids(path)]


def _media_sources(
    imp: Import, folder: Path, files: list[tuple[str, bytes]], kinds: list[str]
) -> list[Any]:
    imp.stored_path = str(folder)
    single_file = len(files) == 1
    sources: list[dict[str, Any]] = []
    for index, ((name, content), kind) in enumerate(zip(files, kinds, strict=True), start=1):
        path = folder / f"source_{index}{Path(name).suffix.lower()}"
        path.write_bytes(content)
        if kind == "image":
            sources.append(media.image_source(name, path))
            continue
        for page in media.pdf_sources(path):
            if not single_file:  # "Page 1" alone, "<file> p1" next to other files
                page["name"] = f"{name} p{page['page']}"
            sources.append(page)
    _dedupe_names(sources)
    return sources


def _dedupe_names(sources: list[dict[str, Any]]) -> None:
    seen: dict[str, int] = {}
    for source in sources:
        name = source["name"]
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            source["name"] = f"{name} ({seen[name]})"


def source_image(imp: Import, index: int) -> Path:
    """The image file of a screenshot source, or the rendered page of a PDF source."""
    if not 0 <= index < len(imp.sheets):
        raise ProblemError(404, "import.no_source", "No such source", index=index)
    source = imp.sheets[index]
    folder = Path(imp.stored_path)
    if source.get("kind") == "image":
        return folder / source["file"]
    if source.get("kind") == "pdf_page":
        return media.page_png(folder / source["file"], source["page"])
    raise ProblemError(404, "import.no_source", "This source has no image", index=index)


def delete_import(session: Session, imp: Import) -> None:
    if imp.status == "committed":
        raise ProblemError(409, "import.committed", "Revert the import before deleting it")
    if imp.status == "extracting":
        raise ProblemError(409, "import.busy", "Cancel the extraction first")
    folder = imports_dir(imp.id)
    session.delete(imp)
    session.flush()
    shutil.rmtree(folder, ignore_errors=True)


# ------------------------------------------------------------ extraction


def make_extractor(session: Session) -> Extractor:
    """Overridden in tests with a fake that returns recorded rows."""
    settings = load_settings()
    key = get_api_key(settings.llm_provider)
    if not key:
        raise ProblemError(
            409, "import.no_api_key", "Set the AI provider's API key in Settings",
            provider=settings.llm_provider,
        )  # fmt: skip
    categories = list(session.scalars(select(Category).order_by(Category.sort_order)))
    brands = list(session.scalars(select(Brand).order_by(Brand.canonical)))
    cls = {
        "anthropic": ClaudeExtractor,
        "google": GeminiExtractor,
        "groq": GroqExtractor,
        "inception": InceptionExtractor,
    }[settings.llm_provider]
    return cls(
        api_key=key,
        model=active_model(settings),
        system=system_prompt(categories, brands),
        category_codes=[c.code for c in categories],
    )


def spawn(target: Callable[[], None]) -> None:
    """Run work off the request thread. Tests replace this to run inline."""
    threading.Thread(target=target, daemon=True, name="quotedesk-import").start()


def start_extraction(
    session: Session, imp: Import, sheets: list[str], hints: dict[str, str]
) -> None:
    if imp.status not in ("uploaded", "review", "failed", "cancelled"):
        raise ProblemError(409, "import.busy", "This import cannot be extracted now")
    known = {s["name"] for s in imp.sheets}
    unknown = [s for s in sheets if s not in known]
    if unknown or not sheets:
        raise ProblemError(422, "import.bad_sheets", "Pick at least one sheet", sheets=unknown)
    extractor = make_extractor(session)  # fail fast (e.g. no API key) before going async
    session.execute(delete(ImportRow).where(ImportRow.import_id == imp.id))
    imp.sheets_selected = sheets
    imp.hints = hints
    imp.status = "extracting"
    imp.error = None
    imp.started_at = datetime.now(UTC)
    imp.progress = {"total_chunks": 0, "done_chunks": 0, "failed_chunks": 0, "errors": []}
    imp.llm_model = extractor.model
    imp.llm_tokens_in = 0
    imp.llm_tokens_out = 0
    session.commit()
    import_id = imp.id
    spawn(lambda: run_extraction(import_id, extractor))


def run_extraction(import_id: int, extractor: Extractor) -> None:
    try:
        asyncio.run(_extract(import_id, extractor))
    except Exception as exc:  # never let a background failure vanish silently
        log.exception("import %s failed", import_id)
        with session_factory()() as session:
            imp = session.get(Import, import_id)
            if imp is not None:
                imp.status = "failed"
                imp.error = str(exc)[:2000]
                session.commit()


@dataclass
class Unit:
    """One model call: a spreadsheet chunk, a screenshot, or a PDF page."""

    sheet: str
    label: str  # rows covered, for error messages ("3-62"); "" for a whole image or page
    context: ChunkContext
    chunk: xl.Chunk | None = None  # spreadsheet chunks can be split when output is too long
    lines: dict[int, str] | None = None  # PDF page text by line number, for the review


def _context(imp: Import, sheet: str, kind: SourceKind, body: str, **kw: Any) -> ChunkContext:
    file_date = xl.date_from_filename(imp.filename)
    return ChunkContext(
        filename=imp.filename,
        sheet=sheet,
        category_hint=imp.hints.get(sheet),
        detected_currency=kw.pop("currency", None),
        detected_fx_rate=kw.pop("fx_rate", None),
        file_date=file_date.isoformat() if file_date else None,
        body=body,
        kind=kind,
        **kw,
    )


def chunk_unit(imp: Import, chunk: xl.Chunk) -> Unit:
    numbers = chunk.row_numbers
    return Unit(
        sheet=chunk.sheet,
        label=f"{numbers[0]}-{numbers[-1]}" if numbers else "",
        context=_context(
            imp, chunk.sheet, "sheet", xl.render_chunk(chunk),
            currency=chunk.meta.currency, fx_rate=chunk.meta.fx_rate,
        ),
        chunk=chunk,
    )  # fmt: skip


def media_unit(imp: Import, source: dict[str, Any]) -> Unit:
    folder = Path(imp.stored_path)
    detected = {"currency": source.get("currency"), "fx_rate": to_decimal(source.get("fx_rate"))}
    if source["kind"] == "image":
        path = folder / source["file"]
        image = media.prepare_image(path.read_bytes(), media.IMAGE_TYPES[path.suffix.lower()])
        ctx = _context(imp, source["name"], "image", "", images=[image], **detected)
        return Unit(source["name"], "", ctx)
    pdf = folder / source["file"]
    page = media.prepare_image(media.page_png(pdf, source["page"]).read_bytes(), "image/png")
    if source.get("scanned"):  # no text layer: the page is just a picture
        ctx = _context(imp, source["name"], "image", "", images=[page], **detected)
        return Unit(source["name"], "", ctx)
    lines = media.numbered_lines(pdf, source["page"])
    body = media.render_numbered(lines)
    ctx = _context(imp, source["name"], "pdf_page", body, images=[page], **detected)
    return Unit(source["name"], "", ctx, lines=lines)


def build_units(imp: Import) -> list[Unit]:
    if imp.file_type in ("xlsx", "csv"):
        grids = [g for g, _ in xl.load_grids(Path(imp.stored_path), imp.sheets_selected)]
        return [chunk_unit(imp, c) for g in grids for c in xl.chunk_grid(g)]
    selected = set(imp.sheets_selected)
    return [media_unit(imp, s) for s in imp.sheets if s["name"] in selected]


async def _extract(import_id: int, extractor: Extractor) -> None:
    with session_factory()() as session:
        imp = session.get(Import, import_id)
        assert imp is not None
        units = build_units(imp)
        per_sheet: dict[str, dict[str, int]] = {}
        for unit in units:
            per_sheet.setdefault(unit.sheet, {"total": 0, "done": 0})["total"] += 1
        imp.progress = {**imp.progress, "total_chunks": len(units), "sheets": per_sheet}
        session.commit()

        semaphore = asyncio.Semaphore(MAX_IN_FLIGHT)
        sheet_meta: dict[str, dict[str, Any]] = {}

        def cancelled() -> bool:
            session.refresh(imp, ["status"])
            return imp.status == "cancelled"

        async def run_rows(unit: Unit) -> list[tuple[Unit, dict[str, Any]]]:
            """Extract a unit; on overlong output, split a spreadsheet chunk in half."""
            try:
                async with semaphore:
                    if cancelled():
                        return []
                    result = await extractor.extract(unit.context)
            except OutputTooLong:
                chunk = unit.chunk
                if chunk is None or len(chunk.rows) < MIN_SPLIT_ROWS * 2:
                    raise
                half = len(chunk.rows) // 2
                parts = [
                    chunk_unit(
                        imp,
                        xl.Chunk(
                            chunk.sheet, chunk.index, rows, chunk.header, chunk.title_rows,
                            chunk.meta,
                        ),
                    )
                    for rows in (chunk.rows[:half], chunk.rows[half:])
                ]  # fmt: skip
                nested = await asyncio.gather(*(run_rows(p) for p in parts))
                return [item for part in nested for item in part]
            imp.llm_tokens_in += result.input_tokens
            imp.llm_tokens_out += result.output_tokens
            if result.sheet_meta:
                merged = sheet_meta.setdefault(unit.sheet, {})
                for key, value in result.sheet_meta.items():
                    if value is not None and key not in merged:
                        merged[key] = value
            return [(unit, row) for row in result.rows]

        async def run_unit(unit: Unit) -> None:
            try:
                items = await run_rows(unit)
                _store_rows(session, imp, items)
            except ExtractionError as exc:
                imp.progress = {
                    **imp.progress,
                    "failed_chunks": imp.progress["failed_chunks"] + 1,
                    "errors": [
                        *imp.progress["errors"],
                        {"sheet": unit.sheet, "rows": unit.label, "message": str(exc)},
                    ],
                }
            sheets = dict(imp.progress.get("sheets", {}))
            entry = dict(sheets.get(unit.sheet, {"total": 0, "done": 0}))
            entry["done"] += 1
            sheets[unit.sheet] = entry
            imp.progress = {
                **imp.progress,
                "done_chunks": imp.progress["done_chunks"] + 1,
                "sheets": sheets,
            }
            session.commit()

        await asyncio.gather(*(run_unit(u) for u in units))

        if cancelled():
            return
        imp.progress = {**imp.progress, "sheet_meta": jsonable(sheet_meta)}
        analyze_import(session, imp)
        failed = imp.progress["failed_chunks"]
        if failed and failed == len(units):
            imp.status = "failed"
            imp.error = imp.progress["errors"][0]["message"] if imp.progress["errors"] else None
        else:
            imp.status = "review"
        session.commit()


def _raw_cells(unit: Unit, number: Any) -> dict[str, str]:
    """What the source holds for this row, shown next to it in the review."""
    if unit.chunk is not None:
        source = next((r for r in unit.chunk.rows if r.number == number), None)
        return {c.ref: c.value for c in source.cells if c.value} if source else {}
    if unit.lines is not None and isinstance(number, int) and number in unit.lines:
        return {f"L{number}": unit.lines[number].strip()}
    return {}  # screenshots: the review shows the image itself


def _store_rows(session: Session, imp: Import, items: list[tuple[Unit, dict[str, Any]]]) -> None:
    for unit, row in items:
        number = row.get("source_row")
        session.add(
            ImportRow(
                import_id=imp.id,
                row_index=int(number) if isinstance(number, int) else 0,
                sheet=unit.sheet,
                source_ref=f"{imp.filename}!{unit.sheet}!{number}",
                raw=_raw_cells(unit, number),
                parsed={"source": jsonable(row)},
                confidence=float(row["confidence"]) if row.get("confidence") is not None else None,
            )
        )


# --------------------------------------------------------------- analysis


def _sheet_info(imp: Import, sheet: str | None, file_date: date | None) -> SheetInfo:
    summary: dict[str, Any] = next((s for s in imp.sheets if s["name"] == sheet), {})
    llm_meta = (imp.progress.get("sheet_meta") or {}).get(sheet or "", {})
    price_date = None
    if llm_meta.get("price_date"):
        try:
            price_date = date.fromisoformat(str(llm_meta["price_date"])[:10])
        except ValueError:
            price_date = None
    return SheetInfo(
        currency=llm_meta.get("currency") or summary.get("currency"),
        fx_rate=to_decimal(llm_meta.get("fx_rate")) or to_decimal(summary.get("fx_rate")),
        price_date=price_date or file_date,
    )


def match_context(session: Session, imp: Import) -> MatchContext:
    settings = load_settings()
    return MatchContext.build(
        session,
        default_fx=Decimal(settings.default_fx_rate_cny_usd),
        import_date=(imp.created_at or datetime.now(UTC)).date(),
    )


def analyze_rows(session: Session, imp: Import, rows: list[ImportRow], ctx: MatchContext) -> None:
    file_date = xl.date_from_filename(imp.filename)
    infos: dict[str | None, SheetInfo] = {}
    for row in rows:
        if row.sheet not in infos:
            infos[row.sheet] = _sheet_info(imp, row.sheet, file_date)
        source_ref = f"{imp.filename}!{row.sheet}!"
        result = analyze_row(
            ctx, row.parsed["source"], row.user_edits or {}, infos[row.sheet], source_ref
        )
        row.status = result.status
        row.match_type = result.match_type
        row.matched_product_id = result.matched_product_id
        row.candidates = result.candidates
        row.issues = result.issues
        keep_decision = (row.user_edits or {}).get("decision")
        row.decision = keep_decision if keep_decision else result.decision
        row.parsed = {**row.parsed, "staged": result.staged, "target_key": result.target_key}


def _row_erp_codes(row: ImportRow) -> set[str]:
    staged = row.parsed.get("staged") or {}
    codes = [staged.get("erp_code"), *(staged.get("erp_code_alt") or [])]
    return {c.upper() for c in codes if c}


def mark_duplicates(rows: list[ImportRow]) -> None:
    """Several rows resolving to one product: the last one wins, like the last upload.

    Rows with different ERP codes are never duplicates, even with identical
    specifications: each ERP code becomes its own product. A row without a code belongs
    to the first code's product. When the group is an existing product (matched without
    a code), a second code cannot update it too: that row is skipped with a warning.
    """
    ordered = sorted(rows, key=lambda r: (r.sheet or "", r.row_index, r.id or 0))
    groups: dict[str, list[ImportRow]] = {}
    for row in ordered:
        key = row.parsed.get("target_key")
        if key and row.decision in ("create", "update"):
            groups.setdefault(key, []).append(row)

    for key, group in groups.items():
        variants: dict[str, list[ImportRow]] = {}  # identity within the group -> rows
        first_codes: set[str] | None = None
        for row in group:
            codes = _row_erp_codes(row)
            if codes and first_codes is not None and not codes & first_codes:
                if key.startswith("product:"):
                    row.decision = "skip"
                    row.issues = [
                        *row.issues,
                        {"code": "erp_conflict", "product": _label(group[0])},
                    ]
                    continue
                code = sorted(codes)[0]
                variant = f"{key}|erp:{code}"
                if not variants.get(variant):  # first row of this ERP variant
                    row.issues = [*row.issues, {"code": "erp_variant", "product": _label(group[0])}]
                row.parsed = {**row.parsed, "target_key": variant}
                variants.setdefault(variant, []).append(row)
                continue
            if codes and first_codes is None:
                first_codes = codes
            variants.setdefault(key, []).append(row)
        for members in variants.values():
            winner = members[-1]
            _inherit_codes(winner, members[:-1])
            for earlier in members[:-1]:
                earlier.decision = "skip"
                earlier.issues = [
                    *earlier.issues,
                    {"code": "duplicate_in_import", "row": f"{winner.sheet}!{winner.row_index}"},
                ]


def _inherit_codes(winner: ImportRow, replaced: list[ImportRow]) -> None:
    """The winning row keeps the ERP codes of the rows it replaces."""
    staged = winner.parsed.get("staged") or {}
    codes = [c for c in [staged.get("erp_code"), *(staged.get("erp_code_alt") or [])] if c]
    for row in replaced:
        other = row.parsed.get("staged") or {}
        for code in [other.get("erp_code"), *(other.get("erp_code_alt") or [])]:
            if code and code not in codes:
                codes.append(code)
    if codes:
        staged = {**staged, "erp_code": codes[0], "erp_code_alt": codes[1:]}
        winner.parsed = {**winner.parsed, "staged": staged}


def _label(row: ImportRow) -> str:
    staged = row.parsed.get("staged") or {}
    return str(staged.get("name_zh") or f"{row.sheet}!{row.row_index}")


def analyze_import(session: Session, imp: Import) -> None:
    session.flush()
    rows = list(session.scalars(select(ImportRow).where(ImportRow.import_id == imp.id)))
    analyze_rows(session, imp, rows, match_context(session, imp))
    mark_duplicates(rows)
    imp.stats = {**(imp.stats or {}), **row_counts(rows)}


def row_counts(rows: list[ImportRow]) -> dict[str, int]:
    counts = {s: 0 for s in ("new", "updated", "unchanged", "possible_match", "problem")}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    counts["total"] = len(rows)
    counts["to_apply"] = sum(1 for r in rows if r.decision in ("create", "update", "merge_into"))
    return counts
