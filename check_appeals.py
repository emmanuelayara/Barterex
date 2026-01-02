#!/usr/bin/env python
"""
Test script to check if appeals are being saved to the database
"""
from app import app, db
from models import User

with app.app_context():
    # Find all banned users
    banned_users = User.query.filter_by(is_banned=True).all()
    
    print(f"\n{'='*60}")
    print(f"BANNED USERS CHECK")
    print(f"{'='*60}\n")
    print(f"Total banned users: {len(banned_users)}\n")
    
    for user in banned_users:
        print(f"User: {user.username} (ID: {user.id})")
        print(f"  is_banned: {user.is_banned}")
        print(f"  ban_date: {user.ban_date}")
        print(f"  ban_reason: {user.ban_reason}")
        print(f"  unban_requested: {user.unban_requested}")
        print(f"  unban_request_date: {user.unban_request_date}")
        print(f"  appeal_message: {user.appeal_message[:50] if user.appeal_message else 'None'}...")
        print()
    
    print(f"\n{'='*60}")
    print(f"USERS WITH PENDING APPEALS")
    print(f"{'='*60}\n")
    
    # Find all users with pending appeals
    pending = User.query.filter(
        User.is_banned == True,
        User.appeal_message != None,
        User.appeal_message != '',
        User.unban_request_date != None
    ).all()
    
    print(f"Total pending appeals: {len(pending)}\n")
    
    for user in pending:
        print(f"User: {user.username}")
        print(f"  Appeal submitted: {user.unban_request_date}")
        print(f"  Message length: {len(user.appeal_message)} chars")
        print(f"  Message preview: {user.appeal_message[:60]}...")
        print()
