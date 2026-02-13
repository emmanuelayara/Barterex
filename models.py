from app import db
from flask_login import UserMixin
from datetime import datetime
import random
import secrets
import json
from sqlalchemy.orm import validates


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone_number = db.Column(db.String(15), nullable=True)
    profile_picture = db.Column(db.String(200), nullable=True)  # URL to the profile picture
    address = db.Column(db.String(255))
    city = db.Column(db.String(50))
    state = db.Column(db.String(50))
    password_hash = db.Column(db.Text, nullable=False)
    
    # Credits & first login flag
    credits = db.Column(db.Integer, default=0)
    first_login = db.Column(db.Boolean, default=True)
    
    # Checkout transaction tracking (CRITICAL: for audit trail and fraud detection)
    last_checkout_transaction_id = db.Column(db.String(8), nullable=True)
    last_checkout_timestamp = db.Column(db.DateTime, nullable=True)
    
    # Email verification (CRITICAL: users cannot log in until email is verified)
    email_verified = db.Column(db.Boolean, default=False, index=True)
    email_verification_token = db.Column(db.String(255), nullable=True, unique=True)
    email_verification_sent_at = db.Column(db.DateTime, nullable=True)
    email_verification_expires_at = db.Column(db.DateTime, nullable=True)
    
    # Profile completion tracking (for referral bonus awarding)
    profile_completed = db.Column(db.Boolean, default=False, index=True)  # True when all required profile fields are filled
    profile_completed_at = db.Column(db.DateTime, nullable=True)  # When profile was completed
    
    # Gamification - Level, Tier, Referrals
    level = db.Column(db.Integer, default=1, index=True)  # User level based on trades
    tier = db.Column(db.String(20), default='Beginner', index=True)  # User tier: Beginner, Novice, Intermediate, Advanced, Expert
    trading_points = db.Column(db.Integer, default=0)  # Points earned from trading
    referral_code = db.Column(db.String(20), unique=True, nullable=True)
    referral_bonus_earned = db.Column(db.Integer, default=0)  # Total bonus from referrals
    referral_count = db.Column(db.Integer, default=0)  # Number of successful referrals

    # Admin/ban fields
    is_admin = db.Column(db.Boolean, default=False, index=True)
    is_banned = db.Column(db.Boolean, default=False, index=True)
    ban_reason = db.Column(db.Text, nullable=True)
    ban_date = db.Column(db.DateTime, nullable=True)  # When the user was banned
    unban_requested = db.Column(db.Boolean, default=False)
    unban_request_date = db.Column(db.DateTime, nullable=True)  # When unban was requested
    appeal_message = db.Column(db.Text, nullable=True)  # User's appeal message explaining why they should be unbanned

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
    items = db.relationship('Item', back_populates='user', lazy=True, foreign_keys='[Item.user_id]')
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

    def generate_email_verification_token(self):
        """Generate a secure email verification token"""
        from datetime import datetime, timedelta
        self.email_verification_token = secrets.token_urlsafe(32)
        self.email_verification_sent_at = datetime.utcnow()
        self.email_verification_expires_at = datetime.utcnow() + timedelta(hours=24)  # Token valid for 24 hours
        return self.email_verification_token
    
    def verify_email_token(self, token):
        """Verify if the provided token is valid and not expired"""
        from datetime import datetime
        if not self.email_verification_token or self.email_verification_token != token:
            return False
        if not self.email_verification_expires_at or datetime.utcnow() > self.email_verification_expires_at:
            return False
        return True
    
    def mark_email_verified(self):
        """Mark email as verified and clear verification token"""
        self.email_verified = True
        self.email_verification_token = None
        self.email_verification_expires_at = None
        return True
    
    def is_profile_complete(self):
        """
        Check if user has completed their profile (required fields filled).
        Required fields: phone_number, address, city, state
        Returns: True if all required profile fields are filled, False otherwise
        """
        required_fields = [
            self.phone_number,
            self.address,
            self.city,
            self.state
        ]
        # Check if all required fields are filled (not None and not empty string)
        return all(field for field in required_fields)
    
    def get_incomplete_profile_fields(self):
        """
        Get list of incomplete profile fields.
        Returns: List of field names that need to be filled
        """
        incomplete = []
        if not self.phone_number:
            incomplete.append('Phone Number')
        if not self.address:
            incomplete.append('Address')
        if not self.city:
            incomplete.append('City')
        if not self.state:
            incomplete.append('State')
        return incomplete


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


