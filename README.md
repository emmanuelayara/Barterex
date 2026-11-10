# Barterex
Trade by Barter

## Saving and acquiring items

Favorites is the user-facing saved-items list; saving does not hold an item.
Users acquire items through individual funded reservations, verification,
settlement, and fulfillment, not a cart or combined checkout. Legacy cart and
checkout URLs redirect to Favorites or the relevant item without purchasing
or deleting historical cart records. Cart notification controls are retired.

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
No database migration is required.

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
