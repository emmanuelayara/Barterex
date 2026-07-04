# Wishlist Feature - Testing & Debugging Guide

## 🧪 Unit Testing Checklist

### Basic Functionality Tests

#### Test 1: Add Wishlist Item (Item Search)
```python
def test_add_wishlist_item():
    user = create_test_user("test@example.com")
    response = post_json('/wishlist/add', {
        'item_name': 'iPhone 15 Pro',
        'category': None,
        'search_type': 'item',
        'notify_via_email': True,
        'notify_via_app': True
    }, user=user)
    
    assert response.status_code == 200
    assert response.json['success'] == True
    assert response.json['wishlist_id'] > 0
    
    # Verify database
    wishlist = Wishlist.query.filter_by(user_id=user.id).first()
    assert wishlist is not None
    assert wishlist.item_name == 'iPhone 15 Pro'
    assert wishlist.is_active == True
```

#### Test 2: Add Wishlist Category
```python
def test_add_wishlist_category():
    user = create_test_user("test@example.com")
    response = post_json('/wishlist/add', {
        'item_name': None,
        'category': 'Electronics',
        'search_type': 'category',
        'notify_via_email': True,
        'notify_via_app': True
    }, user=user)
    
    assert response.status_code == 200
    wishlist = Wishlist.query.filter_by(user_id=user.id).first()
    assert wishlist.category == 'Electronics'
    assert wishlist.search_type == 'category'
```

#### Test 3: Duplicate Detection
```python
def test_duplicate_wishlist_rejected():
    user = create_test_user("test@example.com")
    
    # First addition should succeed
    response1 = post_json('/wishlist/add', {
        'item_name': 'iPhone 15 Pro',
        'search_type': 'item'
    }, user=user)
    assert response1.status_code == 200
    
    # Second addition of same item should fail
    response2 = post_json('/wishlist/add', {
        'item_name': 'iPhone 15 Pro',
        'search_type': 'item'
    }, user=user)
    assert response2.status_code == 400
    assert 'duplicate' in response2.json['error'].lower()
```

#### Test 4: View Wishlist
```python
def test_view_wishlist():
    user = create_test_user("test@example.com")
    
    # Add 25 items
    for i in range(25):
        add_wishlist(f'Item {i}', user=user)
    
    # Page 1 should have 20 items
    response = get_json('/wishlist/view?page=1', user=user)
    assert response.status_code == 200
    assert len(response.json['wishlists']) == 20
    assert response.json['pagination']['total_items'] == 25
    assert response.json['pagination']['total_pages'] == 2
    
    # Page 2 should have 5 items
    response = get_json('/wishlist/view?page=2', user=user)
    assert len(response.json['wishlists']) == 5
```

#### Test 5: Remove Wishlist Item
```python
def test_remove_wishlist_item():
    user = create_test_user("test@example.com")
    wishlist = add_wishlist('iPhone 15', user=user)
    
    response = post_json(f'/wishlist/remove/{wishlist.id}', {}, user=user)
    assert response.status_code == 200
    
    # Verify deleted from database
    deleted = Wishlist.query.get(wishlist.id)
    assert deleted is None
    
    # Verify matches also deleted (cascade)
    matches = WishlistMatch.query.filter_by(wishlist_id=wishlist.id).all()
    assert len(matches) == 0
```

#### Test 6: Pause/Resume Wishlist
```python
def test_pause_resume_wishlist():
    user = create_test_user("test@example.com")
    wishlist = add_wishlist('iPhone 15', user=user)
    
    # Pause
    response = post_json(f'/wishlist/pause/{wishlist.id}', {}, user=user)
    assert response.status_code == 200
    
    # Verify paused
    wishlist_db = Wishlist.query.get(wishlist.id)
    assert wishlist_db.is_active == False
    
    # Resume
    response = post_json(f'/wishlist/resume/{wishlist.id}', {}, user=user)
    assert response.status_code == 200
    
    # Verify resumed
    wishlist_db = Wishlist.query.get(wishlist.id)
    assert wishlist_db.is_active == True
```

