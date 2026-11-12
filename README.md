# Barterex
Trade by Barter

## Saving and acquiring items

Favorites is the user-facing saved-items list; saving does not hold an item.
Users acquire items through individual funded reservations, verification,
settlement, and fulfillment, not a cart or combined checkout. Legacy cart and
checkout URLs redirect to Favorites or the relevant item without purchasing
or deleting historical cart records. Cart notification controls are retired.

## Manual item verification

When requesting manual review during upload, select a verification station in
your profile state. If none are available, update your profile or contact support.
Track pending items under **My Manual Verifications**, save a custody choice and
consent, and bring the item to the selected station. The station can be changed
until staff record a physical review. Existing pending items without a station
must select one before staff can verify them. Referenced stations cannot be
edited or deleted; create a new station if details change. A failed review stays
on the manual page; contact the team for next steps. After a successful review
the item moves to **My Valuations** for its existing video activation process.
Physical review itself grants no credits.

Deployments must back up the database, stop web and worker traffic, and run
`flask db upgrade` before starting the new code. Migration
`manual_station_20261112` adds a nullable station reference without assigning
stations to existing items.

## Trading-level rewards

Approved uploads earn 10 trading points and purchases earn 20. Level-ups
continue to award 300 BXC. Entering Novice (level 6), Intermediate (level 11),
Advanced (level 16), or Expert (level 21) additionally awards 1,000 BXC,
recorded separately in the credit ledger. A normal tier-entry level-up therefore
awards 1,300 BXC total. Starting in Beginner does not award a tier bonus;
levels within the same tier do not repeat it. Bonuses apply to future tier
advances, not tiers already reached. No database migration is needed.

## Referral rewards

Referrers earn 500 BXC for each referred user's profile completion, first
approved item upload, and first purchase: up to 1,500 BXC per referral.
Each milestone pays only once. The shared amount is
`REFERRAL_MILESTONE_BONUS` in `referral_rewards.py`. Newly earned milestones,
including pending milestones on existing referrals, use this amount;
previously paid rewards and historical transactions remain unchanged.
All rewards remain pending until the referred account has a staff-verified,
unique identity, verified email and a positive-value, non-cancelled settled
reservation purchase. Profile completion and approved uploads alone no longer
grant spendable BXC. Settlement and staff identity review release eligible
pending rewards. Approval qualification is retained even while payout is pending.

## Item camera quality and light

Upload/edit photos use only the in-app camera, not a file/gallery picker.
Photos request a 4096x3072 preview; videos request up to 4K/30fps, with lower-resolution/device
defaults when unsupported. Native still capture requests the maximum photo
dimensions advertised by the camera. Native JPEGs up to the server's 5 MiB JPEG limit are not re-encoded
in the browser; other photos use high-quality JPEG encoding with a 6144-pixel
long-edge limit and a 5 MiB upload budget. Saved item images retain up to 6144 pixels at quality 95.
Smaller images are never enlarged. This
affects new uploads, edits and reconfirmation photos, not existing stored images.
Storage and upload times may increase. Video encoding requests 20 Mbps for
above-1080p streams or 10 Mbps otherwise, keeping the existing duration/size limits.

Both cameras offer tap-to-focus and an accessible centre **Focus** button only
when the browser advertises focus modes and points-of-interest constraints.
Tap coordinates account for the cropped fullscreen preview. A marker indicates
the requested point, not confirmation of sharp focus. Unsupported browsers retain
camera defaults. Capture/start waits for advancing, unmuted live frames and an
800 ms settling period at startup and after focus/light changes; stalled frames
disable capture. This does not measure optical focus lock or guarantee sharpness,
because browsers do not reliably expose that state. Close/cancel clears readiness
timers and pending focus UI. More detail increases storage and processing costs.

The **Flash off/on** control appears in both fullscreen cameras only when the
browser exposes a hardware torch. It is a continuous light, not a synchronized
native-camera flash. Closing/cancelling the camera stops its tracks and releases
the light. Unsupported devices (including many iPhone browsers) need external
lighting; there is no simulated screen-flash fallback. Native camera HDR,
multi-frame processing and lens selection may not be exposed to a website, so
matching the device's camera app cannot be guaranteed.

## Security deployment

The security hardening release requires deployment work before serving traffic:

