#!/usr/bin/env python
"""Test if models can be imported without ambiguous foreign key errors"""
import sys
import traceback

try:
    print("Attempting to import models...")
    from models import User, Item
    print("✓ SUCCESS: Models imported without errors!")
    print("The foreign key ambiguity has been resolved.")
    sys.exit(0)
except Exception as e:
    print(f"✗ FAILED: {type(e).__name__}")
    print(f"Error: {e}")
    traceback.print_exc()
    sys.exit(1)
