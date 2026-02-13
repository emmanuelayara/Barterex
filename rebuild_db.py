#!/usr/bin/env python
"""
Complete database rebuild with proper Flask context
"""
import os
import shutil
from datetime import datetime

print("=" * 60)
print("COMPLETE DATABASE REBUILD")
print("=" * 60)

# Backup if exists
if os.path.exists('barter.db'):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f'database_backups/barter_pre_fix_{timestamp}.db'
    os.makedirs('database_backups', exist_ok=True)
    shutil.copy2('barter.db', backup_path)
    print(f"\n✓ Backed up: {backup_path}")
    os.remove('barter.db')
    print("✓ Removed old database")

print("\nImporting Flask app...")
from app import app, db
from models import *  # Import all models to register them

print("✓ App imported")

with app.app_context():
    print("\nRecreating database...")
    
    # Drop all tables
    print("  - Dropping existing tables...")
    db.drop_all()
    
    # Create all tables fresh
    print("  - Creating new tables...")
    db.create_all()
    
    # Commit changes
    db.session.commit()
    print("✓ Database tables created")
    
    # Verify schema
    import sqlite3
    conn = sqlite3.connect('barter.db')
    cursor = conn.cursor()
    
    print("\nVerifying Item table schema...")
    cursor.execute("PRAGMA table_info(item)")
    columns = cursor.fetchall()
    
    print(f"Item table has {len(columns)} columns:")
    for col in columns:
        marker = "→" if col[1] == 'uploaded_by_id' else " "
        print(f"  {marker} {col[1]}")
    
    col_names = {col[1] for col in columns}
    if 'uploaded_by_id' in col_names:
        print("\n✓ SUCCESS: uploaded_by_id column confirmed!")
    else:
        print("\n✗ ERROR: uploaded_by_id column still missing!")
    
    # Check database size
    conn.close()
    size = os.path.getsize('barter.db')
    print(f"\n✓ Database size: {size:,} bytes")

print("\n" + "=" * 60)
print("✓ DATABASE REBUILD COMPLETE")
print("=" * 60)
print("\nThe app is ready. Start it with: flask run --debug")
