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
    credits = db.Column(db.Integer, default=0)
    is_admin = db.Column(db.Boolean, default=False)
    is_banned = db.Column(db.Boolean, default=False)
    ban_reason = db.Column(db.Text, nullable=True)
    unban_requested = db.Column(db.Boolean, default=False)
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
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    delivery_method = db.Column(db.String(20), nullable=False)
    delivery_address = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(50), default="Pending")
    date_ordered = db.Column(db.DateTime, default=db.func.now())
    pickup_station_id = db.Column(db.Integer, db.ForeignKey('pickup_station.id'), nullable=True)
    pickup_station = db.relationship('PickupStation', backref='orders')
    item = db.relationship('Item', backref='orders')
    user = db.relationship('User', back_populates='orders')  # Assuming User has a orders relationship


class PickupStation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(50), nullable=False)
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
    