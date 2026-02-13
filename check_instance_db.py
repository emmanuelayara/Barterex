#!/usr/bin/env python3
"""Check instance database schema"""
import sqlite3

c = sqlite3.connect('instance/barter.db')
cur = c.cursor()
cur.execute("PRAGMA table_info(user)")
rows = cur.fetchall()
cols = [r[1] for r in rows]
c.close()

print("instance/barter.db columns:")
print(f"  profile_completed: {('profile_completed' in cols)}")
print(f"  profile_completed_at: {('profile_completed_at' in cols)}")
print(f"Total columns: {len(cols)}")

if 'profile_completed' not in cols:
    print("\n⚠ Missing profile_completed in instance database!")