1. Back up the database and identity-document directory; pause web and worker traffic.
2. Set separate, cryptographically random `SECRET_KEY` and `IDENTITY_HASH_KEY`
   environment values (at least 32 characters each). Startup fails if missing or
   invalid. Generate each using `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
   Keep `IDENTITY_HASH_KEY` stable across session-key rotations; it deduplicates
   staff-verified NINs without storing another plaintext identifier.
   Rotate an exposed/default `SECRET_KEY` to invalidate existing user/admin
   sessions and signed links. Never put real keys in source control.
3. Run `flask db upgrade` to apply `harden_security_20261110` and `email_2fa_20261110`. These add revocable
   user authentication tokens, unique payment-to-credit ledger links, a unique
   verified-identity hash and pending approval qualification. Previously paid
   rewards/credits are not rewritten. Existing unsupported 2FA flags are cleared
   by the hardening migration; users can now enroll using the verified email flow.
   The email migration adds persistent verification challenges and abuse budgets.
4. Configure the reverse proxy/CDN to deny `/static/uploads/verification/` and
   purge any cached identity-document URLs. Flask also denies this path, but
   Flask cannot protect files served directly by a proxy or revoke downloaded copies.
   Run `flask secure-identity-documents` to relocate registered documents to
   `instance/identity_documents`, outside the public tree. Reconcile any missing,
   duplicate or unregistered legacy files before reopening traffic. Protect private
   storage/backups with deployment filesystem permissions and encryption.
5. Grant the new **Verify identity** permission only to appropriate staff. They
   must download and inspect a customer's private document and confirm the NIN
   through the user-detail screen. Uploading an ID does not verify its owner;
   item-intake `identity_confirmed` checks identify an item, not a person.
6. Restart all web/worker processes. Check payment verification/replay, profile
   email confirmation, password recovery, appeals and staff document access.

### Email two-step verification

Email codes are **optional for users and mandatory for every administrator**,
including super admins. Existing administrator sessions must sign in again.
Configure working `MAIL_SERVER`, `MAIL_PORT`, TLS/SSL, `MAIL_USERNAME`,
`MAIL_PASSWORD` and `MAIL_DEFAULT_SENDER` before deployment. Keep `MAIL_DEBUG`
and `MAIL_SUPPRESS_SEND` off in production; verify actual delivery to staff inboxes.
Code delivery is synchronous and failures do not grant access.

Users enable it at Settings > Password > Email two-step verification (or
`/account/security`). Enabling/disabling requires the current password and an
email code, then revokes all old user sessions. Codes last five minutes, are
browser-bound and single-use; only keyed hashes are stored. Resends wait 60
seconds; five attempts and five emails per account are allowed in a 15-minute
window, including across browsers and restarted sign-ins. Resends preserve the
attempt budget and invalidate earlier codes.
Changing an enrolled user's recovery email requires disabling verification with
the current inbox first; after confirming the new address, enroll again. Older
email-change links cannot bypass enrollment or session revocation.

Users without enrollment retain the existing sign-in flow. Enrolled users must
verify each new sign-in; Remember Me does not bypass this check. Password resets
do not disable verification. Trusted-device/IP labels do not bypass it either.
Keep inboxes secure: email codes are weaker than authenticator apps/security keys.
There are no generated recovery codes or password-only fallback. Lost inbox access
requires support and verified account recovery; this release adds no bypass endpoint.

Payment verification checks gateway reference, NGN currency and exact amount
before an atomic pending-payment claim. A unique ledger constraint additionally
prevents duplicate crediting. Review historical payment credits for earlier
duplicates; this change does not automatically reverse balances or orders.
Password resets are credential-bound and single-use; recovery and password
changes revoke existing login and remember sessions. Email changes require the
current password and confirmation through the new inbox before replacing the
old recovery address. Banned sessions are restricted to appeals/logout.

CSRF protection applies globally, with the signed Paystack webhook as the only
exemption. Shared `static/js/csrf.js` supplies tokens to local forms and
same-origin fetch/XHR mutations; it never sends tokens to signed cloud upload
URLs. New forms should still include an explicit hidden CSRF token for non-JS
operation. Native form submissions without a token fail closed.

## Project Structure

```
Barterex/
├── app.py                    # Flask app initialization and configuration
├── models.py                 # SQLAlchemy database models
├── forms.py                  # WTForms form definitions
├── requirements.txt          # Python dependencies
├── routes/                   # Blueprint modules (refactored from single routes.py)
│   ├── __init__.py
│   ├── auth.py              # Authentication routes (login, register, password reset)
│   ├── marketplace.py        # Marketplace browse routes
│   ├── user.py              # User dashboard and profile routes
│   ├── items.py             # Item upload, activation, and legacy route redirects
│   └── admin.py             # Admin panel routes
├── templates/               # Jinja2 HTML templates
├── static/                  # CSS, JS, and uploaded files
└── migrations/              # Database migration files (Alembic)
```

## Setup Instructions

### Responsive interface

The public/user shell, admin shell and standalone service screens load
`static/css/mobile.css` after their page styles. Its rules apply only at widths
up to 767px: compact headings, cards, media and spacing, with 44px action targets
and 16px form inputs to avoid mobile focus zoom. Desktop styling is unchanged.
Keep tables horizontally scrollable inside their own wrappers rather than
clipping content or scaling the whole page. Validate new pages at 320px, 375px
and 430px, including expanded forms, dialogs and long labels.
For Fund Account, also check empty and maximum funding amounts, the live BXC
summary, expanded help sections and payment errors in light and dark modes.
For Profile Settings, check long saved contact/address details and the prefilled
single-column edit form. Mobile save/cancel actions stay in the document flow
instead of floating over the fields.

### 1. Environment Variables
Copy `.env.example` to `.env` and fill in your configuration:
```bash
cp .env.example .env
```

Then edit `.env` with your actual values:
- `SECRET_KEY`: Generate a secure key for Flask sessions
- `MAIL_USERNAME`: Your Gmail address
- `MAIL_PASSWORD`: Your Gmail app password (not regular password)
- `SQLALCHEMY_DATABASE_URI`: Database connection string

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the Application
```bash
python app.py
```

## Important Security Notes
- **Never commit `.env` to version control** - it's in `.gitignore`
- Use `.env.example` as a template for new developers
- For production, use environment variables from your hosting provider (Heroku, AWS, etc.)

## Recent Changes

### Blueprint Refactoring (v2.0)
- **Split large `routes.py` (1287 lines) into modular blueprints**:
  - `auth.py` - Authentication (login, register, password reset, ban requests)
  - `marketplace.py` - Browse marketplace, view items, static pages
  - `user.py` - User dashboard, profile, orders, trades, notifications
  - `items.py` - Upload items, cart management, checkout, ordering
  - `admin.py` - Admin dashboard, approvals, user management, order management
  
- **Benefits**:
  - ✅ Better code organization and maintainability
  - ✅ Easier to find and modify specific features
  - ✅ Cleaner separation of concerns
  - ✅ Simplified testing of individual modules
  - ✅ Better for team collaboration

### Environment Variables (v1.5)
- Moved all secrets from hardcoded values to `.env` file
- Added `python-dotenv` for secure configuration management

## Architecture

### Blueprints
Each blueprint encapsulates related routes:
- **auth_bp**: User authentication and session management
- **marketplace_bp**: Public marketplace viewing
- **user_bp**: Authenticated user features
- **items_bp**: Item upload, activation, and legacy route redirects
- **admin_bp**: Admin-only features (with `/admin` prefix)

### Database Models
- **User**: User accounts with credits and bans
- **Item**: Marketplace items with images
- **Cart/CartItem**: Shopping cart management
- **Trade**: Transaction history
- **Order/OrderItem**: Order management
- **Notification**: User notifications
- **Admin**: Admin accounts
- **PickupStation**: Delivery pickup locations

## URL Route Reference

### Auth Routes
- `/login` → auth.login
- `/register` → auth.register
- `/logout` → auth.logout
- `/forgot_password` → auth.forgot_password
- `/reset_password/<token>` → auth.reset_password

### User Routes
- `/dashboard` → user.dashboard
- `/user-items` → user.user_items
- `/my-trades` → user.my_trades
- `/notifications` → user.notifications
- `/profile-settings` → user.profile_settings

### Marketplace Routes
- `/` or `/marketplace` → marketplace.marketplace
- `/home` → marketplace.home
- `/item/<id>` → marketplace.view_item

### Item/Cart Routes
- `/upload` → items.upload_item
- `/cart` → items.view_cart
- `/checkout` → items.checkout

### Admin Routes
- `/admin/login` → admin.admin_login
- `/admin/dashboard` → admin.admin_dashboard
- `/admin/users` → admin.manage_users
- `/admin/approvals` → admin.approve_items
