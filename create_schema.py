#!/usr/bin/env python
"""Direct table creation using SQLAlchemy core"""
import os
import sqlite3

# Remove old db file  
if os.path.exists('barter.db'):
    try:
        os.remove('barter.db')
        print("✓ Removed old database")
    except:
        pass

# Create new empty database
conn = sqlite3.connect('barter.db') 
cursor = conn.cursor()

# Create just the Item table with uploaded_by_id for testing
print("Creating Item table schema...")

cursor.execute('''
    CREATE TABLE IF NOT EXISTS item (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(120) NOT NULL,
        description TEXT,
        image_url VARCHAR(300),
        value FLOAT,
        is_available BOOLEAN DEFAULT 0,
        is_approved BOOLEAN DEFAULT 0,
        status VARCHAR(50) DEFAULT 'pending',
        rejection_reason TEXT,
        user_id INTEGER NOT NULL,
        uploaded_by_id INTEGER,
        condition VARCHAR(20),
        category VARCHAR(100) NOT NULL,
        credited BOOLEAN DEFAULT 0,
        location VARCHAR(100),
        item_number VARCHAR(20) UNIQUE NOT NULL,
        FOREIGN KEY(user_id) REFERENCES user(id),
        FOREIGN KEY(uploaded_by_id) REFERENCES user(id)
    )
''')

# Create user table (minimal)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS user (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username VARCHAR(80) UNIQUE NOT NULL,
        email VARCHAR(120) UNIQUE NOT NULL,
        password_hash VARCHAR(255)
    )
''')

conn.commit()

# Verify
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print(f"✓ Created {len(tables)} tables")

cursor.execute("PRAGMA table_info(item)")
columns = cursor.fetchall()
print("\nItem table columns:")
for col in columns:
    marker = "→" if col[1] == 'uploaded_by_id' else " "
    print(f"  {marker} {col[1]} ({col[2]})")

col_names = {col[1] for col in columns}
if 'uploaded_by_id' in col_names:
    print("\n✓ SUCCESS: uploaded_by_id column created!")

size = os.path.getsize('barter.db')
print(f"✓ Database size: {size} bytes")

conn.close()
print("\n✓ Database initialized. Now run Flask to create remaining tables.")
