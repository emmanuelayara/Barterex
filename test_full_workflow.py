#!/usr/bin/env python
"""Test full approval workflow end-to-end"""

from app import app, db
from models import Item

with app.app_context():
    # Check item before
    item_before = Item.query.get(43)
    pending_before = Item.query.filter_by(status='pending').count()
    approved_before = Item.query.filter_by(status='approved').count()
    marketplace_items_before = Item.query.filter(Item.is_approved == True, Item.is_available == True).count()
    
    print("=== BEFORE APPROVAL ===")
    print(f"Item 43: status={item_before.status}, is_approved={item_before.is_approved}")
    print(f"Pending count: {pending_before}")
    print(f"Approved count: {approved_before}")
    print(f"Marketplace items: {marketplace_items_before}")
    
    # Simulate approval
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['user_id'] = 1
            sess['admin_id'] = 1
        
        c.post('/admin/approve/43', data={'value': '180000'})
    
    # Check after
    db.session.expunge_all()  # Clear cache
    item_after = Item.query.get(43)
    pending_after = Item.query.filter_by(status='pending').count()
    approved_after = Item.query.filter_by(status='approved').count()
    marketplace_items_after = Item.query.filter(Item.is_approved == True, Item.is_available == True).count()
    
    print("\n=== AFTER APPROVAL ===")
    print(f"Item 43: status={item_after.status}, is_approved={item_after.is_approved}")
    print(f"Pending count: {pending_after}")
    print(f"Approved count: {approved_after}")
    print(f"Marketplace items: {marketplace_items_after}")
    
    print("\n=== VERIFICATION ===")
    if item_after.status == 'approved' and item_after.is_approved and item_after.is_available:
        print("✓ Item status updated correctly")
    else:
        print("✗ Item status NOT updated")
    
    if pending_after < pending_before:
        print("✓ Item left pending queue")
    else:
        print("✗ Item still in pending queue")
    
    if approved_after > approved_before:
        print("✓ Item added to approved items")
    else:
        print("✗ Item NOT in approved items")
    
    if marketplace_items_after > marketplace_items_before:
        print("✓ Item appears in marketplace")
    else:
        print("✗ Item NOT in marketplace")
