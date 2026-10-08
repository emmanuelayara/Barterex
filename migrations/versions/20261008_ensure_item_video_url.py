"""Ensure item.video_url exists for fresh and existing databases."""
from alembic import op
import sqlalchemy as sa

revision = "ensure_item_video_url_20261008"
down_revision = "add_trade_lifecycle_res"
branch_labels = None
depends_on = None

def upgrade():
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("item")
    }
    if "video_url" not in columns:
        op.add_column(
            "item",
            sa.Column("video_url", sa.String(length=300), nullable=True),
        )

def downgrade():
    # Preserve video URLs that may predate this compatibility migration.
    pass
