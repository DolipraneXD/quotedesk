"""product created by import

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain ADD COLUMN: SQLite accepts a REFERENCES clause on an added nullable column,
    # so the products table is not rebuilt.
    op.execute(
        "ALTER TABLE products ADD COLUMN created_import_id INTEGER "
        "REFERENCES imports (id) ON DELETE SET NULL"
    )
    op.create_index("ix_products_created_import_id", "products", ["created_import_id"])
    # Products created by an import before this column existed: the import row that
    # created them recorded it in commit_info.
    op.execute(
        """
        UPDATE products SET created_import_id = (
            SELECT r.import_id FROM import_rows r JOIN imports i ON i.id = r.import_id
            WHERE i.status = 'committed'
              AND json_extract(r.commit_info, '$.created') = 1
              AND json_extract(r.commit_info, '$.product_id') = products.id
            ORDER BY r.import_id LIMIT 1
        )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_products_created_import_id", table_name="products")
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_column("created_import_id")
