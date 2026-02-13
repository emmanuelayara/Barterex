#!/usr/bin/env python
"""
Direct SQL migration for uploaded_by_id column
No Flask dependencies required
"""

import sqlite3
import sys

def migrate():
    """
    Add uploaded_by_id column to Item table
    """
    db_path = 'barter.db'
    
    print("\n" + "="*60)
    print("Direct SQL Migration - uploaded_by_id Field")
    print("="*60 + "\n")
    
    try:
        print(f"[1/4] Connecting to database: {db_path}")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        print("✓ Connected\n")
        
        # Check if table exists
        print("[2/4] Checking Item table...")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Item'")
        
        if not cursor.fetchone():
            print("✗ Item table not found in database")
            print("   The database may not be initialized yet.")
            print("   Run the Flask app first to create the tables.\n")
            conn.close()
            return False
        
        print("✓ Item table exists\n")
        
        # Check if column already exists
        print("[3/4] Checking for uploaded_by_id column...")
        cursor.execute("PRAGMA table_info(Item)")
        columns = {row[1] for row in cursor.fetchall()}
        
        if 'uploaded_by_id' in columns:
            print("✓ Column 'uploaded_by_id' already exists!")
            print("   No migration needed.\n")
        else:
            print("✓ Adding 'uploaded_by_id' column...")
            cursor.execute("ALTER TABLE Item ADD COLUMN uploaded_by_id INTEGER")
            print("✓ Column added\n")
            
            print("[4/4] Populating existing items...")
            cursor.execute("UPDATE Item SET uploaded_by_id = user_id WHERE uploaded_by_id IS NULL")
            affected = cursor.rowcount
            print(f"✓ Updated {affected} items\n")
            
            conn.commit()
            print("✓ Changes committed\n")
        
        # Verify schema
        print("="*60)
        print("VERIFICATION")
        print("="*60 + "\n")
        
        cursor.execute("PRAGMA table_info(Item)")
        print("Item table schema (relevant columns):")
        for row in cursor.fetchall():
            col_id, col_name, col_type, notnull, default, pk = row
            if col_name in ['id', 'user_id', 'uploaded_by_id', 'name', 'is_approved']:
                marker = "→" if col_name == 'uploaded_by_id' else " "
                print(f"  {marker} {col_name}: {col_type}")
        
        # Count items
        cursor.execute("SELECT COUNT(*) FROM Item WHERE uploaded_by_id IS NOT NULL")
        count = cursor.fetchone()[0]
        print(f"\nItems with uploaded_by_id: {count}\n")
        
        conn.close()
        
        print("="*60)
        print("✓ MIGRATION SUCCESSFUL")
        print("="*60 + "\n")
        
        print("Ready to deploy with new features:")
        print("  • Dashboard shows only uploaded items")
        print("  • Never counts purchased items as 'listed'")
        print("  • Admin view shows accurate item statistics\n")
        
        return True
        
    except sqlite3.Error as e:
        print(f"\n✗ Database error: {e}\n")
        return False
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}\n")
        return False

if __name__ == '__main__':
    success = migrate()
    sys.exit(0 if success else 1)
