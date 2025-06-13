from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import User, Item, Admin  # Ensure your models are correctly defined
from app import app, login_manager, db
from functools import wraps

# Flask-Login user loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ---------------------- PUBLIC ROUTES ---------------------- #

@app.route('/')
def home():
    return render_template('home.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash('User already exists.', 'warning')
            return redirect(url_for('register'))

        user = User(username=username, email=email, password_hash=password)
        db.session.add(user)
        db.session.commit()

        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            login_user(user, remember=True)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials.', 'danger')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)


@app.route('/marketplace')
def marketplace():
    items = Item.query.filter_by(is_available=True, is_approved=True).all()
    return render_template('marketplace.html', items=items)


@app.route('/buy/<int:item_id>')
@login_required
def buy_item(item_id):
    item = Item.query.get_or_404(item_id)

    if not item.is_available:
        flash("This item is no longer available.", "danger")
        return redirect(url_for('marketplace'))

    if current_user.credits < item.value:
        flash("Insufficient credits to buy this item.", "danger")
        return redirect(url_for('marketplace'))

    current_user.credits -= item.value
    item.is_available = False
    db.session.commit()

    flash(f"You have successfully bought '{item.name}'!", "success")
    return redirect(url_for('marketplace'))


@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_item():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        image_url = request.form.get('image_url', '')

        new_item = Item(
            name=name,
            description=description,
            image_url=image_url,
            owner_id=current_user.id
        )
        db.session.add(new_item)
        db.session.commit()

        flash("Item submitted for approval!", "info")
        return redirect(url_for('marketplace'))

    return render_template('upload.html')


@app.route('/request_trade/<int:item_id>', methods=['POST'])
@login_required
def request_trade(item_id):
    # Placeholder logic
    flash('Trade request sent!', 'success')
    return redirect(url_for('marketplace'))


# ---------------------- ADMIN AUTH ---------------------- #

@app.route('/admin/register', methods=['GET', 'POST'])
def admin_register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        admin = Admin(username=username, email=email, password=password)
        db.session.add(admin)
        db.session.commit()
        flash('Admin registered successfully!', 'success')
        return redirect(url_for('admin_login'))

    return render_template('admin_register.html')


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        admin = Admin.query.filter_by(email=email).first()

        if admin and check_password_hash(admin.password, password):
            session['admin_id'] = admin.id
            flash('Logged in as admin!', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials', 'danger')

    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    flash('Logged out successfully', 'info')
    return redirect(url_for('admin_login'))


# ---------------------- ADMIN DASHBOARD & ITEM APPROVAL ---------------------- #

def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Please log in as admin.', 'warning')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/admin/dashboard')
@admin_login_required
def admin_dashboard():
    filter_status = request.args.get('filter', 'pending')
    page = request.args.get('page', 1, type=int)

    if filter_status == 'all':
        items = Item.query.order_by(Item.id.desc()).paginate(page=page, per_page=5)
    else:
        items = Item.query.filter_by(status=filter_status).order_by(Item.id.desc()).paginate(page=page, per_page=5)

    return render_template('admin_dashboard.html', items=items, filter=filter_status)


@app.route('/admin/approvals')
@admin_login_required
def approve_items():
    items = Item.query.filter_by(is_approved=False).all()
    return render_template('admin_approvals.html', items=items)


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

