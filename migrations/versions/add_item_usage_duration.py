"""Add usage_duration column to Item model

Revision ID: add_item_usage_duration
Revises: add_paystack_support
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_item_usage_duration'
down_revision = 'add_paystack_support'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('item', schema=None) as batch_op:
        batch_op.add_column(sa.Column('usage_duration', sa.String(length=100), nullable=True))


def downgrade():
    with op.batch_alter_table('item', schema=None) as batch_op:
        batch_op.drop_column('usage_duration')
