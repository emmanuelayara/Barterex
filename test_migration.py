#!/usr/bin/env python
"""Quick test script to check the migration"""
import sqlite3

conn = sqlite3.connect('barter.db')
cursor = conn.cursor()

# Check current schema
cursor.execute("PRAGMA table_info(item)")
columns = cursor.fetchall()
print("Current Item table columns:")
for col in columns:
    print(f"  {col[1]}: {col[2]}")

# Check if uploaded_by_id exists
col_names = [col[1] for col in columns]
if 'uploaded_by_id' in col_names:
    print("\n✓ uploaded_by_id column exists!")
else:
    print("\n✗ uploaded_by_id column NOT found - running migration...")
    # Add the column
    cursor.execute("ALTER TABLE item ADD COLUMN uploaded_by_id INTEGER")
    # Populate it
    cursor.execute("UPDATE item SET uploaded_by_id = user_id WHERE uploaded_by_id IS NULL")
    conn.commit()
    print(f"✓ Migration complete. Updated {cursor.rowcount} rows")

conn.close()
