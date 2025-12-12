# Gamification System - Developer Reference

## Quick Code Examples

### Example 1: Award Points Manually (For Testing)

```python
from app import app, db
from models import User
from trading_points import award_points_for_upload, create_level_up_notification

with app.app_context():
    # Get user
    user = User.query.filter_by(username='testuser').first()
    
    # Award points for item upload
    level_up_info = award_points_for_upload(user, "Test Item")
    
    # If tier changed, create notification
    if level_up_info:
        create_level_up_notification(user, level_up_info)
        print(f"User promoted to {level_up_info['new_tier']} tier!")
    else:
        print(f"Points awarded. User now at {user.trading_points} points")
```

### Example 2: Check User Progress

```python
from app import app
from models import User
from trading_points import get_user_progress_info

with app.app_context():
    user = User.query.filter_by(username='testuser').first()
    
    progress = get_user_progress_info(user)
    print(f"""
    Level: {progress['current_level']}/30
    Tier: {progress['current_tier']}
    Points: {progress['current_points']}
    Progress to next level: {progress['progress_percentage']:.0f}%
    Points needed: {progress['next_level_points'] - progress['current_points']}
    """)
```

### Example 3: Get Tier Info

```python
from trading_points import get_level_tier, get_tier_info

# Get tier name for a level
tier = get_level_tier(15)  # Returns: 'Intermediate'

# Get complete tier information
tier_info = get_tier_info(15)
print(f"""
    Tier: {tier_info['name']}
    Icon: {tier_info['badge_icon']}
    Description: {tier_info['description']}
    Color: {tier_info['color']}
    Range: {tier_info['level_range']}
""")
```

### Example 4: Batch Award Points (For Backfilling Users)

```python
from app import app, db
from models import User
from trading_points import award_points_for_upload, calculate_level_from_points

with app.app_context():
    # Get all users
    users = User.query.all()
    
    for user in users:
        # Award 100 points to each user
        user.trading_points = 100
        
        # Recalculate level
        user.level = calculate_level_from_points(user.trading_points)
        
        # Update tier
        from trading_points import get_level_tier
        user.tier = get_level_tier(user.level)
        
        print(f"{user.username}: {user.trading_points} points, Level {user.level}, {user.tier}")
    
    db.session.commit()
    print("Backfill complete!")
```

### Example 5: Find Users Near Tier Boundaries

```python
from app import app, db
from models import User

with app.app_context():
    # Find users at 490-510 points (near level 6 boundary)
    users_near_boundary = User.query.filter(
        User.trading_points.between(490, 510)
    ).all()
    
    for user in users_near_boundary:
        print(f"{user.username}: {user.trading_points} points ({user.level})")
```

### Example 6: Check Points System Integrity

```python
from app import app, db
from models import User
from trading_points import calculate_level_from_points, get_level_tier

with app.app_context():
    # Get all users and verify their levels match their points
    users = User.query.all()
    
    issues = []
    for user in users:
        expected_level = calculate_level_from_points(user.trading_points)
        expected_tier = get_level_tier(expected_level)
        
        if user.level != expected_level:
            issues.append(f"{user.username}: Level mismatch ({user.level} vs {expected_level})")
        
        if user.tier != expected_tier:
            issues.append(f"{user.username}: Tier mismatch ({user.tier} vs {expected_tier})")
    
    if issues:
        for issue in issues:
            print(f"⚠️  {issue}")
    else:
        print("✅ All users' levels and tiers are correct!")
```

### Example 7: Admin API to Award Points

```python
from flask import jsonify, request
from app import app, db
from models import User
from trading_points import award_points_for_upload, create_level_up_notification
from flask_login import login_required

@app.route('/admin/api/award-points', methods=['POST'])
@login_required
def award_points_api():
    """Admin endpoint to manually award points"""
    data = request.json
    
    user_id = data.get('user_id')
    points = data.get('points', 10)
    reason = data.get('reason', 'Admin award')
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Award points
    old_points = user.trading_points
    user.trading_points += points
    
    # Update level
    from trading_points import calculate_level_from_points, get_level_tier
    user.level = calculate_level_from_points(user.trading_points)
    user.tier = get_level_tier(user.level)
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'username': user.username,
        'old_points': old_points,
        'new_points': user.trading_points,
        'level': user.level,
        'tier': user.tier
    })
```

---

## Database Query Examples

### Query 1: Get Users by Tier

```sql
SELECT username, level, tier, trading_points, credits
FROM user
WHERE tier = 'Expert'
ORDER BY trading_points DESC;
```

