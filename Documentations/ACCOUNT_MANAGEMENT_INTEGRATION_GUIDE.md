# Account Management Integration Guide

## How to Integrate with Existing Barterex Routes

This guide shows exactly what code to add to your existing `routes.py` to fully integrate the account management system.

---

## 1. Update Login Route

**Location**: Your `auth_bp` routes, in the login function

### Current Code
```python
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect(url_for('dashboard'))
    return render_template('login.html', form=form)
```

### Updated Code
```python
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            
            # ✅ ADD THIS: Import at top of file
            from account_management import log_activity, init_security_settings
            from datetime import datetime
            
            # ✅ ADD THIS: Log the login activity
            log_activity(
                user.id, 
                'login', 
                'User logged in successfully',
                status='success'
            )
            
            # ✅ ADD THIS: Update last login timestamp
            user.last_login = datetime.utcnow()
            
            # ✅ ADD THIS: Initialize security settings if new user
            if not user.security_settings:
                init_security_settings(user.id)
            
            # ✅ ADD THIS: Commit changes
            db.session.commit()
            
            return redirect(url_for('dashboard'))
        else:
            # ✅ ADD THIS: Log failed login attempt
            log_activity(
                User.query.filter_by(email=form.email.data).first().id if User.query.filter_by(email=form.email.data).first() else None,
                'login',
                'Failed login attempt',
                status='failed'
            )
    
    return render_template('login.html', form=form)
```

---

## 2. Update Logout Route

**Location**: Your `auth_bp` routes, in the logout function

### Current Code
```python
@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))
```

### Updated Code
```python
@auth_bp.route('/logout')
@login_required
def logout():
    # ✅ ADD THIS: Import at top of file
    from account_management import log_activity
    
    # ✅ ADD THIS: Log the logout activity
    log_activity(
        current_user.id,
        'logout',
        'User logged out'
    )
    
    logout_user()
    return redirect(url_for('home'))
```

---

## 3. Update Registration Route

**Location**: Your `auth_bp` routes, in the register function

### Current Code
```python
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('auth.login'))
    return render_template('register.html', form=form)
```

### Updated Code
```python
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        # ✅ ADD THIS: Import at top of file
        from account_management import init_security_settings
        from datetime import datetime
        
        user = User(
            username=form.username.data,
            email=form.email.data,
            # ✅ ADD THIS: Set account creation timestamp
            created_at=datetime.utcnow(),
            # ✅ ADD THIS: Set initial last login
            last_login=datetime.utcnow()
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        
        # ✅ ADD THIS: Initialize security settings for new user
        init_security_settings(user.id)
        
        return redirect(url_for('auth.login'))
    return render_template('register.html', form=form)
```

---

## 4. Update Profile Update Route

**Location**: Your profile/account settings route

### Current Code
```python
@user_bp.route('/profile/update', methods=['GET', 'POST'])
@login_required
def update_profile():
    form = ProfileUpdateForm()
    if form.validate_on_submit():
        current_user.first_name = form.first_name.data
        current_user.last_name = form.last_name.data
        current_user.bio = form.bio.data
        db.session.commit()
        flash('Profile updated successfully', 'success')
        return redirect(url_for('user.profile'))
    # ... rest of code
```

### Updated Code
```python
@user_bp.route('/profile/update', methods=['GET', 'POST'])
@login_required
def update_profile():
    # ✅ ADD THIS: Import at top of file
    from account_management import log_activity
    
    form = ProfileUpdateForm()
    if form.validate_on_submit():
        current_user.first_name = form.first_name.data
        current_user.last_name = form.last_name.data
        current_user.bio = form.bio.data
        db.session.commit()
        
        # ✅ ADD THIS: Log the profile update
        log_activity(
            current_user.id,
            'profile_update',
            'User updated profile information'
        )
        
        flash('Profile updated successfully', 'success')
        return redirect(url_for('user.profile'))
    # ... rest of code
```

---

## 5. Add Navigation Links to Base Template

**Location**: Your `templates/base.html` (navbar section)

