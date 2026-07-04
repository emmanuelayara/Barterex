# Referral Rewards System Implementation

## Overview

The referral rewards system has been fully implemented to allow users to earn ₦100 naira credit bonuses when they refer friends to Barterex. The system tracks referrals and awards bonuses at three key points:

1. **Signup Bonus** - ₦100 awarded when referred friend creates an account
2. **Item Upload Bonus** - ₦100 awarded when referred friend uploads an item that gets approved by admin
3. **Purchase Bonus** - ₦100 awarded when referred friend makes their first purchase

## System Architecture

### Database Models (`models.py`)

#### User Model Additions
- `referral_code`: Unique code for each user (format: REF{id}{random_chars})
- `referral_count`: Counter of successful referrals
- `referral_bonus_earned`: Total credits earned from referrals
- `generate_referral_code()`: Method to create unique referral codes

#### New Referral Model
```python
class Referral(db.Model):
    id                        - Primary key
    referrer_id              - FK to User (who referred)
    referred_user_id         - FK to User (who was referred)
    referral_code_used       - The code entered during signup
    signup_bonus_earned      - Boolean flag for signup bonus
    item_upload_bonus_earned - Boolean flag for item upload bonus
    purchase_bonus_earned    - Boolean flag for purchase bonus
    created_at              - Timestamp of referral signup
    item_upload_bonus_date  - When item upload bonus was awarded
    purchase_bonus_date     - When purchase bonus was awarded
```

Relationships:
- `referrer`: Relationship to User (who made the referral)
- `referred_user`: Relationship to User (who was referred)

### Form Validation (`forms.py`)

#### RegisterForm Updates
- Added `referral_code` StringField (optional)
- Added `validate_referral_code()` method that:
  - Checks if referral code exists in User table
  - Raises ValidationError if code is invalid
  - Allows empty code (referral is optional)

### Helper Module (`referral_rewards.py`)

#### award_referral_bonus() Function
Awards credits to referrer when referred user completes actions.

**Parameters:**
- `referred_user_id` (int): ID of referred user
- `bonus_type` (str): 'signup', 'item_upload', or 'purchase'
- `amount` (int): Credits to award (default 100)

**Returns:**
```python
{
    'success': bool,           # Whether bonus was awarded
    'referrer_id': int,        # ID of referrer (if successful)
    'amount_awarded': int,     # Credits awarded
    'message': str            # Status message
}
```

**Logic:**
1. Queries Referral record for referred_user_id
2. Checks if bonus has already been awarded (prevents duplicates)
3. Updates referrer credits
4. Sets appropriate bonus flag (signup_bonus_earned, etc.)
5. Records date bonus was awarded
6. Creates CreditTransaction for audit trail
7. Creates Notification to inform referrer
8. Returns success/failure status

### Route Integration

#### Registration (`routes/auth.py`)
- Captures referral_code from form
- Creates User with credits=5000
- If referral_code provided:
  - Queries User by referral_code
  - Creates Referral record linking referrer to new user
  - Awards ₦100 signup bonus immediately
  - Increments referrer's referral_count
  - Creates notification for referrer

#### Item Approval (`routes/admin.py`)
- When admin approves item:
  - Calls `award_referral_bonus(item.user_id, 'item_upload', 100)`
  - Checks if user was referred
  - Awards ₦100 if applicable
  - Logs referral bonus result

#### Purchase Checkout (`routes/items.py`)
- When user completes purchase:
  - Calls `award_referral_bonus(current_user.id, 'purchase', 100)`
  - Checks if user was referred
  - Awards ₦100 if applicable
  - Logs referral bonus result

### UI Template (`templates/register.html`)

Added referral code input field:
- Full-width optional text input
- Placeholder: "Enter referral code (optional)"
- Hint: "Have a referral code? Enter it to earn bonus credits!"
- Error messages display if code is invalid
- Integrated with form validation

## User Flow

### For Referrer:
1. User shares their referral code (found on dashboard/profile)
2. Friend signs up with referral code
3. Referrer receives:
   - ₦100 immediately on friend signup
   - ₦100 when friend's uploaded item is approved
   - ₦100 when friend makes first purchase
   - Notifications for each bonus awarded
   - Total potential: ₦300 per successful referral

### For Referred User:
1. Receives referral code from friend
2. Enters code during registration
3. Creates account with 5000 credits (standard)
4. Can earn additional credits when:
   - Their friend gets signup bonus
   - Their item is approved
   - They make a purchase

## Database Records Created

### CreditTransaction
Each bonus award creates a transaction record:
- Type: `'referral_signup_bonus'`, `'referral_item_upload_bonus'`, or `'referral_purchase_bonus'`
- Amount: 100
- User: The referrer
- Timestamp: Automatically recorded

### Notification
Each bonus award creates a notification:
- Type: 'referral'
- Category: 'reward'
- Message: Describes the referral action and bonus amount
- User: The referrer

### Referral Record
Tracks the relationship and bonus status:
- Links referrer to referred user
- Records which code was used
- Tracks which bonuses have been earned
- Records when each bonus was awarded

## Safety Features

### Duplicate Prevention
- Bonus flags prevent same bonus being awarded multiple times
- Referral record is unique per referred user
- CreditTransaction creates audit trail

### Validation
- Referral code must exist in User table
- Can only award bonus if referral record exists
- Graceful handling of edge cases

### Error Handling
- Try-catch blocks in helper function
- Database rollback on error
- Returns detailed status messages
- All errors logged with context

## Testing Checklist

- [ ] User can sign up without referral code
- [ ] User can sign up with valid referral code
- [ ] Invalid referral code shows validation error
- [ ] Referrer receives notification on signup
- [ ] Referrer credits increase by 100
- [ ] Referral record is created
- [ ] Signup bonus can only be awarded once
- [ ] Item upload bonus is awarded when item approved
- [ ] Purchase bonus is awarded when user makes purchase
- [ ] Duplicate bonus prevention works
- [ ] CreditTransaction records are created
- [ ] All notifications display correctly

## Configuration

No additional configuration needed. The system:
- Uses existing database and ORM
- Integrates with existing User model
- Uses existing notification system
- Uses existing credit transaction system
- Uses existing authentication flow

## Performance Considerations

- Referral lookups use indexed foreign keys
- Bonus award function is idempotent (safe to call multiple times)
- CreditTransaction creation uses batch commits
- Notifications created asynchronously (non-blocking)

## Future Enhancements

Possible additions:
- Referral tier system (more bonuses for multiple referrals)
- Variable bonus amounts by user tier
- Referral expiration (code valid for X days)
- Referral leaderboard
- Maximum referral rewards per user
- Special promotions (double bonus events)

## Files Modified

1. `models.py` - Added Referral model, updated User model
2. `forms.py` - Updated RegisterForm with referral_code field
3. `routes/auth.py` - Updated register() to process referrals
4. `routes/admin.py` - Updated approve_item() to award bonuses
5. `routes/items.py` - Updated process_checkout() to award bonuses
6. `templates/register.html` - Added referral code input field

## New Files Created

1. `referral_rewards.py` - Helper module for award_referral_bonus()

## Deployment Notes

1. Run database migration to add Referral model table
2. No schema changes needed for User model (fields already exist from previous work)
3. Verify referral_code field exists in User table
4. Update any dashboards/profiles to display user's referral code
5. Test full flow: signup → item approval → purchase

## Support

For issues or questions:
- Check CreditTransaction table for payment history
- Check Referral table for referral records
- Check Notification table for user notifications
- Check logs for referral_rewards.py execution
