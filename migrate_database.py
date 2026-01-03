"""
Database migration script to add cancellation columns to Order table.
Run this once to migrate your database schema.

Usage:
    python migrate_database.py
"""

import os
import sys
from sqlalchemy import text

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db

def migrate_database():
    """Add cancellation columns to Order table"""
    
    with app.app_context():
        # Get the database connection
        with db.engine.connect() as connection:
            # Check if columns already exist
            inspector = db.inspect(db.engine)
            columns = {col['name'] for col in inspector.get_columns('order')}
            
            print("Current Order table columns:", columns)
            
            # Add cancelled column if it doesn't exist
            if 'cancelled' not in columns:
                print("Adding 'cancelled' column...")
                try:
                    connection.execute(text('ALTER TABLE "order" ADD COLUMN cancelled BOOLEAN DEFAULT 0'))
                    connection.commit()
                    print("✓ 'cancelled' column added successfully")
                except Exception as e:
                    print(f"✗ Error adding 'cancelled' column: {e}")
            else:
                print("✓ 'cancelled' column already exists")
            
            # Add cancelled_at column if it doesn't exist
            if 'cancelled_at' not in columns:
                print("Adding 'cancelled_at' column...")
                try:
                    connection.execute(text('ALTER TABLE "order" ADD COLUMN cancelled_at DATETIME'))
                    connection.commit()
                    print("✓ 'cancelled_at' column added successfully")
                except Exception as e:
                    print(f"✗ Error adding 'cancelled_at' column: {e}")
            else:
                print("✓ 'cancelled_at' column already exists")
            
            # Add cancellation_reason column if it doesn't exist
            if 'cancellation_reason' not in columns:
                print("Adding 'cancellation_reason' column...")
                try:
                    connection.execute(text('ALTER TABLE "order" ADD COLUMN cancellation_reason TEXT'))
                    connection.commit()
                    print("✓ 'cancellation_reason' column added successfully")
                except Exception as e:
                    print(f"✗ Error adding 'cancellation_reason' column: {e}")
            else:
                print("✓ 'cancellation_reason' column already exists")
        
        print("\n✓ Database migration completed successfully!")

if __name__ == '__main__':
    print("Starting database migration...")
    print("=" * 50)
    migrate_database()
    print("=" * 50)
    print("Done!")
