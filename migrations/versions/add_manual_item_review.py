"""Support optional manual valuation and non-reservation inventory acquisitions."""
from alembic import op
import sqlalchemy as sa

revision = 'add_manual_item_review'
down_revision = 'add_stolen_item_reports'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('item') as batch:
        batch.add_column(sa.Column('manual_review_requested', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column('manual_verified_value', sa.Float()))
        batch.add_column(sa.Column('manual_verified_at', sa.DateTime()))
        batch.add_column(sa.Column('manual_custody_choice', sa.String(20)))
        batch.add_column(sa.Column('manual_custody_consent_at', sa.DateTime()))
    with op.batch_alter_table('clearing_inventory_item') as batch:
        batch.alter_column('reservation_id', existing_type=sa.Integer(), nullable=True)
        batch.alter_column('reservation_asset_id', existing_type=sa.Integer(), nullable=True)


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text(
        'SELECT COUNT(*) FROM clearing_inventory_item WHERE reservation_id IS NULL OR reservation_asset_id IS NULL'
    )).scalar():
        raise RuntimeError('Manual acquisitions exist; preserve/reconcile them before downgrading.')
    if connection.execute(sa.text(
        'SELECT COUNT(*) FROM item WHERE manual_review_requested = true'
    )).scalar():
        raise RuntimeError('Manual review records exist; preserve/reconcile them before downgrading.')
    with op.batch_alter_table('clearing_inventory_item') as batch:
        batch.alter_column('reservation_id', existing_type=sa.Integer(), nullable=False)
        batch.alter_column('reservation_asset_id', existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table('item') as batch:
        for column in (
            'manual_review_requested', 'manual_verified_value', 'manual_verified_at',
            'manual_custody_choice', 'manual_custody_consent_at',
        ):
            batch.drop_column(column)
