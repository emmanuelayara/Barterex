"""Add final terms and service-fee payment gating for new reservations."""

from alembic import op
import sqlalchemy as sa

revision = 'service_fee_20261113'
down_revision = 'manual_station_20261112'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('reservation') as batch:
        batch.add_column(sa.Column('service_fee_status', sa.String(24), nullable=False,
                                   server_default='not_required'))
        batch.add_column(sa.Column('service_fee_naira', sa.Numeric(12, 2), nullable=True))
        batch.add_column(sa.Column('service_fee_deadline', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('final_terms_accepted_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('final_terms_version', sa.String(40), nullable=True))


def downgrade():
    if op.get_bind().execute(sa.text(
        "SELECT 1 FROM reservation WHERE service_fee_status != 'not_required' LIMIT 1"
    )).first():
        raise RuntimeError('Cannot remove service-fee records while reservations use them.')
    with op.batch_alter_table('reservation') as batch:
        for column in ('final_terms_version', 'final_terms_accepted_at',
                       'service_fee_deadline', 'service_fee_naira', 'service_fee_status'):
            batch.drop_column(column)
