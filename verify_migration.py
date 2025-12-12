#!/usr/bin/env python3
from app import app
from models import db
from sqlalchemy import text

with app.app_context():
    result = db.session.execute(text('PRAGMA table_info(user)'))
    rows = result.fetchall()
    print("User table schema:")
    for row in rows:
        print(row)
    
    # Check specifically for tier column
    print("\nChecking for tier column...")
    tier_found = any('tier' in str(row) for row in rows)
    if tier_found:
        print("✓ Tier column successfully added to user table!")
    else:
        print("✗ Tier column not found in user table")
