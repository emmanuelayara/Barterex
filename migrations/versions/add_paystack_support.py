"""Add Paystack support to Payment model

Revision ID: add_paystack_support
Revises: 2edc53b7f671_add_payment_model_for_moniepoint
Create Date: 2026-03-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_paystack_support'
down_revision = '2edc53b7f671_add_payment_model_for_moniepoint'
branch_labels = None
depends_on = None


def upgrade():
    # Make monnify_reference nullable to support multiple payment methods
    with op.batch_alter_table('payment', schema=None) as batch_op:
        batch_op.alter_column('monnify_reference',
                              existing_type=sa.String(length=255),
                              nullable=True)
        # Add Paystack reference column
        batch_op.add_column(sa.Column('paystack_reference', sa.String(length=255), nullable=True))
        batch_op.create_index('ix_payment_paystack_reference', ['paystack_reference'], unique=True)


def downgrade():
    with op.batch_alter_table('payment', schema=None) as batch_op:
        batch_op.drop_index('ix_payment_paystack_reference')
        batch_op.drop_column('paystack_reference')
        # Revert monnify_reference back to NOT NULL
        batch_op.alter_column('monnify_reference',
                              existing_type=sa.String(length=255),
                              nullable=False)
