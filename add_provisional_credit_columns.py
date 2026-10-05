"""
One-off helper: add the provisional-credit columns to the `item` table.

Use this on a database where you do NOT run `flask db upgrade` (e.g. your local dev
SQLite file). It is safe to run more than once; existing columns are skipped.

    python add_provisional_credit_columns.py
"""
from sqlalchemy import inspect, text

from app import app, db

COLUMNS = [
    ('provisional_credit_amount', 'FLOAT'),
    ('provisional_credit_granted_at', 'TIMESTAMP'),
    ('provisional_credit_settled', 'BOOLEAN DEFAULT 0'),
]


def main():
    with app.app_context():
        existing = {c['name'] for c in inspect(db.engine).get_columns('item')}
        added = []
        with db.engine.begin() as conn:
            for name, coltype in COLUMNS:
                if name not in existing:
                    conn.execute(text(f'ALTER TABLE item ADD COLUMN {name} {coltype}'))
                    added.append(name)
        if added:
            print('Added columns:', ', '.join(added))
        else:
            print('All provisional-credit columns already exist. Nothing to do.')


if __name__ == '__main__':
    main()
