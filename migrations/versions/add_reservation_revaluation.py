"""Add reservation revaluation proposals and additional backing support.

Revision ID: reservation_revaluation
Revises: reconcile_legacy_direct_checkouts
"""

from alembic import op
import sqlalchemy as sa


revision = 'reservation_revaluation'
down_revision = 'reconcile_legacy_direct_checkouts'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'reservation',
        sa.Column(
            'seller_item_revaluation_failed',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        'reservation',
        sa.Column(
            'spendable_funding_held',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
    )
    op.add_column(
        'reservation',
        sa.Column('revaluation_shortfall_expires_at', sa.DateTime(), nullable=True),
    )
    op.add_column(
        'reservation_asset',
        sa.Column(
            'reserved_provisional_amount',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
    )
    op.add_column(
        'reservation_asset',
        sa.Column(
            'excluded_from_settlement',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute(
        'UPDATE reservation_asset SET reserved_provisional_amount = amount'
    )
    op.execute(
        "UPDATE reservation SET spendable_funding_held = spendable_credits_held "
        "WHERE funding_mode = 'spendable'"
    )
    op.create_table(
        'reservation_revaluation',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reservation_id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('reservation_asset_id', sa.Integer(), nullable=True),
        sa.Column('original_value', sa.Integer(), nullable=False),
        sa.Column('proposed_value', sa.Integer(), nullable=False),
        sa.Column('proposed_by_admin_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('buyer_decision', sa.String(length=10), nullable=False),
        sa.Column('seller_decision', sa.String(length=10), nullable=False),
        sa.Column('buyer_decision_at', sa.DateTime(), nullable=True),
        sa.Column('seller_decision_at', sa.DateTime(), nullable=True),
        sa.Column('proposed_at', sa.DateTime(), nullable=False),
        sa.Column('decision_expires_at', sa.DateTime(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ['reservation_id'],
            ['reservation.id'],
            name='fk_reservation_revaluation_reservation',
        ),
        sa.ForeignKeyConstraint(['item_id'], ['item.id']),
        sa.ForeignKeyConstraint(['reservation_asset_id'], ['reservation_asset.id']),
        sa.ForeignKeyConstraint(['proposed_by_admin_id'], ['admin.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'idx_reservation_revaluation_reservation',
        'reservation_revaluation',
        ['reservation_id'],
    )
    op.create_index(
        'idx_reservation_revaluation_status_deadline',
        'reservation_revaluation',
        ['status', 'decision_expires_at'],
    )
    op.create_index(
        'idx_reservation_revaluation_item',
        'reservation_revaluation',
        ['item_id'],
    )


def downgrade():
    raise RuntimeError(
        'Reservation revaluation and decision records must be preserved.'
    )
