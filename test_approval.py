#!/usr/bin/env python
"""
Simulate admin approval request to test the approval logic
"""

from app import app, db
from models import Item, User, Notification
from flask import session as flask_session

# Create a test client
client = app.test_client()

# We need to set up a logged-in session for admin
with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['user_id'] = 1  # Admin user
        sess['admin_id'] = 1
    
    # Check item before approval
    with app.app_context():
        item_before = Item.query.get(43)
        print(f"BEFORE APPROVAL: status={item_before.status}, is_approved={item_before.is_approved}")
    
    # Make the POST request to approve
    print("\nSending POST request to /admin/approve/43...")
    response = c.post('/admin/approve/43', data={'value': '180000'}, follow_redirects=False)
    print(f"Response status: {response.status_code}")
    print(f"Response location: {response.location}")
    
    # Check item after approval
    with app.app_context():
        db.session.expunge_all()  # Clear all cached objects
        item_after = Item.query.get(43)
        print(f"\nAFTER APPROVAL: status={item_after.status}, is_approved={item_after.is_approved}, is_available={item_after.is_available}")
        
        if item_after.status == 'approved' and item_after.is_approved:
            print("\n*** APPROVAL WORKED! ***")
        else:
            print("\n*** APPROVAL FAILED - CHANGES NOT PERSISTED ***")
