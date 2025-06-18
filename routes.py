from flask import (
    Flask, render_template, redirect, url_for, request,
    flash, session
    
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, login_required,
    logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from sqlalchemy import and_
from sqlalchemy.orm import joinedload
import os
from werkzeug.utils import secure_filename

from app import app, login_manager, db
from models import User, Item, Admin, Trade, Notification, CreditTransaction
from forms import AdminRegisterForm, AdminLoginForm, RegisterForm, LoginForm, UploadItemForm, PasswordResetRequestForm


# Configuration
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------------------- USER AUTH ---------------------- #

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/')
def home():
    trending_items = Item.query.filter_by(is_approved=True).order_by(Item.id.desc()).limit(6).all()  # 3 rows x 2 cols
    return render_template('home.html', trending_items=trending_items)


from forms import RegisterForm  # Adjust the import path as needed

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        # Hash the password
        form.password.data = generate_password_hash(form.password.data)
        # Logic to create a new user and add to DB
        user = User(username=form.username.data, email=form.email.data, password_hash=form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)



@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        # handle login logic
        username = form.username.data
        password = form.password.data   
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html', form=form)



@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_banned:
        flash('Your account has been banned.', 'danger')
        logout_user()
        return redirect(url_for('login'))
    
    credits = current_user.credits  # assuming this field exists on User
    item_count = Item.query.filter_by(user_id=current_user.id).count()
    pending_trades = Trade.query.filter(db.or_(Trade.sender_id == current_user.id,Trade.receiver_id == current_user.id),Trade.status == 'pending').count()

    # Get latest 5 notifications
    recent_notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.timestamp.desc()).limit(5).all()

    return render_template('dashboard.html', user=current_user, credits=credits, item_count=item_count, pending_trades=pending_trades, recent_notifications=recent_notifications)


@app.route('/user-items')
@login_required
def user_items():

    page = request.args.get('page', 1, type=int)

    items = Item.query.filter_by(user_id=current_user.id).order_by(Item.id.desc()).paginate(page=page, per_page=10)
    return render_template('user_items.html', items=items)


@app.route('/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
def edit_item(item_id):
    item = Item.query.get_or_404(item_id)
    
    if item.user_id != current_user.id:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('marketplace'))

    form = UploadItemForm(obj=item)  # Pre-fill form with current data

    if form.validate_on_submit():
        item.name = form.name.data
        item.description = form.description.data
        item.condition = form.condition.data
        item.category = form.category.data

        file = form.image.data
        if file and allowed_file(file.filename):
            # Remove old image if it exists
            if item.image_url:
                old_path = os.path.join(app.root_path, item.image_url.strip("/"))
                if os.path.exists(old_path):
                    os.remove(old_path)

            filename = secure_filename(file.filename)
            new_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(new_path)
            item.image_url = f"/{new_path}"  # Save new image path

        db.session.commit()
        flash("Item updated successfully!", "success")
        return redirect(url_for('user_items', item_id=item.id))

    return render_template('edit_item.html', form=form, item=item)



@app.route('/my-trades')
@login_required
def my_trades():
    trades = Trade.query.filter(
        (Trade.sender_id == current_user.id) | (Trade.receiver_id == current_user.id)
    ).order_by(Trade.id.desc()).all()
    return render_template('my_trades.html', trades=trades)


@app.route('/credit-history')
@login_required
def credit_history():
    history = CreditTransaction.query.filter_by(user_id=current_user.id).order_by(CreditTransaction.id.desc()).all()
    return render_template('credit_history.html', history=history)


@app.route('/notifications')
@login_required
def notifications():
    notes = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
    return render_template('notifications.html', notifications=notes)


@app.route('/profile-settings', methods=['GET', 'POST'])
@login_required
def profile_settings():
    if request.method == 'POST':
        current_user.username = request.form['username']
        current_user.email = request.form['email']
        db.session.commit()
        flash('Profile updated successfully', 'success')
        return redirect(url_for('profile_settings'))

    return render_template('profile_settings.html', user=current_user)


# ---------------------- MARKETPLACE ---------------------- #

@app.route('/marketplace')
def marketplace():
    page = request.args.get('page', 1, type=int)
    condition_filter = request.args.get('condition')
    category_filter = request.args.get('category')
    search = request.args.get('search', '')

    filters = [Item.is_approved == True, Item.is_available == True]

    if condition_filter:
        filters.append(Item.condition == condition_filter)

    if category_filter:
        filters.append(Item.category == category_filter)

    if search:
        filters.append(Item.name.ilike(f'%{search}%'))

    items = Item.query.filter(and_(*filters)).order_by(Item.id.desc()).paginate(page=page, per_page=8)

    return render_template('marketplace.html', items=items)


@app.route('/item/<int:item_id>', methods=['GET', 'POST'])
def view_item(item_id):
    item = Item.query.get_or_404(item_id)
    return render_template('item_detail.html', item=item)


@app.route('/buy/<int:item_id>', methods=['POST', 'GET'])
@login_required
def buy_item(item_id):
    item = Item.query.get_or_404(item_id)

    if not item.is_available:
        flash("This item is no longer available.", "danger")
        return redirect(url_for('marketplace'))

    if item.user_id == current_user.id:
        flash("You already own this item.", "info")
        return redirect(url_for('marketplace'))

    if current_user.credits < item.value:
        flash("Insufficient credits to buy this item.", "danger")
        return redirect(url_for('marketplace'))

    # Proceed with trade
    current_user.credits -= item.value
    item.owner_id = current_user.id
    item.is_available = False
    db.session.commit()

    flash(f"You have successfully bought '{item.name}'!", "success")
    return redirect(url_for('dashboard'))