### Query 2: Count Users per Tier

```sql
SELECT tier, COUNT(*) as user_count, AVG(trading_points) as avg_points
FROM user
GROUP BY tier
ORDER BY CASE
    WHEN tier = 'Beginner' THEN 1
    WHEN tier = 'Novice' THEN 2
    WHEN tier = 'Intermediate' THEN 3
    WHEN tier = 'Advanced' THEN 4
    WHEN tier = 'Expert' THEN 5
END;
```

### Query 3: Users Not Yet Verified (No Points)

```sql
SELECT username, email, created_at, trading_points, level, tier
FROM user
WHERE trading_points = 0
ORDER BY created_at DESC;
```

### Query 4: Recent Level Ups

```sql
SELECT u.username, u.level, u.tier, u.trading_points, n.created_at
FROM user u
JOIN notification n ON u.id = n.user_id
WHERE n.notification_type = 'achievement'
ORDER BY n.created_at DESC
LIMIT 20;
```

### Query 5: Top Traders

```sql
SELECT username, level, tier, trading_points, credits, created_at
FROM user
ORDER BY trading_points DESC
LIMIT 10;
```

---

## Flask Shell Examples

```bash
# Enter Flask shell
flask shell

# Import what you need
>>> from app import db
>>> from models import User
>>> from trading_points import *

# Check a user
>>> user = User.query.filter_by(username='john').first()
>>> print(f"Points: {user.trading_points}, Level: {user.level}, Tier: {user.tier}")

# Award points
>>> level_up = award_points_for_upload(user, "Test Item")
>>> if level_up:
...     print(f"Promoted to {level_up['new_tier']}!")
... 
>>> db.session.commit()

# Check progress
>>> progress = get_user_progress_info(user)
>>> print(progress)

# Get tier info
>>> tier_info = get_tier_info(user.level)
>>> print(tier_info)

# Exit
>>> exit()
```

---

## Frontend Integration Examples

### Example 1: Display Tier Icon in Template

```html
{% from trading_points import get_tier_info %}

{% set tier_info = get_tier_info(current_user.level) %}

<div class="tier-display">
    <span class="tier-icon">{{ tier_info.badge_icon }}</span>
    <span class="tier-name">{{ tier_info.name }}</span>
    <span class="tier-level">Level {{ current_user.level }}</span>
</div>
```

### Example 2: Progress Bar Calculation

```python
# In your route
def calculate_progress_percentage(user):
    current_points = user.trading_points
    current_level = user.level
    
    if current_level >= 30:
        return 100  # Max level
    
    # Get thresholds
    from trading_points import LEVEL_THRESHOLDS
    
    current_threshold = LEVEL_THRESHOLDS.get(current_level, 0)
    next_threshold = LEVEL_THRESHOLDS.get(current_level + 1, current_points)
    
    if next_threshold == current_threshold:
        return 100
    
    progress = ((current_points - current_threshold) / 
                (next_threshold - current_threshold)) * 100
    
    return min(progress, 100)
```

### Example 3: Tier Badge Selector

```python
# In your template context
def get_tier_badge(user):
    tier = user.tier
    badges = {
        'Beginner': '🌱',
        'Novice': '⭐',
        'Intermediate': '💎',
        'Advanced': '👑',
        'Expert': '🏆'
    }
    return badges.get(tier, '🌱')
```

---

## Testing Examples

### Unit Test: Level Calculation

```python
import pytest
from trading_points import calculate_level_from_points, get_level_tier

def test_level_calculation():
    """Test level calculation from points"""
    test_cases = [
        (0, 1, 'Beginner'),
        (100, 2, 'Beginner'),
        (500, 6, 'Novice'),
        (1000, 11, 'Intermediate'),
        (1500, 16, 'Advanced'),
        (2000, 21, 'Expert'),
        (2900, 30, 'Expert'),
    ]
    
    for points, expected_level, expected_tier in test_cases:
        level = calculate_level_from_points(points)
        tier = get_level_tier(level)
        
        assert level == expected_level, f"Expected level {expected_level}, got {level}"
        assert tier == expected_tier, f"Expected tier {expected_tier}, got {tier}"

def test_points_award():
    """Test points awarding"""
    from app import app
    from models import User
    
    with app.app_context():
        # Create test user
        user = User(username='testuser', email='test@test.com')
        user.trading_points = 100
        
        # Award points
        from trading_points import award_points_for_upload
        award_points_for_upload(user, "Test Item")
        
        assert user.trading_points == 110
        assert user.level == 2
```

