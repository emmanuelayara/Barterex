"""
Database migration: Add profile completion tracking and update referral bonus system
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = 'barter.db'

def migrate_database():
    """Add new columns for profile completion tracking"""
    
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        print("Starting database migration...")
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(user)")
        existing_columns = [col[1] for col in cursor.fetchall()]
        
        # Add profile_completed column if it doesn't exist
        if 'profile_completed' not in existing_columns:
            print("Adding 'profile_completed' column to user table...")
            cursor.execute('''
                ALTER TABLE user ADD COLUMN profile_completed BOOLEAN DEFAULT 0
            ''')
            print("✓ Added profile_completed column")
        else:
            print("✓ profile_completed column already exists")
        
        # Add profile_completed_at column if it doesn't exist
        if 'profile_completed_at' not in existing_columns:
            print("Adding 'profile_completed_at' column to user table...")
            cursor.execute('''
                ALTER TABLE user ADD COLUMN profile_completed_at DATETIME
            ''')
            print("✓ Added profile_completed_at column")
        else:
            print("✓ profile_completed_at column already exists")
        
        # Check referral table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='referral'")
        referral_exists = cursor.fetchone() is not None
        
        if not referral_exists:
            print("⚠️  Referral table doesn't exist - it will be created when you run the app")
            print("    The referral table will be auto-created from the SQLAlchemy model")
        else:
            cursor.execute("PRAGMA table_info(referral)")
            referral_columns = [col[1] for col in cursor.fetchall()]
            
            # Update signup_bonus_earned documentation
            if 'signup_bonus_earned_at' not in referral_columns:
                print("Adding 'signup_bonus_earned_at' column to referral table...")
                cursor.execute('''
                    ALTER TABLE referral ADD COLUMN signup_bonus_earned_at DATETIME
                ''')
                print("✓ Added signup_bonus_earned_at column")
            else:
                print("✓ signup_bonus_earned_at column already exists")
        
        # Create indexes for better query performance
        print("\nCreating indexes...")
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_profile_completed ON user(profile_completed)')
        print("✓ Created index on user.profile_completed")
        
        # Only create referral indexes if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='referral'")
        if cursor.fetchone():
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_referral_signup_bonus_earned ON referral(signup_bonus_earned)')
            print("✓ Created index on referral.signup_bonus_earned")
        else:
            print("⚠️  Skipping referral index (table will be created by Flask)")
        
        conn.commit()
        conn.close()
        
        print("\n" + "="*60)
        print("✅ Database migration completed successfully!")
        print("="*60)
        print("\nChanges made:")
        print("1. Added 'profile_completed' column to user table")
        print("2. Added 'profile_completed_at' column to user table")
        print("3. Added 'signup_bonus_earned_at' column to referral table")
        print("4. Created performance indexes")
        print("\nReferral bonus logic:")
        print("  - Referred signup bonus NOW awarded AFTER profile completion")
        print("  - Previously awarded immediately on signup")
        print("  - Users must fill: phone, address, city, state to complete profile")
        
        return True
        
    except Exception as e:
        print(f"❌ Migration error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("="*60)
    print("Referral Bonus System Migration")
    print("="*60)
    
    success = migrate_database()
    exit(0 if success else 1)
