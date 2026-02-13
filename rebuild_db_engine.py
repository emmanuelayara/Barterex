#!/usr/bin/env python
"""
Direct engine-based database creation
"""
import os
import shutil
from datetime import datetime
from sqlalchemy import create_engine, MetaData, inspect

print("DatabaseRebuild - Direct Engine Approach\n")

# Backup
if os.path.exists('barter.db'):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs('database_backups', exist_ok=True)
    backup_path = f'database_backups/barter_{timestamp}.db'
    shutil.copy2('barter.db', backup_path)
    print(f"✓ Backed up to: {backup_path}")
    os.remove('barter.db')

# Create engine
engine = create_engine('sqlite:///barter.db', echo=False)

print("Importing app and models...")
from app import app, db
from models import *

# Use app context for table metadata
with app.app_context():
    print("Creating all tables via metadata...")
    
    # Get the metadata from db
    db.metadata.create_all(engine)
    
    print("✓ Tables created")
    
    # Verify
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"✓ {len(tables)} tables created")
    
    # Check Item table
    if 'item' in tables:
        columns = inspector.get_columns('item')
        col_names = {col['name'] for col in columns}
        
        print(f"\nItem table: {len(columns)} columns")
        print("Columns:")
        for col in columns:
            marker = "→" if col['name'] == 'uploaded_by_id' else " "
            print(f"  {marker} {col['name']} ({col['type']})")
        
        if 'uploaded_by_id' in col_names:
            print("\n✓ SUCCESS: uploaded_by_id exists!")
        else:
            print("\n✗ FAIL: uploaded_by_id missing!")
    else:
        print("✗ Item table not found!")
    
    # Size
    size = os.path.getsize('barter.db')
    print(f"\n✓ Database size: {size:,} bytes")
    print("✓ Done! Run: flask run --debug")
