#!/usr/bin/env python
"""Test if app/models work with the relationship fix"""
import sys
import traceback

try:
    print("Attempting to load Flask app...")
    from app import app, db
    with app.app_context():
        from models import User, Item
        print("✓ SUCCESS: App and models loaded without ambiguous foreign key errors!")
        sys.exit(0)
except Exception as e:
    print(f"✗ FAILED: {type(e).__name__}")
    print(f"Error: {e}")
    if "AmbiguousForeignKeysError" in str(type(e)):
        print("\nThe foreign key ambiguity is still present!")
    traceback.print_exc()
    sys.exit(1)
