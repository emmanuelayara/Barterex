#!/usr/bin/env python
"""
Script to add the video_url column to the Item table
(YouTube link recorded by staff during appraisal, shown as a "Video" button on item detail page)
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'barter.db')

print(f"Database path: {DB_PATH}")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(item)")
existing_columns = {row[1] for row in cursor.fetchall()}
print(f"\nExisting columns: {existing_columns}")

if 'video_url' not in existing_columns:
    try:
        cursor.execute("ALTER TABLE item ADD COLUMN video_url VARCHAR(300)")
        conn.commit()
        print("✅ Added column: video_url (VARCHAR(300))")
    except sqlite3.OperationalError as e:
        print(f"❌ Error adding video_url: {e}")
else:
    print("⏭️  Column already exists: video_url")

cursor.execute("PRAGMA table_info(item)")
final_columns = {row[1] for row in cursor.fetchall()}
print(f"\nFinal columns: {final_columns}")

conn.close()
