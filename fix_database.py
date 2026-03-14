import sqlite3
import os

db_path = 'instance/barter.db'
if os.path.exists(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Try to add the paystack_reference column (nullable, no unique constraint)
        try:
            cursor.execute("ALTER TABLE payment ADD COLUMN paystack_reference VARCHAR(255)")
            conn.commit()
            print("✓ Successfully added paystack_reference column to payment table")
        except sqlite3.OperationalError as e:
            if "already exists" in str(e):
                print("✓ Column already exists - database is up to date")
            else:
                print(f"Error: {e}")
                raise
        
        # Try to create unique index
        try:
            cursor.execute("CREATE UNIQUE INDEX ix_payment_paystack_reference ON payment(paystack_reference)")
            conn.commit()
            print("✓ Created unique index on paystack_reference")
        except sqlite3.OperationalError as e:
            if "already exists" in str(e):
                print("✓ Unique index already exists")
            else:
                print(f"Index creation note: {e}")
                
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        conn.close()
else:
    print(f"Database file not found at: {db_path}")
