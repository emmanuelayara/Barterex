import sqlite3

# Connect to the database
conn = sqlite3.connect('barter.db')
cursor = conn.cursor()

try:
    # Check current columns
    cursor.execute("PRAGMA table_info(user);")
    columns = [row[1] for row in cursor.fetchall()]
    
    # Add missing columns if they don't exist
    if 'profile_completed' not in columns:
        print('Adding profile_completed column...')
        cursor.execute('ALTER TABLE user ADD COLUMN profile_completed BOOLEAN DEFAULT 0')
        print('✓ profile_completed added')
    else:
        print('✓ profile_completed already exists')
    
    if 'profile_completed_at' not in columns:
        print('Adding profile_completed_at column...')
        cursor.execute('ALTER TABLE user ADD COLUMN profile_completed_at DATETIME')
        print('✓ profile_completed_at added')
    else:
        print('✓ profile_completed_at already exists')
    
    # Check referral table
    cursor.execute("PRAGMA table_info(referral);")
    ref_columns = [row[1] for row in cursor.fetchall()]
    
    if 'signup_bonus_earned_at' not in ref_columns:
        print('Adding signup_bonus_earned_at column...')
        cursor.execute('ALTER TABLE referral ADD COLUMN signup_bonus_earned_at DATETIME')
        print('✓ signup_bonus_earned_at added')
    else:
        print('✓ signup_bonus_earned_at already exists')
    
    conn.commit()
    print('✅ Database migration completed successfully!')
    
except Exception as e:
    print(f'❌ Error: {e}')
    conn.rollback()
finally:
    conn.close()
