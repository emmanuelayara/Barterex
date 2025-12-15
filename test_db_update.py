#!/usr/bin/env python
"""Test direct database update"""

from app import db, app
from models import Item

with app.app_context():
    print("=== BEFORE UPDATE ===")
    item = Item.query.filter_by(id=43).first()
    print(f"Item 43 - status: {item.status}, is_approved: {item.is_approved}")
    
    print("\n=== UPDATING ITEM ===")
    item.status = 'approved'
    item.is_approved = True
    item.is_available = True
    print(f"Changed in ORM: status={item.status}, is_approved={item.is_approved}")
    
    print("\n=== COMMITTING ===")
    try:
        db.session.commit()
        print("✓ Commit successful")
    except Exception as e:
        print(f"✗ Commit failed: {e}")
        db.session.rollback()
        raise
    
    print("\n=== AFTER UPDATE (SAME SESSION) ===")
    print(f"Item 43 - status: {item.status}, is_approved: {item.is_approved}")
    
    # Create NEW session to verify persistence
    db.session.remove()
    print("\n=== AFTER UPDATE (NEW SESSION) ===")
    item2 = Item.query.filter_by(id=43).first()
    print(f"Item 43 - status: {item2.status}, is_approved: {item2.is_approved}")
    
    if item2.status == 'approved' and item2.is_approved == True:
        print("\n✓✓✓ DATABASE UPDATE SUCCESSFUL ✓✓✓")
    else:
        print("\n✗✗✗ DATABASE UPDATE FAILED - CHANGES NOT PERSISTED ✗✗✗")
