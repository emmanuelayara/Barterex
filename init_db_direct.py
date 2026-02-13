#!/usr/bin/env python
"""
Initialize database using SQLAlchemy engine directly
"""
import os
from sqlalchemy import create_engine, text

# Remove 0-byte database if it exists
if os.path.exists('barter.db') and os.path.getsize('barter.db') == 0:
    os.remove('barter.db')
    print("Removed empty database")

# Create engine and initialize
engine = create_engine('sqlite:///barter.db')

print("Attempting to create tables through Flask app...")

try:
    from app import app, db
    from models import User, Item  # Import to register models
    
    with app.app_context():
        # Drop all (start fresh) - WARNING: This deletes all data
        # db.drop_all()
        
        # Create all tables
        db.create_all()
        db.session.commit()
        print("✓ Tables created via db.create_all()")
        
        # Force a connection to ensure database is written
        with engine.connect() as connection:
            result = connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            tables = result.fetchall()
            print(f"✓ {len(tables)} tables in database")
            
            # Check Item table
            result = connection.execute(text("PRAGMA table_info(Item)"))
            columns = result.fetchall()
            
            if columns:
                print("\nItem table schema:")
                for col in columns:
                    marker = "→" if col[1] == 'uploaded_by_id' else " "
                    print(f"  {marker} {col[1]} ({col[2]})")
                
                col_names = {col[1] for col in columns}
                if 'uploaded_by_id' in col_names:
                    print("\n✓ SUCCESS: Database initialized with uploaded_by_id column!")
                else:
                    print("\n✗ Column missing - checking alternative locations...")
            else:
                print("✗ Item table appears empty")
            
            connection.commit()
    
    # Final size check
    size = os.path.getsize('barter.db')
    print(f"✓ Database size: {size} bytes\n")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
