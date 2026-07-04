# Referral Bonus System - Profile Completion Requirement

## Overview

The referral bonus system has been updated to award bonuses **ONLY AFTER** the referred user completes their profile with all required information. Previously, bonuses were awarded immediately upon signup.

## What Changed

### Previous Behavior ❌
```
User A signs up with referral code from User B
                    ↓
User B immediately receives ₦100 bonus
                    ↓
User A may never complete profile
```

### New Behavior ✅
```
User A signs up with referral code from User B
                    ↓
User B gets notification: "User hasn't completed profile yet"
                    ↓
User A completes profile with ALL required information
                    ↓
User B receives ₦100 referral bonus + notification
```

## Required Fields for Profile Completion

A profile is considered "complete" when ALL of these fields are filled:
- ✅ **Email** (already required at registration)
- ✅ **Phone Number** (must be 10-15 digits)
- ✅ **Address** (delivery/contact address)
- ✅ **City** (location)
- ✅ **State** (Nigerian state)

**Optional fields:**
- Profile Picture

## Implementation Details

### Database Changes

#### User Table
- `profile_completed` (BOOLEAN) - Tracks if user has filled all required fields
- `profile_completed_at` (DATETIME) - When profile was completed

#### Referral Table  
- `signup_bonus_earned` - Changed: NOW means "profile completion bonus earned" (not signup bonus)
- `signup_bonus_earned_at` (DATETIME) - When the bonus was actually awarded

### Code Changes

#### [models.py](models.py)
- Added `profile_completed` and `profile_completed_at` fields to User model
- Updated Referral model documentation and added `signup_bonus_earned_at` field

#### [referral_utils.py](referral_utils.py) (NEW FILE)
Utility functions for referral bonus management:

```python
is_profile_complete(user)
```
- Checks if user has filled all required profile fields
- Returns: bool

```python
award_referral_signup_bonus(referred_user)
```
- Awards ₦100 to referrer when referred user completes profile
- Creates transaction and notification
- Returns: status dict with success/failure info

```python
check_and_award_pending_bonuses(user)
```
- Main function: checks if profile is complete and awards bonus if applicable
- Called after profile update

#### [routes/auth.py](routes/auth.py)
- Modified registration to NOT award bonus immediately
- Referrer notified: "User needs to complete profile to earn bonus"
- Referral record created with `signup_bonus_earned=False`

#### [routes/user.py](routes/user.py)
- Modified `profile_settings()` route:
  - Checks if profile becomes complete on update
  - Calls `check_and_award_pending_bonuses()` if profile was incomplete and is now complete
  - Updates `profile_completed` and `profile_completed_at` fields
  - Displays success message to referrer if bonus awarded

## User Flow

### For User Being Referred (User A)

1. **Registration**
   ```
   Click "Sign Up"
   Enter email, username, password
   Enter referral code (optional)
   Submit → Email verification required
   ```

2. **Profile Completion**
   ```
   After email verification, update profile:
   - Phone number (fill with: 08012345678)
   - Address (fill with: complete address)
   - City (fill with: Lagos)
   - State (select: Lagos)
   - Optional: Profile picture
   Click "Update Profile" → ✅ Complete!
   ```

3. **Notification**
   ```
   When profile completed:
   - Referrer (User B) receives notification
   - "🎉 [User A] completed their profile! You earned ₦100 referral bonus."
   ```

### For Referrer (User B)

1. **Share Referral Code**
   ```
   Dashboard → Share referral code: REFXX1234567
   ```

2. **Someone Signs Up**
   ```
   Notification: "👤 [User A] signed up using your referral code! 
   They need to complete their profile to earn the ₦100 bonus."
   ```

3. **When Profile is Completed**
   ```
   Notification: "🎉 [User A] completed their profile! 
   You earned ₦100 referral bonus."
   - ₦100 added to referrer's account
   - Transaction logged
   - Credit transaction created
   ```

## Testing the Feature

### Test Case 1: Full Referral Flow

```python
# 1. User A registers with referral code
POST /register
{
    'email': 'alice@example.com',
    'username': 'alice',
    'password': 'TestPass123!',
    'referral_code': 'REFXX1234567'  # User B's code
}

# 2. User A verifies email
GET /verify-email/<token>

# 3. User B check referral status (no bonus yet)
GET /dashboard
# Sees referral_count += 1 but credits unchanged

# 4. User A updates profile
POST /profile-settings
{
    'email': 'alice@example.com',
    'phone_number': '08012345678',
    'address': '123 Main Street, Lagos',
    'city': 'Lagos',
    'state': 'Lagos'
}

# 5. User B receives bonus
GET /dashboard
# credits increased by 100
# Notification received
```

### Test Case 2: Profile Not Complete (Bonus NOT Awarded)

```python
# User A registers with referral code
# User A verifies email
# User A updates profile but ONLY fills email (doesn't fill phone, address, city, state)
# Result: profile_completed = False
# Result: User B bonus NOT awarded
# Result: User B notification says "still needs to complete profile"
```

## Important Notes

### ⚠️ Migration Impact
If there are existing referral records with `signup_bonus_earned=True`:
- These represent bonuses that were already awarded (under old system)
- They will remain as-is (no automatic reversal)
- Future referrals will follow the new profile-completion-based system

### 🔄 Handling Incomplete Profiles
If a referred user doesn't complete their profile:
- No bonus is awarded
- Referral record remains with `signup_bonus_earned=False`
- If user later completes profile, bonus IS awarded retroactively

### 💡 Business Logic
This change encourages:
- Referred users to complete their profiles (requirement for using platform)
- Platform participation (more complete profiles = better user experience)
- Trust building (verified user info in database)

## Files Modified

1. **models.py** - Added profile completion fields
2. **referral_utils.py** - NEW: Utility functions for bonus management
3. **routes/auth.py** - Modified registration logic
4. **routes/user.py** - Modified profile update logic  
5. **migrate_referral_bonus.py** - Database migration script

## Verification Commands

```bash
# Run database migration
python migrate_referral_bonus.py

# Start Flask app
.\venv\Scripts\python.exe -m flask run --debug
```

## Transaction Types

The referral bonus still uses the same transaction type:
- `referral_signup_bonus` - But now awarded AFTER profile completion (not signup)

This appears in:
- Transaction history as "🎁 Referral Signup Bonus"
- When profile completion bonus is awarded to referrer

## Support

If users have questions about why they haven't received their bonus:
1. Check if referred user has completed profile (all fields filled)
2. Check if referral record exists in database
3. Check transaction history for `referral_signup_bonus` entries
4. If user completed profile but no bonus: verify bonus awarding logic ran