class UserGamification(db.Model):
    """
    Extracted gamification data from User model for better normalization.
    Contains: level, tier, trading_points, referral info
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    level = db.Column(db.Integer, default=1, nullable=False, index=True)
    tier = db.Column(db.String(20), default='Beginner', nullable=False, index=True)
    trading_points = db.Column(db.Integer, default=0, nullable=False)
    referral_code = db.Column(db.String(20), unique=True, nullable=True)
    referral_bonus_earned = db.Column(db.Integer, default=0, nullable=False)
    referral_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationship
    user = db.relationship('User', backref='gamification', uselist=False)
    
    def __repr__(self):
        return f'<UserGamification user_id={self.user_id}, tier={self.tier}, level={self.level}>'


class UserSecurity(db.Model):
    """
    Extracted security data from User model for better normalization.
    Contains: failed login attempts, account locks, 2FA settings
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    failed_login_attempts = db.Column(db.Integer, default=0, nullable=False)
    account_locked_until = db.Column(db.DateTime, nullable=True)
    two_factor_enabled = db.Column(db.Boolean, default=False, nullable=False)
    two_factor_secret = db.Column(db.String(32), nullable=True)
    last_password_change = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    password_change_required = db.Column(db.Boolean, default=False, nullable=False)
    
    # Relationship
    user = db.relationship('User', backref='security', uselist=False)
    
    def __repr__(self):
        return f'<UserSecurity user_id={self.user_id}, 2fa_enabled={self.two_factor_enabled}>'


