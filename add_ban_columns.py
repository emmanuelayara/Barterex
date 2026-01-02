#!/usr/bin/env python
"""
Script to add missing ban tracking columns to the User table
This addresses the OperationalError: no such column: user.ban_date
"""
import sqlite3
import os

DB_PATH = 'c:\\Users\\ayara\\Documents\\Python\\Barterex\\instance\\barter.db'

print(f"Database path: {DB_PATH}")

# Connect to the database
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Get existing columns
cursor.execute("PRAGMA table_info(user)")
existing_columns = {row[1] for row in cursor.fetchall()}
print(f"\nExisting columns: {existing_columns}")

# List of columns to add
columns_to_add = [
    ('ban_date', 'DATETIME'),
    ('unban_request_date', 'DATETIME'),
    ('appeal_message', 'TEXT'),
]

# Add missing columns
columns_added = []
for col_name, col_type in columns_to_add:
    if col_name not in existing_columns:
        try:
            cursor.execute(f"ALTER TABLE user ADD COLUMN {col_name} {col_type}")
            columns_added.append(col_name)
            print(f"✅ Added column: {col_name} ({col_type})")
        except sqlite3.OperationalError as e:
            print(f"❌ Error adding {col_name}: {e}")
    else:
        print(f"⏭️  Column already exists: {col_name}")

# Commit changes
conn.commit()

# Verify columns were added
cursor.execute("PRAGMA table_info(user)")
final_columns = {row[1] for row in cursor.fetchall()}
print(f"\nFinal columns: {final_columns}")

conn.close()

if columns_added:
    print(f"\n✅ Successfully added {len(columns_added)} column(s): {', '.join(columns_added)}")
else:
    print(f"\n✅ All required columns already exist")
