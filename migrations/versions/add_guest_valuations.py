"""Add private temporary guest valuations."""
from alembic import op
import sqlalchemy as sa

revision = 'add_guest_valuations'
down_revision = 'service_fee_20261113'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'guest_valuation',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('condition', sa.String(20), nullable=False),
        sa.Column('usage_duration', sa.String(100)),
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('image_files', sa.Text(), nullable=False),
        sa.Column('ai_fields', sa.Text()),
        sa.Column('ai_valuated_at', sa.DateTime()),
        sa.Column('error_message', sa.String(255)),
        sa.Column('pending_user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='SET NULL')),
        sa.Column('claimed_by_user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='SET NULL')),
        sa.Column('claimed_item_id', sa.Integer(), sa.ForeignKey('item.id', ondelete='SET NULL'), unique=True),
        sa.Column('claimed_at', sa.DateTime()),
    )
    op.create_index('ix_guest_valuation_expires_at', 'guest_valuation', ['expires_at'])
    op.create_index('ix_guest_valuation_pending_user_id', 'guest_valuation', ['pending_user_id'])


def downgrade():
    op.drop_index('ix_guest_valuation_pending_user_id', table_name='guest_valuation')
    op.drop_index('ix_guest_valuation_expires_at', table_name='guest_valuation')
    op.drop_table('guest_valuation')
