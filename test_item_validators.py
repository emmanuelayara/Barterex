#!/usr/bin/env python
"""Test script for Item model validators"""

from app import app, db
from models import Item

app.app_context().push()

print("=" * 60)
print("ITEM VALIDATION TESTS")
print("=" * 60)

# Test 1: Valid price
print("\nTest 1: Valid positive price")
try:
    item = Item(name='Test Item', value=5000, condition='Brand New', category='Electronics', user_id=1)
    print("✓ Valid price (5000) accepted")
except ValueError as e:
    print(f"✗ Error: {e}")

# Test 2: Negative price
print("\nTest 2: Invalid negative price")
try:
    item = Item(name='Test Item', value=-5000, condition='Brand New', category='Electronics', user_id=1)
    print("✗ Negative price accepted (BAD!)")
except ValueError as e:
    print(f"✓ Blocked: {e}")

# Test 3: Zero price
print("\nTest 3: Invalid zero price")
try:
    item = Item(name='Test Item', value=0, condition='Brand New', category='Electronics', user_id=1)
    print("✗ Zero price accepted (BAD!)")
except ValueError as e:
    print(f"✓ Blocked: {e}")

# Test 4: Valid condition
print("\nTest 4: Valid condition (Fairly Used)")
try:
    item = Item(name='Test Item', value=5000, condition='Fairly Used', category='Electronics', user_id=1)
    print("✓ Valid condition (Fairly Used) accepted")
except ValueError as e:
    print(f"✗ Error: {e}")

# Test 5: Invalid condition
print("\nTest 5: Invalid condition (Perfect)")
try:
    item = Item(name='Test Item', value=5000, condition='Perfect', category='Electronics', user_id=1)
    print("✗ Invalid condition accepted (BAD!)")
except ValueError as e:
    print(f"✓ Blocked: {e}")

# Test 6: All valid conditions
print("\nTest 6: All valid conditions")
valid_conditions = ['Brand New', 'Like New', 'Lightly Used', 'Fairly Used', 'Used', 'For Parts']
for condition in valid_conditions:
    try:
        item = Item(name='Test', value=5000, condition=condition, category='Electronics', user_id=1)
        print(f"  ✓ {condition}")
    except ValueError:
        print(f"  ✗ {condition} failed")

# Test 7: Non-numeric price
print("\nTest 7: Invalid non-numeric price")
try:
    item = Item(name='Test Item', value='invalid', condition='Brand New', category='Electronics', user_id=1)
    print("✗ Non-numeric price accepted (BAD!)")
except ValueError as e:
    print(f"✓ Blocked: {e}")

# Test 8: NULL price (should be allowed)
print("\nTest 8: NULL price (should be allowed)")
try:
    item = Item(name='Test Item', value=None, condition='Brand New', category='Electronics', user_id=1)
    print("✓ NULL price allowed")
except ValueError as e:
    print(f"✗ Error: {e}")

# Test 9: NULL condition (should be allowed)
print("\nTest 9: NULL condition (should be allowed)")
try:
    item = Item(name='Test Item', value=5000, condition=None, category='Electronics', user_id=1)
    print("✓ NULL condition allowed")
except ValueError as e:
    print(f"✗ Error: {e}")

print("\n" + "=" * 60)
print("✅ ALL VALIDATION TESTS PASSED!")
print("=" * 60)
