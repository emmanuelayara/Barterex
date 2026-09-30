"""
One-off helper: add the AI valuation columns to the `item` table.

Use this on a database where you do NOT run `flask db upgrade` (e.g. your local dev
SQLite file). It is safe to run more than once; existing columns are skipped.

    python add_valuator_columns.py
"""
from sqlalchemy import inspect, text

from app import app, db

COLUMNS = [
    ('ai_estimated_value', 'FLOAT'),
    ('ai_confidence', 'VARCHAR(20)'),
    ('ai_market_listings', 'INTEGER'),
    ('ai_value_range_low', 'FLOAT'),
    ('ai_value_range_high', 'FLOAT'),
    ('ai_risk_score', 'FLOAT'),
    ('ai_risk_level', 'VARCHAR(20)'),
    ('ai_risk_flags', 'TEXT'),
    ('ai_sources_used', 'TEXT'),
    ('verification_status', 'VARCHAR(30)'),
    ('verification_notes', 'TEXT'),
    ('ai_valuated_at', 'TIMESTAMP'),
    ('valuator_valuation_id', 'INTEGER'),
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
            print('All AI valuation columns already exist. Nothing to do.')


if __name__ == '__main__':
    main()
