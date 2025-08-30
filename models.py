from app import db
from flask_login import UserMixin
from datetime import datetime
import random


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone_number = db.Column(db.String(15), nullable=True)
    profile_picture = db.Column(db.String(200), nullable=True)  # URL to the profile picture
    address = db.Column(db.String(255))
    city = db.Column(db.String(50))
    state = db.Column(db.String(50))
    password_hash = db.Column(db.String(128), nullable=False)
    
    # Credits & first login flag
    credits = db.Column(db.Integer, default=0)
    first_login = db.Column(db.Boolean, default=True)

    # Admin/ban fields
    is_admin = db.Column(db.Boolean, default=False)
    is_banned = db.Column(db.Boolean, default=False)
    ban_reason = db.Column(db.Text, nullable=True)
    unban_requested = db.Column(db.Boolean, default=False)

    # Relationships
    items = db.relationship('Item', back_populates='user', lazy=True)
    transactions = db.relationship('CreditTransaction', back_populates='user', lazy=True)
    notifications = db.relationship('Notification', back_populates='user', lazy=True)
    orders = db.relationship('Order', back_populates='user', lazy=True)


class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)


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
    # Unique number in format EA-123456
    item_number = db.Column(
        db.String(20), 
        unique=True, 
        nullable=False, 
        default=lambda: f"EA-{random.randint(1, 999999999)}"
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
    delivery_method = db.Column(db.String(20), nullable=False)
    delivery_address = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(50), default="Pending")
    date_ordered = db.Column(db.DateTime, default=db.func.now())
    pickup_station_id = db.Column(db.Integer, db.ForeignKey('pickup_station.id'), nullable=True)

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
    user = db.relationship('User', back_populates='notifications')  # Assuming User has a notifications relationship
    is_read = db.Column(db.Boolean, default=False)  # To track if the notification has been read
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


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