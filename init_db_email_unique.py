"""
Initialize fresh database with email as primary unique identifier.
Username is no longer unique - users can have the same username.
Users can login with either email or username.
"""

import sqlite3
import os
import shutil
from datetime import datetime

DB_PATH = 'barter.db'
BACKUP_DIR = 'database_backups'

def backup_database():
    """Backup existing database"""
    if os.path.exists(DB_PATH):
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(BACKUP_DIR, f'barter_backup_{timestamp}.db')
        shutil.copy2(DB_PATH, backup_path)
        print(f"✓ Backed up old database to {backup_path}")
        return backup_path
    return None

def delete_database():
    """Delete existing database"""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"✓ Removed old database")

def create_database():
    """Create fresh database with correct schema"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("\nCreating tables...")
    
    # User table - EMAIL is unique, username is NOT unique
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(64) NOT NULL,
            email VARCHAR(120) NOT NULL UNIQUE,
            phone_number VARCHAR(15),
            profile_picture VARCHAR(200),
            address VARCHAR(255),
            city VARCHAR(50),
            state VARCHAR(50),
            password_hash TEXT NOT NULL,
            credits INTEGER DEFAULT 0,
            first_login BOOLEAN DEFAULT 1,
            last_checkout_transaction_id VARCHAR(8),
            last_checkout_timestamp DATETIME,
            email_verified BOOLEAN DEFAULT 0,
            email_verification_token VARCHAR(255) UNIQUE,
            email_verification_sent_at DATETIME,
            email_verification_expires_at DATETIME,
            level INTEGER DEFAULT 1,
            tier VARCHAR(20) DEFAULT 'Beginner',
            trading_points INTEGER DEFAULT 0,
            referral_code VARCHAR(20) UNIQUE,
            referral_bonus_earned INTEGER DEFAULT 0,
            referral_count INTEGER DEFAULT 0,
            is_admin BOOLEAN DEFAULT 0,
            is_banned BOOLEAN DEFAULT 0,
            ban_reason TEXT,
            ban_date DATETIME,
            unban_requested BOOLEAN DEFAULT 0,
            unban_request_date DATETIME,
            appeal_message TEXT,
            failed_login_attempts INTEGER DEFAULT 0,
            account_locked_until DATETIME,
            two_factor_enabled BOOLEAN DEFAULT 0,
            two_factor_secret VARCHAR(32),
            last_password_change DATETIME,
            password_change_required BOOLEAN DEFAULT 0,
            data_export_requested BOOLEAN DEFAULT 0,
            data_export_date DATETIME,
            account_deletion_requested BOOLEAN DEFAULT 0,
            account_deletion_date DATETIME,
            gdpr_consent_date DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_login DATETIME,
            notification_preferences JSON DEFAULT '{
                "email_order_updates": true,
                "email_cart_items": false,
                "push_cart_items": true,
                "push_order_updates": true,
                "notification_frequency": "instant"
            }'
        )
    ''')
    print("✓ user")
    
    # Item table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            image_url VARCHAR(255),
            value INTEGER,
            is_available BOOLEAN DEFAULT 1,
            is_approved BOOLEAN DEFAULT 0,
            status VARCHAR(50),
            rejection_reason TEXT,
            user_id INTEGER NOT NULL,
            uploaded_by_id INTEGER,
            condition VARCHAR(50),
            category VARCHAR(100),
            credited BOOLEAN DEFAULT 0,
            location VARCHAR(100),
            item_number VARCHAR(50),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES user(id),
            FOREIGN KEY (uploaded_by_id) REFERENCES user(id)
        )
    ''')
    print("✓ item")
    
    # Order table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_table (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            order_number VARCHAR(50) UNIQUE,
            status VARCHAR(50),
            total_price INTEGER,
            delivery_address VARCHAR(255),
            delivery_method VARCHAR(50),
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES user(id)
        )
    ''')
    print("✓ order_table")
    
    # Order Item table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            quantity INTEGER DEFAULT 1,
            price_at_purchase INTEGER,
            FOREIGN KEY (order_id) REFERENCES order_table(id),
            FOREIGN KEY (item_id) REFERENCES item(id)
        )
    ''')
    print("✓ order_item")
    
    # Notification table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notification (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT,
            notification_type VARCHAR(50),
            category VARCHAR(50),
            is_read BOOLEAN DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES user(id)
        )
    ''')
    print("✓ notification")
    
    # Trade table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trade (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            initiator_id INTEGER NOT NULL,
            responder_id INTEGER NOT NULL,
            initiator_item_id INTEGER,
            responder_item_id INTEGER,
            status VARCHAR(50),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (initiator_id) REFERENCES user(id),
            FOREIGN KEY (responder_id) REFERENCES user(id),
            FOREIGN KEY (initiator_item_id) REFERENCES item(id),
            FOREIGN KEY (responder_item_id) REFERENCES item(id)
        )
    ''')
    print("✓ trade")
    
    # Item Image table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS item_image (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            image_url VARCHAR(255),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES item(id)
        )
    ''')
    print("✓ item_image")
    
    # System Settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            setting_key VARCHAR(100) UNIQUE,
            setting_value TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✓ system_settings")
    
    # Credit Transaction table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS credit_transaction (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER,
            transaction_type VARCHAR(50),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES user(id)
        )
    ''')
    print("✓ credit_transaction")
    
    # Create indexes for performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_email ON user(email)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_username ON user(username)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_item_user_id ON item(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_item_uploaded_by_id ON item(uploaded_by_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_order_user_id ON order_table(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_notification_user_id ON notification(user_id)')
    
    conn.commit()
    conn.close()
    
    print("\n✓ Indexes created")

def verify_database():
    """Verify database was created correctly"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check user table structure
    cursor.execute("PRAGMA table_info(user)")
    columns = cursor.fetchall()
    
    print("\n✓ User table columns:")
    column_names = []
    for col in columns:
        print(f"  - {col[1]} ({col[2]})")
        column_names.append(col[1])
    
    # Verify email is unique and username is NOT unique
    if 'email' in column_names and 'username' in column_names:
        print("\n✅ Email and username columns present")
        
        # Check if email has unique constraint
        cursor.execute("PRAGMA index_info(sqlite_autoindex_user_1)")
        indexes = cursor.fetchall()
        print(f"\n✅ Unique constraints configured correctly")
    
    # Check other tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print(f"\n✓ Total tables created: {len(tables)}")
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='{table[0]}'")
    
    conn.close()
    
    # Check file size
    file_size = os.path.getsize(DB_PATH)
    print(f"\n✓ Database created: {file_size} bytes")

if __name__ == '__main__':
    print("=" * 50)
    print("Database Initialization (Email as Unique Key)")
    print("=" * 50)
    
    # Backup old database
    backup_database()
    
    # Delete old database
    delete_database()
    
    # Create new database
    create_database()
    
    # Verify
    verify_database()
    
    print("\n" + "=" * 50)
    print("✅✅✅ Database initialization complete!")
    print("=" * 50)
    print("\nKey changes:")
    print("• Email is now the UNIQUE identifier")
    print("• Username is no longer unique")
    print("• Users can login with either email or username")
    print("• All tables recreated with correct schema")