@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_item():
    if current_user.is_banned:
        flash('Your account has been banned.', 'danger')
        logout_user()
        return redirect(url_for('login'))

    form = UploadItemForm()
    if form.validate_on_submit():
        file = form.image.data  # file field from your form

        image_url = None
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(image_path)
            image_url = f"/{image_path}"  # Public path to be stored in DB

        new_item = Item(
            name=form.name.data,
            description=form.description.data,
            image_url=image_url,
            condition=form.condition.data,
            category=form.category.data,
            user_id=current_user.id,
            is_available=True,
            is_approved=False,
        )
        db.session.add(new_item)
        db.session.commit()
        flash("Item submitted for approval!", "info")
        return redirect(url_for('marketplace'))

    return render_template('upload.html', form=form)


@app.route('/request_trade/<int:item_id>', methods=['POST'])
@login_required
def request_trade(item_id):
    flash('Trade request sent!', 'success')
    return redirect(url_for('marketplace'))


# ---------------------- ADMIN AUTH ---------------------- #

@app.route('/admin/register', methods=['GET', 'POST'])
def admin_register():
    form = AdminRegisterForm()

    if form.validate_on_submit():
        username = form.username.data
        email = form.email.data
        password = form.password.data

        # Password confirmation already handled by the form validator
        hashed_password = generate_password_hash(password)

        new_admin = Admin(username=username, email=email, password=hashed_password)
        db.session.add(new_admin)
        db.session.commit()

        flash('Admin registered successfully!', 'success')
        return redirect(url_for('admin_login'))

    # If form is not valid or GET method, render the form again
    return render_template('admin/register.html', form=form)



@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    form = AdminLoginForm()
    
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data

        admin = Admin.query.filter_by(email=email).first()
        if admin and check_password_hash(admin.password, password):
            session['admin_id'] = admin.id
            flash('Logged in successfully!', 'success')
            return redirect(url_for('admin_dashboard'))  # Replace with your dashboard route
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('admin/login.html', form=form)



@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    flash('Logged out successfully', 'info')
    return redirect(url_for('admin_login'))


# ---------------------- ADMIN UTILITY ---------------------- #

def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Please log in as admin.', 'warning')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function


# ---------------------- ADMIN DASHBOARD ---------------------- #

@app.route('/admin/dashboard')
@admin_login_required
def admin_dashboard():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    status = request.args.get('status', 'pending')  # Defaults to 'pending'

    # Base query with status filter and user preload
    query = Item.query.options(joinedload(Item.user)).filter(Item.status == status)

    # If search is applied
    if search:
        query = query.join(User).filter(
            (Item.name.ilike(f"%{search}%")) | (User.username.ilike(f"%{search}%"))
        )

    # Paginate items
    items = query.order_by(Item.id.desc()).paginate(page=page, per_page=10)

    # Admin stats
    total_users = User.query.count()
    total_items = Item.query.count()
    approved_items = Item.query.filter_by(status='approved').count()
    pending_items = Item.query.filter_by(status='pending').count()
    rejected_items = Item.query.filter_by(status='rejected').count()
    traded_items = Item.query.filter_by(is_available=False).count()
    total_credits_traded = db.session.query(db.func.sum(Item.value)).filter_by(is_available=False).scalar() or 0

    return render_template(
        'admin/dashboard.html',
        items=items,
        total_users=total_users,
        total_items=total_items,
        approved_items=approved_items,
        pending_items=pending_items,
        rejected_items=rejected_items,
        traded_items=traded_items,
        total_credits_traded=total_credits_traded,
        search=search,
        status=status
    )



@app.route('/admin/users')
@admin_login_required
def manage_users():
    users = User.query.all()
    return render_template('admin/users.html', users=users)


@app.route('/admin/ban_user/<int:user_id>', methods=['POST'])
@admin_login_required
def ban_user(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == session.get('admin_id'):
        flash("You can't ban yourself.", 'danger')
        return redirect(url_for('manage_users'))

    db.session.delete(user)
    db.session.commit()
    flash(f'User {user.username} has been banned and deleted.', 'warning')
    return redirect(url_for('manage_users'))


@app.route('/admin/user/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_login_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        new_credits = request.form.get('credits', type=int)
        user.credits = new_credits
        db.session.commit()
        flash(f"{user.username}'s credits updated to {new_credits}.", "success")
        return redirect(url_for('manage_users'))

    return render_template('edit_user.html', user=user)


@app.route('/admin/approvals')
@admin_login_required
def approve_items():
    items = Item.query.filter_by(is_approved=False).all()
    return render_template('admin/approvals.html', items=items)


@app.route('/admin/approve/<int:item_id>', methods=['POST'])
@admin_login_required
def approve_item(item_id):
    item = Item.query.get_or_404(item_id)

    try:
        value = float(request.form['value'])
        item.value = value
        item.is_approved = True
        item.is_available = True
        db.session.commit()
        flash(f"Item '{item.name}' approved with value {value} credits.", "success")
    except ValueError:
        flash("Invalid value entered.", "danger")

    return redirect(url_for('approve_items'))


@app.route('/admin/reject/<int:item_id>', methods=['POST'])
@admin_login_required
def reject_item(item_id):
    item = Item.query.get_or_404(item_id)
    item.is_approved = False
    item.is_available = False
    db.session.commit()
    flash('Item rejected.', 'warning')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/update-status', methods=['POST'])
@login_required
def update_item_status():
    if not current_user.is_admin:
        flash("Unauthorized access", "danger")
        return redirect(url_for('home'))

    item_id = request.form.get('item_id')
    new_status = request.form.get('status')

    item = Item.query.get_or_404(item_id)
    item.status = new_status
    db.session.commit()

    flash(f"Item '{item.name}' has been marked as {new_status}.", "success")
    return redirect(url_for('admin_dashboard', status='pending'))

