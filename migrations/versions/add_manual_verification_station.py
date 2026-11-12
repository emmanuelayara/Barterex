"""Associate manual physical reviews with a verification station."""

from alembic import op
import sqlalchemy as sa

revision = 'manual_station_20261112'
down_revision = 'email_2fa_20261110'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('item') as batch:
        batch.add_column(sa.Column('manual_station_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_item_manual_station', 'pickup_station', ['manual_station_id'], ['id'])


def downgrade():
    if op.get_bind().execute(sa.text(
        'SELECT 1 FROM item WHERE manual_station_id IS NOT NULL LIMIT 1'
    )).first():
        raise RuntimeError('Cannot remove manual verification stations while items reference them.')
    with op.batch_alter_table('item') as batch:
        batch.drop_constraint('fk_item_manual_station', type_='foreignkey')
        batch.drop_column('manual_station_id')
