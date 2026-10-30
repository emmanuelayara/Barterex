"""Remove the separate pre-listing item pre-verification stage.

Revision ID: remove_preverify_20261030
Revises: notif_reminder_20261019
"""

from alembic import op
import sqlalchemy as sa


revision = 'remove_preverify_20261030'
down_revision = 'notif_reminder_20261019'
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
