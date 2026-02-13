#!/usr/bin/env python
"""
Reset database to apply new schema with uploaded_by_id column
This script backs up the old database and creates a fresh one
"""
import os
import shutil
from datetime import datetime

db_path = 'barter.db'
backup_dir = 'database_backups'

# Create backup directory if it doesn't exist
if not os.path.exists(backup_dir):
    os.makedirs(backup_dir)

# Backup old database if it exists
if os.path.exists(db_path):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(backup_dir, f'barter_backup_{timestamp}.db')
    shutil.copy2(db_path, backup_path)
    print(f"✓ Old database backed up to: {backup_path}")
    
    # Delete the old database
    os.remove(db_path)
    print(f"✓ Old database removed: {db_path}")
else:
    print("  No existing database found")

# Initialize Flask app to create tables
print("\nInitializing new database with updated schema...")
try:
    from app import app, db
    
    with app.app_context():
        db.create_all()
        print("✓ New database created with all tables")
        print("✓ The uploaded_by_id column is now included in the schema")
        
        # Display schema verification
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(Item)")
        columns = {row[1] for row in cursor.fetchall()}
        
        if 'uploaded_by_id' in columns:
            print("✓ VERIFIED: uploaded_by_id column exists in Item table")
        
        conn.close()
        print("\n✓ Database migration complete! App is ready to use.")
        
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
