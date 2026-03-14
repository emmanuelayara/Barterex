import sqlite3

db_path = 'instance/barter.db'
if __name__ == '__main__':
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("Modifying payment table to allow nullable monnify_reference...")
        
        # SQLite doesn't support direct ALTER COLUMN, so we need to recreate the table
        # First, create a backup and then recreate with correct constraints
        
        # Get the current schema
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='payment'")
        original_sql = cursor.fetchone()[0]
        print(f"Original schema:\n{original_sql}\n")
        
        # Rename old table
        cursor.execute("ALTER TABLE payment RENAME TO payment_old")
        
        # Create new table with nullable monnify_reference
        new_sql = original_sql.replace(
            "monnify_reference VARCHAR(255) NOT NULL",
            "monnify_reference VARCHAR(255)"
        )
        cursor.execute(new_sql)
        
        # Copy data from old table
        cursor.execute("""
            INSERT INTO payment 
            SELECT * FROM payment_old
        """)
        
        # Drop old table
        cursor.execute("DROP TABLE payment_old")
        
        conn.commit()
        print("✓ Successfully made monnify_reference nullable")
        
        # Verify
        cursor.execute('PRAGMA table_info(payment)')
        cols = cursor.fetchall()
        print("\n✓ Updated Payment table columns:")
        for col in cols:
            print(f"  - {col[1]:30s} (nullable: {col[3] == 0})")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()
