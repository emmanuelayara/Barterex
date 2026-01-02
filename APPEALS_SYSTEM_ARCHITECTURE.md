# Appeal System Architecture & Data Flow

## 📊 System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      BARTEREX UNBAN APPEAL SYSTEM                │
└─────────────────────────────────────────────────────────────────┘

                        ┌──────────────┐
                        │  User Banned │
                        │   by Admin   │
                        └──────┬───────┘
                               │
                    ┌──────────┴──────────┐
                    │                     │
            ┌───────▼────────┐   ┌────────▼──────────┐
            │  Ban Recorded  │   │ Notification     │
            │  in Database   │   │ Email Sent       │
            │                │   │ with Appeal Link │
            └───────┬────────┘   └────────┬──────────┘
                    │                     │
                    │         ┌───────────┘
                    │         │
                    │   ┌─────▼──────────┐
                    │   │ User Visits   │
                    │   │ /auth/banned  │
                    │   └─────┬──────────┘
                    │         │
                    │   ┌─────▼──────────────────┐
                    │   │ User Fills Appeal Form│
                    │   │ 20-2000 Characters    │
                    │   └─────┬──────────────────┘
                    │         │
        ┌───────────┴─────────┴──────────┐
        │                                │
        ▼                                │
    ┌──────────────────┐                │
    │  User Database   │                │
    │  ┌────────────┐  │   Validates   │
    │  │ ban_date   │  │◄──────────────┘
    │  │ ban_reason │  │
    │  │ is_banned  │  │
    │  │ unban_req  │  │
    │  │   _date    │  │
    │  │  appeal_   │  │
    │  │  message   │  │
    │  └────────────┘  │
    └──────┬───────────┘
           │
        ┌──┴──┐
        │     │
        │  ✅ Submitted
        │     │
   ┌────▼─────────────────────────────────┐
   │   Admin Dashboard Options            │
   ├─────────────────────────────────────┤
   │ 1. /admin/pending_appeals            │
   │    (Dedicated Appeals Dashboard)     │
   │    ├─ Shows all pending appeals      │
   │    ├─ User profile picture           │
   │    ├─ Full appeal message            │
   │    ├─ Character count                │
   │    └─ Action buttons                 │
   │                                      │
   │ 2. /admin/view_user/<id>             │
   │    (Individual User Profile)         │
   │    ├─ Ban information section        │
   │    ├─ Appeal status indicator        │
   │    ├─ Full appeal message            │
   │    └─ Action buttons                 │
   └────┬──────────────────────────────────┘
        │
        │ Admin Reviews Appeal
        │ Reads user's message
        │
   ┌────┴────────────────────┐
   │                          │
   ▼                          ▼
┌──────────────┐     ┌─────────────────┐
│   Approve    │     │     Reject      │
│   Appeal     │     │     Appeal      │
└──────┬───────┘     └────────┬────────┘
       │                      │
   ┌───▼───────────┐      ┌───▼──────────┐
   │ User Unbanned │      │ User Remains │
   │ is_banned=F   │      │ is_banned=T  │
   │ Email Sent    │      │ Appeal Clear │
   │ "Restored"    │      │ No Email     │
   └───────────────┘      └──────────────┘
       │                        │
       │                        │ Can reappeal
       │                        │ after 30 days
       │                        │
       └────────┬───────────────┘
                │
          ┌─────▼─────┐
          │ Audit Log │
          │ Recorded  │
          └───────────┘
