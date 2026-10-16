"""Add admin.deleted_at so removed admins can be hidden while history stays intact.

Revision ID: add_admin_deleted_at
Revises: add_admin_permissions
"""

from alembic import op
import sqlalchemy as sa


revision = 'add_admin_deleted_at'
down_revision = 'add_admin_permissions'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('admin', sa.Column('deleted_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('admin') as batch_op:
        batch_op.drop_column('deleted_at')
