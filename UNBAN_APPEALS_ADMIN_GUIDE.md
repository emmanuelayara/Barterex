# Admin Ban Appeals Management System

## Overview
When users submit unban appeals, their messages are stored in the database and displayed in multiple admin locations for review and action.

---

## Where Admins Can Review Appeals

### 1. **Pending Appeals Dashboard** ⭐ (Primary Location)
**URL:** `/admin/pending_appeals`

- **Purpose:** Centralized view of all pending unban appeals waiting for admin review
- **Features:**
  - List of all suspended users with pending appeals
  - User profile picture and contact info
  - Ban date and ban reason
  - Appeal submission date
  - Full appeal message with character count (0-2000)
  - Quick action buttons (Approve or Reject)

**How to Access:**
1. Log in as admin
2. Navigate to Admin Dashboard
3. Look for "Pending Appeals" link in the navigation
4. Or visit: `/admin/pending_appeals`

**Actions Available:**
- ✅ **Approve Appeal & Unban** - Immediately unban the user and send them an "account restored" email
- ❌ **Reject Appeal** - Clear the appeal message and keep user banned (they can appeal again in 30 days)
- 👤 **View Full Profile** - See complete user details and account history

---

### 2. **User Detail Page** (Secondary Location)
**URL:** `/admin/view_user/<user_id>`

- **Purpose:** Individual user profile page where admins can see appeals tied to specific users
- **Features:**
  - Ban information section (when user is banned)
  - Appeal status indicator
  - Full appeal message display
  - Admin action buttons

**When It Appears:**
- Only displays if user is currently banned (`is_banned = True`)
- Shows appeal information if appeal exists

**How to Find It:**
1. Go to User Management (`/admin/users`)
2. Click on any banned user's name
3. Scroll to the "Account Suspended" section at the bottom
4. View the appeal details and take action

---

## Database Storage

Appeal messages are stored in the **User model** in these fields:

| Field | Type | Purpose |
|-------|------|---------|
| `ban_date` | DateTime | When account was banned |
| `unban_request_date` | DateTime | When appeal was submitted |
| `appeal_message` | Text | User's appeal explanation (20-2000 characters) |
| `is_banned` | Boolean | Whether account is currently suspended |
| `ban_reason` | String | Reason for the ban |

---

## Complete Appeal Workflow

### For Users:
1. User's account gets banned by admin
2. User receives ban notification email with appeal link
3. User visits banned page and fills out appeal form
4. App validates appeal (20-2000 characters)
5. Appeal is stored in database
6. User sees "Appeal Submitted" status

### For Admins:
1. **Admin receives notification** (optional - can be configured)
2. **Admin reviews appeal** in one of two places:
   - Dedicated `/admin/pending_appeals` page (recommended)
   - User's detail page (`/admin/view_user/<id>`)
3. **Admin takes action:**
   - **Approve:** Unban user immediately, send "account restored" email
   - **Reject:** Clear appeal, keep user banned, can reappeal in 30 days

---

## Key Information Displayed to Admins

### On Pending Appeals Page:
```
User: john_doe
Email: john@example.com
Profile Picture: [Displayed]

Ban Details:
- Banned on: January 2, 2026 at 3:45 PM (5 days ago)
- Reason: Fraudulent trading activity

Appeal Details:
- Submitted on: January 5, 2026 at 2:15 PM (2 days ago)
- Status: Awaiting Admin Review

Appeal Message:
"I apologize for my previous behavior. I have learned from my mistakes
and am committed to following all community guidelines. I will be more
careful with trade descriptions and pricing. Please give me another chance."

Character count: 187/2000
```

---

## Recommended Admin Workflow

### Quick Review Process:
1. **Go to Pending Appeals** - `/admin/pending_appeals`
2. **Read each appeal** - Evaluate if it's genuine or dismissive
3. **Make decision:**
   - **Genuine appeal?** → Click "Approve Appeal & Unban"
   - **Dismissive appeal?** → Click "Reject Appeal"
   - **Unsure?** → Click "View Full Profile" for more context
4. **Action is logged** - Audit trail shows admin ID and timestamp

---

## Email Notifications

### When Admin Approves Appeal:
- **User receives:** Account restoration email
- **Subject:** "Your account has been restored"
- **Content:** Details about account being active again

### When Admin Rejects Appeal:
- **User receives:** No automatic email (can send custom message if needed)
- **User can:** Resubmit appeal after 30 days

---

## Appeal Rejection Rules (Future Enhancement)

Admins can currently:
- ✅ Approve appeals and immediately unban users
- ✅ Reject appeals and clear the message
- ⏳ (Future) Add custom rejection reasons
- ⏳ (Future) Set appeal cooldown periods
- ⏳ (Future) Send custom messages with rejection

---

## Audit & Logging

All admin actions are logged:
```
2026-01-06 14:23:45 - User unbanned - User ID: 42, Username: john_doe, Admin ID: 1
2026-01-06 14:24:12 - Unban appeal rejected - User ID: 43, Username: jane_smith, Admin ID: 1
```

Location: Application logs (`logs/` directory)

---

## Troubleshooting

### "No Pending Appeals" but user submitted one?
- Check user's `is_banned` status - appeal only shows if `is_banned = True`
- Check `appeal_message` is not empty or NULL
- Check `unban_request_date` is set

### Appeals not visible in user detail page?
- Verify user's `is_banned = True`
- Refresh page (cache may need to clear)
- Check browser console for JavaScript errors

### Can't find Pending Appeals link?
- Verify you're logged in as admin
- Try direct URL: `/admin/pending_appeals`
- Check admin permissions in database

---

## Summary

**Users** submit appeals via the banned page form → **Admins** review in Pending Appeals dashboard → **Admins** approve or reject → **System** unbans user or keeps them suspended.

The appeal message is the user's explanation for why they should be unbanned, allowing admins to make informed decisions about account reinstatement.
