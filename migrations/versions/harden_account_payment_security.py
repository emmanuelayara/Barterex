"""Revoke sessions, deduplicate payment credits and defer referral rewards."""

from alembic import op
import sqlalchemy as sa

revision = 'harden_security_20261110'
down_revision = 'add_manual_item_review'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user') as batch:
        batch.add_column(sa.Column('auth_token', sa.String(64), nullable=True))
        batch.create_unique_constraint('uq_user_auth_token', ['auth_token'])
        batch.add_column(sa.Column('verified_identity_hash', sa.String(64), nullable=True))
        batch.create_unique_constraint('uq_user_verified_identity_hash', ['verified_identity_hash'])
    with op.batch_alter_table('credit_transaction') as batch:
        batch.add_column(sa.Column('payment_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_credit_transaction_payment', 'payment', ['payment_id'], ['id'])
        batch.create_unique_constraint('uq_credit_transaction_payment', ['payment_id'])
    with op.batch_alter_table('referral') as batch:
        batch.add_column(sa.Column('item_upload_qualified', sa.Boolean(), nullable=False, server_default=sa.false()))
    connection = op.get_bind()
    connection.execute(sa.text('UPDATE "user" SET two_factor_enabled = false, two_factor_secret = NULL'))
    connection.execute(sa.text("""
        UPDATE referral SET item_upload_qualified = true
        WHERE item_upload_bonus_earned = true OR EXISTS (
            SELECT 1 FROM item
            WHERE item.uploaded_by_id = referral.referred_user_id AND item.is_approved = true
        )
    """))
    if 'user_security' in sa.inspect(connection).get_table_names():
        connection.execute(sa.text('UPDATE user_security SET two_factor_enabled = false, two_factor_secret = NULL'))


def downgrade():
    raise RuntimeError('Security hardening is forward-only. Restore a reviewed backup rather than re-enabling vulnerable authentication and payment behavior.')
