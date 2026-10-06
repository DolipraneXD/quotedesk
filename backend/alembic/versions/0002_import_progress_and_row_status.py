"""import progress and row status

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("import_rows", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(length=20), nullable=False, server_default="new")
        )
        batch_op.add_column(sa.Column("commit_info", sa.JSON(), nullable=True))
        batch_op.create_index(batch_op.f("ix_import_rows_status"), ["status"], unique=False)

    with op.batch_alter_table("imports", schema=None) as batch_op:
        batch_op.add_column(sa.Column("sheets", sa.JSON(), nullable=False, server_default="[]"))
        batch_op.add_column(sa.Column("hints", sa.JSON(), nullable=False, server_default="{}"))
        batch_op.add_column(sa.Column("progress", sa.JSON(), nullable=False, server_default="{}"))


def downgrade() -> None:
    with op.batch_alter_table("imports", schema=None) as batch_op:
        batch_op.drop_column("progress")
        batch_op.drop_column("hints")
        batch_op.drop_column("sheets")

    with op.batch_alter_table("import_rows", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_import_rows_status"))
        batch_op.drop_column("commit_info")
        batch_op.drop_column("status")
