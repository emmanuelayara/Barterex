from flask import (
    Flask, render_template, redirect, url_for, request, 
    flash, session,
    abort,
    current_app
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
import time
from werkzeug.utils import secure_filename

from flask_mail import Mail, Message
from app import app, login_manager, db, mail
from models import User, Item, Admin, Trade, Notification, CreditTransaction, db, Order, PickupStation, ItemImage, Cart, CartItem, OrderItem
from forms import AdminRegisterForm, AdminLoginForm, RegisterForm, LoginForm, UploadItemForm, ProfileUpdateForm, OrderForm, PickupStationForm, ForgotPasswordForm, ResetPasswordForm

mail = Mail(app)

from itsdangerous import URLSafeTimedSerializer

def generate_reset_token(email, expires_sec=3600):
    s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return s.dumps(email, salt='password-reset-salt')

def verify_reset_token(token, expires_sec=3600):
    s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    try:
        email = s.loads(token, salt='password-reset-salt', max_age=expires_sec)
    except Exception:
        return None
    return email


# Utility function for cart management
from datetime import datetime

def get_or_create_cart(user_id):
    cart = Cart.query.filter_by(user_id=user_id).first()
    if not cart:
        cart = Cart(user_id=user_id, created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        db.session.add(cart)
        db.session.commit()
    return cart


def get_total_cost(self):
    """Calculate total cost of all items in cart"""
    return sum(cart_item.item.value for cart_item in self.items if cart_item.item.is_available)

def get_item_count(self):
    """Get count of items in cart"""
    return len([item for item in self.items if item.item.is_available])

def clear(self):
    """Remove all items from cart"""
    CartItem.query.filter_by(cart_id=self.id).delete()
    db.session.commit()


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



def create_notification(user_id, message):
    # Save notification in DB
    notification = Notification(user_id=user_id, message=message)
    db.session.add(notification)
    db.session.commit()

    # Get the user email
    user = User.query.get(user_id)
    if user and user.email:
        try:
            msg = Message(
                subject="New notification from Barter Express",
                recipients=[user.email],
                body=message
            )
            mail.send(msg)
        except Exception as e:
            print(f"Email failed: {e}")



@app.route('/home')
def home():
    trending_items = Item.query.filter_by(is_approved=True).order_by(Item.id.desc()).limit(6).all()  # 3 rows x 2 cols
    return render_template('home.html', trending_items=trending_items)


@app.route('/contact')
def contact():
    return render_template('contact.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        # Hash the password
        hashed_password = generate_password_hash(form.password.data)

        # New user with signup bonus
        user = User(
            username=form.username.data,
            email=form.email.data,
            password_hash=hashed_password,
            credits=5000,         # 🎁 Beta signup bonus
            first_login=True      # Mark so we can show flash later
        )
        db.session.add(user)
        db.session.commit()

        # ✅ Send personalized welcome email
        msg = Message(
            subject="🎉 Welcome to Barterex!",
            sender="info.barterex@gmail.com",
            recipients=[user.email]
        )
        # Render the HTML template and inject username
        msg.html = render_template("emails/welcome_email.html", username=user.username)

        mail.send(msg)

        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html', form=form)



""" @app.route('/register', methods=['GET', 'POST'])
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
    return render_template('register.html', form=form)  """


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        user = User.query.filter_by(username=username).first()

        if user:
            if user.is_banned:
                return render_template(
                    "banned.html",
                    reason=user.ban_reason,
                    unban_requested=user.unban_requested
                )

        if user and check_password_hash(user.password_hash, password):
            login_user(user)

            # First login bonus message
            if user.first_login:
                flash(
                    "Welcome Beta Tester! You've been given 5000 credits as a signup bonus. ",
                    "success"
                )
                user.first_login = False
                db.session.commit()
            else:
                flash('Login successful!', 'success')

            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html', form=form)


""" @app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        user = User.query.filter_by(username=username).first()

        if user:
            if user.is_banned:
                return render_template("banned.html", reason=user.ban_reason, unban_requested=user.unban_requested)
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html', form=form) """



@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            token = generate_reset_token(user.email)
            reset_url = url_for('reset_password', token=token, _external=True)

            msg = Message(
                subject="🔑 Reset Your Password",
                sender="info.barterex@gmail.com",
                recipients=[user.email]
            )
            msg.html = render_template(
                "emails/reset_password_email.html",
                username=user.username,
                reset_url=reset_url
            )
            mail.send(msg)

        flash('If that email exists, a reset link has been sent.', 'info')
        return redirect(url_for('login'))

    return render_template('forgot_password.html', form=form)



@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    email = verify_reset_token(token)
    if not email:
        flash('The reset link is invalid or has expired.', 'danger')
        return redirect(url_for('forgot_password'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=email).first()
        if user:
            user.password_hash = generate_password_hash(form.password.data)
            db.session.commit()
            flash('Your password has been updated! Please log in.', 'success')
            return redirect(url_for('login'))

    return render_template('reset_password.html', form=form)



@app.route('/banned')
def banned():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])

    # If somehow the user is not banned but tries to access banned page
    if not user.is_banned:
        return redirect(url_for('login'))

    return render_template(
        'banned.html',
        reason=user.ban_reason,
        unban_requested=user.unban_requested
    )


@app.route('/request_unban', methods=['POST'])
def request_unban():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('login'))

    if not user.is_banned:
        flash("You are not banned.", "info")
        return redirect(url_for('dashboard'))  # Redirect to user dashboard if not banned

    if not user.unban_requested:
        user.unban_requested = True
        db.session.commit()
        flash('Your unban request has been submitted. Please wait for admin review.', 'info')
    else:
        flash('You have already submitted an unban request.', 'warning')

    return redirect(url_for('banned'))



@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('marketplace'))


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


