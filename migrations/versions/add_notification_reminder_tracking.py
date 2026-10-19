"""Track reservation deadline reminders and listing freshness warnings.

Revision ID: add_notification_reminder_tracking
Revises: add_admin_deleted_at
"""

from alembic import op
import sqlalchemy as sa


revision = 'add_notification_reminder_tracking'
down_revision = 'add_admin_deleted_at'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('reservation', sa.Column('deadline_reminder_hours', sa.Integer(), nullable=True))
    op.add_column('item', sa.Column('freshness_warning_sent_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('item') as batch_op:
        batch_op.drop_column('freshness_warning_sent_at')
    with op.batch_alter_table('reservation') as batch_op:
        batch_op.drop_column('deadline_reminder_hours')
