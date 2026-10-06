"""catalog and imports

Revision ID: 0001
Revises:
Create Date: 2026-10-04 09:19:44.269373
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('brands',
    sa.Column('canonical', sa.String(length=120), nullable=False),
    sa.Column('name_en', sa.String(length=120), nullable=True),
    sa.Column('name_zh', sa.String(length=120), nullable=True),
    sa.Column('needs_review', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('canonical')
    )
    op.create_table('categories',
    sa.Column('code', sa.String(length=40), nullable=False),
    sa.Column('name_en', sa.String(length=120), nullable=False),
    sa.Column('name_zh', sa.String(length=120), nullable=False),
    sa.Column('is_main', sa.Boolean(), nullable=False),
    sa.Column('attribute_schema', sa.JSON(), nullable=False),
    sa.Column('default_margin_pct', sa.String(length=32), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_table('imports',
    sa.Column('filename', sa.String(length=300), nullable=False),
    sa.Column('stored_path', sa.String(length=500), nullable=False),
    sa.Column('file_type', sa.String(length=10), nullable=False),
    sa.Column('sheets_selected', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('llm_model', sa.String(length=80), nullable=True),
    sa.Column('llm_tokens_in', sa.Integer(), nullable=False),
    sa.Column('llm_tokens_out', sa.Integer(), nullable=False),
    sa.Column('stats', sa.JSON(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('committed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('note_rules',
    sa.Column('pattern', sa.String(length=300), nullable=False),
    sa.Column('field', sa.String(length=60), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('value', sa.String(length=120), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('brand_aliases',
    sa.Column('brand_id', sa.Integer(), nullable=False),
    sa.Column('alias', sa.String(length=120), nullable=False),
    sa.Column('alias_key', sa.String(length=120), nullable=False),
    sa.Column('lang', sa.String(length=8), nullable=False),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('alias_key')
    )
    op.create_table('products',
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('erp_code', sa.String(length=60), nullable=True),
    sa.Column('erp_code_alt', sa.JSON(), nullable=False),
    sa.Column('mpn', sa.String(length=120), nullable=True),
    sa.Column('name_zh', sa.String(length=300), nullable=False),
    sa.Column('name_en', sa.String(length=300), nullable=True),
    sa.Column('name_en_auto', sa.Boolean(), nullable=False),
    sa.Column('brand_id', sa.Integer(), nullable=True),
    sa.Column('attributes', sa.JSON(), nullable=False),
    sa.Column('fingerprint', sa.String(length=40), nullable=False),
    sa.Column('current_price_usd', sa.String(length=32), nullable=True),
    sa.Column('current_price_tier_forecast_usd', sa.String(length=32), nullable=True),
    sa.Column('price_date', sa.Date(), nullable=True),
    sa.Column('last_import_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('confirm_before_order', sa.Boolean(), nullable=False),
    sa.Column('lead_time_confirm', sa.Boolean(), nullable=False),
    sa.Column('needs_validation', sa.Boolean(), nullable=False),
    sa.Column('quote_on_request', sa.Boolean(), nullable=False),
    sa.Column('recommended', sa.Boolean(), nullable=False),
    sa.Column('stock_qty', sa.Integer(), nullable=True),
    sa.Column('demand_qty', sa.Integer(), nullable=True),
    sa.Column('stock_after_qty', sa.Integer(), nullable=True),
    sa.Column('max_order_qty', sa.Integer(), nullable=True),
    sa.Column('from_stock_qty', sa.Integer(), nullable=True),
    sa.Column('payment_terms', sa.Text(), nullable=True),
    sa.Column('supply_note', sa.Text(), nullable=True),
    sa.Column('market', sa.String(length=40), nullable=True),
    sa.Column('notes_raw', sa.Text(), nullable=True),
    sa.Column('platform', sa.String(length=120), nullable=True),
    sa.Column('is_manual', sa.Boolean(), nullable=False),
    sa.Column('description_zh', sa.Text(), nullable=True),
    sa.Column('description_en', sa.Text(), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], ),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
    sa.ForeignKeyConstraint(['last_import_id'], ['imports.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('erp_code'),
    sa.UniqueConstraint('fingerprint')
    )
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.create_index('ix_products_category', ['category_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_products_mpn'), ['mpn'], unique=False)

    op.create_table('import_rows',
    sa.Column('import_id', sa.Integer(), nullable=False),
    sa.Column('row_index', sa.Integer(), nullable=False),
    sa.Column('sheet', sa.String(length=120), nullable=True),
    sa.Column('source_ref', sa.String(length=300), nullable=True),
    sa.Column('raw', sa.JSON(), nullable=False),
    sa.Column('parsed', sa.JSON(), nullable=False),
    sa.Column('match_type', sa.String(length=20), nullable=True),
    sa.Column('matched_product_id', sa.Integer(), nullable=True),
    sa.Column('candidates', sa.JSON(), nullable=False),
    sa.Column('decision', sa.String(length=20), nullable=True),
    sa.Column('user_edits', sa.JSON(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('issues', sa.JSON(), nullable=False),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['import_id'], ['imports.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['matched_product_id'], ['products.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('import_rows', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_import_rows_import_id'), ['import_id'], unique=False)

    op.create_table('price_history',
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('import_id', sa.Integer(), nullable=True),
    sa.Column('price_usd', sa.String(length=32), nullable=False),
    sa.Column('tier', sa.String(length=20), nullable=False),
    sa.Column('amount_original', sa.String(length=32), nullable=True),
    sa.Column('currency_original', sa.String(length=8), nullable=True),
    sa.Column('fx_rate', sa.String(length=32), nullable=True),
    sa.Column('price_date', sa.Date(), nullable=True),
    sa.Column('source_ref', sa.String(length=300), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('is_current', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['import_id'], ['imports.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('price_history', schema=None) as batch_op:
        batch_op.create_index('ix_price_history_product', ['product_id', 'tier', 'is_current'], unique=False)

    op.create_table('product_aliases',
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('fingerprint', sa.String(length=40), nullable=False),
    sa.Column('name_zh', sa.String(length=300), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('fingerprint')
    )

    # Product search. Trigram tokenizer because product names are unsegmented Chinese;
    # rowid = products.id, kept in sync by app.services.search.
    op.execute(
        "CREATE VIRTUAL TABLE products_fts USING fts5("
        "name_zh, name_en, erp_code, mpn, brand, attributes_text, tokenize='trigram')"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS products_fts")
    op.drop_table('product_aliases')
    with op.batch_alter_table('price_history', schema=None) as batch_op:
        batch_op.drop_index('ix_price_history_product')

    op.drop_table('price_history')
    with op.batch_alter_table('import_rows', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_import_rows_import_id'))

    op.drop_table('import_rows')
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_products_mpn'))
        batch_op.drop_index('ix_products_category')

    op.drop_table('products')
    op.drop_table('brand_aliases')
    op.drop_table('note_rules')
    op.drop_table('imports')
    op.drop_table('categories')
    op.drop_table('brands')
