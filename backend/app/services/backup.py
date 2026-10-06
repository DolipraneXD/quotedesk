"""Backups (plan §9): a copy of app.db on every start and on demand, and a "full" zip that
also holds photos, uploaded price lists and settings. API keys (data/.env) are never in a
backup. Restoring first backs up the current state, then migrates the restored database."""

from __future__ import annotations

import re
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import data_dir, db_path
from app.errors import ProblemError

NAME_RE = re.compile(r"[\w.-]+\.(db|zip)")
FULL_DIRS = ("images", "imports")
SQLITE_MAGIC = b"SQLite format 3\x00"


def backups_dir() -> Path:
    return data_dir() / "backups"


def _new_path(prefix: str, suffix: str) -> Path:
    """backups/<prefix>-YYYYMMDD-HHMMSS<suffix>, never an existing file."""
    base = f"{prefix}-{datetime.now():%Y%m%d-%H%M%S}"
    path, n = backups_dir() / f"{base}{suffix}", 2
    while path.exists():
        path, n = backups_dir() / f"{base}-{n}{suffix}", n + 1
    return path


def _copy_db(source: Path, target: Path) -> None:
    """SQLite's online backup API: safe while the app holds the database open (WAL)."""
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)


def _prune(pattern: str, retention: int) -> None:
    files = sorted(backups_dir().glob(pattern), key=lambda p: p.stat().st_mtime)
    for old in files[: max(len(files) - retention, 0)]:
        old.unlink()


def backup_db(retention: int = 30, prefix: str = "app") -> Path | None:
    """Copy app.db to backups/<prefix>-YYYYMMDD-HHMMSS.db; keep the newest ``retention``."""
    source = db_path()
    if not source.exists():
        return None
    backups_dir().mkdir(parents=True, exist_ok=True)
    target = _new_path(prefix, ".db")
    _copy_db(source, target)
    _prune(f"{prefix}-*.db", retention)
    return target


def full_backup(retention: int = 10) -> Path:
    """app.db plus photos, uploaded files and settings.json, in one zip."""
    backups_dir().mkdir(parents=True, exist_ok=True)
    target = _new_path("full", ".zip")
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "app.db"
        _copy_db(db_path(), snapshot)
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(snapshot, "app.db")
            settings = data_dir() / "settings.json"
            if settings.exists():
                zf.write(settings, "settings.json")
            for name in FULL_DIRS:
                folder = data_dir() / name
                for path in sorted(folder.rglob("*")) if folder.exists() else []:
                    if path.is_file():
                        zf.write(path, f"{name}/{path.relative_to(folder).as_posix()}")
    _prune("full-*.zip", retention)
    return target


def list_backups() -> list[dict[str, Any]]:
    folder = backups_dir()
    files = [p for p in folder.iterdir() if NAME_RE.fullmatch(p.name)] if folder.exists() else []
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {
            "name": p.name,
            "kind": "full" if p.suffix == ".zip" else "database",
            "size": p.stat().st_size,
            "created_at": datetime.fromtimestamp(p.stat().st_mtime).astimezone(),
        }
        for p in files
    ]


def get_path(name: str) -> Path:
    path = backups_dir() / name
    if not NAME_RE.fullmatch(name) or not path.is_file():
        raise ProblemError(404, "backup.not_found", "Backup not found", name=name)
    return path


def _check(path: Path) -> None:
    """A real SQLite database, or a zip holding one."""
    if path.suffix == ".db":
        with open(path, "rb") as fh:
            ok = fh.read(16) == SQLITE_MAGIC
    else:
        try:
            with zipfile.ZipFile(path) as zf:
                ok = "app.db" in zf.namelist() and zf.read("app.db")[:16] == SQLITE_MAGIC
        except zipfile.BadZipFile:
            ok = False
    if not ok:
        raise ProblemError(422, "backup.invalid", "This file is not a QuoteDesk backup")


def save_upload(filename: str, content: bytes) -> Path:
    """A backup brought from another computer, kept next to the others."""
    suffix = Path(filename).suffix.lower()
    if suffix not in (".db", ".zip"):
        raise ProblemError(422, "backup.invalid", "This file is not a QuoteDesk backup")
    backups_dir().mkdir(parents=True, exist_ok=True)
    target = _new_path("uploaded", suffix)
    target.write_bytes(content)
    try:
        _check(target)
    except ProblemError:
        target.unlink()
        raise
    return target


def restore(name: str, retention: int = 30) -> Path | None:
    """Replace the current data with a backup. The current database is saved first as
    ``before-restore-….db``, so a restore can itself be undone."""
    from app.db import reset_engine  # the app's engine must let go of app.db
    from app.migrate import upgrade_and_seed

    path = get_path(name)
    _check(path)
    safety = backup_db(retention, prefix="before-restore")
    reset_engine()
    if path.suffix == ".db":
        _copy_db(path, db_path())
    else:
        with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(path) as zf:
            for member in zf.namelist():  # no absolute paths or ".." in a restored zip
                if member.startswith("/") or ".." in Path(member).parts:
                    raise ProblemError(422, "backup.invalid", "Unsafe path in the backup")
            zf.extractall(tmp)
            _copy_db(Path(tmp) / "app.db", db_path())
            if (Path(tmp) / "settings.json").exists():
                shutil.copy2(Path(tmp) / "settings.json", data_dir() / "settings.json")
            for folder in FULL_DIRS:
                source = Path(tmp) / folder
                if source.exists():
                    shutil.rmtree(data_dir() / folder, ignore_errors=True)
                    shutil.copytree(source, data_dir() / folder)
    reset_engine()
    upgrade_and_seed()  # an older backup gets the newer tables
    return safety


def delete(name: str) -> None:
    get_path(name).unlink()
