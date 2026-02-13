import sqlite3

conn = sqlite3.connect('barter.db')
cursor = conn.cursor()

try:
    # Check if columns exist
    cursor.execute("PRAGMA table_info(user);")
    columns = {row[1] for row in cursor.fetchall()}
    
    if 'profile_completed' not in columns:
        print("Adding profile_completed column...")
        cursor.execute('ALTER TABLE user ADD COLUMN profile_completed BOOLEAN DEFAULT 0')
        print("✓ Added profile_completed")
    else:
        print("✓ profile_completed already exists")
    
    if 'profile_completed_at' not in columns:
        print("Adding profile_completed_at column...")
        cursor.execute('ALTER TABLE user ADD COLUMN profile_completed_at DATETIME')
        print("✓ Added profile_completed_at")
    else:
        print("✓ profile_completed_at already exists")
    
    conn.commit()
    print("✅ Database migration completed!")
except Exception as e:
    print(f"❌ Error: {e}")
    conn.rollback()
finally:
    conn.close()