### Current Code
```html
{% if current_user.is_authenticated %}
    <li class="nav-item">
        <a class="nav-link" href="{{ url_for('user.profile') }}">Profile</a>
    </li>
    <li class="nav-item">
        <a class="nav-link" href="{{ url_for('auth.logout') }}">Logout</a>
    </li>
{% endif %}
```

### Updated Code
```html
{% if current_user.is_authenticated %}
    <!-- ✅ ADD THIS: Account Dropdown Menu -->
    <li class="nav-item dropdown">
        <a class="nav-link dropdown-toggle" href="#" id="accountDropdown" role="button" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">
            <i class="fas fa-user-shield"></i> Account
        </a>
        <div class="dropdown-menu dropdown-menu-right" aria-labelledby="accountDropdown">
            <a class="dropdown-item" href="{{ url_for('user.profile') }}">
                <i class="fas fa-user"></i> My Profile
            </a>
            <div class="dropdown-divider"></div>
            
            <!-- Security Section -->
            <a class="dropdown-item" href="{{ url_for('account.security_settings') }}">
                <i class="fas fa-shield-alt"></i> Security Settings
            </a>
            <a class="dropdown-item" href="{{ url_for('account.change_password_page') }}">
                <i class="fas fa-lock"></i> Change Password
            </a>
            <a class="dropdown-item" href="{{ url_for('account.activity_log') }}">
                <i class="fas fa-history"></i> Activity Log
            </a>
            <div class="dropdown-divider"></div>
            
            <!-- Privacy Section -->
            <a class="dropdown-item" href="{{ url_for('account.data_export') }}">
                <i class="fas fa-download"></i> Export My Data
            </a>
            <a class="dropdown-item text-danger" href="{{ url_for('account.delete_account') }}">
                <i class="fas fa-trash"></i> Delete Account
            </a>
            <div class="dropdown-divider"></div>
            
            <a class="dropdown-item" href="{{ url_for('auth.logout') }}">
                <i class="fas fa-sign-out-alt"></i> Logout
            </a>
        </div>
    </li>
{% endif %}
```

---

## 6. Required Imports to Add to routes.py

Add these imports at the top of your routes file(s):

```python
# Account Management
from account_management import (
    log_activity, 
    get_activity_history,
    init_security_settings,
    change_password,
    validate_password_strength,
    enable_2fa,
    disable_2fa,
    request_data_export,
    export_user_data,
    export_user_data_csv,
    request_account_deletion,
    cancel_account_deletion,
    delete_user_account,
    init_security_settings,
    update_security_settings,
    add_trusted_device,
    add_trusted_ip,
    get_security_score
)

# Forms
from forms import (
    ChangePasswordForm,
    SecuritySettingsForm,
    TwoFactorSetupForm,
    ExportDataForm,
    DeleteAccountForm
)

# Models
from models import ActivityLog, SecuritySettings

# DateTime
from datetime import datetime
```

---

## 7. Optional: Add Admin Functionality

If you have an admin section, consider adding these admin routes:

```python
# In your admin blueprint or routes
@admin_bp.route('/admin/users/<int:user_id>/activity')
@login_required
@admin_required
def view_user_activity(user_id):
    """Admin view of user's activity log"""
    user = User.query.get_or_404(user_id)
    activities = ActivityLog.query.filter_by(user_id=user_id).order_by(
        ActivityLog.timestamp.desc()
    ).limit(100).all()
    
    return render_template('admin/user_activity.html', 
                         user=user, 
                         activities=activities)

@admin_bp.route('/admin/users/<int:user_id>/security')
@login_required
@admin_required
def view_user_security(user_id):
    """Admin view of user's security settings"""
    user = User.query.get_or_404(user_id)
    settings = user.security_settings
    
    return render_template('admin/user_security.html',
                         user=user,
                         settings=settings)
```

---

## 8. Complete Integration Checklist

### Routes to Update
- [ ] Login route - Add activity logging and security settings init
- [ ] Logout route - Add activity logging
- [ ] Registration route - Add account creation timestamp and security settings
- [ ] Profile update route - Add activity logging
- [ ] Password change route (if exists) - Add activity logging

