"""Add company-owned clearing inventory and reservation consent tracking.

Revision ID: add_clearing_inventory_ownership
Revises: merge_reservation_ledger_video
"""

from alembic import op
import sqlalchemy as sa


revision = 'add_clearing_inventory_ownership'
down_revision = 'merge_reservation_ledger_video'
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _add_column_if_missing(table, column):
    if column.name not in {column_info['name'] for column_info in _inspector().get_columns(table)}:
        op.add_column(table, column)


def upgrade():
    _add_column_if_missing(
        'item',
        sa.Column('owner_type', sa.String(length=20), nullable=False, server_default='user'),
    )
    user_id_column = next(
        column for column in _inspector().get_columns('item') if column['name'] == 'user_id'
    )
    if not user_id_column['nullable']:
        with op.batch_alter_table('item') as batch_op:
            batch_op.alter_column(
                'user_id',
                existing_type=sa.Integer(),
                nullable=True,
            )

    _add_column_if_missing('reservation', sa.Column('purchase_value', sa.Integer(), nullable=True))
    _add_column_if_missing(
        'reservation',
        sa.Column('spendable_credits_held', sa.Integer(), nullable=False, server_default='0'),
    )
    _add_column_if_missing(
        'reservation',
        sa.Column('clearing_mode', sa.String(length=30), nullable=False, server_default='legacy_swap'),
    )
    _add_column_if_missing(
        'reservation',
        sa.Column('backing_asset_consent_at', sa.DateTime(), nullable=True),
    )
    _add_column_if_missing(
        'reservation_asset',
        sa.Column('consent_confirmed_at', sa.DateTime(), nullable=True),
    )

    if not _inspector().has_table('clearing_inventory_item'):
        op.create_table(
            'clearing_inventory_item',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('item_id', sa.Integer(), nullable=False),
            sa.Column('reservation_id', sa.Integer(), nullable=False),
            sa.Column('reservation_asset_id', sa.Integer(), nullable=False),
            sa.Column('source_user_id', sa.Integer(), nullable=True),
            sa.Column('acquisition_value', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(length=30), nullable=False, server_default='held_for_resale'),
            sa.Column('acquired_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['item_id'], ['item.id']),
            sa.ForeignKeyConstraint(['reservation_id'], ['reservation.id']),
            sa.ForeignKeyConstraint(['reservation_asset_id'], ['reservation_asset.id']),
            sa.ForeignKeyConstraint(['source_user_id'], ['user.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('item_id'),
            sa.UniqueConstraint('reservation_asset_id'),
        )

    for index_name, columns in (
        ('idx_clearing_inventory_status', ['status']),
        ('idx_clearing_inventory_acquired_at', ['acquired_at']),
    ):
        if index_name not in {index['name'] for index in _inspector().get_indexes('clearing_inventory_item')}:
            op.create_index(index_name, 'clearing_inventory_item', columns, unique=False)


def downgrade():
    op.drop_index('idx_clearing_inventory_acquired_at', table_name='clearing_inventory_item')
    op.drop_index('idx_clearing_inventory_status', table_name='clearing_inventory_item')
    op.drop_table('clearing_inventory_item')
    op.drop_column('reservation_asset', 'consent_confirmed_at')
    op.drop_column('reservation', 'backing_asset_consent_at')
    op.drop_column('reservation', 'clearing_mode')
    op.drop_column('reservation', 'spendable_credits_held')
    op.drop_column('reservation', 'purchase_value')
    with op.batch_alter_table('item') as batch_op:
        batch_op.alter_column(
            'user_id',
            existing_type=sa.Integer(),
            nullable=False,
        )
    op.drop_column('item', 'owner_type')
