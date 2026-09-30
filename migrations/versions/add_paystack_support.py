"""Paystack support (already part of the initial schema)

Revision ID: add_paystack_support
Revises: 0c5157c2782b

The initial schema (0c5157c2782b) already contains payment.paystack_reference and
its index, and this file used to point at a revision that no longer exists, which
broke `flask db upgrade`. It is now a no-op step so the chain is linear:
0c5157c2782b -> add_paystack_support -> add_valuator_columns
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_paystack_support'
down_revision = '0c5157c2782b'
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