### Templates to Update
- [ ] base.html - Add account menu dropdown
- [ ] navbar.html (if separate) - Add account menu
- [ ] Any admin templates - Add security/activity links

### Imports to Add
- [ ] All account_management functions needed
- [ ] All new forms
- [ ] ActivityLog and SecuritySettings models
- [ ] datetime for timestamps

### Testing
- [ ] Test login with activity log check
- [ ] Test logout with activity log check
- [ ] Test new user registration
- [ ] Test security settings access
- [ ] Test 2FA setup
- [ ] Test password change
- [ ] Test data export
- [ ] Test account deletion

---

## 9. Minimal Integration (Quick Version)

If you want to integrate with minimal changes, just do these 3 steps:

### Step 1: Add to Login Route
```python
from account_management import log_activity, init_security_settings
from datetime import datetime

# After successful login_user(user)
log_activity(user.id, 'login', 'User logged in', 'success')
user.last_login = datetime.utcnow()
if not user.security_settings:
    init_security_settings(user.id)
db.session.commit()
```

### Step 2: Add to Logout Route
```python
from account_management import log_activity

# Before logout_user()
log_activity(current_user.id, 'logout', 'User logged out')
```

### Step 3: Add to Base Template
```html
<!-- In navbar after Profile link -->
<a class="nav-link" href="{{ url_for('account.security_settings') }}">
    <i class="fas fa-shield-alt"></i> Security
</a>
```

---

## 10. Testing Integration

### Test 1: Verify Routes Work
```bash
# Start Flask app
python app.py

# Visit these URLs
http://localhost:5000/account/security
http://localhost:5000/account/change-password
http://localhost:5000/account/activity
```

### Test 2: Verify Activity Logging
```bash
# In Python shell
python
>>> from app import app, db
>>> from models import User, ActivityLog
>>> with app.app_context():
>>>     # Check if activities are being logged
>>>     logs = ActivityLog.query.limit(10).all()
>>>     for log in logs:
>>>         print(f"{log.activity_type} - {log.timestamp}")
```

### Test 3: Verify Security Settings
```bash
# In Python shell
python
>>> from app import app, db
>>> from models import User, SecuritySettings
>>> with app.app_context():
>>>     # Check if security settings created
>>>     user = User.query.first()
>>>     if user.security_settings:
>>>         print("✅ Security settings initialized")
>>>     else:
>>>         print("❌ Security settings missing")
```

---

## 11. Troubleshooting Integration

### Issue: "ImportError: cannot import 'account_bp'"
**Solution**: Verify `routes_account.py` is in root directory and `app.py` has `from routes_account import account_bp`

### Issue: "ActivityLog table doesn't exist"
**Solution**: Run migration: `flask db upgrade`

### Issue: "Links in navbar return 404"
**Solution**: Verify blueprint routes are registered in `app.py`: `app.register_blueprint(account_bp)`

### Issue: "Activity not being logged"
**Solution**: Verify `log_activity()` is called in login/logout routes with correct imports

### Issue: "Templates not found"
**Solution**: Ensure `templates/account/` directory exists with all 7 template files

---

## 12. Production Deployment Checklist

Before deploying to production:

- [ ] All routes updated with activity logging
- [ ] Database migrations applied
- [ ] Templates copied to production
- [ ] All imports added to routes
- [ ] Static files linked (CSS/JS)
- [ ] Email configuration tested (for alerts)
- [ ] Rate limiting configured
- [ ] HTTPS enabled
- [ ] Error handling tested
- [ ] Activity logs populated
- [ ] 2FA functionality verified
- [ ] Data export tested
- [ ] Account deletion workflow tested

---

## Summary

Integration involves:
1. **3-4 route updates** (login, logout, register, profile)
2. **1 template update** (navbar in base.html)
3. **4-5 imports** to add
4. **1 database migration** to run
5. **Testing** to verify everything works

**Estimated Integration Time**: 15-20 minutes

---

**Integration Guide Version**: 1.0
**Last Updated**: Session 2
**Status**: Ready for Production Integration