```

---

## 🔄 Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER APPEAL SUBMISSION FLOW                  │
└─────────────────────────────────────────────────────────────────┘

                        START
                          │
                    ┌─────▼─────┐
                    │ User Visits│
                    │ /banned    │
                    └─────┬─────┘
                          │
              ┌───────────▼───────────┐
              │ Sees Appeal Form      │
              │ • Character counter   │
              │ • Min 20 chars        │
              │ • Max 2000 chars      │
              │ • Guidelines          │
              └───────────┬───────────┘
                          │
              ┌───────────▼────────────┐
              │ User Types Message     │
              │ Counter Updates Live   │
              │ Border Color Changes   │
              │ Green: 20+ chars ✓     │
              │ Yellow: <20 chars ⚠️   │
              └───────────┬────────────┘
                          │
              ┌───────────▼──────────────┐
              │ User Clicks Submit       │
              └───────────┬──────────────┘
                          │
         ┌────────────────▼─────────────────┐
         │  Validation Check                │
         │  ┌─────────────────────────────┐ │
         │  │ Message length < 20?        │ │
         │  │ ✗ FAIL → Show error         │ │
         │  └─────────────────────────────┘ │
         │  ┌─────────────────────────────┐ │
         │  │ Message length > 2000?      │ │
         │  │ ✗ FAIL → Show error         │ │
         │  └─────────────────────────────┘ │
         │  ┌─────────────────────────────┐ │
         │  │ All checks pass?            │ │
         │  │ ✓ PASS → Continue           │ │
         │  └─────────────────────────────┘ │
         └────────────┬──────────────────────┘
                      │
        ┌─────────────▼──────────────┐
        │ Store in Database          │
        │ SET User:                  │
        │ • appeal_message = "..."   │
        │ • unban_request_date = NOW │
        │ • unban_requested = TRUE   │
        └─────────────┬──────────────┘
                      │
        ┌─────────────▼──────────────┐
        │ Show Success Message       │
        │ "Appeal Submitted"         │
        │ "Expected: 3-5 days"       │
        └─────────────┬──────────────┘
                      │
        ┌─────────────▼──────────────┐
        │ Display Status Section     │
        │ • Show appeal message      │
        │ • Show submission date     │
        │ • Show timeline            │
        └─────────────┬──────────────┘
                      │
                    END

┌─────────────────────────────────────────────────────────────────┐
│                    ADMIN REVIEW FLOW                            │
└─────────────────────────────────────────────────────────────────┘

                        START
                          │
            ┌─────────────▼───────────┐
            │ Admin Logs In           │
            │ Sees Admin Panel        │
            │ Clicks "Unban Appeals"  │
            │ OR /admin/pending_appeals
            └─────────────┬───────────┘
                          │
            ┌─────────────▼──────────────┐
            │ Loads Pending Appeals Page │
            │ Query DB for:              │
            │ • is_banned = TRUE         │
            │ • appeal_message != NULL   │
            │ • unban_request_date set   │
            └─────────────┬──────────────┘
                          │
            ┌─────────────▼─────────────────┐
            │ Displays Appeal Cards         │
            │ For Each Appeal Shows:        │
            │ • User info & profile pic     │
            │ • Ban date & reason           │
            │ • Appeal submission date      │
            │ • Full appeal message         │
            │ • Character count             │
            │ • Action buttons              │
            └─────────────┬─────────────────┘
                          │
            ┌─────────────▼──────────────┐
            │ Admin Reviews Appeal       │
            │ Reads message carefully    │
            │ Evaluates request          │
            │ Checks user history        │
            │ Makes decision             │
            └─────────────┬──────────────┘
                          │
         ┌────────────────┴──────────────┐
         │                               │
         ▼                               ▼
    ┌─────────────┐          ┌────────────────┐
    │   Approve   │          │     Reject     │
    │   Appeal    │          │     Appeal     │
    └──────┬──────┘          └────────┬───────┘
           │                         │
    ┌──────▼──────────────┐  ┌───────▼────────────┐
    │ POST to             │  │ POST to            │
    │ /admin/unban_user   │  │ /admin/reject_un   │
    │                     │  │ ban_appeal         │
    │ Updates User:       │  │                    │
    │ • is_banned = FALSE │  │ Updates User:      │
    │ • ban_reason = NULL │  │ • appeal_msg = "" │
    │ • unban_req = FALSE │  │ • unban_req = F   │
    └──────┬──────────────┘  └───────┬────────────┘
           │                         │
    ┌──────▼──────────────┐  ┌───────▼────────────┐
    │ Send Email          │  │ No email sent      │
    │ "Account Restored"  │  │ User stays banned  │
    │                     │  │ Can reappeal later │
    └──────┬──────────────┘  └───────┬────────────┘
           │                         │
    ┌──────▼──────────────┐  ┌───────▼────────────┐
    │ Log to Audit Trail  │  │ Log to Audit Trail │
    │ "User unbanned"     │  │ "Appeal rejected"  │
    │ Admin ID recorded   │  │ Admin ID recorded  │
    │ Timestamp recorded  │  │ Timestamp recorded │
    └──────┬──────────────┘  └───────┬────────────┘
           │                         │
           └─────────┬───────────────┘
                     │
                  REDIRECT
                     │
              Admin sees
             success message
                     │
                    END
```

