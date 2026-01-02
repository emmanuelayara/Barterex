"""Add AuditLog model for admin activity tracking

Revision ID: 84a3275df4f2
Revises: 8b0cb27b0de2
Create Date: 2026-01-02 17:47:05.144495

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '84a3275df4f2'
down_revision = '8b0cb27b0de2'
branch_labels = None
depends_on = None


def upgrade():
    # Create audit_log table
    op.create_table('audit_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('admin_id', sa.Integer(), nullable=False),
    sa.Column('action_type', sa.String(length=100), nullable=False),
    sa.Column('target_type', sa.String(length=50), nullable=False),
    sa.Column('target_id', sa.Integer(), nullable=True),
    sa.Column('target_name', sa.String(length=255), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('before_value', sa.Text(), nullable=True),
    sa.Column('after_value', sa.Text(), nullable=True),
    sa.Column('timestamp', sa.DateTime(), nullable=False),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.ForeignKeyConstraint(['admin_id'], ['user.id'], name='fk_audit_log_admin_id'),
    sa.PrimaryKeyConstraint('id')
    )
    
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.create_index('ix_audit_log_action_type', ['action_type'], unique=False)
        batch_op.create_index('ix_audit_log_admin_id', ['admin_id'], unique=False)
        batch_op.create_index('ix_audit_log_target_id', ['target_id'], unique=False)
        batch_op.create_index('ix_audit_log_timestamp', ['timestamp'], unique=False)


def downgrade():
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.drop_index('ix_audit_log_timestamp')
        batch_op.drop_index('ix_audit_log_target_id')
        batch_op.drop_index('ix_audit_log_admin_id')
        batch_op.drop_index('ix_audit_log_action_type')

    op.drop_table('audit_log')
