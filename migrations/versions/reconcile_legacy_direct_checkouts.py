"""Track legacy direct-checkout reversals.

Revision ID: reconcile_legacy_direct_checkouts
Revises: reservation_delivery_fulfillment
"""

from alembic import op
import sqlalchemy as sa


revision = "reconcile_legacy_direct_checkouts"
down_revision = "reservation_delivery_fulfillment"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "legacy_checkout_reconciliation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("buyer_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("credits_refunded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["order.id"]),
        sa.ForeignKeyConstraint(["buyer_id"], ["user.id"]),
    )


def downgrade():
    raise RuntimeError(
        "Legacy checkout reconciliation records must be preserved to prevent duplicate refunds."
    )
