"""Add reservation funding, delivery, orders, and fee payment linkage.

Revision ID: reservation_delivery_fulfillment
Revises: merge_reservation_ledger_video, verification_intake_custody
"""

from alembic import op
import sqlalchemy as sa


revision = 'reservation_delivery_fulfillment'
down_revision = ('merge_reservation_ledger_video', 'verification_intake_custody')
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('reservation') as batch_op:
        batch_op.add_column(sa.Column(
            'funding_mode', sa.String(length=20), nullable=False, server_default='item_backed'
        ))
        batch_op.add_column(sa.Column(
            'delivery_method', sa.String(length=20), nullable=False, server_default='pickup'
        ))
        batch_op.add_column(sa.Column('delivery_address', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('pickup_station_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('delivery_quote_naira', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column(
            'delivery_fee_status', sa.String(length=20), nullable=False, server_default='not_required'
        ))
        batch_op.add_column(sa.Column(
            'backing_return_status', sa.String(length=20), nullable=False, server_default='not_required'
        ))
        batch_op.create_foreign_key(
            'fk_reservation_pickup_station_id', 'pickup_station', ['pickup_station_id'], ['id']
        )

    with op.batch_alter_table('payment') as batch_op:
        batch_op.add_column(sa.Column(
            'purpose', sa.String(length=30), nullable=False, server_default='credit_purchase'
        ))
        batch_op.add_column(sa.Column('reservation_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_payment_reservation_id', 'reservation', ['reservation_id'], ['id']
        )
        batch_op.create_index('ix_payment_reservation_id', ['reservation_id'], unique=False)

    with op.batch_alter_table('order') as batch_op:
        batch_op.add_column(sa.Column('reservation_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('logistics_fee_naira', sa.Float(), nullable=True))
        batch_op.create_foreign_key(
            'fk_order_reservation_id', 'reservation', ['reservation_id'], ['id']
        )
        batch_op.create_unique_constraint('uq_order_reservation_id', ['reservation_id'])


def downgrade():
    with op.batch_alter_table('order') as batch_op:
        batch_op.drop_constraint('uq_order_reservation_id', type_='unique')
        batch_op.drop_constraint('fk_order_reservation_id', type_='foreignkey')
        batch_op.drop_column('logistics_fee_naira')
        batch_op.drop_column('reservation_id')

    with op.batch_alter_table('payment') as batch_op:
        batch_op.drop_index('ix_payment_reservation_id')
        batch_op.drop_constraint('fk_payment_reservation_id', type_='foreignkey')
        batch_op.drop_column('reservation_id')
        batch_op.drop_column('purpose')

    with op.batch_alter_table('reservation') as batch_op:
        batch_op.drop_constraint('fk_reservation_pickup_station_id', type_='foreignkey')
        batch_op.drop_column('backing_return_status')
        batch_op.drop_column('delivery_fee_status')
        batch_op.drop_column('delivery_quote_naira')
        batch_op.drop_column('pickup_station_id')
        batch_op.drop_column('delivery_address')
        batch_op.drop_column('delivery_method')
        batch_op.drop_column('funding_mode')
