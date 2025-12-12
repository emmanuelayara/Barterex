# Gamification System - Deployment Guide

## Pre-Deployment Checklist

- [ ] Read `GAMIFICATION_REWARDS_IMPLEMENTATION.md`
- [ ] Read `GAMIFICATION_QUICK_REFERENCE.md`
- [ ] Backup existing database
- [ ] Review changes in `models.py`, `routes/admin.py`, `routes/items.py`, `templates/dashboard.html`
- [ ] Test in development environment
- [ ] Verify email notifications work
- [ ] Test tier progression logic

## Step-by-Step Deployment

### Step 1: Create Database Migration
```bash
cd /path/to/barterex
flask db migrate -m "Add tier field to User model"
```

This creates a migration file in the `migrations/versions/` folder.

### Step 2: Review Migration
The migration file should contain:
```python
def upgrade():
    # Add tier column to user table
    op.add_column('user', sa.Column('tier', sa.String(length=20), nullable=True))
    # Set default value for existing users
    op.execute("UPDATE user SET tier = 'Beginner' WHERE tier IS NULL")

def downgrade():
    op.drop_column('user', 'tier')
```

### Step 3: Apply Migration
```bash
flask db upgrade
```

### Step 4: Verify Database Changes
```python
# In Python shell or test script
from app import db
from models import User

# Create/update a user to verify tier field exists
user = User.query.first()
print(f"User: {user.username}, Tier: {user.tier}")
```

**Expected Output**: 
```
User: testuser, Tier: Beginner
```

### Step 5: Test Points Award System

#### Test Upload Approval (10 points)
1. Navigate to admin panel
2. Create test item (upload to pending)
3. Go to "Approvals" page
4. Approve the item with value 500
5. Check user dashboard - should see:
   - Trading points increased by 10
   - "10 trading points earned" notification

#### Test Purchase Completion (20 points)
1. Create test order with items
2. Go to admin "Manage Orders"
3. Progress order: Pending → Shipped → Out for Delivery → Delivered
4. Check user dashboard - should see:
   - Trading points increased by 20
   - "20 trading points earned" notification
   - If level up occurred, bonus notification with 300 credits

#### Test Tier Progression
1. Manually set user trading_points to 400 (near level 5 boundary):
   ```python
   user = User.query.filter_by(username='testuser').first()
   user.trading_points = 400
   db.session.commit()
   ```

2. Award 10 more points via item approval
3. User should now have 410 points (Level 5) - no tier change yet
4. Set to 490 points, award 10 more = 500 points (Level 6 - Novice tier!)
5. Check for:
   - Level-up notification with tier badge
   - 300 bonus credits added
   - Email sent to user
   - Dashboard shows new tier "Novice"

### Step 6: Test Email Notifications

1. Ensure mail configuration is correct in `.env`:
   ```
   MAIL_SERVER=smtp.gmail.com
   MAIL_PORT=587
   MAIL_USE_TLS=True
   MAIL_USERNAME=your-email@gmail.com
   MAIL_PASSWORD=your-app-password
   MAIL_DEFAULT_SENDER=Barter Express,info.barterex@gmail.com
   ```

2. Reach a tier boundary to trigger level-up
3. Check email inbox for celebratory email with:
   - ✅ Subject line: "🎉 Level Up! You've Reached Level X"
   - ✅ Tier badge icon and description
   - ✅ Bonus credits amount (300)
   - ✅ Total trading points
   - ✅ Tier progression overview

### Step 7: Test Dashboard Display

1. Log in as user who has earned points
2. Navigate to Dashboard
3. Verify:
   - ✅ Tier Progression card displays all 5 tiers
   - ✅ Current tier is highlighted with orange border and "Current" badge
   - ✅ Tier badges show correct icons (🌱⭐💎👑🏆)
   - ✅ "How to Earn Rewards" section displays
   - ✅ Level display shows correct level and tier name
   - ✅ Points to next level calculation is accurate
   - ✅ Progress bar fills correctly

### Step 8: Test Responsive Design

Test dashboard on different screen sizes:
- [ ] Desktop (1200px+)
- [ ] Tablet (768px-1023px)
- [ ] Mobile (480px-767px)
- [ ] Small mobile (< 480px)

Verify:
- ✅ Tier grid responsively changes columns
- ✅ Text remains readable
- ✅ Cards don't overflow
- ✅ Spacing is appropriate

### Step 9: Verify Points System Integrity

