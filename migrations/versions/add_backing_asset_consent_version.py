"""Record the version of the backing-asset surrender consent.

Revision ID: backing_asset_consent_version
Revises: add_clearing_inventory_ownership
"""

from alembic import op
import sqlalchemy as sa


revision = 'backing_asset_consent_version'
down_revision = 'add_clearing_inventory_ownership'
branch_labels = None
depends_on = None


def upgrade():
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('reservation')}
    if 'backing_asset_consent_version' not in columns:
        op.add_column(
            'reservation',
            sa.Column('backing_asset_consent_version', sa.String(length=40), nullable=True),
        )


def downgrade():
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('reservation')}
    if 'backing_asset_consent_version' in columns:
        op.drop_column('reservation', 'backing_asset_consent_version')
