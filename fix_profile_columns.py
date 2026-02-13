#!/usr/bin/env python3
"""
Fix missing profile_completed columns in the user table
These columns are defined in models.py but missing from the database
"""

import sqlite3
import os

# Try to find the database file
db_paths = [
    'barter.db',
    'instance/barter.db',
]

db_path = None
for path in db_paths:
    if os.path.exists(path):
        db_path = path
        print(f"✓ Found database at: {path}")
        break

if not db_path:
    print("✗ Could not find barter.db file!")
    print("Please ensure the database file exists in either:")
    print("  - barter.db")
    print("  - instance/barter.db")
    exit(1)

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    columns_to_add = [
        ('profile_completed', 'BOOLEAN DEFAULT 0'),
        ('profile_completed_at', 'DATETIME'),
        ('unban_request_date', 'DATETIME'),
        ('appeal_message', 'TEXT'),
        ('ban_date', 'DATETIME'),
    ]
    
    print("\nAttempting to add missing columns...")
    print("-" * 50)
    
    for col_name, col_type in columns_to_add:
        try:
            cursor.execute(f'ALTER TABLE user ADD COLUMN {col_name} {col_type}')
            conn.commit()
            print(f'✓ Added {col_name}')
        except Exception as e:
            error_msg = str(e).lower()
            if 'duplicate' in error_msg or 'already exists' in error_msg:
                print(f'✓ {col_name} already exists')
            else:
                print(f'✗ {col_name}: {str(e)[:80]}')
    
    conn.close()
    print("-" * 50)
    print("✓ Database update complete!")
    print("\nYou can now restart your Flask application.")
    
except Exception as e:
    print(f"✗ Error connecting to database: {str(e)}")
    exit(1)