---

## 📍 Data Storage Map

```
┌─────────────────────────────────────────────────────────────────┐
│                   USER DATABASE TABLE                           │
└─────────────────────────────────────────────────────────────────┘

┌─ Existing Columns ──────────────────────────────────────────────┐
│  id                              (PK)                           │
│  username                        (String)                       │
│  email                           (String)                       │
│  password_hash                   (String)                       │
│  is_admin                        (Boolean)                      │
│  credits                         (Float)                        │
│  is_banned                       (Boolean)                      │
│  ban_reason                      (String)                       │
│  ...other columns...                                            │
└─────────────────────────────────────────────────────────────────┘

┌─ NEW: Ban Appeal Columns ───────────────────────────────────────┐
│                                                                 │
│  ban_date              (DateTime)  ← When user was banned       │
│  ├─ Set by:  admin.ban_user()                                  │
│  ├─ Format:  2026-01-02 15:45:30                               │
│  └─ Used for: Calculate "days since ban"                       │
│                                                                 │
│  unban_request_date    (DateTime)  ← When appeal submitted     │
│  ├─ Set by:  auth.request_unban()                              │
│  ├─ Format:  2026-01-05 14:23:45                               │
│  └─ Used for: Show "time since appeal" to admin                │
│                                                                 │
│  appeal_message        (Text)      ← User's appeal text        │
│  ├─ Set by:  auth.request_unban()                              │
│  ├─ Format:  "I apologize for..."  (20-2000 chars)            │
│  ├─ Shown to: Admin in dashboard                               │
│  └─ Cleared: When appeal rejected                              │
│                                                                 │
│  unban_requested       (Boolean)   ← Appeal submitted flag     │
│  ├─ Set by:  auth.request_unban()                              │
│  ├─ Value:   TRUE when appeal submitted                        │
│  └─ Cleared: When appeal approved/rejected                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

Example Data Row:
┌──────────────────────────────────────────────────────────────┐
│ id: 42                                                       │
│ username: john_doe                                           │
│ email: john@example.com                                      │
│ is_banned: TRUE                                              │
│ ban_reason: "Fraudulent trading"                             │
│ ban_date: 2026-01-02 15:45:30  ← NEW                         │
│ unban_request_date: 2026-01-05 14:23:45  ← NEW              │
│ appeal_message: "I apologize..."  ← NEW                      │
│ unban_requested: TRUE  ← NEW                                 │
│ ...other fields...                                           │
└──────────────────────────────────────────────────────────────┘
```

---

## 🔗 Route/URL Mapping

