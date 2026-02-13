#!/usr/bin/env python
"""
Create database using raw SQL - bypasses Flask/SQLAlchemy issues
"""
import os
import shutil
import sqlite3
from datetime import datetime

print("Creating database with raw SQL...\n")

# Backup old one
if os.path.exists('barter.db'):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs('database_backups', exist_ok=True)
    shutil.copy2('barter.db', f'database_backups/barter_{timestamp}.db')
    print(f"✓ Backed up old database")
    os.remove('barter.db')
    print(f"✓ Removed old database\n")

# Create new database
conn = sqlite3.connect('barter.db')
cursor = conn.cursor()

print("Creating tables...\n")

# User table
cursor.execute('''
    CREATE TABLE user (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username VARCHAR(80) UNIQUE NOT NULL,
        email VARCHAR(120) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_banned BOOLEAN DEFAULT 0,
        profile_picture VARCHAR(300),
        phone_number VARCHAR(20),
        address VARCHAR(255),
        city VARCHAR(100),
        state VARCHAR(100),
        credits FLOAT DEFAULT 0,
        level INTEGER DEFAULT 1,
        trading_points INTEGER DEFAULT 0,
        referral_code VARCHAR(12) UNIQUE,
        profile_completion_percentage INTEGER DEFAULT 0,
        last_checkout_transaction_id VARCHAR(50),
        last_checkout_timestamp TIMESTAMP
    )
''')
print("✓ user")

# Item table - MAIN TABLE
cursor.execute('''
    CREATE TABLE item (
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES user(id) ON DELETE CASCADE,
        FOREIGN KEY(uploaded_by_id) REFERENCES user(id)
    )
''')
print("✓ item")

# Create indexes for item  
cursor.execute('CREATE INDEX idx_item_user_id ON item(user_id)')
cursor.execute('CREATE INDEX idx_item_uploaded_by_id ON item(uploaded_by_id)')
cursor.execute('CREATE INDEX idx_item_is_available ON item(is_available)')
cursor.execute('CREATE INDEX idx_item_status ON item(status)')

# Other essential tables
cursor.execute('''
    CREATE TABLE order_table (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        date_ordered TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status VARCHAR(50) DEFAULT 'Processing',
        total_cost FLOAT NOT NULL,
        delivery_method VARCHAR(50),
        FOREIGN KEY(user_id) REFERENCES user(id)
    )
''')
print("✓ order_table")

cursor.execute('''
    CREATE TABLE order_item (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        quantity INTEGER DEFAULT 1,
        FOREIGN KEY(order_id) REFERENCES order_table(id),
        FOREIGN KEY(item_id) REFERENCES item(id)
    )
''')
print("✓ order_item")

cursor.execute('''
    CREATE TABLE notification (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_read BOOLEAN DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES user(id)
    )
''')
print("✓ notification")

cursor.execute('''
    CREATE TABLE trade (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        status VARCHAR(50) DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(sender_id) REFERENCES user(id),
        FOREIGN KEY(receiver_id) REFERENCES user(id)
    )
''')
print("✓ trade")

cursor.execute('''
    CREATE TABLE item_image (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER NOT NULL,
        image_url VARCHAR(300) NOT NULL,
        FOREIGN KEY(item_id) REFERENCES item(id)
    )
''')
print("✓ item_image")

cursor.execute('''
    CREATE TABLE system_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        maintenance_mode BOOLEAN DEFAULT 0,
        maintenance_message TEXT
    )
''')
print("✓ system_settings")

cursor.execute('''
    CREATE TABLE credit_transaction (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount FLOAT NOT NULL,
        transaction_type VARCHAR(50),
        description TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES user(id)
    )
''')
print("✓ credit_transaction")

# Commit
conn.commit()

# Verify item table
cursor.execute("PRAGMA table_info(item)")
columns = cursor.fetchall()
col_names = {col[1] for col in columns}

print(f"\n✓ Created {len(columns)} columns in item table")
print("Item table columns:")
for col in columns:
    marker = "→" if col[1] == 'uploaded_by_id' else " "
    print(f"  {marker} {col[1]}")

if 'uploaded_by_id' in col_names:
    print("\n✓✓✓ SUCCESS: uploaded_by_id column is present!")
else:
    print("\n✗ ERROR: uploaded_by_id column missing!")

# Cleanup
conn.close()
size = os.path.getsize('barter.db')
print(f"\n✓ Database created: {size:,} bytes")
print("\nDatabase is ready! Start Flask with: flask run --debug")
