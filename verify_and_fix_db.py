import sqlite3
import os

db_path = 'barter.db'
print(f"Database path: {os.path.abspath(db_path)}")
print(f"Database exists: {os.path.exists(db_path)}")
print(f"Database size: {os.path.getsize(db_path)} bytes\n")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Get all columns in user table
    print("Current columns in user table:")
    cursor.execute("PRAGMA table_info(user);")
    columns = cursor.fetchall()
    for col in columns:
        print(f"  - {col[1]} ({col[2]})")
    
    print("\n" + "="*60 + "\n")
    
    # Check if target columns exist
    column_names = {col[1] for col in columns}
    missing = []
    
    if 'profile_completed' not in column_names:
        missing.append('profile_completed')
        print("Adding profile_completed column...")
        cursor.execute('ALTER TABLE user ADD COLUMN profile_completed BOOLEAN DEFAULT 0')
        print("✓ Added profile_completed")
    
    if 'profile_completed_at' not in column_names:
        missing.append('profile_completed_at')
        print("Adding profile_completed_at column...")
        cursor.execute('ALTER TABLE user ADD COLUMN profile_completed_at DATETIME')
        print("✓ Added profile_completed_at")
    
    if missing:
        conn.commit()
        print(f"\n✅ Added {len(missing)} missing column(s)")
    else:
        print("\n✅ All columns already exist")
    
    # Verify columns now exist
    print("\nVerifying columns after migration:")
    cursor.execute("PRAGMA table_info(user);")
    columns = cursor.fetchall()
    for col in columns:
        if col[1] in ['profile_completed', 'profile_completed_at']:
            print(f"  ✓ {col[1]} ({col[2]})")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    conn.rollback()
finally:
    conn.close()
