"""device type on products and configurations

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pc | laptop | tablet; NULL = a general part that fits any device
    op.add_column("products", sa.Column("device_type", sa.String(length=20), nullable=True))
    op.create_index("ix_products_device_type", "products", ["device_type"])
    op.add_column("configurations", sa.Column("device_type", sa.String(length=20), nullable=True))
    # products of category Tablet, and the parts of tablets imported before this column
    op.execute(
        "UPDATE products SET device_type = 'tablet' WHERE category_id IN "
        "(SELECT id FROM categories WHERE code = 'tablet')"
    )
    op.execute(
        """
        UPDATE products SET device_type = 'tablet' WHERE id IN (
            SELECT json_extract(r.commit_info, '$.product_id') FROM import_rows r
            WHERE json_extract(r.parsed, '$.staged.assembly_role') = 'part'
              AND json_extract(r.commit_info, '$.product_id') IS NOT NULL
              AND json_extract(r.parsed, '$.staged.assembly') IN (
                  SELECT json_extract(u.parsed, '$.staged.assembly') FROM import_rows u
                  WHERE u.import_id = r.import_id
                    AND json_extract(u.parsed, '$.staged.category_code') = 'tablet'
              )
        )
        """
    )
    # a configuration whose catalog parts are all tablet parts is a tablet build
    op.execute(
        """
        UPDATE configurations SET device_type = 'tablet' WHERE id IN (
            SELECT i.configuration_id FROM configuration_items i
            JOIN products p ON p.id = i.product_id
            GROUP BY i.configuration_id
            HAVING SUM(p.device_type = 'tablet') = COUNT(*)
        )
        """
    )


def downgrade() -> None:
    op.drop_column("configurations", "device_type")
    op.drop_index("ix_products_device_type", "products")
    op.drop_column("products", "device_type")
