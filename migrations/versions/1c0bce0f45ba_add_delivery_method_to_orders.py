"""add delivery method to orders

Revision ID: 1c0bce0f45ba
Revises: 4aa9bd3505e3
Create Date: 2025-08-12 15:46:28.019397

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1c0bce0f45ba'
down_revision = '4aa9bd3505e3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('order', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pickup_station_id', sa.Integer(), nullable=True))
        batch_op.alter_column(
            'delivery_method',
            existing_type=sa.VARCHAR(length=50),
            type_=sa.String(length=20),
            existing_nullable=False
        )
        batch_op.create_foreign_key(
            'fk_order_pickup_station',
            'pickup_station',
            ['pickup_station_id'],
            ['id']
        )


def downgrade():
    with op.batch_alter_table('order', schema=None) as batch_op:
        batch_op.drop_constraint('fk_order_pickup_station', type_='foreignkey')
        batch_op.alter_column(
            'delivery_method',
            existing_type=sa.String(length=20),
            type_=sa.VARCHAR(length=50),
            existing_nullable=False
        )
        batch_op.drop_column('pickup_station_id')


    # ### end Alembic commands ###
