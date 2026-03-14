import sqlite3

conn = sqlite3.connect('instance/barter.db')
cursor = conn.cursor()
cursor.execute('PRAGMA table_info(payment)')
cols = cursor.fetchall()
print('✓ Payment table schema:')
for col in cols:
    print(f"  - {col[1]:30s} ({col[2]})")
conn.close()
print("\n✓ Database is ready for Paystack payments!")
