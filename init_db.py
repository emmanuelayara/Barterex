#!/usr/bin/env python
"""
Initialize database and apply uploaded_by_id migration
Run this to set up or update the database
"""

import os
import sys
from datetime import datetime

# Add the app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    print("\n" + "="*60)
    print("Database Initialization & Migration")
    print("="*60 + "\n")
    
    try:
        # Import app and db AFTER adding to path
        from app import app, db
        from models import Item, User
        
        print("[1/3] Creating Flask app context...")
        with app.app_context():
            print("✓ App context created\n")
            
            print("[2/3] Initializing database tables...")
            # Create all tables that don't exist
            db.create_all()
            print("✓ Database tables initialized\n")
            
            print("[3/3] Applying uploaded_by_id migration...")
            
            # Check if column exists
            import sqlite3
            conn = sqlite3.connect('barter.db')
            cursor = conn.cursor()
            
            # Check Item table schema
            try:
                cursor.execute("PRAGMA table_info(Item)")
                columns = [row[1] for row in cursor.fetchall()]
                
                if 'uploaded_by_id' in columns:
                    print("✓ Column 'uploaded_by_id' already exists\n")
                else:
                    print("✓ Adding 'uploaded_by_id' column...")
                    cursor.execute("ALTER TABLE Item ADD COLUMN uploaded_by_id INTEGER")
                    
                    # Populate existing items
                    print("✓ Populating existing items...")
                    cursor.execute("UPDATE Item SET uploaded_by_id = user_id WHERE uploaded_by_id IS NULL")
                    affected = cursor.rowcount
                    print(f"✓ Updated {affected} items\n")
                    
                    conn.commit()
                
                # Verify
                cursor.execute("PRAGMA table_info(Item)")
                print("✓ Item table schema verified:")
                for col in cursor.fetchall():
                    marker = "→" if col[1] == 'uploaded_by_id' else " "
                    print(f"    {marker} {col[1]}: {col[2]}")
                
            finally:
                conn.close()
            
        print("\n" + "="*60)
        print("✓ INITIALIZATION & MIGRATION COMPLETE")
        print("="*60)
        print("\nDatabase is ready!")
        print("Changes applied:")
        print("  • Database tables created/verified")
        print("  • uploaded_by_id column added to Item table")
        print("  • Existing items populated with uploader info\n")
        
        return 0
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        print("\n" + "="*60)
        print("✗ INITIALIZATION FAILED")
        print("="*60 + "\n")
        return 1

if __name__ == '__main__':
    sys.exit(main())
