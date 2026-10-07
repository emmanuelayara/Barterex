"""
One-off helper: add Phase 6 columns (asset-selection + dual verification) and
create the new `reservation_asset` table.

Use this on a database where you do NOT run `flask db upgrade` (e.g. your local dev
SQLite file). It is safe to run more than once; existing columns/tables are skipped.

    python add_settlement_verification_columns.py
"""
from sqlalchemy import inspect, text

from app import app, db
import models  # noqa: F401  (registers ReservationAsset on db.metadata before create_all)

USER_COLUMNS = [
    ('reliability_score', 'INTEGER DEFAULT 100'),
]

ITEM_COLUMNS = [
    ('locked_for_reservation_id', 'INTEGER'),
]

RESERVATION_COLUMNS = [
    ("seller_item_verification_status", "VARCHAR(20) DEFAULT 'not_submitted'"),
    ('seller_item_verified_at', 'TIMESTAMP'),
    ('seller_item_verification_notes', 'TEXT'),
]


def _add_missing_columns(table_name, columns):
    existing = {c['name'] for c in inspect(db.engine).get_columns(table_name)}
    added = []
    with db.engine.begin() as conn:
        for name, coltype in columns:
            if name not in existing:
                conn.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {name} {coltype}'))
                added.append(name)
    return added


def main():
    with app.app_context():
        added_user = _add_missing_columns('user', USER_COLUMNS)
        added_item = _add_missing_columns('item', ITEM_COLUMNS)
        added_reservation = _add_missing_columns('reservation', RESERVATION_COLUMNS)

        existing_tables = inspect(db.engine).get_table_names()
        db.create_all()
        created_reservation_asset = 'reservation_asset' not in existing_tables

        if added_user:
            print('Added user columns:', ', '.join(added_user))
        if added_item:
            print('Added item columns:', ', '.join(added_item))
        if added_reservation:
            print('Added reservation columns:', ', '.join(added_reservation))
        if created_reservation_asset:
            print('Created reservation_asset table.')
        if not (added_user or added_item or added_reservation or created_reservation_asset):
            print('Everything already up to date. Nothing to do.')


if __name__ == '__main__':
    main()