#### Test 7: Matching Logic
```python
def test_wishlist_matching():
    user = create_test_user("test@example.com")
    wishlist = add_wishlist('iPhone 15 Pro', user=user)
    
    # Create matching item in marketplace
    item = create_item('iPhone 15 Pro 256GB', user=admin_user())
    
    # Trigger matching (normally happens on admin approval)
    matches = find_wishlist_matches(item)
    
    assert len(matches) == 1
    assert matches[0][0].id == wishlist.id
    
    # Verify WishlistMatch created
    match = WishlistMatch.query.filter_by(wishlist_id=wishlist.id).first()
    assert match is not None
    assert match.item_id == item.id
```

#### Test 8: Category Matching
```python
def test_category_wishlist_matching():
    user = create_test_user("test@example.com")
    wishlist = add_wishlist(category='Electronics', user=user)
    
    # Create item in Electronics category
    item = create_item('Samsung TV', category='Electronics', user=admin_user())
    
    # Should match
    matches = find_wishlist_matches(item)
    assert len(matches) == 1
    
    # Create item in different category
    item2 = create_item('Book', category='Books', user=admin_user())
    
    # Should NOT match
    matches2 = find_wishlist_matches(item2)
    assert len(matches2) == 0
```

#### Test 9: Authorization
```python
def test_authorization():
    user1 = create_test_user("user1@example.com")
    user2 = create_test_user("user2@example.com")
    
    wishlist = add_wishlist('iPhone 15', user=user1)
    
    # User2 cannot remove user1's wishlist
    response = post_json(
        f'/wishlist/remove/{wishlist.id}',
        {},
        user=user2
    )
    assert response.status_code == 403
    
    # Wishlist still exists
    assert Wishlist.query.get(wishlist.id) is not None
```

#### Test 10: Notification Sending
```python
def test_notification_sending():
    user = create_test_user("test@example.com")
    wishlist = add_wishlist(
        'iPhone 15 Pro',
        notify_via_email=True,
        notify_via_app=True,
        user=user
    )
    
    # Create matching item
    item = create_item('iPhone 15 Pro 256GB', user=admin_user())
    
    # Clear email queue
    clear_email_queue()
    
    # Trigger matching and notification
    send_wishlist_notification(wishlist, item, user)
    
    # Verify email sent
    assert len(email_queue) == 1
    email = email_queue[0]
    assert user.email in email.recipients
    assert 'iPhone 15 Pro' in email.subject
    
    # Verify in-app notification
    notification = Notification.query.filter_by(user_id=user.id).first()
    assert notification is not None
    assert 'iPhone 15 Pro' in notification.message
```

---

## 🐛 Debugging Tips

### Check Database State
```python
# In Flask shell
flask shell

# View all wishlists for a user
user = User.query.filter_by(email='test@example.com').first()
wishlists = Wishlist.query.filter_by(user_id=user.id).all()
for w in wishlists:
    print(f"ID: {w.id}, Item: {w.item_name}, Active: {w.is_active}")

# View all matches for a wishlist
matches = WishlistMatch.query.filter_by(wishlist_id=1).all()
for m in matches:
    print(f"Match ID: {m.id}, Item: {m.item_id}, Email sent: {m.email_sent}")

# Check migration status
db.session.query(db.text('SELECT * FROM alembic_version')).all()
```

### Verify Routes Registered
```python
from app import app

routes = [str(rule) for rule in app.url_map.iter_rules() if 'wishlist' in str(rule)]
for route in sorted(routes):
    print(route)
```

### Test Service Functions
```python
from app import app
from services.wishlist_service import calculate_similarity, find_wishlist_matches

with app.app_context():
    # Test similarity
    score = calculate_similarity('iPhone 15 Pro', 'iPhone 15 Pro 256GB')
    print(f"Similarity: {score}")  # Should be ~0.8+
    
    # Test with lower similarity
    score2 = calculate_similarity('iPhone 15', 'Samsung Galaxy S24')
    print(f"Similarity: {score2}")  # Should be <0.7
```

### Check Email Configuration
```python
# In Flask shell
app.config.get('MAIL_SERVER')
app.config.get('MAIL_PORT')
app.config.get('MAIL_USERNAME')
app.config.get('MAIL_USE_TLS')
```

