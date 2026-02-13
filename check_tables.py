import sqlite3

conn = sqlite3.connect('barter.db')
cursor = conn.cursor()

# Get all table names
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()

print("Tables in barter.db:")
for table in tables:
    print(f"  - {table[0]}")

# Check the Item table schema
cursor.execute("PRAGMA table_info(Item)")
columns = cursor.fetchall()
print("\nItem table columns:")
for col in columns:
    print(f"  {col[1]}: {col[2]}")

conn.close()
