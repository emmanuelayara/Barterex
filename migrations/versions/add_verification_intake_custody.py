"""Add physical verification intake and custody records.

Revision ID: verification_intake_custody
Revises: failed_seller_title_consent
"""

from alembic import op
import sqlalchemy as sa


revision = 'verification_intake_custody'
down_revision = 'failed_seller_title_consent'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('verification_intake'):
        op.create_table(
            'verification_intake',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('item_id', sa.Integer(), nullable=False),
            sa.Column('reservation_id', sa.Integer(), nullable=True),
            sa.Column('reservation_asset_id', sa.Integer(), nullable=True),
            sa.Column('workflow_type', sa.String(length=40), nullable=False),
            sa.Column('outcome', sa.String(length=20), nullable=False),
            sa.Column('received_at', sa.DateTime(), nullable=False),
            sa.Column('received_location', sa.String(length=200), nullable=False),
            sa.Column('received_by_admin_id', sa.Integer(), nullable=False),
            sa.Column('observed_condition', sa.String(length=20), nullable=False),
            sa.Column('observed_serial_number', sa.String(length=100), nullable=True),
            sa.Column('serial_check', sa.String(length=20), nullable=False),
            sa.Column('identity_confirmed', sa.Boolean(), nullable=False),
            sa.Column('accessories_received', sa.Text(), nullable=True),
            sa.Column('inspection_notes', sa.Text(), nullable=True),
            sa.Column('inspected_at', sa.DateTime(), nullable=False),
            sa.Column('inspected_by_admin_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['item_id'], ['item.id']),
            sa.ForeignKeyConstraint(['reservation_id'], ['reservation.id']),
            sa.ForeignKeyConstraint(['reservation_asset_id'], ['reservation_asset.id']),
            sa.ForeignKeyConstraint(['received_by_admin_id'], ['admin.id']),
            sa.ForeignKeyConstraint(['inspected_by_admin_id'], ['admin.id']),
            sa.PrimaryKeyConstraint('id'),
        )
    inspector = sa.inspect(op.get_bind())
    existing_indexes = {index['name'] for index in inspector.get_indexes('verification_intake')}
    for name, columns in (
        ('ix_verification_intake_item_id', ['item_id']),
        ('ix_verification_intake_reservation_id', ['reservation_id']),
        ('ix_verification_intake_reservation_asset_id', ['reservation_asset_id']),
        ('idx_verification_intake_received_at', ['received_at']),
        ('idx_verification_intake_workflow', ['workflow_type', 'outcome']),
    ):
        if name not in existing_indexes:
            op.create_index(name, 'verification_intake', columns, unique=False)

    if not inspector.has_table('custody_event'):
        op.create_table(
            'custody_event',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('item_id', sa.Integer(), nullable=False),
            sa.Column('intake_id', sa.Integer(), nullable=False),
            sa.Column('event_type', sa.String(length=20), nullable=False),
            sa.Column('from_location', sa.String(length=200), nullable=True),
            sa.Column('to_location', sa.String(length=200), nullable=False),
            sa.Column('custodian_name', sa.String(length=120), nullable=False),
            sa.Column('recorded_by_admin_id', sa.Integer(), nullable=False),
            sa.Column('recorded_at', sa.DateTime(), nullable=False),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(['item_id'], ['item.id']),
            sa.ForeignKeyConstraint(['intake_id'], ['verification_intake.id']),
            sa.ForeignKeyConstraint(['recorded_by_admin_id'], ['admin.id']),
            sa.PrimaryKeyConstraint('id'),
        )
    inspector = sa.inspect(op.get_bind())
    existing_indexes = {index['name'] for index in inspector.get_indexes('custody_event')}
    for name, columns in (
        ('ix_custody_event_item_id', ['item_id']),
        ('ix_custody_event_intake_id', ['intake_id']),
        ('idx_custody_event_recorded_at', ['recorded_at']),
        ('idx_custody_event_item', ['item_id', 'recorded_at']),
    ):
        if name not in existing_indexes:
            op.create_index(name, 'custody_event', columns, unique=False)


def downgrade():
    op.drop_index('idx_custody_event_item', table_name='custody_event')
    op.drop_index('idx_custody_event_recorded_at', table_name='custody_event')
    op.drop_index('ix_custody_event_intake_id', table_name='custody_event')
    op.drop_index('ix_custody_event_item_id', table_name='custody_event')
    op.drop_table('custody_event')
    op.drop_index('idx_verification_intake_workflow', table_name='verification_intake')
    op.drop_index('idx_verification_intake_received_at', table_name='verification_intake')
    op.drop_index('ix_verification_intake_reservation_asset_id', table_name='verification_intake')
    op.drop_index('ix_verification_intake_reservation_id', table_name='verification_intake')
    op.drop_index('ix_verification_intake_item_id', table_name='verification_intake')
    op.drop_table('verification_intake')