class UserPreferences(db.Model):
    """
    Extracted user preferences from User model for better normalization.
    Contains: notification preferences and other user settings
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    notification_preferences = db.Column(db.JSON, default=lambda: {
        'email_order_updates': True,
        'email_cart_items': False,
        'push_cart_items': True,
        'push_order_updates': True,
        'notification_frequency': 'instant'
    }, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationship
    user = db.relationship('User', backref='preferences', uselist=False)
    
    def __repr__(self):
        return f'<UserPreferences user_id={self.user_id}>'


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
    user = db.relationship('User', back_populates='items', foreign_keys='[Item.user_id]')
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_item_uploader'), nullable=True)
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
    
    # Valid condition values for items
    VALID_CONDITIONS = {'Brand New', 'Like New', 'Lightly Used', 'Fairly Used', 'Used', 'For Parts'}
    
    @validates('value')
    def validate_value(self, key, value):
        """Validate that item price/value is positive"""
        if value is not None:
            if not isinstance(value, (int, float)):
                raise ValueError('Price must be a number')
            if value < 0:
                raise ValueError('Price cannot be negative')
            if value == 0:
                raise ValueError('Price must be greater than 0')
        return value
    
    @validates('condition')
    def validate_condition(self, key, condition):
        """Validate that item condition is one of allowed values"""
        if condition is not None:
            condition = str(condition).strip()
            if condition not in self.VALID_CONDITIONS:
                valid_options = ', '.join(sorted(self.VALID_CONDITIONS))
                raise ValueError(f'Invalid condition. Must be one of: {valid_options}')
        return condition
    
    # Database indexes for frequently queried fields (performance optimization)
    # ✅ user_id: Used in dashboard, user profile, "my items" queries
    # ✅ category: Used in marketplace filtering and search
    # ✅ is_available: Used in marketplace listings, available items queries
    # ✅ status: Used in filtering pending/approved/rejected items
    __table_args__ = (
        db.Index('idx_item_user_id', 'user_id'),
        db.Index('idx_item_category', 'category'),
        db.Index('idx_item_is_available', 'is_available'),
        db.Index('idx_item_status', 'status'),
        # Composite index for common combined queries
        db.Index('idx_item_category_available', 'category', 'is_available'),
    )



class ItemImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    image_url = db.Column(db.String(300), nullable=False)
    is_primary = db.Column(db.Boolean, default=False)  # Mark primary image
    order_index = db.Column(db.Integer, default=0)  # For ordering images
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Image metadata for quality analysis
    width = db.Column(db.Integer, nullable=True)  # Image width in pixels
    height = db.Column(db.Integer, nullable=True)  # Image height in pixels
    file_size = db.Column(db.Integer, nullable=True)  # File size in bytes
    quality_flags = db.Column(db.Text, nullable=True)  # JSON string of suspicious patterns detected
    
    item = db.relationship('Item', back_populates='images')

    def __repr__(self):
        return f'<ItemImage {self.id} for Item {self.item_id}>'
    
    def get_quality_flags(self):
        """Parse quality_flags JSON and return list of issues"""
        if not self.quality_flags:
            return []
        import json
        try:
            return json.loads(self.quality_flags)
        except:
            return []
    
    def has_quality_issues(self):
        """Check if image has any quality issues"""
        return len(self.get_quality_flags()) > 0
    


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
    
    # Database indexes for frequently queried fields (performance optimization)
    # ✅ status: Used in filtering trades by status (pending, completed, etc.)
    # ✅ sender_id/receiver_id: Used for user's trade history
    __table_args__ = (
        db.Index('idx_trade_status', 'status'),
        db.Index('idx_trade_sender_id', 'sender_id'),
        db.Index('idx_trade_receiver_id', 'receiver_id'),
    )


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    delivery_method = db.Column(db.String(20), nullable=False)  # 'home delivery' or 'pickup'
    delivery_address = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(50), default="Pending")  # Pending, Processing, Shipped, Delivered, Cancelled
    date_ordered = db.Column(db.DateTime, default=db.func.now())
    pickup_station_id = db.Column(db.Integer, db.ForeignKey('pickup_station.id'), nullable=True)
    
    # Cancellation fields
    cancelled = db.Column(db.Boolean, default=False)  # Track if order was cancelled
    cancelled_at = db.Column(db.DateTime, nullable=True)  # Timestamp of cancellation
    cancellation_reason = db.Column(db.Text, nullable=True)  # Reason for cancellation
    
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
    transaction_type = db.Column(db.String(50))  # e.g., 'credit', 'debit', 'purchase', 'referral_bonus'
    description = db.Column(db.String(255), nullable=True)  # Detailed description for user
    reason = db.Column(db.String(100), nullable=True)  # Reason for transaction (e.g., 'item_purchase', 'sign_up_bonus')
    balance_before = db.Column(db.Float, nullable=True)  # User's credit balance before transaction
    balance_after = db.Column(db.Float, nullable=True)  # User's credit balance after transaction
    related_order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=True)  # Link to order if applicable
    related_item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=True)  # Link to item if applicable
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', back_populates='transactions')  # Assuming User has a transactions relationship
    
    def get_human_readable_description(self):
        """Generate a human-readable explanation of the transaction"""
        if self.description:
            return self.description
        
        # Default descriptions based on transaction type
        if self.transaction_type == 'purchase':
            return f"Paid ₦{self.amount:,.0f} for item purchase"
        elif self.transaction_type == 'referral_signup_bonus':
            return f"Earned ₦{self.amount:,.0f} referral bonus from new signup"
        elif self.transaction_type == 'referral_purchase_bonus':
            return f"Earned ₦{self.amount:,.0f} referral bonus from purchase"
        elif self.transaction_type == 'admin_credit':
            return f"Received ₦{self.amount:,.0f} from admin"
        elif self.transaction_type == 'refund':
            return f"Refunded ₦{self.amount:,.0f}"
        else:
            return f"{self.transaction_type.replace('_', ' ').title()}: ₦{self.amount:,.0f}"
    


# Cart Database Models
class Cart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='cart_items')
    items = db.relationship('CartItem', backref='cart', cascade='all, delete-orphan')
    
    # Database indexes for frequently queried fields (performance optimization)
    # ✅ user_id: Used in Cart.query.filter_by(user_id=...) for user cart lookups
    __table_args__ = (
        db.Index('idx_cart_user_id', 'user_id'),
    )


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
    
    # Composite unique constraint + indexes for performance optimization
    # ✅ cart_id: Used in CartItem.query.filter_by(cart_id=...) for cart item lookups
    __table_args__ = (
        db.UniqueConstraint('cart_id', 'item_id', name='unique_cart_item'),
        db.Index('idx_cartitem_cart_id', 'cart_id'),
    )


class Referral(db.Model):
    """Track referral relationships and bonuses earned"""
    id = db.Column(db.Integer, primary_key=True)
    referrer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # User who referred
    referred_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # User who was referred
    referral_code_used = db.Column(db.String(20), nullable=False)  # The code that was used
    
    # Bonus tracking
    signup_bonus_earned = db.Column(db.Boolean, default=False)  # ₦100 after referred user completes profile
    signup_bonus_earned_at = db.Column(db.DateTime, nullable=True)  # When bonus was awarded
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


class AuditLog(db.Model):
    """Track all admin actions for compliance and auditing"""
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'), nullable=False, index=True)
    admin = db.relationship('Admin', backref='audit_logs')
    
    action_type = db.Column(db.String(100), nullable=False, index=True)  # e.g., 'approve_item', 'ban_user', 'edit_credits'
    target_type = db.Column(db.String(50), nullable=False)  # 'user', 'item', 'order', etc.
    target_id = db.Column(db.Integer, nullable=True, index=True)  # ID of the affected user/item
    target_name = db.Column(db.String(255), nullable=True)  # Name of user/item for reference
    
    description = db.Column(db.Text, nullable=True)  # What was done
    reason = db.Column(db.Text, nullable=True)  # Why it was done (rejection reason, ban reason, etc.)
    
    before_value = db.Column(db.Text, nullable=True)  # JSON of previous state
    after_value = db.Column(db.Text, nullable=True)  # JSON of new state
    
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    ip_address = db.Column(db.String(45), nullable=True)  # IPv4 or IPv6
    
    def __repr__(self):
        return f'<AuditLog {self.action_type} by Admin {self.admin_id} on {self.target_type} {self.target_id}>'
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        import json
        return {
            'id': self.id,
            'admin_id': self.admin_id,
            'admin_name': self.admin.username if self.admin else 'Unknown',
            'action_type': self.action_type,
            'target_type': self.target_type,
            'target_id': self.target_id,
            'target_name': self.target_name,
            'description': self.description,
            'reason': self.reason,
            'before_value': self._parse_json_safe(self.before_value),
            'after_value': self._parse_json_safe(self.after_value),
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'ip_address': self.ip_address
        }
    
    def _parse_json_safe(self, value):
        """Safely parse JSON, returning plain string if not valid JSON"""
        if not value:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            # If not valid JSON, return as plain string
            return value


class SystemSettings(db.Model):
    """Store system-wide settings and configuration"""
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Maintenance mode
    maintenance_mode = db.Column(db.Boolean, default=False, index=True)
    maintenance_message = db.Column(db.Text, default='Platform under maintenance. Please try again later.')
    maintenance_enabled_by = db.Column(db.Integer, db.ForeignKey('admin.id', name='fk_maintenance_admin'), nullable=True)
    maintenance_admin = db.relationship('Admin', foreign_keys=[maintenance_enabled_by])
    maintenance_enabled_at = db.Column(db.DateTime, nullable=True)
    
    # Feature flags
    allow_uploads = db.Column(db.Boolean, default=True)
    allow_trading = db.Column(db.Boolean, default=True)
    allow_browsing = db.Column(db.Boolean, default=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<SystemSettings maintenance_mode={self.maintenance_mode}>'
    
    @staticmethod
    def get_settings():
        """Get or create system settings"""
        settings = SystemSettings.query.first()
        if not settings:
            settings = SystemSettings()
            db.session.add(settings)
            db.session.commit()
        return settings
    
    @staticmethod
    def is_maintenance_enabled():
        """Check if maintenance mode is enabled"""
        settings = SystemSettings.get_settings()
        return settings.maintenance_mode
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'maintenance_mode': self.maintenance_mode,
            'maintenance_message': self.maintenance_message,
            'maintenance_enabled_by': self.maintenance_admin.username if self.maintenance_admin else None,
            'maintenance_enabled_at': self.maintenance_enabled_at.isoformat() if self.maintenance_enabled_at else None,
            'allow_uploads': self.allow_uploads,
            'allow_trading': self.allow_trading,
            'allow_browsing': self.allow_browsing,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# ==================== FAVORITES DATABASE MODEL ====================
class Favorite(db.Model):
    """User's saved items/favorites list"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='favorites')
    item = db.relationship('Item', backref='favorited_by')
    
    # Database indexes for frequently queried fields (performance optimization)
    # ✅ user_id: Used in Favorite.query.filter_by(user_id=...) for user favorites lookups
    # ✅ item_id: Used to check if item is favorited by user
    __table_args__ = (
        db.UniqueConstraint('user_id', 'item_id', name='unique_user_favorite'),
        db.Index('idx_favorite_user_id', 'user_id'),
        db.Index('idx_favorite_item_id', 'item_id'),
    )
    
    def __repr__(self):
        return f'<Favorite user_id={self.user_id}, item_id={self.item_id}>'