@app.route('/my_orders')
@login_required
def user_orders():
    # Fetch all orders belonging to the logged-in user
    page = request.args.get('page', 1, type=int)
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.date_ordered.desc()).paginate(page=page, per_page=6)

    return render_template('user_orders.html', orders=orders)


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
    
    # Ensure the current user owns the item
    if item.user_id != current_user.id:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('marketplace'))

    # Block edit if item is approved
    if item.is_approved:
        flash("This item has already been approved by the admin and cannot be edited.", "warning")
        return redirect(url_for('dashboard'))

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

    page = request.args.get('page', 1, type=int)

    sent_trades = Trade.query.filter_by(sender_id=current_user.id).order_by(Trade.timestamp.desc()).paginate(page=page, per_page=9)
    received_trades = Trade.query.filter_by(receiver_id=current_user.id).order_by(Trade.timestamp.desc()).paginate(page=page, per_page=9)
    return render_template('my_trades.html', sent_trades=sent_trades, received_trades=received_trades)


@app.route('/credit-history')
@login_required
def credit_history():
    history = CreditTransaction.query.filter_by(user_id=current_user.id).order_by(CreditTransaction.id.desc()).all()
    return render_template('credit_history.html', history=history)


@app.route('/notifications')
@login_required
def notifications():

    page = request.args.get('page', 1, type=int)

    notes = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.created_at.desc()
    ).paginate(page=page, per_page=9)

    return render_template('notifications.html', notifications=notes)


@app.route('/notifications/mark_read/<int:note_id>', methods=['POST'])
@login_required
def mark_notification_read(note_id):
    note = Notification.query.get_or_404(note_id)
    if note.user_id == current_user.id:
        note.is_read = True
        db.session.commit()
    return redirect(url_for('notifications'))



@app.route('/profile-settings', methods=['GET', 'POST'])
@login_required
def profile_settings():
    form = ProfileUpdateForm(obj=current_user)

    if request.method == 'POST':
        current_user.email = request.form['email']
        current_user.phone_number = request.form['phone_number']
        current_user.address = request.form['address']
        current_user.city = request.form['city']              # Add this
        current_user.state = request.form['state']
        if form.profile_picture.data:
            file = form.profile_picture.data
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                current_user.profile_picture = f"/{file_path}"
        else:
            current_user.profile_picture = None
            
        db.session.commit()
        flash('Profile updated successfully', 'success')
        return redirect(url_for('dashboard'))

    return render_template('profile_settings.html', user=current_user, form=form)


# ---------------------- MARKETPLACE ---------------------- #

