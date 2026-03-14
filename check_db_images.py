#!/usr/bin/env python
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'instance', 'barter.db')

with open('db_check_output.txt', 'w') as f:
    try:
        f.write(f"Checking database at: {db_path}\n")
        f.write(f"File exists: {os.path.exists(db_path)}\n\n")
        
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        # List all tables
        tables = cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        f.write("Tables in database:\n")
        for table in tables:
            f.write(f"  - {table[0]}\n")
        
        # Check item_image specifically
        try:
            rows = cur.execute("SELECT id, item_id, image_url FROM item_image LIMIT 5").fetchall()
            f.write("\nItemImage records (first 5):\n")
            for row in rows:
                f.write(f"  ID: {row[0]}, Item: {row[1]}, URL: {row[2]}\n")
        except Exception as e:
            f.write(f"\nError querying item_image: {e}\n")
            
        conn.close()
    except Exception as e:
        f.write(f"Error: {e}\n")

print("Output written to db_check_output.txt")
