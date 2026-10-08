"""Trade lifecycle, provisional credits, reservations and item videos

Revision ID: add_trade_lifecycle_res
Revises: add_valuator_columns

Brings the database in line with models.py for everything added after the
valuator columns:

  user      : provisional_credits, reliability_score
  item      : provisional-credit columns, reservation columns, staged
              "Trade This Item" lifecycle columns, reconfirmation columns
  new tables: item_video, reservation, reservation_asset

Until now these were only created by the one-off helper scripts
(add_reservation_columns.py etc.), which use SQLite-only SQL (BOOLEAN DEFAULT 0)
and are not part of `flask db upgrade`. This migration works on PostgreSQL and
SQLite, and is safe to run more than once: anything that already exists
(columns, tables, indexes, foreign keys) is skipped.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_trade_lifecycle_res'
down_revision = 'add_valuator_columns'
branch_labels = None
depends_on = None


USER_COLUMNS = [
    ('provisional_credits', lambda: sa.Column('provisional_credits', sa.Integer(), nullable=True, server_default='0')),
    ('reliability_score', lambda: sa.Column('reliability_score', sa.Integer(), nullable=True, server_default='100')),
]

ITEM_COLUMNS = [
    ('provisional_credit_amount', lambda: sa.Column('provisional_credit_amount', sa.Float(), nullable=True)),
    ('provisional_credit_granted_at', lambda: sa.Column('provisional_credit_granted_at', sa.DateTime(), nullable=True)),
    ('provisional_credit_settled', lambda: sa.Column('provisional_credit_settled', sa.Boolean(), nullable=True, server_default=sa.false())),
    ('reserved_by_id', lambda: sa.Column('reserved_by_id', sa.Integer(), nullable=True)),
    ('reserved_at', lambda: sa.Column('reserved_at', sa.DateTime(), nullable=True)),
    ('reservation_expires_at', lambda: sa.Column('reservation_expires_at', sa.DateTime(), nullable=True)),
    ('locked_for_reservation_id', lambda: sa.Column('locked_for_reservation_id', sa.Integer(), nullable=True)),
    ('trade_requested_at', lambda: sa.Column('trade_requested_at', sa.DateTime(), nullable=True)),
    ('preverification_notes', lambda: sa.Column('preverification_notes', sa.Text(), nullable=True)),
    ('preverification_approved_at', lambda: sa.Column('preverification_approved_at', sa.DateTime(), nullable=True)),
    ('preverification_approved_by_id', lambda: sa.Column('preverification_approved_by_id', sa.Integer(), nullable=True)),
    ('ownership_confirmed', lambda: sa.Column('ownership_confirmed', sa.Boolean(), nullable=True, server_default=sa.false())),
    ('serial_number', lambda: sa.Column('serial_number', sa.String(length=100), nullable=True)),
    ('activated_at', lambda: sa.Column('activated_at', sa.DateTime(), nullable=True)),
    ('last_reconfirmed_at', lambda: sa.Column('last_reconfirmed_at', sa.DateTime(), nullable=True)),
    ('reconfirmation_code', lambda: sa.Column('reconfirmation_code', sa.String(length=12), nullable=True)),
]

# (constraint name, local column, referred table, referred column) for the new item columns
ITEM_FOREIGN_KEYS = [
    ('fk_item_reserved_by', 'reserved_by_id', 'user', 'id'),
    ('fk_item_locked_for_reservation', 'locked_for_reservation_id', 'reservation', 'id'),
    ('fk_item_preverification_admin', 'preverification_approved_by_id', 'admin', 'id'),
]


def _inspector():
    return sa.inspect(op.get_bind())


def _add_missing_columns(table, specs):
    existing = {c['name'] for c in _inspector().get_columns(table)}
    for name, make_column in specs:
        if name not in existing:
            op.add_column(table, make_column())


def _create_index_if_missing(index_name, table, columns):
    existing = {i['name'] for i in _inspector().get_indexes(table)}
    if index_name not in existing:
        op.create_index(index_name, table, columns)


def upgrade():
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    # ---- columns on existing tables --------------------------------------
    _add_missing_columns('user', USER_COLUMNS)
    _add_missing_columns('item', ITEM_COLUMNS)

    # ---- new tables --------------------------------------------------------
    if not _inspector().has_table('item_video'):
        op.create_table(
            'item_video',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('item_id', sa.Integer(), sa.ForeignKey('item.id', name='fk_itemvideo_item'), nullable=False),
            sa.Column('uploaded_by_id', sa.Integer(), sa.ForeignKey('user.id', name='fk_itemvideo_uploader'), nullable=False),
            sa.Column('temp_video_url', sa.String(length=500), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
            sa.Column('rejection_reason', sa.Text(), nullable=True),
            sa.Column('submitted_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('reviewed_at', sa.DateTime(), nullable=True),
            sa.Column('reviewed_by_admin_id', sa.Integer(), sa.ForeignKey('admin.id'), nullable=True),
            sa.Column('youtube_video_id', sa.String(length=50), nullable=True),
            sa.Column('youtube_url', sa.String(length=300), nullable=True),
            sa.Column('temp_copy_deleted_at', sa.DateTime(), nullable=True),
        )
    _create_index_if_missing('idx_itemvideo_item_id', 'item_video', ['item_id'])
    _create_index_if_missing('idx_itemvideo_status', 'item_video', ['status'])

    if not _inspector().has_table('reservation'):
        op.create_table(
            'reservation',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id', name='fk_reservation_user'), nullable=False),
            sa.Column('item_id', sa.Integer(), sa.ForeignKey('item.id', name='fk_reservation_item'), nullable=False),
            sa.Column('provisional_credits_used', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('cancelled_at', sa.DateTime(), nullable=True),
            sa.Column('seller_item_verification_status', sa.String(length=20), nullable=False,
                      server_default='not_submitted'),
            sa.Column('seller_item_verified_at', sa.DateTime(), nullable=True),
            sa.Column('seller_item_verification_notes', sa.Text(), nullable=True),
        )
    else:
        # table created earlier by add_reservation_columns.py: add the later (phase 6) columns
        _add_missing_columns('reservation', [
            ('seller_item_verification_status', lambda: sa.Column(
                'seller_item_verification_status', sa.String(length=20), nullable=False,
                server_default='not_submitted')),
            ('seller_item_verified_at', lambda: sa.Column('seller_item_verified_at', sa.DateTime(), nullable=True)),
            ('seller_item_verification_notes', lambda: sa.Column('seller_item_verification_notes', sa.Text(), nullable=True)),
        ])
    _create_index_if_missing('idx_reservation_user_id', 'reservation', ['user_id'])
    _create_index_if_missing('idx_reservation_item_id', 'reservation', ['item_id'])
    _create_index_if_missing('idx_reservation_status', 'reservation', ['status'])

    if not _inspector().has_table('reservation_asset'):
        op.create_table(
            'reservation_asset',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('reservation_id', sa.Integer(),
                      sa.ForeignKey('reservation.id', name='fk_reservationasset_reservation'), nullable=False),
            sa.Column('item_id', sa.Integer(), sa.ForeignKey('item.id', name='fk_reservationasset_item'), nullable=False),
            sa.Column('amount', sa.Integer(), nullable=False),
            sa.Column('verification_status', sa.String(length=20), nullable=False, server_default='not_submitted'),
            sa.Column('verified_at', sa.DateTime(), nullable=True),
            sa.Column('verification_notes', sa.Text(), nullable=True),
        )
    _create_index_if_missing('idx_reservationasset_reservation_id', 'reservation_asset', ['reservation_id'])
    _create_index_if_missing('idx_reservationasset_item_id', 'reservation_asset', ['item_id'])

    _create_index_if_missing('idx_item_reserved_by_id', 'item', ['reserved_by_id'])

    # ---- foreign keys on the new item columns (PostgreSQL only) ---------------
    # SQLite cannot add constraints to an existing table without rebuilding it,
    # and does not enforce them by default, so they are skipped there.
    if not is_sqlite:
        existing_fk_columns = set()
        for fk in _inspector().get_foreign_keys('item'):
            existing_fk_columns.update(fk.get('constrained_columns') or [])
        for name, column, ref_table, ref_column in ITEM_FOREIGN_KEYS:
            if column not in existing_fk_columns:
                op.create_foreign_key(name, 'item', ref_table, [column], [ref_column])


def downgrade():
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    existing_item_columns = {c['name'] for c in _inspector().get_columns('item')}

    if not is_sqlite:
        existing_fks = {fk.get('name') for fk in _inspector().get_foreign_keys('item')}
        for name, _column, _ref_table, _ref_column in ITEM_FOREIGN_KEYS:
            if name in existing_fks:
                op.drop_constraint(name, 'item', type_='foreignkey')

    for table in ('reservation_asset', 'item_video', 'reservation'):
        if _inspector().has_table(table):
            op.drop_table(table)

    item_indexes = {i['name'] for i in _inspector().get_indexes('item')}
    with op.batch_alter_table('item', schema=None) as batch_op:
        if 'idx_item_reserved_by_id' in item_indexes:
            batch_op.drop_index('idx_item_reserved_by_id')
        for name, _make in ITEM_COLUMNS:
            if name in existing_item_columns:
                batch_op.drop_column(name)

    existing_user_columns = {c['name'] for c in _inspector().get_columns('user')}
    with op.batch_alter_table('user', schema=None) as batch_op:
        for name, _make in USER_COLUMNS:
            if name in existing_user_columns:
                batch_op.drop_column(name)