```
┌─────────────────────────────────────────────────────────────────┐
│                     ADMIN ROUTES FOR APPEALS                    │
└─────────────────────────────────────────────────────────────────┘

Route 1: View All Pending Appeals
  URL:      /admin/pending_appeals
  Method:   GET
  Function: admin.pending_appeals()
  Purpose:  Show dashboard of all pending appeals
  Query:    WHERE is_banned=TRUE AND appeal_message IS NOT NULL
  Template: pending_appeals.html
  ├─ Shows: List of all banned users with appeals
  ├─ User info, profile picture, ban/appeal dates
  ├─ Full appeal message with character count
  └─ Approve/Reject/View Profile buttons

Route 2: Approve Unban Appeal
  URL:      /admin/unban_user/<user_id>
  Method:   POST
  Function: admin.unban_user(user_id)
  Purpose:  Unban user and clear appeal
  Updates:  is_banned = FALSE, unban_requested = FALSE
  Email:    Sends "account restored" notification
  Log:      Records action in audit trail
  Redirect: /admin/admin_banned_users

Route 3: Reject Unban Appeal
  URL:      /admin/reject_unban_appeal/<user_id>
  Method:   POST
  Function: admin.reject_unban_appeal(user_id)
  Purpose:  Reject appeal and keep user banned
  Updates:  appeal_message = NULL, unban_request_date = NULL
  Email:    No automatic email (optional custom message)
  Log:      Records action in audit trail
  Redirect: /admin/view_user/<user_id>

Route 4: View User with Appeal Section
  URL:      /admin/view_user/<user_id>
  Method:   GET
  Function: admin.view_user(user_id)
  Purpose:  Show full user profile + appeal section if banned
  Template: view_user.html (enhanced)
  ├─ If is_banned=TRUE: Shows ban & appeal section
  ├─ Ban info: date, reason, days since ban
  ├─ Appeal info: date, status, message
  └─ Action buttons: Approve/Reject/View profile

Nav Link: Sidebar Link
  Location: Admin Panel sidebar
  Text:     "Unban Appeals" with "Pending" badge
  Icon:     chat-left-quote icon
  Link:     /admin/pending_appeals
  Badge:    Shows "Pending" indicator
```

---

## 🔐 Security Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    SECURITY & VALIDATION FLOW                   │
└─────────────────────────────────────────────────────────────────┘

USER SIDE:
  1. Form Submission
     ├─ CSRF token required
     ├─ Message length validated (20-2000)
     ├─ Whitespace trimmed
     └─ Special chars preserved (user quote)

  2. Database Storage
     ├─ Text sanitized (no code injection)
     ├─ Timestamp auto-set (utcnow())
     ├─ User ID verified from session
     └─ Transaction completed

ADMIN SIDE:
  1. Route Access
     ├─ Admin login required
     ├─ Session check enforced
     ├─ User ID validated
     └─ POST CSRF token required

  2. Database Update
     ├─ User existence verified (404 if not found)
     ├─ Ban status confirmed
     ├─ Transaction committed
     └─ Error logging on failure

AUDIT:
  1. Action Logging
     ├─ Admin ID recorded
     ├─ Timestamp recorded
     ├─ Action type logged
     └─ User ID logged

  2. Verification
     ├─ Can be searched in audit log
     ├─ Shows who approved/rejected
     ├─ Shows when action taken
     └─ Shows which user affected
```

---

## 📈 System State Diagram

```
User Account States:
┌────────────┐
│  ACTIVE    │  User can trade, access platform
│  is_banned │  = FALSE
└─────┬──────┘
      │ Admin bans user
      ▼
┌──────────────────┐
│  BANNED          │  User cannot access
│  is_banned=TRUE  │  No appeal submitted yet
│  appeal_msg=NULL │
└─────┬────────────┘
      │ User submits appeal
      ▼
┌─────────────────────┐
│  BANNED w/ APPEAL   │  User banned but appealing
│  is_banned=TRUE     │  Admin reviewing
│  appeal_msg!=NULL   │  unban_request_date set
└────┬──────────┬─────┘
     │          │
     │ Approve  │ Reject
     ▼          ▼
┌────────────┐ ┌─────────────────┐
│  ACTIVE    │ │  BANNED         │
│  (restored)│ │  (appeal cleared)
└────────────┘ └─────────────────┘
               │ Can reappeal
               │ after 30 days
               ▼
          [Return to BANNED
           with new appeal]
```

---

## 🎯 Summary

The appeal system works through a simple but effective flow:

1. **User** → Gets banned, submits appeal message (20-2000 chars)
2. **Database** → Stores ban_date, appeal_message, unban_request_date
3. **Admin** → Views appeals in dashboard or user profile
4. **Admin** → Approves (unbans) or Rejects (keeps banned)
5. **System** → Updates database, sends email, logs action
6. **User** → Notified of decision (if approved)

Two admin locations to review:
- Primary: `/admin/pending_appeals` (dedicated dashboard)
- Secondary: `/admin/view_user/<id>` (user profile with appeal section)

Everything is logged, audited, and secure! ✅
