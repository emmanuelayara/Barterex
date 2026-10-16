"""Add per-admin permissions, super-admin flag and active flag.

Existing admins keep full access by being marked as super admins.

Revision ID: add_admin_permissions
Revises: reservation_revaluation
"""

from alembic import op
import sqlalchemy as sa


revision = 'add_admin_permissions'
down_revision = 'reservation_revaluation'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'admin',
        sa.Column('is_super_admin', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'admin',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column('admin', sa.Column('permissions', sa.Text(), nullable=True))
    op.execute('UPDATE admin SET is_super_admin = ' + ('1' if op.get_bind().dialect.name == 'sqlite' else 'TRUE'))


def downgrade():
    with op.batch_alter_table('admin') as batch_op:
        batch_op.drop_column('permissions')
        batch_op.drop_column('is_active')
        batch_op.drop_column('is_super_admin')
