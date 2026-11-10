"""Add persistent email second-factor challenges and abuse budgets."""

from alembic import op
import sqlalchemy as sa

revision = 'email_2fa_20261110'
down_revision = 'harden_security_20261110'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'email_login_challenge',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('principal', sa.String(80), nullable=False, unique=True),
        sa.Column('challenge_token', sa.String(64), nullable=False),
        sa.Column('binding_hash', sa.String(64), nullable=False),
        sa.Column('code_hash', sa.String(64)),
        sa.Column('credential_hash', sa.String(64), nullable=False),
        sa.Column('purpose', sa.String(20), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('window_started_at', sa.DateTime(), nullable=False),
        sa.Column('last_sent_at', sa.DateTime(), nullable=False),
        sa.Column('sends', sa.Integer(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('consumed', sa.Boolean(), nullable=False),
    )


def downgrade():
    raise RuntimeError('Email 2FA is required for administrators. Do not remove its enforcement/storage without a reviewed replacement.')
