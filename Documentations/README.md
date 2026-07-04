# Barterex
Trade by Barter

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
│   ├── items.py             # Item upload, cart, and checkout routes
│   └── admin.py             # Admin panel routes
├── templates/               # Jinja2 HTML templates
├── static/                  # CSS, JS, and uploaded files
└── migrations/              # Database migration files (Alembic)
```

## Setup Instructions

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
- **items_bp**: Item and cart management
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

