"""Add reservation BXC ledger entries.

Revision ID: add_reservation_credit_ledger
Revises: add_trade_lifecycle_res
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_reservation_credit_ledger'
down_revision = 'add_trade_lifecycle_res'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if 'reservation_credit_entry' in inspector.get_table_names():
        return

    op.create_table(
        'reservation_credit_entry',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'reservation_id',
            sa.Integer(),
            sa.ForeignKey(
                'reservation.id',
                name='fk_reservation_credit_entry_reservation',
            ),
            nullable=True,
        ),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('item_id', sa.Integer(), sa.ForeignKey('item.id'), nullable=True),
        sa.Column('balance_type', sa.String(length=20), nullable=False),
        sa.Column('entry_type', sa.String(length=30), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('balance_before', sa.Integer(), nullable=False),
        sa.Column('balance_after', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        'idx_reservation_credit_entry_reservation',
        'reservation_credit_entry',
        ['reservation_id'],
    )
    op.create_index(
        'idx_reservation_credit_entry_user',
        'reservation_credit_entry',
        ['user_id'],
    )


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if 'reservation_credit_entry' not in inspector.get_table_names():
        return

    op.drop_index(
        'idx_reservation_credit_entry_user',
        table_name='reservation_credit_entry',
    )
    op.drop_index(
        'idx_reservation_credit_entry_reservation',
        table_name='reservation_credit_entry',
    )
    op.drop_table('reservation_credit_entry')
