"""Add image metadata columns to ItemImage

Revision ID: 8b0cb27b0de2
Revises: add_email_verification_fields
Create Date: 2026-01-02 17:26:30.703626

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8b0cb27b0de2'
down_revision = 'add_email_verification_fields'
branch_labels = None
depends_on = None


def upgrade():
    # Add image metadata columns to item_image table
    with op.batch_alter_table('item_image', schema=None) as batch_op:
        batch_op.add_column(sa.Column('width', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('height', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('file_size', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('quality_flags', sa.Text(), nullable=True))


def downgrade():
    # Remove image metadata columns from item_image table
    with op.batch_alter_table('item_image', schema=None) as batch_op:
        batch_op.drop_column('quality_flags')
        batch_op.drop_column('file_size')
        batch_op.drop_column('height')
        batch_op.drop_column('width')
