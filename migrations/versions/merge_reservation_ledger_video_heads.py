"""Merge reservation credit ledger and item video migration heads.

Revision ID: merge_reservation_ledger_video
Revises: ensure_item_video_url_20261008, add_reservation_credit_ledger
"""

revision = 'merge_reservation_ledger_video'
down_revision = ('ensure_item_video_url_20261008', 'add_reservation_credit_ledger')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