@app.route('/')
def marketplace():
    page = request.args.get('page', 1, type=int)
    condition_filter = request.args.get('condition')
    category_filter = request.args.get('category')
    search = request.args.get('search', '')
    
    # New price filtering parameters
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    price_range = request.args.get('price_range')  # For predefined ranges

    filters = [Item.is_approved == True, Item.is_available == True]

    if condition_filter:
        filters.append(Item.condition == condition_filter)

    if category_filter:
        filters.append(Item.category == category_filter)

    if search:
        filters.append(Item.name.ilike(f'%{search}%'))

    # Price filtering logic
    if price_range:
        # Handle predefined price ranges
        if price_range == 'under-1000':
            filters.append(Item.value < 1000)
        elif price_range == '1000-5000':
            filters.append(Item.value >= 1000)
            filters.append(Item.value <= 5000)
        elif price_range == '5000-10000':
            filters.append(Item.value >= 5000)
            filters.append(Item.value <= 10000)
        elif price_range == '10000-25000':
            filters.append(Item.value >= 10000)
            filters.append(Item.value <= 25000)
        elif price_range == '25000-50000':
            filters.append(Item.value >= 25000)
            filters.append(Item.value <= 50000)
        elif price_range == 'over-50000':
            filters.append(Item.value > 50000)
    else:
        # Handle custom min/max price inputs
        if min_price is not None:
            filters.append(Item.value >= min_price)
        if max_price is not None:
            filters.append(Item.value <= max_price)

    # Only include items with actual values (not None)
    filters.append(Item.value.isnot(None))

    items = Item.query.filter(and_(*filters)).order_by(Item.id.desc()).paginate(page=page, per_page=1000)

    return render_template('marketplace.html', items=items)


@app.route('/item/<int:item_id>', methods=['GET', 'POST'])
def view_item(item_id):
    item = Item.query.get_or_404(item_id)
    
    # Get all images for this item, ordered by order_index
    item_images = ItemImage.query.filter_by(item_id=item.id).order_by(ItemImage.order_index).all()
    
    # If no images in ItemImage table, use the legacy image_url
    if not item_images and item.image_url:
        # Create a temporary image object for backward compatibility
        class TempImage:
            def __init__(self, url, is_primary=True):
                self.image_url = url
                self.is_primary = is_primary
        
        item_images = [TempImage(item.image_url)]

    related_items = Item.query.filter(
        Item.category == item.category,
        Item.id != item.id,
        Item.is_available == True
    ).limit(5).all()

    return render_template('item_detail.html', item=item, item_images=item_images, related_items=related_items)


@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_item():
    if current_user.is_banned:
        flash('Your account has been banned.', 'danger')
        logout_user()
        return redirect(url_for('login'))

    form = UploadItemForm()
    if form.validate_on_submit():
        # Create the item first
        new_item = Item(
            name=form.name.data,
            description=form.description.data,
            condition=form.condition.data,
            category=form.category.data,
            user_id=current_user.id,
            location=current_user.state,
            is_available=True,
            is_approved=False,
            status='pending'
        )
        db.session.add(new_item)
        db.session.flush()  # Get the item ID without committing
        
        # Handle multiple image uploads
        uploaded_images = []
        if form.images.data:
            for index, file in enumerate(form.images.data):
                if file and allowed_file(file.filename):
                    # Generate unique filename
                    filename = secure_filename(file.filename)
                    unique_filename = f"{new_item.id}_{index}_{int(time.time())}_{filename}"
                    image_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                    file.save(image_path)
                    
                    # Create ItemImage record
                    item_image = ItemImage(
                        item_id=new_item.id,
                        image_url=f"/{image_path}",
                        is_primary=(index == 0),  # First image is primary
                        order_index=index
                    )
                    db.session.add(item_image)
                    uploaded_images.append(item_image)
        
        # Set the main image_url to the first uploaded image for backward compatibility
        if uploaded_images:
            new_item.image_url = uploaded_images[0].image_url
        
        try:
            db.session.commit()
            flash(f"Item submitted for approval with {len(uploaded_images)} images!", "info")
            return redirect(url_for('marketplace'))
        except Exception as e:
            db.session.rollback()
            flash("Error uploading item. Please try again.", "danger")
            return redirect(url_for('upload_item'))

    return render_template('upload.html', form=form)




