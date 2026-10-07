"""
One-off helper: add the staged-lifecycle columns to `item`, and create the new
`item_video` table.

Use this on a database where you do NOT run `flask db upgrade` (e.g. your local dev
SQLite file). It is safe to run more than once; existing columns/tables are skipped.

    python add_staged_lifecycle_columns.py
"""
from sqlalchemy import inspect, text

from app import app, db
import models  # noqa: F401  (registers ItemVideo on db.metadata before create_all)

ITEM_COLUMNS = [
    ('trade_requested_at', 'TIMESTAMP'),
    ('preverification_notes', 'TEXT'),
    ('preverification_approved_at', 'TIMESTAMP'),
    ('preverification_approved_by_id', 'INTEGER'),
    ('ownership_confirmed', 'BOOLEAN DEFAULT 0'),
    ('serial_number', 'VARCHAR(100)'),
    ('activated_at', 'TIMESTAMP'),
    ('last_reconfirmed_at', 'TIMESTAMP'),
    ('reconfirmation_code', 'VARCHAR(12)'),
]


def main():
    with app.app_context():
        existing = {c['name'] for c in inspect(db.engine).get_columns('item')}
        added = []
        with db.engine.begin() as conn:
            for name, coltype in ITEM_COLUMNS:
                if name not in existing:
                    conn.execute(text(f'ALTER TABLE item ADD COLUMN {name} {coltype}'))
                    added.append(name)

        existing_tables = inspect(db.engine).get_table_names()
        db.create_all()
        created_item_video = 'item_video' not in existing_tables

        if added:
            print('Added item columns:', ', '.join(added))
        if created_item_video:
            print('Created item_video table.')
        if not (added or created_item_video):
            print('Everything already up to date. Nothing to do.')


if __name__ == '__main__':
    main()