### Monitor Notification Flow
```python
# Add logging to services/wishlist_service.py

import logging
logger = logging.getLogger(__name__)

@app.before_request
def setup_logging():
    if not app.debug:
        logger.setLevel(logging.INFO)

# In send_wishlist_notification():
logger.info(f"Sending notification to user {user.id} for item {item.id}")
logger.info(f"Email sent: {email_result}")
logger.info(f"In-app notification ID: {notification.id}")
```

---

## 🔍 Common Issues & Solutions

### Issue 1: "No such column: wishlist.is_active"
**Cause**: Migration didn't apply properly
```bash
flask db current  # Should show 119211f50d0a
flask db upgrade  # If not showing head
```

### Issue 2: Notifications Not Sending
**Checks**:
1. Verify Flask-Mail is configured:
   ```python
   from flask_mail import Mail
   mail = Mail(app)
   ```
2. Check email settings in `.env` or `config.py`
3. Verify `notify_via_email` is True on wishlist
4. Check logs for email errors

### Issue 3: No Matches Found
**Checks**:
1. Verify item name similarity >70%:
   ```python
   from services.wishlist_service import calculate_similarity
   score = calculate_similarity('wishlist item', 'new item')
   print(score)  # Should be >0.7
   ```
2. Verify wishlist is active (`is_active=True`)
3. Verify item is in correct format (not archived, etc.)

### Issue 4: Circular Import Error
**Cause**: Direct import of service outside app context
**Solution**:
```python
# ❌ Wrong
from services.wishlist_service import find_wishlist_matches

# ✅ Right
from app import app
with app.app_context():
    from services.wishlist_service import find_wishlist_matches
```

### Issue 5: 403 Forbidden on Remove/Pause
**Cause**: User doesn't own the wishlist
**Solution**:
1. Verify user ID matches wishlist owner
2. Check session/authentication isn't lost
3. Test with correct user account

---

## 📊 Performance Testing

### Load Test (100 Wishlists)
```python
import time
from app import app
from models import db, Wishlist, User

with app.app_context():
    user = User.query.first()
    
    # Add 100 wishlist items
    start = time.time()
    for i in range(100):
        w = Wishlist(
            user_id=user.id,
            item_name=f'Item {i}',
            search_type='item'
        )
        db.session.add(w)
    db.session.commit()
    elapsed = time.time() - start
    print(f"Added 100 items in {elapsed:.2f}s")
    
    # Paginated view
    start = time.time()
    wishlists = Wishlist.query.filter_by(user_id=user.id).paginate(page=1, per_page=20)
    elapsed = time.time() - start
    print(f"Paginated query in {elapsed:.4f}s")
```

### Matching Performance
```python
import time
from app import app
from models import Item, Wishlist
from services.wishlist_service import find_wishlist_matches

with app.app_context():
    item = Item.query.first()
    
    start = time.time()
    matches = find_wishlist_matches(item)
    elapsed = time.time() - start
    print(f"Found {len(matches)} matches in {elapsed:.4f}s")
```

---

## 📋 Pre-Deployment Checklist

- [ ] All 6 endpoints returning 200 OK
- [ ] Wishlist models created in database
- [ ] WishlistMatch records created on admin approval
- [ ] Notifications sent to email
- [ ] In-app notifications created
- [ ] Pagination working (20 items/page)
- [ ] Authorization checks working
- [ ] Duplicate detection working
- [ ] Pause/resume functionality working
- [ ] Category and item search both working
- [ ] Migration 119211f50d0a applied successfully
- [ ] No circular import errors
- [ ] Email configuration verified
- [ ] Logs show successful notifications

---

## 📝 Logging Configuration

Add to app.py:
```python
import logging

if not app.debug:
    wishlist_log = logging.getLogger('wishlist')
    wishlist_log.setLevel(logging.INFO)
    handler = logging.FileHandler('logs/wishlist.log')
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    wishlist_log.addHandler(handler)
```

Then in services/wishlist_service.py:
```python
import logging
logger = logging.getLogger('wishlist')

# Use throughout:
logger.info(f"Matching found for wishlist {wishlist_id}")
logger.error(f"Email send failed: {str(e)}")
```
