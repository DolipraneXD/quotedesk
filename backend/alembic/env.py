from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from app.config import ensure_data_dirs
from app.db import get_engine
from app.models import Base

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logging", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
ensure_data_dirs()


def include_object(obj, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    # products_fts* are FTS5 tables created with raw SQL; autogenerate must not touch them
    if type_ == "table" and name and name.startswith("products_fts"):
        return False
    # 0003 and 0006 added these FKs inline with ALTER TABLE ADD COLUMN (no table rebuild).
    # SQLite keeps their ON DELETE SET NULL, but reflection of inline column constraints
    # drops it, so autogenerate would keep proposing a rebuild. Checked in
    # test_products_remember_the_import_that_added_them.
    columns = getattr(obj, "column_keys", None) or [c.name for c in getattr(obj, "columns", [])]
    inline = {"created_import_id", "configuration_id"}
    return not (type_ == "foreign_key_constraint" and inline & set(columns))


def run_migrations_offline() -> None:
    context.configure(
        url=str(get_engine().url),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with get_engine().connect() as connection:
        # SQLite: a batch migration rebuilds a table by dropping it; with foreign keys
        # enforced, that drop would cascade into child tables (price history, import
        # rows). The pragma must be set outside a transaction, so before the migration.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