@app.route('/add_to_cart/<int:item_id>', methods=['POST', 'GET'])
@login_required
def add_to_cart(item_id):
    item = Item.query.get_or_404(item_id)

    if not item.is_available:
        flash("This item is no longer available.", "danger")
        return redirect(url_for('marketplace'))

    if item.user_id == current_user.id:
        flash("You cannot add your own item to cart.", "info")
        return redirect(url_for('marketplace'))

    # Get or create cart for current user
    cart = get_or_create_cart(current_user.id)

    # Check if item is already in cart
    existing_cart_item = CartItem.query.filter_by(cart_id=cart.id, item_id=item_id).first()
    if existing_cart_item:
        flash("This item is already in your cart.", "info")
        return redirect(url_for('view_cart'))

    # Add item to cart
    cart_item = CartItem(cart_id=cart.id, item_id=item_id)
    db.session.add(cart_item)
    
    # Update cart timestamp
    cart.updated_at = datetime.utcnow()
    db.session.commit()

    flash(f"'{item.name}' has been added to your cart.", "success")
    return redirect(url_for('view_cart'))


@app.route('/cart')
@login_required
def view_cart():
    cart = Cart.query.filter_by(user_id=current_user.id).first()
    
    if not cart:
        cart_items = []
        total_cost = 0
    else:
        # Only show items that are still available
        cart_items = [ci for ci in cart.items if ci.item.is_available]
        total_cost = cart.get_total_cost()
        
        # Remove unavailable items from cart
        unavailable_items = [ci for ci in cart.items if not ci.item.is_available]
        if unavailable_items:
            for ci in unavailable_items:
                db.session.delete(ci)
            db.session.commit()
            if len(unavailable_items) == 1:
                flash("1 item was removed from your cart as it's no longer available.", "warning")
            else:
                flash(f"{len(unavailable_items)} items were removed from your cart as they're no longer available.", "warning")
    
    return render_template('cart.html', cart_items=cart_items, total_cost=total_cost)


@app.route('/remove_from_cart/<int:item_id>', methods=['POST'])
@login_required
def remove_from_cart(item_id):
    cart = Cart.query.filter_by(user_id=current_user.id).first()
    
    if cart:
        cart_item = CartItem.query.filter_by(cart_id=cart.id, item_id=item_id).first()
        if cart_item:
            db.session.delete(cart_item)
            cart.updated_at = datetime.utcnow()
            db.session.commit()
            flash("Item removed from cart.", "success")
    
    return redirect(url_for('view_cart'))


@app.route('/clear_cart', methods=['POST'])
@login_required
def clear_cart():
    cart = Cart.query.filter_by(user_id=current_user.id).first()
    
    if cart:
        cart.clear()
        flash("Cart cleared.", "success")
    
    return redirect(url_for('view_cart'))


@app.route('/checkout')
@login_required
def checkout():
    cart = Cart.query.filter_by(user_id=current_user.id).first()
    
    if not cart or not cart.items:
        flash("Your cart is empty.", "info")
        return redirect(url_for('marketplace'))
    
    # Filter available items
    available_items = [ci for ci in cart.items if ci.item.is_available]
    
    if not available_items:
        flash("No available items in your cart.", "info")
        return redirect(url_for('view_cart'))
    
    total_cost = sum(ci.item.value for ci in available_items)
    
    # Check if user has sufficient credits
    if current_user.credits < total_cost:
        flash(f"Insufficient credits. You need {total_cost} credits but only have {current_user.credits}.", "danger")
        return redirect(url_for('view_cart'))
    
    return render_template('checkout.html', cart_items=available_items, total_cost=total_cost)



@app.route('/process_checkout', methods=['POST'])
@login_required
def process_checkout():
    cart = Cart.query.filter_by(user_id=current_user.id).first()

    if not cart or not cart.items:
        flash("Your cart is empty.", "info")
        return redirect(url_for('marketplace'))

    available = [ci for ci in cart.items if ci.item and ci.item.is_available]
    if not available:
        flash("No available items in your cart.", "info")
        return redirect(url_for('view_cart'))

    total_cost = sum(ci.item.value for ci in available)
    if current_user.credits < total_cost:
        flash(f"Insufficient credits. You need {total_cost}, but only have {current_user.credits}.", "danger")
        return redirect(url_for('view_cart'))

    try:
        purchased_items = []
        for ci in available:
            item = ci.item
            if not item.is_available:
                continue

            seller_id = getattr(item, "owner_id", None) or getattr(item, "user_id", None)
            current_user.credits -= item.value
            item.user_id = current_user.id
            item.is_available = False

            db.session.add(Trade(
                sender_id=current_user.id,
                receiver_id=seller_id,
                item_id=item.id,
                item_received_id=item.id,
                status='completed'
            ))

            purchased_items.append(item)
            db.session.delete(ci)

        db.session.commit()

    except Exception:
        db.session.rollback()
        flash("Something went wrong while processing your purchase.", "danger")
        return redirect(url_for('view_cart'))

    if not purchased_items:
        return redirect(url_for('view_cart'))

    # Save purchased items in session and redirect to ONE delivery form
    session['pending_order_items'] = [i.id for i in purchased_items]
    flash("Now set up delivery for your purchased items.", "info")
    return redirect(url_for('order_item'))



