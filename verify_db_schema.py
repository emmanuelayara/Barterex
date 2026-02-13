#!/usr/bin/env python3
"""
Verify the current database schema and check for mismatches
"""

import sqlite3
import os

db_paths = ['barter.db', 'instance/barter.db']

db_path = None
for path in db_paths:
    if os.path.exists(path):
        db_path = path
        break

if not db_path:
    print("✗ Database not found!")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print(f"Database: {db_path}")
print("=" * 80)
print("\nUSER TABLE SCHEMA:")
print("-" * 80)

cursor.execute('PRAGMA table_info(user)')
rows = cursor.fetchall()

if not rows:
    print("✗ user table does not exist!")
else:
    print(f"{'ID':<5} {'Column':<30} {'Type':<20} {'NotNull':<10} {'Default':<15}")
    print("-" * 80)
    
    columns = []
    for row in rows:
        col_id, col_name, col_type, not_null, default_val, pk = row
        print(f"{col_id:<5} {col_name:<30} {col_type:<20} {not_null:<10} {str(default_val):<15}")
        columns.append(col_name)
    
    print("\n" + "=" * 80)
    print("MISSING COLUMNS (checking against models.py):")
    print("-" * 80)
    
    required_columns = [
        'id', 'username', 'email', 'phone_number', 'profile_picture',
        'address', 'city', 'state', 'password_hash', 'credits', 'first_login',
        'last_checkout_transaction_id', 'last_checkout_timestamp',
        'email_verified', 'email_verification_token', 'email_verification_sent_at',
        'email_verification_expires_at', 'profile_completed', 'profile_completed_at',
        'level', 'tier', 'trading_points', 'referral_code', 'referral_bonus_earned',
        'referral_count', 'is_admin', 'is_banned', 'ban_reason', 'unban_requested',
        'unban_request_date', 'appeal_message', 'ban_date', 'failed_login_attempts',
        'account_locked_until', 'two_factor_enabled', 'two_factor_secret',
        'last_password_change', 'password_change_required', 'data_export_requested',
        'data_export_date', 'account_deletion_requested', 'account_deletion_date',
        'gdpr_consent_date', 'created_at', 'last_login', 'notification_preferences'
    ]
    
    missing = [col for col in required_columns if col not in columns]
    
    if missing:
        for col in missing:
            print(f"  ✗ {col}")
    else:
        print("  ✓ All required columns present!")
    
    print("\n" + "=" * 80)
    print(f"Total columns in database: {len(columns)}")
    print(f"Total required columns: {len(required_columns)}")

conn.close()
