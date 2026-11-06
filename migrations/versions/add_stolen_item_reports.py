"""Add private stolen-item reports and evidence attachments."""
from alembic import op
import sqlalchemy as sa

revision = 'add_stolen_item_reports'
down_revision = 'add_durable_video_publishing'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'stolen_item_report',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('item_id', sa.Integer(), sa.ForeignKey('item.id', ondelete='SET NULL')),
        sa.Column('reporter_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='SET NULL')),
        sa.Column('item_name', sa.String(200), nullable=False),
        sa.Column('contact_email', sa.String(120), nullable=False),
        sa.Column('details', sa.Text(), nullable=False),
        sa.Column('imei', sa.String(15)),
        sa.Column('serial_number', sa.String(120)),
        sa.Column('police_reference', sa.String(120)),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime()),
        sa.Column('reviewed_by_id', sa.Integer(), sa.ForeignKey('admin.id', ondelete='SET NULL')),
        sa.Column('review_notes', sa.Text()),
    )
    op.create_index('idx_stolen_report_status', 'stolen_item_report', ['status', 'created_at'])
    op.create_index('idx_stolen_report_reporter_item', 'stolen_item_report', ['reporter_id', 'item_id'])
    op.create_table(
        'stolen_report_evidence',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('report_id', sa.Integer(), sa.ForeignKey('stolen_item_report.id', ondelete='CASCADE'), nullable=False),
        sa.Column('content_type', sa.String(30), nullable=False),
        sa.Column('data', sa.LargeBinary(), nullable=False),
    )
    op.create_index('ix_stolen_report_evidence_report_id', 'stolen_report_evidence', ['report_id'])


def downgrade():
    op.drop_table('stolen_report_evidence')
    op.drop_table('stolen_item_report')
