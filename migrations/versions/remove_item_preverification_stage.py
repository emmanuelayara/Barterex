"""Remove the separate pre-listing item pre-verification stage.

Revision ID: remove_item_preverification_stage
Revises: add_notification_reminder_tracking
"""

from alembic import op
import sqlalchemy as sa


revision = 'remove_item_preverification_stage'
down_revision = 'add_notification_reminder_tracking'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE item
        SET status = 'pending_activation'
        WHERE status IN ('trade_requested', 'preverification_approved')
          AND EXISTS (
              SELECT 1
              FROM item_video
              WHERE item_video.item_id = item.id
                AND item_video.status = 'pending'
          )
    """))
    connection.execute(sa.text("""
        UPDATE item
        SET status = 'valuation_only'
        WHERE status IN ('trade_requested', 'preverification_approved')
    """))


def downgrade():
    pass
