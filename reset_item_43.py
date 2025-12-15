#!/usr/bin/env python
"""Reset item 43 to pending status for testing"""

from app import db, app
from models import Item

with app.app_context():
    item = Item.query.filter_by(id=43).first()
    
    print(f"Before: status={item.status}, is_approved={item.is_approved}")
    
    # Reset to pending
    item.status = 'pending'
    item.is_approved = False
    item.is_available = False
    
    db.session.flush()
    db.session.commit()
    
    # Verify
    db.session.remove()
    item2 = Item.query.filter_by(id=43).first()
    print(f"After: status={item2.status}, is_approved={item2.is_approved}")
    print("Item 43 reset to pending - ready for approval test")
