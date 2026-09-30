"""Add AI valuation columns to item

Revision ID: add_valuator_columns
Revises: add_paystack_support

Safe to run more than once: each column is only added if it is missing.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_valuator_columns'
down_revision = 'add_paystack_support'
branch_labels = None
depends_on = None


COLUMNS = [
    ('ai_estimated_value', sa.Float()),
    ('ai_confidence', sa.String(length=20)),
    ('ai_market_listings', sa.Integer()),
    ('ai_value_range_low', sa.Float()),
    ('ai_value_range_high', sa.Float()),
    ('ai_risk_score', sa.Float()),
    ('ai_risk_level', sa.String(length=20)),
    ('ai_risk_flags', sa.Text()),
    ('ai_sources_used', sa.Text()),
    ('verification_status', sa.String(length=30)),
    ('verification_notes', sa.Text()),
    ('ai_valuated_at', sa.DateTime()),
    ('valuator_valuation_id', sa.Integer()),
]


def upgrade():
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('item')}
    with op.batch_alter_table('item', schema=None) as batch_op:
        for name, coltype in COLUMNS:
            if name not in existing:
                batch_op.add_column(sa.Column(name, coltype, nullable=True))


def downgrade():
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('item')}
    with op.batch_alter_table('item', schema=None) as batch_op:
        for name, _ in COLUMNS:
            if name in existing:
                batch_op.drop_column(name)
