#!/usr/bin/env python
"""
Complete Migration Runner for uploaded_by_id field
Handles database schema update and data migration
"""

import sqlite3
import sys
import os
from datetime import datetime

class ItemUploadMigration:
    def __init__(self, db_path='barter.db'):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        
    def connect(self):
        """Connect to database"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
            print(f"✓ Connected to database: {self.db_path}")
            return True
        except Exception as e:
            print(f"✗ Failed to connect: {e}")
            return False
    
    def check_column_exists(self):
        """Check if uploaded_by_id column already exists"""
        self.cursor.execute("PRAGMA table_info(item)")
        columns = [row[1] for row in self.fetchall()]
        return 'uploaded_by_id' in columns
    
    def execute(self, query):
        """Execute a query"""
        return self.cursor.execute(query)
    
    def fetchall(self):
        """Fetch all results"""
        return self.cursor.fetchall()
    
    def fetchone(self):
        """Fetch one result"""
        return self.cursor.fetchone()
    
    def commit(self):
        """Commit transaction"""
        self.conn.commit()
    
    def rollback(self):
        """Rollback transaction"""
        self.conn.rollback()
    
    def close(self):
        """Close connection"""
        if self.conn:
            self.conn.close()
    
    def run_migration(self):
        """Run the complete migration"""
        print("\n" + "="*60)
        print("Item Upload Migration - Add uploaded_by_id Field")
        print("="*60 + "\n")
        
        # Step 1: Connect
        if not self.connect():
            return False
        
        # Step 2: Check if already migrated
        print("[1/4] Checking if migration is needed...")
        if self.check_column_exists():
            print("✓ Column 'uploaded_by_id' already exists - No migration needed\n")
            self.close()
            return True
        
        print("✓ Column doesn't exist - Proceeding with migration\n")
        
        try:
            # Step 3: Add column
            print("[2/4] Creating 'uploaded_by_id' column...")
            self.execute("ALTER TABLE item ADD COLUMN uploaded_by_id INTEGER")
            print("✓ Column created\n")
            
            # Step 4: Populate data
            print("[3/4] Populating data for existing items...")
            self.execute("""
                UPDATE item 
                SET uploaded_by_id = user_id 
                WHERE uploaded_by_id IS NULL
            """)
            affected = self.cursor.rowcount
            print(f"✓ Updated {affected} existing items\n")
            
            # Step 5: Commit
            print("[4/4] Committing changes...")
            self.commit()
            print("✓ Changes committed\n")
            
            # Verify
            print("="*60)
            print("VERIFICATION")
            print("="*60 + "\n")
            
            self.cursor.execute("PRAGMA table_info(item)")
            print("Item table columns:")
            for col in self.cursor.fetchall():
                col_id, col_name, col_type = col[0], col[1], col[2]
                marker = "→" if col_name == 'uploaded_by_id' else " "
                print(f"  {marker} {col_name}: {col_type}")
            
            self.cursor.execute("SELECT COUNT(*) FROM item WHERE uploaded_by_id IS NOT NULL")
            count = self.cursor.fetchone()[0]
            print(f"\nItems with uploaded_by_id set: {count}\n")
            
            return True
            
        except Exception as e:
            print(f"✗ Error during migration: {e}\n")
            self.rollback()
            return False
        finally:
            self.close()

def main():
    """Main entry point"""
    migration = ItemUploadMigration()
    success = migration.run_migration()
    
    if success:
        print("="*60)
        print("✓ MIGRATION COMPLETED SUCCESSFULLY")
        print("="*60)
        print("\nThe following changes have been made:")
        print("  • Added uploaded_by_id column to track original uploaders")
        print("  • Dashboard now shows only uploaded items (not purchased)")
        print("  • Admin user view shows accurate upload statistics")
        print("  • 'My Items' page displays only uploaded items\n")
        return 0
    else:
        print("="*60)
        print("✗ MIGRATION FAILED")
        print("="*60)
        print("\nPlease check the error messages above and try again.\n")
        return 1

if __name__ == '__main__':
    sys.exit(main())
