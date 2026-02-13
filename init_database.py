#!/usr/bin/env python
"""
Properly initialize database with Flask context
"""
import os
import sys

# Remove old 0-byte database
if os.path.exists('barter.db') and os.path.getsize('barter.db') == 0:
    os.remove('barter.db')
    print("✓ Removed empty database file")

try:
    from app import app, db
    from models import User, Item  # Import models to ensure they're registered
    
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("✓ Database tables created")
        
        # Verify
        import sqlite3
        conn = sqlite3.connect('barter.db')
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"✓ Database contains {len(tables)} tables")
        
        # Check Item table specifically
        cursor.execute("PRAGMA table_info(Item)")
        columns = cursor.fetchall()
        col_names = {col[1] for col in columns}
        
        print("\nItem table columns:")
        for col in columns:
            marker = "→" if col[1] == 'uploaded_by_id' else " "
            print(f"  {marker} {col[1]}: {col[2]}")
        
        if 'uploaded_by_id' in col_names:
            print("\n✓ SUCCESS: uploaded_by_id column is present!")
        else:
            print("\n✗ ERROR: uploaded_by_id column is missing!")
        
        # Check database size
        conn.close()
        size = os.path.getsize('barter.db')
        print(f"\n✓ Database size: {size} bytes")
        print("✓ Database is ready to use!")
        
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
