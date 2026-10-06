from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import BUNDLE_DIR, FROZEN
from app.db import session_factory
from app.seed import seed

# alembic.ini and alembic/ (the migration scripts are read as files, also when frozen)
BACKEND_DIR = BUNDLE_DIR / "backend" if FROZEN else Path(__file__).resolve().parents[1]


def upgrade_and_seed() -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["configure_logging"] = False  # keep the app's logging config
    command.upgrade(cfg, "head")
    with session_factory()() as session:
        seed(session)
