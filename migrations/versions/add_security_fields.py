"""Add security fields for rate limiting and account lockout

Revision ID: security_001
Revises: 9a03719bec94
Create Date: 2025-12-06 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'security_001'
down_revision = '9a03719bec94'
branch_labels = None
depends_on = None


def upgrade():
    # Add failed login tracking fields to User table
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('failed_login_attempts', sa.Integer(), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('account_locked_until', sa.DateTime(), nullable=True))

    # Add failed login tracking fields to Admin table
    with op.batch_alter_table('admin', schema=None) as batch_op:
        batch_op.add_column(sa.Column('failed_login_attempts', sa.Integer(), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('account_locked_until', sa.DateTime(), nullable=True))


def downgrade():
    # Remove failed login tracking fields from Admin table
    with op.batch_alter_table('admin', schema=None) as batch_op:
        batch_op.drop_column('account_locked_until')
        batch_op.drop_column('failed_login_attempts')

    # Remove failed login tracking fields from User table
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('account_locked_until')
        batch_op.drop_column('failed_login_attempts')
