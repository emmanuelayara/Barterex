# Gamification System - Quick Reference

## Tier Badges & Icons
```
🌱 Beginner    (Level 1-5)
⭐ Novice      (Level 6-10)
💎 Intermediate (Level 11-15)
👑 Advanced    (Level 16-20)
🏆 Expert      (Level 21-30)
```

## Points System

### How Users Earn Points
| Action | Points | Trigger |
|--------|--------|---------|
| Item Approved | 10 pts | Admin approves user's uploaded item |
| Purchase Completed | 20 pts | Order marked as "Delivered" |
| Tier Promotion | 300 credits | Reaching new tier (automatic) |

### Level Progression
| Level | Points Needed | Tier |
|-------|---------------|------|
| 1 | 0 | Beginner |
| 2 | 100 | Beginner |
| 3 | 200 | Beginner |
| 4 | 300 | Beginner |
| 5 | 400 | Beginner |
| 6 | 500 | Novice |
| 7 | 600 | Novice |
| 8 | 700 | Novice |
| 9 | 800 | Novice |
| 10 | 900 | Novice |
| 11 | 1000 | Intermediate |
| 12 | 1100 | Intermediate |
| 13 | 1200 | Intermediate |
| 14 | 1300 | Intermediate |
| 15 | 1400 | Intermediate |
| 16 | 1500 | Advanced |
| 17 | 1600 | Advanced |
| 18 | 1700 | Advanced |
| 19 | 1800 | Advanced |
| 20 | 1900 | Advanced |
| 21 | 2000 | Expert |
| 22-30 | 2100-2900 | Expert |

## Code Integration Points

### Item Approval Flow
**File**: `routes/admin.py` - `approve_item()` endpoint (Line 368-427)
```python
# Award trading points for upload approval
level_up_info = award_points_for_upload(item.user, item.name)

# Create level up notification and send email if applicable
if level_up_info:
    create_level_up_notification(item.user, level_up_info)
```

### Order Completion Flow
**File**: `routes/admin.py` - `update_order_status()` endpoint (Line 647-683)
```python
# Award points when order is delivered
if order.status == "Delivered" and old_status != "Delivered":
    user = order.user
    level_up_info = award_points_for_purchase(user, order.order_number)
    
    if level_up_info:
        create_level_up_notification(user, level_up_info)
```

### Purchase Completion Flow
**File**: `routes/items.py` - `process_checkout()` endpoint (Line 360-385)
```python
# Award trading points for purchase (20 points per item)
level_up_info = award_points_for_purchase(current_user, f"item-{item.id}")
if level_up_info:
    level_up_notifications.append(level_up_info)
```

## Dashboard Display

### Location
**File**: `templates/dashboard.html` (Lines 1280-1365)

### Displayed Information
- Current level (large number display)
- Current tier name with emoji badge
- Total trading points
- Progress bar to next level
- Progress percentage
- Points needed to next level
- Tier structure card showing all 5 tiers
- Current tier highlighted with badge
- "How to Earn Rewards" section

## Notification System

### In-App Notifications
- **Type**: `achievement`
- **Category**: `status_update`
- **Priority**: `high`
- **Message Format**: Congratulations message with emoji, level, tier, bonus credits, and total points

### Email Notifications
- **Template**: `templates/emails/level_up_notification.html`
- **Subject**: 🎉 Level Up! You've Reached Level X
- **Content**: Tier info, bonus credits, tier progression overview, encouragement

## User Model Fields

### New Field
```python
tier = db.Column(db.String(20), default='Beginner')
```

### Existing Fields Used
```python
level = db.Column(db.Integer, default=1)  # User level (1-30)
trading_points = db.Column(db.Integer, default=0)  # Total points
credits = db.Column(db.Integer, default=0)  # User balance
```

## Frontend Components

### Tier Item Card (Rewards Structure)
- Shows tier badge icon
- Displays level range (e.g., "Level 1-5")
- Shows tier name
- Includes tier description
- Highlights current tier with orange border and "Current" badge
- Hover effect for interactivity

### Rewards Info Section
- 4 reward items with icons:
  - 📤 Upload Approval (10 pts)
  - 🛍️ Completed Purchase (20 pts)
  - ⬆️ Level Up Bonus (300 credits)
  - 📊 Points Required (threshold info)

## Key Variables

### In Dashboard Context
```python
tier_badge = '🌱'  # Icon for current tier
tier_info = {
    'name': 'Beginner',
    'description': '...',
    'badge_icon': '🌱',
    'color': '#10b981'
}
points_to_next = 50  # Points needed to reach next level
profile_completion = 85  # Percentage
max_level = 30
```

## Helper Functions

### From `trading_points.py`

#### `get_level_tier(level)`
Returns tier name for a given level

#### `calculate_level_from_points(points)`
Calculates level based on total points

#### `award_points_for_upload(user, item_name)`
Awards 10 points, returns level_up_info if tier changed

#### `award_points_for_purchase(user, order_number)`
Awards 20 points, returns level_up_info if tier changed

#### `create_level_up_notification(user, level_up_info)`
Creates in-app notification and sends email

#### `get_user_progress_info(user)`
Returns comprehensive progress info (level, tier, points, progress %)

## Database Migration

Before deploying, run:
```bash
flask db migrate -m "Add tier field to User model"
flask db upgrade
```

## Testing Commands

### Check user points and level
```python
from models import User
user = User.query.filter_by(username='testuser').first()
print(f"Points: {user.trading_points}, Level: {user.level}, Tier: {user.tier}")
```

### Award points manually
```python
from trading_points import award_points_for_upload, create_level_up_notification
user = User.query.filter_by(username='testuser').first()
level_up_info = award_points_for_upload(user, "Test Item")
if level_up_info:
    create_level_up_notification(user, level_up_info)
db.session.commit()
```

### Check tier assignment
```python
from trading_points import get_level_tier
tier = get_level_tier(15)  # Should return 'Intermediate'
```
