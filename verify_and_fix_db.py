import sqlite3
import os


def add_column_if_missing(conn, column_name, column_type_sql):
    cursor = conn.cursor()
    cursor.execute('PRAGMA table_info(user);')
    existing = {row[1] for row in cursor.fetchall()}
    if column_name in existing:
        print(f'✓ {column_name} already exists')
        return False

    sql = f'ALTER TABLE user ADD COLUMN {column_name} {column_type_sql}'
    cursor.execute(sql)
    conn.commit()
    print(f'✓ Added {column_name} ({column_type_sql})')
    return True


def get_active_db_path():
    candidates = [
        os.path.join('instance', 'barter.db'),
        'barter.db',
    ]
    for path in candidates:
        if os.path.exists(path):
            conn = sqlite3.connect(path)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user'")
            has_user = cur.fetchone() is not None
            conn.close()
            if has_user:
                return path
    return os.path.join('instance', 'barter.db')


# Ensure we repair the real app database, which lives under instance by default.
db_path = get_active_db_path()
print(f"Database path: {os.path.abspath(db_path)}")
print(f"Database exists: {os.path.exists(db_path)}")
print(f"Database size: {os.path.getsize(db_path)} bytes\n")

conn = sqlite3.connect(db_path)

try:
    print("Current columns in user table:")
    columns = conn.execute('PRAGMA table_info(user);').fetchall()
    for col in columns:
        print(f"  - {col[1]} ({col[2]})")

    print("\n" + "=" * 60 + "\n")

    columns_to_add = [
        ('profile_completed', 'BOOLEAN DEFAULT 0'),
        ('profile_completed_at', 'DATETIME'),
        ('ban_date', 'DATETIME'),
        ('unban_request_date', 'DATETIME'),
        ('appeal_message', 'TEXT'),
        ('nin', 'VARCHAR(20)'),
        ('government_id_document', 'VARCHAR(255)'),
        ('id_verification_status', 'VARCHAR(30) DEFAULT "not_submitted"'),
        ('id_verified_at', 'DATETIME'),
    ]

    added_count = 0
    for column_name, column_type_sql in columns_to_add:
        if add_column_if_missing(conn, column_name, column_type_sql):
            added_count += 1

    if added_count == 0:
        print("\n✅ All required columns already exist")
    else:
        print(f"\n✅ Added {added_count} missing column(s)")

    print("\nVerifying required columns after migration:")
    columns = conn.execute('PRAGMA table_info(user);').fetchall()
    required = {'profile_completed', 'profile_completed_at', 'ban_date', 'unban_request_date', 'appeal_message', 'nin', 'government_id_document', 'id_verification_status', 'id_verified_at'}
    for col in columns:
        if col[1] in required:
            print(f"  ✓ {col[1]} ({col[2]})")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    conn.rollback()
finally:
    conn.close()
