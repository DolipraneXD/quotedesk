"""Backups (plan §6 Settings, §9): list, create, download, upload, restore, delete."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, File, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import SessionDep
from app.config import load_settings
from app.errors import ProblemError
from app.models import Import
from app.services import backup

router = APIRouter(prefix="/backups", tags=["backups"])

MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024


class BackupOut(BaseModel):
    name: str
    kind: Literal["database", "full"]
    size: int
    created_at: datetime


class BackupCreate(BaseModel):
    full: bool = False


@router.get("", response_model=list[BackupOut])
def list_backups() -> list[dict[str, object]]:
    return backup.list_backups()


def _out(name: str) -> dict[str, object]:
    return next(b for b in backup.list_backups() if b["name"] == name)


@router.post("", response_model=BackupOut, status_code=201)
def create_backup(body: BackupCreate) -> dict[str, object]:
    retention = load_settings().backup_retention
    path = backup.full_backup() if body.full else backup.backup_db(retention, prefix="manual")
    if path is None:
        raise ProblemError(409, "backup.no_database", "There is no database to back up yet")
    return _out(path.name)


@router.post("/upload", response_model=BackupOut, status_code=201)
async def upload_backup(file: Annotated[UploadFile, File()]) -> dict[str, object]:
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise ProblemError(413, "backup.too_large", "The file is too large")
    return _out(backup.save_upload(file.filename or "backup", content).name)


@router.get("/{name}/download")
def download_backup(name: str) -> FileResponse:
    return FileResponse(backup.get_path(name), filename=name)


@router.post("/{name}/restore", response_model=BackupOut | None)
def restore_backup(session: SessionDep, name: str) -> dict[str, object] | None:
    """Returns the backup of the data as it was just before the restore."""
    busy = session.scalar(select(Import.id).where(Import.status == "extracting").limit(1))
    if busy is not None:
        raise ProblemError(409, "backup.import_running", "Wait for the running import to finish")
    session.close()
    safety = backup.restore(name, load_settings().backup_retention)
    return _out(safety.name) if safety else None


@router.delete("/{name}", status_code=204)
def delete_backup(name: str) -> Response:
    backup.delete(name)
    return Response(status_code=204)