### Integration Test: Admin Approval Flow

```python
def test_admin_approval_awards_points(client, app):
    """Test that admin approval awards points"""
    with app.app_context():
        # Create test user and item
        user = create_test_user()
        item = create_test_item(user)
        
        # Admin approves item
        response = client.post(f'/admin/approve/{item.id}', 
                             data={'value': 100})
        
        assert response.status_code == 302  # Redirect after success
        
        # Verify points awarded
        db.session.refresh(user)
        assert user.trading_points == 10
        assert user.level >= 1
```

---

## Debugging Tips

### Enable Debug Logging

```python
import logging

logger = logging.getLogger('trading_points')
logger.setLevel(logging.DEBUG)

# Then check logs:
# logger.debug("Points awarded...")
# logger.info("Level up!")
# logger.error("Something went wrong!")
```

### Check Database State

```python
from app import app, db
from models import User

with app.app_context():
    # Raw SQL query
    result = db.session.execute("""
        SELECT username, level, tier, trading_points 
        FROM user 
        WHERE username = 'testuser'
    """)
    
    for row in result:
        print(row)
```

### Monitor Notifications

```python
from app import app, db
from models import Notification

with app.app_context():
    # Get recent notifications
    notifications = Notification.query.order_by(
        Notification.created_at.desc()
    ).limit(10).all()
    
    for notif in notifications:
        print(f"{notif.created_at}: {notif.message[:50]}...")
```

### Test Email Sending

```python
from app import mail
from flask_mail import Message

# Create test message
msg = Message(
    subject="Test Email",
    recipients=["test@example.com"],
    body="This is a test email"
)

# Send
try:
    mail.send(msg)
    print("✅ Email sent successfully!")
except Exception as e:
    print(f"❌ Email failed: {e}")
```

---

## Performance Considerations

### Database Indexes to Add

```sql
-- Speed up user lookups by tier
CREATE INDEX idx_user_tier ON user(tier);

-- Speed up user lookups by level
CREATE INDEX idx_user_level ON user(level);

-- Speed up notification queries
CREATE INDEX idx_notification_user_type ON notification(user_id, notification_type);
```

### Query Optimization

```python
# AVOID: N+1 queries
users = User.query.all()
for user in users:
    print(user.trading_points)  # Triggers separate query per user

# PREFERRED: Use eager loading
users = User.query.options(
    joinedload(User.items)
).all()
```

---

## Monitoring & Analytics

### Track Tier Distribution

```python
def get_tier_stats():
    from models import User
    from sqlalchemy import func
    
    stats = db.session.query(
        User.tier,
        func.count(User.id).label('count'),
        func.avg(User.trading_points).label('avg_points')
    ).group_by(User.tier).all()
    
    return {row[0]: {'count': row[1], 'avg_points': row[2]} for row in stats}
```

### Email Success Rate

```python
def get_email_stats():
    from models import Notification
    from sqlalchemy import func
    
    total = Notification.query.filter_by(
        notification_type='achievement'
    ).count()
    
    sent = Notification.query.filter_by(
        notification_type='achievement',
        is_email_sent=True
    ).count()
    
    success_rate = (sent / total * 100) if total > 0 else 0
    
    return {'total': total, 'sent': sent, 'success_rate': success_rate}
```

---

## Common Mistakes to Avoid

### ❌ Don't Forget to Commit

```python
# WRONG
user.trading_points += 10
# Data not saved!

# CORRECT
user.trading_points += 10
db.session.commit()  # Always commit!
```

### ❌ Don't Update Tier Without Level

```python
# WRONG
user.tier = 'Expert'  # Without checking level

# CORRECT
new_level = calculate_level_from_points(user.trading_points)
user.level = new_level
user.tier = get_level_tier(new_level)
```

### ❌ Don't Award Multiple Times

```python
# WRONG - Could double award
if order.status == 'Delivered':
    award_points_for_purchase(user, order_id)
# This runs every time function is called!

# CORRECT - Check old status
if order.status == 'Delivered' and old_status != 'Delivered':
    award_points_for_purchase(user, order_id)
```

### ❌ Don't Ignore Email Errors

```python
# WRONG
try:
    mail.send(msg)
except Exception as e:
    pass  # Silently fails!

# CORRECT
try:
    mail.send(msg)
except Exception as e:
    logger.error(f"Email failed: {e}")  # Log the error
    # Optionally retry or alert admin
```

---

This reference provides all the code examples, database queries, and debugging tools you need to work with the gamification system!