# ==================== WISHLIST DATABASE MODEL ====================
class Wishlist(db.Model):
    """User's watchlist for items they want or searching for"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    
    # Either specific item name OR category
    item_name = db.Column(db.String(255), nullable=True)  # e.g., "iPhone 13 Pro"
    category = db.Column(db.String(100), nullable=True)   # e.g., "Electronics", "Furniture"
    search_type = db.Column(db.String(20), default='item')  # 'item' for specific name, 'category' for category
    
    # Notification settings
    is_active = db.Column(db.Boolean, default=True, index=True)  # User can pause/resume notifications
    notify_via_email = db.Column(db.Boolean, default=True)  # Whether to send email notifications
    notify_via_app = db.Column(db.Boolean, default=True)  # Whether to send in-app notifications
    
    # Tracking
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    last_notified_at = db.Column(db.DateTime, nullable=True)  # Prevent sending duplicate notifications
    notification_count = db.Column(db.Integer, default=0)  # How many times user was notified
    
    # Relationships
    user = db.relationship('User', backref='wishlists')
    
    # Database indexes for frequently queried fields
    __table_args__ = (
        db.UniqueConstraint('user_id', 'item_name', 'search_type', name='unique_wishlist_item'),
        db.Index('idx_wishlist_user_id', 'user_id'),
        db.Index('idx_wishlist_category', 'category'),
        db.Index('idx_wishlist_active', 'is_active'),
    )
    
    def __repr__(self):
        if self.search_type == 'item':
            return f'<Wishlist user_id={self.user_id}, item_name={self.item_name}>'
        else:
            return f'<Wishlist user_id={self.user_id}, category={self.category}>'


# ==================== WISHLIST MATCH DATABASE MODEL ====================
class WishlistMatch(db.Model):
    """Track which items matched wishlists (prevent duplicate emails to same user)"""
    id = db.Column(db.Integer, primary_key=True)
    wishlist_id = db.Column(db.Integer, db.ForeignKey('wishlist.id'), nullable=False, index=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False, index=True)
    
    # Notification tracking
    notification_sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    email_sent = db.Column(db.Boolean, default=False)
    app_notification_sent = db.Column(db.Boolean, default=False)
    notification_id = db.Column(db.Integer, db.ForeignKey('notification.id'), nullable=True)
    
    # Relationships
    wishlist = db.relationship('Wishlist', backref='matched_items')
    item = db.relationship('Item', backref='wishlist_matches')
    notification = db.relationship('Notification', foreign_keys=[notification_id])
    
    # Database indexes for frequently queried fields
    __table_args__ = (
        db.UniqueConstraint('wishlist_id', 'item_id', name='unique_wishlist_match'),
        db.Index('idx_wishlist_match_wishlist_id', 'wishlist_id'),
        db.Index('idx_wishlist_match_item_id', 'item_id'),
    )
    
    def __repr__(self):
        return f'<WishlistMatch wishlist_id={self.wishlist_id}, item_id={self.item_id}>'


# ==================== CONTACT MESSAGE DATABASE MODEL ====================
class ContactMessage(db.Model):
    """User contact form messages for admin dashboard"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    
    # User relationship (optional - can be null if submitted anonymously)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    user = db.relationship('User', backref='contact_messages')
    
    # Admin handling
    is_read = db.Column(db.Boolean, default=False, index=True)
    response = db.Column(db.Text, nullable=True)
    response_sent_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='pending', index=True)  # pending, in_progress, resolved, spam
    
    # Tracking
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    ip_address = db.Column(db.String(45), nullable=True)  # Support IPv6
    user_agent = db.Column(db.String(500), nullable=True)
    
    # Database indexes for frequently queried fields
    __table_args__ = (
        db.Index('idx_contact_message_status', 'status'),
        db.Index('idx_contact_message_created_at', 'created_at'),
        db.Index('idx_contact_message_user_id', 'user_id'),
    )
    
    def __repr__(self):
        return f'<ContactMessage id={self.id}, name={self.name}, status={self.status}, created_at={self.created_at}>'