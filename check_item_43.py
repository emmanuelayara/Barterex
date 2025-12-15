#!/usr/bin/env python
"""Quick script to check the state of item 43 in the database"""

from app import db, app
from models import Item

with app.app_context():
    item = Item.query.filter_by(id=43).first()
    
    if item:
        print(f"\n=== ITEM 43 STATUS ===")
        print(f"ID: {item.id}")
        print(f"Name: {item.name}")
        print(f"Status: {item.status}")
        print(f"is_approved: {item.is_approved}")
        print(f"is_available: {item.is_available}")
        print(f"Value: {item.value}")
        print(f"User ID: {item.user_id}")
    else:
        print("Item 43 not found!")
    
    # Check all items
    print(f"\n=== ALL ITEMS STATUS ===")
    all_items = Item.query.all()
    for item in all_items:
        print(f"ID {item.id}: {item.name[:30]} - status={item.status}, approved={item.is_approved}, available={item.is_available}")
    
    # Count pending
    pending = Item.query.filter_by(status='pending').count()
    approved = Item.query.filter_by(status='approved').count()
    rejected = Item.query.filter_by(status='rejected').count()
    
    print(f"\n=== COUNTS ===")
    print(f"Pending: {pending}")
    print(f"Approved: {approved}")
    print(f"Rejected: {rejected}")
