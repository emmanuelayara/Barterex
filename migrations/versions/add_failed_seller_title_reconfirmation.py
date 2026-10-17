"""Add renewed title-transfer consent for failed requested items.

Revision ID: failed_seller_title_consent
Revises: add_backing_asset_consent_version
"""

from alembic import op
import sqlalchemy as sa


revision = 'failed_seller_title_consent'
down_revision = 'add_backing_asset_consent_version'
branch_labels = None
depends_on = None


def upgrade():
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('reservation')}
    for column in (
        sa.Column('title_transfer_decision', sa.String(length=10), nullable=True),
        sa.Column('title_transfer_decision_at', sa.DateTime(), nullable=True),
        sa.Column('title_transfer_decision_expires_at', sa.DateTime(), nullable=True),
    ):
        if column.name not in columns:
            op.add_column('reservation', column)


def downgrade():
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('reservation')}
    for column_name in (
        'title_transfer_decision_expires_at',
        'title_transfer_decision_at',
        'title_transfer_decision',
    ):
        if column_name in columns:
            op.drop_column('reservation', column_name)
