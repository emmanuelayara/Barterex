import sqlite3

conn = sqlite3.connect('instance/barter.db')
cursor = conn.cursor()

columns_to_add = [
    ('email_verified', 'BOOLEAN DEFAULT 0'),
    ('email_verification_token', 'VARCHAR(255)'),
    ('email_verification_sent_at', 'DATETIME'),
    ('email_verification_expires_at', 'DATETIME'),
    ('level', 'INTEGER DEFAULT 1'),
    ('tier', 'VARCHAR(20) DEFAULT "Beginner"'),
    ('trading_points', 'INTEGER DEFAULT 0'),
    ('referral_code', 'VARCHAR(20)'),
    ('referral_bonus_earned', 'INTEGER DEFAULT 0'),
    ('referral_count', 'INTEGER DEFAULT 0'),
    ('is_admin', 'BOOLEAN DEFAULT 0'),
    ('is_banned', 'BOOLEAN DEFAULT 0'),
    ('ban_reason', 'TEXT'),
    ('unban_requested', 'BOOLEAN DEFAULT 0'),
    ('failed_login_attempts', 'INTEGER DEFAULT 0'),
    ('account_locked_until', 'DATETIME'),
    ('two_factor_enabled', 'BOOLEAN DEFAULT 0'),
    ('two_factor_secret', 'VARCHAR(32)'),
    ('last_password_change', 'DATETIME'),
    ('password_change_required', 'BOOLEAN DEFAULT 0'),
    ('data_export_requested', 'BOOLEAN DEFAULT 0'),
    ('data_export_date', 'DATETIME'),
    ('account_deletion_requested', 'BOOLEAN DEFAULT 0'),
    ('account_deletion_date', 'DATETIME'),
    ('gdpr_consent_date', 'DATETIME'),
    ('created_at', 'DATETIME'),
    ('last_login', 'DATETIME'),
    ('notification_preferences', 'JSON'),
]

for col_name, col_type in columns_to_add:
    try:
        cursor.execute(f'ALTER TABLE user ADD COLUMN {col_name} {col_type}')
        print(f'✓ Added {col_name}')
    except Exception as e:
        error_msg = str(e).lower()
        if 'duplicate' in error_msg or 'already exists' in error_msg:
            print(f'✓ {col_name} already exists')
        else:
            print(f'✗ {col_name}: {str(e)[:50]}')

conn.commit()
conn.close()
print('\nDatabase update complete')
