"""
One-off helper: add the reservation/provisional-credit columns and the new
`reservation` table.

Use this on a database where you do NOT run `flask db upgrade` (e.g. your local dev
SQLite file). It is safe to run more than once; existing columns/tables are skipped.

    python add_reservation_columns.py
"""
from sqlalchemy import inspect, text

from app import app, db
import models  # noqa: F401  (registers Reservation on db.metadata before create_all)

USER_COLUMNS = [
    ('provisional_credits', 'INTEGER DEFAULT 0'),
]

ITEM_COLUMNS = [
    ('reserved_by_id', 'INTEGER'),
    ('reserved_at', 'TIMESTAMP'),
    ('reservation_expires_at', 'TIMESTAMP'),
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

        # Brand-new table; create_all only creates tables that don't exist yet.
        existing_tables = inspect(db.engine).get_table_names()
        db.create_all()
        created_reservation = 'reservation' not in existing_tables

        if added_user:
            print('Added user columns:', ', '.join(added_user))
        if added_item:
            print('Added item columns:', ', '.join(added_item))
        if created_reservation:
            print('Created reservation table.')
        if not (added_user or added_item or created_reservation):
            print('Everything already up to date. Nothing to do.')


if __name__ == '__main__':
    main()