@app.route('/order_item', methods=['GET', 'POST'])
@login_required
def order_item():
    form = OrderForm()
    stations = PickupStation.query.filter_by(state=current_user.state).all()
    form.pickup_station.choices = [(s.id, s.name) for s in stations]
    # Only fetch current purchased items
    pending_item_ids = session.get('pending_order_items', [])
    items = Item.query.filter(Item.id.in_(pending_item_ids)).all()
    
    if request.method == 'GET' and current_user.address:
        form.delivery_address.data = current_user.address
    
    if form.validate_on_submit():
        delivery_method = form.delivery_method.data
        pickup_station_id = form.pickup_station.data if delivery_method == 'pickup' else None
        delivery_address = form.delivery_address.data if delivery_method == 'home delivery' else None
        
        # Create one order
        order = Order(
            user_id=current_user.id,
            delivery_method=delivery_method,
            delivery_address=delivery_address,
            pickup_station_id=pickup_station_id
        )
        db.session.add(order)
        
        # Attach all purchased items to this order
        for item_id in pending_item_ids:
            db.session.add(OrderItem(order=order, item_id=item_id))
        
        db.session.commit()  # ✅ commit before notification and email
        
        # --- Personalized Notification ---
        if delivery_method == "pickup":
            station = PickupStation.query.get(pickup_station_id)
            extra_info = f"Pickup Station: {station.name}, {station.address}" if station else ""
        else:
            extra_info = f"Delivery Address: {delivery_address}"
        
        # Item names for notification
        item_names = [item.name for item in items]
        if len(item_names) == 1:
            item_info = f"Item: '{item_names[0]}' keep using Barterex for seamless trading."
        else:
            item_info = f"Items: {', '.join(item_names)} keep using Barterex for seamless trading."
        
        create_notification(
            current_user.id,
            f"📦 Your order has been set up for delivery via {delivery_method}. {item_info}. {extra_info}"
        )
        
        # ✅ Send order confirmation email using template
        msg = Message(
            subject="📦 Order Confirmation - Barterex",
            sender="info.barterex@gmail.com",
            recipients=[current_user.email]
        )
        
        # Prepare data for email template
        email_data = {
            'username': current_user.username,
            'order_id': order.id,
            'items': items,
            'delivery_method': delivery_method,
            'delivery_address': delivery_address,
            'pickup_station': PickupStation.query.get(pickup_station_id) if pickup_station_id else None,
            'order_date': order.created_at.strftime('%B %d, %Y at %I:%M %p') if hasattr(order, 'created_at') else 'Today'
        }
        
        # Render the HTML template and inject order data
        msg.html = render_template("emails/order_confirmation.html", **email_data)
        mail.send(msg)
        # --- End Email ---
        
        session.pop('pending_order_items', None)
        flash("Delivery set up successfully for your purchased items! Confirmation email sent.", "success")
        return redirect(url_for('dashboard'))
    
    return render_template('order_item.html', form=form, stations=stations, items=items)



