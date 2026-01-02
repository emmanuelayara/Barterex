#!/usr/bin/env python
"""
Test script to manually create an appeal and verify it appears
"""
from app import app, db
from models import User
from datetime import datetime

with app.app_context():
    # Find the banned user
    user = User.query.filter_by(username='Ayara').first()
    
    if user and user.is_banned:
        print(f"\nTesting appeal for user: {user.username}")
        print(f"Current state:")
        print(f"  unban_requested: {user.unban_requested}")
        print(f"  unban_request_date: {user.unban_request_date}")
        print(f"  appeal_message: {user.appeal_message}")
        
        # Simulate appeal submission
        test_appeal = "I sincerely apologize for my previous violations. I have thoroughly reviewed the community guidelines and understand the seriousness of my actions. I commit to following all rules moving forward and will be more careful with my trading activities. Thank you for your consideration."
        
        user.unban_requested = True
        user.unban_request_date = datetime.utcnow()
        user.appeal_message = test_appeal
        db.session.commit()
        
        print(f"\nAfter simulating appeal submission:")
        print(f"  unban_requested: {user.unban_requested}")
        print(f"  unban_request_date: {user.unban_request_date}")
        print(f"  appeal_message: {user.appeal_message[:80]}...")
        
        # Check if it appears in pending appeals query
        pending = User.query.filter(
            User.is_banned == True,
            User.appeal_message != None,
            User.appeal_message != '',
            User.unban_request_date != None
        ).all()
        
        print(f"\nPending appeals now: {len(pending)}")
        for p in pending:
            print(f"  - {p.username}: {p.appeal_message[:60]}...")
        
        if len(pending) > 0:
            print("\n✅ Appeal is now visible to admins!")
        else:
            print("\n❌ Appeal is NOT visible to admins - there's a problem")
    else:
        print("User not found or not banned")
