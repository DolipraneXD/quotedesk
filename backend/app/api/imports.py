from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Query, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select

from app.api.deps import SessionDep
from app.errors import ProblemError
from app.models import Category, Import, ImportRow
from app.services.importer import commit as committer
from app.services.importer import mapping, pipeline

router = APIRouter(prefix="/imports", tags=["imports"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
EDITABLE_KEYS = {
    "category_code", "name_zh", "name_en", "brand", "erp_codes", "mpn", "attributes",
    "price_usd", "notes_raw", "status", "match_product_id", "force_new",
}  # fmt: skip


class ImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_type: str
    status: str
    sheets: list[dict[str, Any]]
    sheets_selected: list[str]
    hints: dict[str, Any]
    progress: dict[str, Any]
    stats: dict[str, Any]
    llm_model: str | None
    llm_tokens_in: int
    llm_tokens_out: int
    error: str | None
    created_at: datetime
    started_at: datetime | None
    committed_at: datetime | None

    @field_validator("sheets")
    @classmethod
    def _default_kind(cls, sheets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Imports made before screenshots and PDFs existed have no source kind."""
        return [{"kind": "sheet", **sheet} for sheet in sheets]


class ImportSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_type: str
    status: str
    stats: dict[str, Any]
    progress: dict[str, Any]
    llm_tokens_in: int
    llm_tokens_out: int
    created_at: datetime
    committed_at: datetime | None


class RowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sheet: str | None
    row_index: int
    source_ref: str | None
    raw: dict[str, Any]
    parsed: dict[str, Any]
    user_edits: dict[str, Any]
    status: str
    decision: str | None
    match_type: str | None
    matched_product_id: int | None
    candidates: list[dict[str, Any]]
    issues: list[dict[str, Any]]
    confidence: float | None


class RowList(BaseModel):
    items: list[RowOut]
    total: int
    counts: dict[str, int]


class ExtractIn(BaseModel):
    sheets: list[str]
    hints: dict[str, str] = Field(default_factory=dict)


class RowPatch(BaseModel):
    decision: Literal["create", "update", "skip"] | None = None
    # field -> new value; null removes an earlier edit
    edits: dict[str, Any] | None = None


class BulkIn(BaseModel):
    action: Literal["skip", "accept", "skip_unchanged", "accept_updates", "set_category"]
    row_ids: list[int] | None = None
    category_code: str | None = None


def _get(session: SessionDep, import_id: int) -> Import:
    imp = session.get(Import, import_id)
    if imp is None:
        raise ProblemError(404, "import.not_found", "Import not found", id=import_id)
    return imp


def _require_review(imp: Import) -> None:
    if imp.status != "review":
        raise ProblemError(409, "import.not_in_review", "This import is not in review")


def _refresh(session: SessionDep, imp: Import) -> None:
    """Re-analyze the whole import after an edit: one row's identity can change which
    other rows are duplicates, and a few hundred rows analyze in well under a second."""
    pipeline.analyze_import(session, imp)


@router.get("", response_model=list[ImportSummary])
def list_imports(session: SessionDep) -> list[Import]:
    return list(session.scalars(select(Import).order_by(Import.id.desc()).limit(200)))


@router.post("", response_model=ImportOut, status_code=201)
async def upload(session: SessionDep, files: Annotated[list[UploadFile], File()]) -> Import:
    """One spreadsheet, or several screenshots / PDFs that form one import."""
    contents: list[tuple[str, bytes]] = []
    total = 0
    for file in files:
        content = await file.read(MAX_UPLOAD_BYTES + 1 - total)
        total += len(content)
        if total > MAX_UPLOAD_BYTES:
            raise ProblemError(413, "import.too_large", "Files are larger than 50 MB in total")
        contents.append((file.filename or "upload", content))
    imp = pipeline.create_import(session, contents)
    session.commit()
    return imp


@router.get("/{import_id}", response_model=ImportOut)
def get_import(session: SessionDep, import_id: int) -> Import:
    return _get(session, import_id)


@router.get("/{import_id}/sources/{index}/image")
def source_image(session: SessionDep, import_id: int, index: int) -> FileResponse:
    """The screenshot, or the rendered PDF page, behind source ``index`` of ``sheets``."""
    path = pipeline.source_image(_get(session, import_id), index)
    return FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/{import_id}", status_code=204)
def delete_import(session: SessionDep, import_id: int) -> Response:
    pipeline.delete_import(session, _get(session, import_id))
    session.commit()
    return Response(status_code=204)


@router.post("/{import_id}/extract", response_model=ImportOut, status_code=202)
def extract(session: SessionDep, import_id: int, body: ExtractIn) -> Import:
    imp = _get(session, import_id)
    pipeline.start_extraction(session, imp, body.sheets, body.hints)
    session.refresh(imp)
    return imp


class SheetColumn(BaseModel):
    letter: str
    header: str
    samples: list[str]


@router.get("/{import_id}/columns", response_model=list[SheetColumn])
def sheet_columns(
    session: SessionDep, import_id: int, sheet: str, header_row: int = Query(ge=1)
) -> list[dict[str, Any]]:
    """The columns of a sheet under a given header row, for the column-mapping dialog."""
    return mapping.columns(mapping.grid_for(_get(session, import_id), sheet), header_row)


class MappingIn(BaseModel):
    sheet: str
    header_row: int = Field(ge=1)
    category_code: str
    name_columns: list[str] = Field(min_length=1)
    fields: dict[Literal[mapping.FIELDS], str] = {}  # type: ignore[valid-type]
    attributes: dict[str, str] = {}
    currency: Literal["USD", "CNY"] = "USD"
    fx_rate: Decimal | None = Field(default=None, gt=0)


@router.post("/{import_id}/map", response_model=ImportOut)
def map_columns(session: SessionDep, import_id: int, body: MappingIn) -> Import:
    """Import a sheet without the AI: the seller says which column holds what."""
    imp = _get(session, import_id)
    mapping.apply(session, imp, mapping.ColumnMapping(**body.model_dump()))
    session.commit()
    session.refresh(imp)
    return imp


@router.post("/{import_id}/cancel", response_model=ImportOut)
def cancel(session: SessionDep, import_id: int) -> Import:
    imp = _get(session, import_id)
    if imp.status != "extracting":
        raise ProblemError(409, "import.not_extracting", "Nothing to cancel")
    imp.status = "cancelled"
    session.commit()
    return imp


@router.get("/{import_id}/rows", response_model=RowList)
def list_rows(
    session: SessionDep,
    import_id: int,
    status: str | None = None,
    sheet: str | None = None,
    category: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
) -> RowList:
    _get(session, import_id)
    base = select(ImportRow).where(ImportRow.import_id == import_id)
    if sheet:
        base = base.where(ImportRow.sheet == sheet)
    if category:
        base = base.where(func.json_extract(ImportRow.parsed, "$.staged.category_code") == category)
    if q:
        like = f"%{q.strip()}%"
        base = base.where(
            or_(
                func.json_extract(ImportRow.parsed, "$.staged.name_zh").like(like),
                func.json_extract(ImportRow.parsed, "$.source.name_zh").like(like),
                func.json_extract(ImportRow.parsed, "$.staged.erp_code").like(like),
            )
        )
    filtered = base.subquery()
    counts_rows = session.execute(
        select(filtered.c.status, func.count()).group_by(filtered.c.status)
    )
    counts = {s: n for s, n in counts_rows}
    stmt = base.where(ImportRow.status == status) if status else base
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = session.scalars(
        stmt.order_by(ImportRow.sheet, ImportRow.row_index, ImportRow.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return RowList(items=[RowOut.model_validate(r) for r in items], total=total, counts=counts)


@router.patch("/{import_id}/rows/{row_id}", response_model=RowOut)
def patch_row(session: SessionDep, import_id: int, row_id: int, body: RowPatch) -> ImportRow:
    imp = _get(session, import_id)
    _require_review(imp)
    row = session.get(ImportRow, row_id)
    if row is None or row.import_id != imp.id:
        raise ProblemError(404, "import.row_not_found", "Row not found", id=row_id)
    edits = dict(row.user_edits or {})
    if body.edits:
        unknown = set(body.edits) - EDITABLE_KEYS
        if unknown:
            raise ProblemError(422, "import.bad_edit", "Unknown field", fields=sorted(unknown))
        if body.edits.get("category_code") and not session.scalar(
            select(Category.id).where(Category.code == body.edits["category_code"])
        ):
            raise ProblemError(422, "category.not_found", "Unknown category")
        for key, value in body.edits.items():
            if value is None:
                edits.pop(key, None)
            else:
                edits[key] = value
        if "match_product_id" in body.edits and body.edits["match_product_id"]:
            edits.pop("force_new", None)
        if body.edits.get("force_new"):
            edits.pop("match_product_id", None)
        edits.pop("decision", None)  # identity may have changed: re-derive the decision
    if body.decision:
        if body.decision == "update" and not (
            row.matched_product_id or edits.get("match_product_id")
        ):
            raise ProblemError(422, "import.no_match", "Pick the product to update first")
        edits["decision"] = body.decision
    row.user_edits = edits
    _refresh(session, imp)
    session.commit()
    return row


@router.post("/{import_id}/bulk", response_model=dict[str, int])
def bulk(session: SessionDep, import_id: int, body: BulkIn) -> dict[str, int]:
    imp = _get(session, import_id)
    _require_review(imp)
    stmt = select(ImportRow).where(ImportRow.import_id == imp.id)
    if body.row_ids is not None:
        stmt = stmt.where(ImportRow.id.in_(body.row_ids))
    rows = list(session.scalars(stmt))
    for row in rows:
        edits = dict(row.user_edits or {})
        if body.action == "skip":
            edits["decision"] = "skip"
        elif body.action == "skip_unchanged" and row.status == "unchanged":
            edits["decision"] = "skip"
        elif body.action == "accept_updates" and row.status == "updated":
            edits["decision"] = "update"
        elif body.action == "accept" and row.status in ("new", "updated"):
            edits["decision"] = "create" if row.status == "new" else "update"
        elif body.action == "set_category" and body.category_code:
            edits["category_code"] = body.category_code
            edits.pop("decision", None)
        else:
            continue
        row.user_edits = edits
        row.decision = edits.get("decision", row.decision)
    if body.action == "set_category" and not session.scalar(
        select(Category.id).where(Category.code == body.category_code)
    ):
        raise ProblemError(422, "category.not_found", "Unknown category")
    _refresh(session, imp)
    session.commit()
    return pipeline.row_counts(
        list(session.scalars(select(ImportRow).where(ImportRow.import_id == imp.id)))
    )


@router.post("/{import_id}/commit", response_model=ImportOut)
def commit(session: SessionDep, import_id: int) -> Import:
    imp = _get(session, import_id)
    committer.commit_import(session, imp)
    session.refresh(imp)
    return imp


@router.post("/{import_id}/revert", response_model=ImportOut)
def revert(session: SessionDep, import_id: int) -> Import:
    imp = _get(session, import_id)
    committer.revert_import(session, imp)
    session.refresh(imp)
    return imp