# Context processor to make cart info available in templates
@app.context_processor
def inject_cart_info():
    if current_user.is_authenticated:
        cart = Cart.query.filter_by(user_id=current_user.id).first()
        if cart:
            cart_count = cart.get_item_count()
        else:
            cart_count = 0
        return {'cart_count': cart_count}
    return {'cart_count': 0}


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

    # Base query with optional status filter
    query = Item.query.options(joinedload(Item.user))

    if status != 'all':
        query = query.filter(Item.status == status)


    # If search is applied
    if search:
        query = query.join(User).filter(
            (Item.name.ilike(f"%{search}%")) | (User.username.ilike(f"%{search}%")) | (Item.item_number == search)
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
    unban_requests = User.query.filter_by(unban_requested=True, is_banned=True).all()
    banned_users = User.query.filter_by(is_banned=True).all()
    return render_template('admin/users.html', users=users, unban_requests=unban_requests,
        banned_users=banned_users)


@app.route('/admin/view_user/<int:user_id>')
@admin_login_required
def view_user(user_id):
    user = User.query.get_or_404(user_id)
    items_uploaded = Item.query.filter_by(user_id=user.id).count()
    items_traded = Item.query.filter_by(user_id=user.id, is_available=False).count()


    return render_template('admin/view_user.html', user=user,
                           items_uploaded=items_uploaded,
                           items_traded=items_traded)


@app.route('/admin/ban_user/<int:user_id>', methods=['POST'])
@admin_login_required
def ban_user(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == session.get('admin_id'):
        flash("You can't ban yourself.", 'danger')
        return redirect(url_for('manage_users'))

    reason = request.form.get('ban_reason')  # Get reason from form
    if not reason.strip():
        flash("You must provide a reason for banning this user.", 'danger')
        return redirect(url_for('manage_users'))

    user.is_banned = True
    user.ban_reason = reason
    db.session.commit()

    flash(f'User {user.username} has been banned.', 'warning')
    return redirect(url_for('manage_users'))


@app.route('/admin/banned_users')
@admin_login_required
def admin_banned_users():
    users = User.query.all()
    banned_users = User.query.filter_by(is_banned=True).all()
    return render_template('admin/users.html', users=users, banned_users=banned_users)

@app.route('/admin/unban_user/<int:user_id>', methods=['POST'])
@admin_login_required
def unban_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_banned = False
    user.ban_reason = None
    user.unban_requested = False
    db.session.commit()

    flash(f"{user.username} has been unbanned.", "success")
    return redirect(url_for('admin_banned_users'))


@app.route('/admin/approve_unban/<int:user_id>', methods=['POST'])
@admin_login_required
def approve_unban(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_banned:
        user.is_banned = False
        user.unban_requested = False
        user.ban_reason = None
        db.session.commit()
        flash(f'User {user.username} has been unbanned.', 'success')
    return redirect(url_for('manage_users'))


@app.route('/admin/reject_unban/<int:user_id>', methods=['POST'])
@admin_login_required
def reject_unban(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_banned and user.unban_requested:
        user.unban_requested = False
        db.session.commit()
        flash(f'User {user.username}\'s unban request has been rejected.', 'danger')
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
    items = Item.query.filter_by(status='pending').all()
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
        item.status = 'approved'


        # ✅ Give user the same value as credits
        item.user.credits += int(value)


        if item.status == 'approved':
            create_notification(item.user_id, f"🎉 Your item '{item.name}' has been approved for ₦{item.value} credits!. And your New Balance is: ₦{item.user.credits:,} credits. Keep using Barterex for seamless trading.")
        else:
            create_notification(item.user_id, f"❌ Your item '{item.name}' was rejected because: {item.rejection_reason}. Keep using Barterex for seamless trading.")


        db.session.commit()
        flash(f"Item '{item.name}' approved with value {value} credits.", "success")
    except ValueError:
        flash("Invalid value entered.", "danger")

    return redirect(url_for('approve_items'))


@app.route('/admin/reject/<int:item_id>', methods=['POST'])
@admin_login_required
def reject_item(item_id):
    item = Item.query.get_or_404(item_id)
    reason = request.form.get("rejection_reason")  # from form input

    item.is_approved = False
    item.is_available = False
    item.status = 'rejected'
    item.rejection_reason = reason

    db.session.commit()

    # Notify user (assuming you have some send_notification + email setup)
    flash(f'Item rejected. Reason: {reason}', 'warning')
    return redirect(url_for('admin_dashboard'))



@app.route('/admin/update-status', methods=['POST'])
@admin_login_required
def update_item_status():
    item_id = request.form.get('item_id')
    new_status = request.form.get('status')

    item = Item.query.get_or_404(item_id)
    item.status = new_status
    db.session.commit()

    flash(f"Item '{item.name}' has been marked as {new_status}.", "success")
    return redirect(url_for('admin_dashboard', status='pending'))


@app.route('/admin/fix-status', methods=['POST'])
@admin_login_required
def fix_misclassified_items():
    items_to_fix = Item.query.filter(Item.is_approved == True, Item.status == 'pending').all()
    count = 0

    for item in items_to_fix:
        item.status = 'approved'
        count += 1

    db.session.commit()
    flash(f"{count} item(s) with approved status were moved from 'pending' to 'approved'.", "info")
    return redirect(url_for('admin_dashboard', status='approved'))


@app.route('/admin/fix-missing-credits', methods=['POST'])
@admin_login_required
def fix_missing_credits():
    items_to_fix = Item.query.filter(
        Item.is_approved == True,
        Item.credited == False,
        Item.is_available == True
    ).all()

    count = 0
    for item in items_to_fix:
        if item.user:
            item.user.credits += item.value or 0
            item.credited = True
            count += 1

    db.session.commit()
    flash(f"{count} item(s) were fixed and credits added to users.", "success")
    return redirect(url_for('admin_dashboard'))

# Add Station
@app.route('/admin/pickup-stations/add', methods=['GET', 'POST'])
@admin_login_required
def add_pickup_station():
    form = PickupStationForm()
    if form.validate_on_submit():
        station = PickupStation(
            name=form.name.data,
            address=form.address.data,
            state=form.state.data,
            city=form.city.data
        )
        db.session.add(station)
        db.session.commit()
        flash("Pickup station added successfully!", "success")
        return redirect(url_for('manage_pickup_stations'))

    # Pass both form and stations to template
    stations = PickupStation.query.all()
    return render_template(
        "admin/manage_pickup_stations.html",
        form=form,
        stations=stations
    )


# Edit Station
@app.route('/admin/pickup_stations/edit/<int:station_id>', methods=['GET', 'POST'])
@admin_login_required
def edit_pickup_station(station_id):
    station = PickupStation.query.get_or_404(station_id)
    form = PickupStationForm(obj=station)  # ✅ bind station data into the form

    if form.validate_on_submit():
        station.name = form.name.data
        station.address = form.address.data
        station.city = form.city.data
        station.state = form.state.data
        db.session.commit()
        flash('Pickup station updated successfully!', 'success')
        return redirect(url_for('manage_pickup_stations'))

    return render_template(
        'admin/edit_pickup_station.html',
        form=form,            # ✅ now template has `form`
        station=station
    )


# Delete Station
@app.route('/admin/pickup_stations/delete/<int:station_id>', methods=['POST'])
def delete_pickup_station(station_id):
    station = PickupStation.query.get_or_404(station_id)
    db.session.delete(station)
    db.session.commit()
    flash('Pickup Station deleted successfully!', 'danger')
    return redirect(url_for('manage_pickup_stations'))

# Manage Station
@app.route('/admin/pickup-stations', methods=['GET'])
@admin_login_required
def manage_pickup_stations():
    form = PickupStationForm()
    stations = PickupStation.query.all()
    return render_template(
        "admin/manage_pickup_stations.html",
        form=form,           
        stations=stations
    )


@app.route('/admin/manage_orders')
@admin_login_required
def manage_orders():
    orders = Order.query.order_by(Order.date_ordered.desc()).all()
    items = Item.query.all()
    return render_template('admin/manage_orders.html', orders=orders, items=items)


@app.route('/admin/update_order_status/<int:order_id>', methods=['POST'])
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    if order.status == "Pending":
        order.status = "Shipped"
    elif order.status == "Shipped":
        order.status = "Out for Delivery"
    elif order.status == "Out for Delivery":
        order.status = "Delivered"


    item_names = ", ".join([f"{oi.item.name}" for oi in order.items])

    status_messages = {
        "Shipped": f"Your order for {item_names} has been shipped.",
        "Out for Delivery": f"Your order for {item_names} is out for delivery.",
        "Delivered": f"Your order for {item_names} has been delivered. 🎉",
    }

    note = Notification(
        user_id=order.user_id,
        message=status_messages.get(order.status, f"Order status updated to {order.status}")
    )
    db.session.add(note)

    db.session.commit()
    flash(f"Order status updated to {order.status}", "success")
    return redirect(url_for('manage_orders'))
