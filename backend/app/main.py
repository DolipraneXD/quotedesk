from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import (
    backups,
    brands,
    categories,
    configurations,
    customers,
    images,
    imports,
    meta,
    note_rules,
    products,
    proformas,
    quotes,
    settings,
)
from app.config import FRONTEND_DIST, data_dir, ensure_data_dirs, load_settings
from app.errors import install_handlers
from app.migrate import upgrade_and_seed
from app.services.backup import backup_db

log = logging.getLogger("quotedesk")


def _configure_logging() -> RotatingFileHandler:
    handler = RotatingFileHandler(
        data_dir() / "logs" / "app.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    return handler


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    ensure_data_dirs()
    handler = _configure_logging()
    backup = backup_db(load_settings().backup_retention)
    if backup:
        log.info("startup backup written to %s", backup)
    upgrade_and_seed()
    log.info("QuoteDesk %s ready, data dir %s", __version__, data_dir())
    try:
        yield
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()


def create_app() -> FastAPI:
    app = FastAPI(title="QuoteDesk", version=__version__, lifespan=lifespan)
    install_handlers(app)
    for module in (
        meta,
        note_rules,
        products,
        categories,
        brands,
        imports,
        settings,
        customers,
        quotes,
        proformas,
        configurations,
        images,
        backups,
    ):
        app.include_router(module.router, prefix="/api/v1")

    if FRONTEND_DIST.exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            # client-side routes fall back to index.html; real files are served as-is
            candidate = (FRONTEND_DIST / path).resolve()
            if path and candidate.is_file() and FRONTEND_DIST in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()