Run this test script:
```python
from app import app, db
from models import User
from trading_points import (
    calculate_level_from_points,
    get_level_tier,
    award_points_for_upload,
    award_points_for_purchase
)

with app.app_context():
    # Test level calculation
    test_cases = [
        (0, 1, 'Beginner'),
        (100, 2, 'Beginner'),
        (500, 6, 'Novice'),
        (1500, 16, 'Advanced'),
        (2000, 21, 'Expert'),
        (2900, 30, 'Expert'),
    ]
    
    for points, expected_level, expected_tier in test_cases:
        level = calculate_level_from_points(points)
        tier = get_level_tier(level)
        assert level == expected_level, f"Level mismatch: {level} != {expected_level}"
        assert tier == expected_tier, f"Tier mismatch: {tier} != {expected_tier}"
        print(f"✓ {points} points → Level {level} ({tier})")
    
    print("\n✅ All point system tests passed!")
```

### Step 10: Monitor First Week

After deployment:
- [ ] Monitor error logs for any issues
- [ ] Check that users see tier progression correctly
- [ ] Verify email notifications are being sent
- [ ] Ensure no duplicate notifications
- [ ] Check database for any inconsistencies
- [ ] Monitor performance with new queries

## Rollback Plan

If issues occur:

### Quick Rollback
```bash
flask db downgrade
```

This removes the `tier` column but keeps all trading points data intact.

### Full Rollback
1. Restore database from backup
2. Revert code changes
3. Redeploy without gamification system

## Monitoring Queries

### Check Points Distribution
```sql
SELECT level, COUNT(*) as user_count 
FROM user 
GROUP BY level 
ORDER BY level;
```

### Check Tier Distribution
```sql
SELECT tier, COUNT(*) as user_count 
FROM user 
GROUP BY tier 
ORDER BY tier;
```

### Find Users Near Tier Boundaries
```sql
SELECT username, level, trading_points, tier
FROM user 
WHERE trading_points >= 490 AND trading_points <= 510
ORDER BY trading_points DESC;
```

### Check Email Delivery
```sql
SELECT user_id, message, created_at 
FROM notification 
WHERE notification_type = 'achievement' 
ORDER BY created_at DESC 
LIMIT 10;
```

## Common Issues & Solutions

### Issue: Tier field is NULL
**Solution**: Run migration and explicitly update:
```python
from models import User
User.query.update({User.tier: 'Beginner'})
db.session.commit()
```

### Issue: Email notifications not sending
**Solution**: 
1. Check MAIL_* configuration in `.env`
2. Verify MAIL_DEFAULT_SENDER format: "Name,email@domain.com"
3. Test with simple mail test script
4. Check app logs for email errors

### Issue: Points not being awarded
**Solution**:
1. Verify `trading_points.py` imports are correct
2. Check that `award_points_for_upload()` is called in `approve_item()`
3. Check that `award_points_for_purchase()` is called in `update_order_status()`
4. Verify database commit is called after award functions

### Issue: Level calculation incorrect
**Solution**:
1. Verify LEVEL_THRESHOLDS in `trading_points.py`
2. Test `calculate_level_from_points()` function manually
3. Check for duplicate level assignments

### Issue: Dashboard not showing tier structure
**Solution**:
1. Clear browser cache (Ctrl+Shift+Delete)
2. Check browser console for JavaScript errors
3. Verify dashboard.html changes were saved
4. Check that Jinja2 template renders correctly

## Performance Considerations

The gamification system adds:
- 1 new database column (tier)
- 2-3 additional database queries per trade completion
- 1 email send per tier promotion
- 1 notification record per tier promotion

**Expected Impact**: Negligible (< 1% performance impact)

## Rollout Strategy

### Phase 1: Internal Testing (Day 1)
- Test with admin accounts
- Verify all features work
- Check email delivery

### Phase 2: Beta Testing (Days 2-3)
- Invite 5-10 active users to beta
- Monitor for bugs
- Gather feedback

### Phase 3: Full Deployment (Day 4+)
- Deploy to all users
- Monitor error logs
- Support users with questions

## Post-Deployment Support

### Common User Questions

**Q: How do I earn points?**
A: Upload items and complete purchases. Each item approval gives 10 points, each completed purchase gives 20 points.

**Q: When do I get the bonus credits?**
A: When you reach a new tier! You'll receive a notification and email with details.

**Q: How many points to reach Expert?**
A: You need 2000+ points to reach level 21 (Expert tier).

**Q: Can I lose points?**
A: No, points only accumulate. You can't go backwards in level.

## Success Metrics

Track these metrics after deployment:
- Average points per user
- Users reaching each tier
- Engagement increase (more trades)
- Email open rate for level-up emails
- User satisfaction (positive feedback)

## Documentation Update

Update these docs after deployment:
- [ ] User guide with tier information
- [ ] FAQ with gamification questions
- [ ] Admin guide on approving items
- [ ] Help center with rewards info
