from app import db
from flask_login import UserMixin
from datetime import datetime
import random
import secrets


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone_number = db.Column(db.String(15), nullable=True)
    profile_picture = db.Column(db.String(200), nullable=True)  # URL to the profile picture
    address = db.Column(db.String(255))
    city = db.Column(db.String(50))
    state = db.Column(db.String(50))
    password_hash = db.Column(db.Text, nullable=False)
    
    # Credits & first login flag
    credits = db.Column(db.Integer, default=0)
    first_login = db.Column(db.Boolean, default=True)
    
    # Gamification - Level, Tier, Referrals
    level = db.Column(db.Integer, default=1)  # User level based on trades
    tier = db.Column(db.String(20), default='Beginner')  # User tier: Beginner, Novice, Intermediate, Advanced, Expert
    trading_points = db.Column(db.Integer, default=0)  # Points earned from trading
    referral_code = db.Column(db.String(20), unique=True, nullable=True)
    referral_bonus_earned = db.Column(db.Integer, default=0)  # Total bonus from referrals
    referral_count = db.Column(db.Integer, default=0)  # Number of successful referrals

    # Admin/ban fields
    is_admin = db.Column(db.Boolean, default=False)
    is_banned = db.Column(db.Boolean, default=False)
    ban_reason = db.Column(db.Text, nullable=True)
    unban_requested = db.Column(db.Boolean, default=False)

    # Security - failed login tracking for brute force protection
    failed_login_attempts = db.Column(db.Integer, default=0)
    account_locked_until = db.Column(db.DateTime, nullable=True)

    # Account Security & GDPR
    two_factor_enabled = db.Column(db.Boolean, default=False)
    two_factor_secret = db.Column(db.String(32), nullable=True)
    last_password_change = db.Column(db.DateTime, default=datetime.utcnow)
    password_change_required = db.Column(db.Boolean, default=False)
    data_export_requested = db.Column(db.Boolean, default=False)
    data_export_date = db.Column(db.DateTime, nullable=True)
    account_deletion_requested = db.Column(db.Boolean, default=False)
    account_deletion_date = db.Column(db.DateTime, nullable=True)
    gdpr_consent_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    # Notification Preferences (Consignment Model)
    notification_preferences = db.Column(db.JSON, default=lambda: {
        'email_order_updates': True,
        'email_cart_items': False,
        'push_cart_items': True,
        'push_order_updates': True,
        'notification_frequency': 'instant'  # instant, daily, weekly
    })

    # Relationships
    items = db.relationship('Item', back_populates='user', lazy=True)
    transactions = db.relationship('CreditTransaction', back_populates='user', lazy=True)
    notifications = db.relationship('Notification', back_populates='user', lazy=True)
    orders = db.relationship('Order', back_populates='user', lazy=True)
    activity_logs = db.relationship('ActivityLog', back_populates='user', lazy=True, cascade='all, delete-orphan')
    security_settings = db.relationship('SecuritySettings', back_populates='user', lazy=True, uselist=False, cascade='all, delete-orphan')

    def generate_referral_code(self):
        """Generate a unique referral code for the user"""
        import string
        import random
        if not self.referral_code:
            # Generate a unique code like REF-USERNAME-XXXXX
            code = f"REF{self.id}{random.randint(1000, 9999)}"
            self.referral_code = code
        return self.referral_code


class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    
    # Security - failed login tracking
    failed_login_attempts = db.Column(db.Integer, default=0)
    account_locked_until = db.Column(db.DateTime, nullable=True)


class ActivityLog(db.Model):
    """Track user account activity for security and GDPR compliance"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_activity_log_user'), nullable=False)
    user = db.relationship('User', back_populates='activity_logs')
    
    activity_type = db.Column(db.String(50), nullable=False)  # login, logout, password_change, profile_update, etc.
    description = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)  # Support IPv6
    user_agent = db.Column(db.String(500), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status = db.Column(db.String(20), default='success')  # success, failed
    
    def __repr__(self):
        return f'<ActivityLog {self.user.username} - {self.activity_type} at {self.timestamp}>'


class SecuritySettings(db.Model):
    """Store user security preferences and settings"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_security_settings_user'), nullable=False, unique=True)
    user = db.relationship('User', back_populates='security_settings')
    
    # Session security
    remember_device = db.Column(db.Boolean, default=False)
    trusted_devices = db.Column(db.JSON, default=lambda: [])  # List of trusted device fingerprints
    
    # Login alerts
    alert_on_new_device = db.Column(db.Boolean, default=True)
    alert_on_location_change = db.Column(db.Boolean, default=True)
    
    # Password policy
    password_strength_required = db.Column(db.String(20), default='medium')  # weak, medium, strong
    
    # IP whitelisting
    ip_whitelist = db.Column(db.JSON, default=lambda: [])  # List of trusted IPs
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<SecuritySettings for {self.user.username}>'


class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(300), nullable=True)
    value = db.Column(db.Float, nullable=True)
    is_available = db.Column(db.Boolean, default=False)
    is_approved = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(50), default='pending') 
    rejection_reason = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_item_user'), nullable=False)
    user = db.relationship('User', back_populates='items')
    condition = db.Column(db.String(20))  # e.g., "Brand New" or "Fairly Used"
    category = db.Column(db.String(100), nullable=False)  # Electronics, etc.
    credited = db.Column(db.Boolean, default=False)
    location = db.Column(db.String(100))  # New field
    # Unique number in format EA-XXXXXX (cryptographically secure)
    item_number = db.Column(
        db.String(20), 
        unique=True, 
        nullable=False, 
        default=lambda: f"EA-{secrets.token_hex(4).upper()}"
    )
    
    images = db.relationship('ItemImage', back_populates='item', cascade="all, delete-orphan")



class ItemImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    image_url = db.Column(db.String(300), nullable=False)
    is_primary = db.Column(db.Boolean, default=False)  # Mark primary image
    order_index = db.Column(db.Integer, default=0)  # For ordering images
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    item = db.relationship('Item', back_populates='images')

    def __repr__(self):
        return f'<ItemImage {self.id} for Item {self.item_id}>'
    


class Trade(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # Optional user reference
    user = db.relationship('User', foreign_keys=[user_id], backref='trades')

    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_trades')

    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_trades')

    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    item = db.relationship('Item', foreign_keys=[item_id], backref='trades')

    item_given_id = db.Column(db.Integer, db.ForeignKey('item.id'))
    item_given = db.relationship('Item', foreign_keys=[item_given_id], backref='given_trades')

    item_received_id = db.Column(db.Integer, db.ForeignKey('item.id'))
    item_received = db.relationship('Item', foreign_keys=[item_received_id], backref='received_trades')

    status = db.Column(db.String(20), nullable=False, default='pending')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    delivery_method = db.Column(db.String(20), nullable=False)  # 'home delivery' or 'pickup'
    delivery_address = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(50), default="Pending")  # Pending, Processing, Shipped, Delivered, Cancelled
    date_ordered = db.Column(db.DateTime, default=db.func.now())
    pickup_station_id = db.Column(db.Integer, db.ForeignKey('pickup_station.id'), nullable=True)
    
    # Transaction Clarity fields
    order_number = db.Column(db.String(50), unique=True, nullable=False)  # e.g., ORD-20251207-00042
    total_credits = db.Column(db.Float, default=0)  # Total credit value of items
    credits_used = db.Column(db.Float, default=0)  # Credits actually spent
    credits_balance_before = db.Column(db.Float, default=0)  # User balance before order
    credits_balance_after = db.Column(db.Float, default=0)  # User balance after order
    estimated_delivery_date = db.Column(db.DateTime, nullable=True)  # Estimated delivery date
    actual_delivery_date = db.Column(db.DateTime, nullable=True)  # Actual delivery date
    receipt_downloaded = db.Column(db.Boolean, default=False)  # Track if receipt was downloaded
    transaction_notes = db.Column(db.Text, nullable=True)  # Additional notes about the transaction
    
    user = db.relationship('User', back_populates='orders')
    pickup_station = db.relationship('PickupStation', backref='orders')
    items = db.relationship('OrderItem', back_populates='order', cascade="all, delete-orphan")


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)

    order = db.relationship('Order', back_populates='items')
    item = db.relationship('Item')



class PickupStation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(50), nullable=False)
    city = db.Column(db.String(50), nullable=False)
    address = db.Column(db.String(255), nullable=False)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow) 
    user = db.relationship('User', back_populates='notifications')
    is_read = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Enhanced notification fields for real-time and categorization
    notification_type = db.Column(db.String(50), default='system')  # cart, order, message, listing, system, etc.
    category = db.Column(db.String(50), default='general')  # quick_action, status_update, alert, recommendation, etc.
    action_url = db.Column(db.String(500), nullable=True)  # URL to navigate when clicked
    data = db.Column(db.JSON, nullable=True)  # Additional data (order_id, item_id, etc.)
    is_email_sent = db.Column(db.Boolean, default=False)  # Track if email notification was sent
    priority = db.Column(db.String(20), default='normal')  # low, normal, high, urgent
    
    def __repr__(self):
        return f'<Notification {self.id}: {self.notification_type}>'


class CreditTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    amount = db.Column(db.Integer, nullable=False)
    transaction_type = db.Column(db.String(50))  # e.g., 'credit', 'debit'
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', back_populates='transactions')  # Assuming User has a transactions relationship
    


# Cart Database Models
class Cart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='cart_items')
    items = db.relationship('CartItem', backref='cart', cascade='all, delete-orphan')


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
    


class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.Integer, db.ForeignKey('cart.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)  # For future use if you want multiple quantities
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    item = db.relationship('Item', backref='cart_items')
    
    # Composite unique constraint to prevent duplicate items in same cart
    __table_args__ = (db.UniqueConstraint('cart_id', 'item_id', name='unique_cart_item'),)


class Referral(db.Model):
    """Track referral relationships and bonuses earned"""
    id = db.Column(db.Integer, primary_key=True)
    referrer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # User who referred
    referred_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # User who was referred
    referral_code_used = db.Column(db.String(20), nullable=False)  # The code that was used
    
    # Bonus tracking
    signup_bonus_earned = db.Column(db.Boolean, default=False)  # ₦100 on signup
    item_upload_bonus_earned = db.Column(db.Boolean, default=False)  # ₦100 on approved item upload
    purchase_bonus_earned = db.Column(db.Boolean, default=False)  # ₦100 on friend's purchase
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # When referred user signed up
    item_upload_bonus_date = db.Column(db.DateTime, nullable=True)  # When item was approved
    purchase_bonus_date = db.Column(db.DateTime, nullable=True)  # When friend made a purchase
    
    # Relationships
    referrer = db.relationship('User', foreign_keys=[referrer_id])
    referred_user = db.relationship('User', foreign_keys=[referred_user_id])
    
    def __repr__(self):
        return f'<Referral {self.referrer_id} -> {self.referred_user_id}>'