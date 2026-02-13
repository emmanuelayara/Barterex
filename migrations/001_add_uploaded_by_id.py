"""
Migration: Add uploaded_by_id column to Item table
This tracks who originally uploaded the item, separate from who currently owns it.
"""

import sqlite3
import sys

def migrate():
    """Add uploaded_by_id column to Item table"""
    try:
        # Connect to database
        conn = sqlite3.connect('barter.db')
        cursor = conn.cursor()
        
        print("Starting migration: Add uploaded_by_id to Item table...")
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(item)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'uploaded_by_id' in columns:
            print("✓ Column 'uploaded_by_id' already exists. Skipping migration.")
            conn.close()
            return True
        
        # Add the new column
        print("Adding 'uploaded_by_id' column to 'item' table...")
        cursor.execute("""
            ALTER TABLE item 
            ADD COLUMN uploaded_by_id INTEGER
        """)
        
        # Populate existing items: set uploaded_by_id = user_id for all existing items
        # This assumes current owner is the original uploader (since before this change, user_id was the uploader)
        print("Populating uploaded_by_id for existing items...")
        cursor.execute("""
            UPDATE item 
            SET uploaded_by_id = user_id 
            WHERE uploaded_by_id IS NULL
        """)
        
        affected_rows = cursor.rowcount
        print(f"✓ Updated {affected_rows} existing items")
        
        # Add foreign key constraint
        print("Note: Foreign key constraint will be enforced by SQLAlchemy")
        
        # Commit changes
        conn.commit()
        print("✓ Migration completed successfully!")
        
        return True
        
    except sqlite3.Error as e:
        print(f"✗ Database error: {e}")
        conn.rollback()
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    success = migrate()
    sys.exit(0 if success else 1)
