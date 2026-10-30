"""Persist video publishing work, resumable sessions, leases, and cleanup retries."""
from alembic import op
import sqlalchemy as sa

revision = 'add_durable_video_publishing'
down_revision = 'remove_item_preverification_stage'
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column('publish_phase', sa.String(30)),
        sa.Column('publish_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('publish_progress', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('publish_error', sa.Text()),
        sa.Column('publish_next_attempt_at', sa.DateTime()),
        sa.Column('publish_started_at', sa.DateTime()),
        sa.Column('publish_lease_token', sa.String(32)),
        sa.Column('publish_lease_until', sa.DateTime()),
        sa.Column('upload_session_uri', sa.Text()),
        sa.Column('upload_source_sha256', sa.String(64)),
        sa.Column('cleanup_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cleanup_next_attempt_at', sa.DateTime()),
        sa.Column('cleanup_error', sa.Text()),
    ):
        op.add_column('item_video', column)
    op.create_index('idx_itemvideo_publish_due', 'item_video', ['status', 'publish_next_attempt_at'])
    op.create_index('idx_itemvideo_youtube_id', 'item_video', ['youtube_video_id'], unique=True)


def downgrade():
    op.drop_index('idx_itemvideo_youtube_id', table_name='item_video')
    op.drop_index('idx_itemvideo_publish_due', table_name='item_video')
    with op.batch_alter_table('item_video') as batch:
        for name in (
            'publish_phase', 'publish_attempts', 'publish_progress', 'publish_error',
            'publish_next_attempt_at', 'publish_started_at', 'publish_lease_token',
            'publish_lease_until', 'upload_session_uri', 'upload_source_sha256',
            'cleanup_attempts', 'cleanup_next_attempt_at', 'cleanup_error',
        ):
            batch.drop_column(name)
