"""
Notifications Service Module
Handles creation, delivery, and management of notifications for Barterex

Features:
- Create notifications of different types (cart, order, message, etc.)
- Send email notifications based on user preferences
- Track notification delivery status
- Handle real-time toast notifications
- Support multiple notification categories
"""

from models import db, User, Notification, Order, Item
from datetime import datetime, timedelta
import json
from flask import render_template_string
import logging

logger = logging.getLogger(__name__)

# Notification types
NOTIFICATION_TYPES = {
    'cart': 'Shopping Cart',
    'order': 'Order Update',
    'message': 'Message',
    'listing': 'Listing Activity',
    'trade': 'Trade Request',
    'system': 'System Alert',
    'recommendation': 'Recommendation'
}

# Notification categories
NOTIFICATION_CATEGORIES = {
    'quick_action': 'Quick Action',
    'status_update': 'Status Update',
    'alert': 'Alert',
    'recommendation': 'Recommendation',
    'general': 'General'
}

# Priority levels
NOTIFICATION_PRIORITIES = {
    'low': 'Low',
    'normal': 'Normal',
    'high': 'High',
    'urgent': 'Urgent'
}


class NotificationService:
    """Service class for managing notifications"""
    
    @staticmethod
    def create_notification(
        user_id,
        message,
        notification_type='system',
        category='general',
        action_url=None,
        data=None,
        priority='normal',
        send_email=True
    ):
        """
        Create a notification for a user
        
        Args:
            user_id (int): User ID
            message (str): Notification message
            notification_type (str): Type of notification (cart, order, etc.)
            category (str): Notification category
            action_url (str): URL to navigate when clicked
            data (dict): Additional data (order_id, item_id, etc.)
            priority (str): Priority level
            send_email (bool): Whether to send email notification
            
        Returns:
            Notification: Created notification object
        """
        try:
            notification = Notification(
                user_id=user_id,
                message=message,
                notification_type=notification_type,
                category=category,
                action_url=action_url,
                data=data or {},
                priority=priority,
                is_email_sent=False
            )
            
            db.session.add(notification)
            db.session.commit()
            
            # Send email if enabled and user preferences allow it
            if send_email:
                NotificationService.send_email_notification(
                    user_id,
                    notification_type,
                    message,
                    action_url,
                    data
                )
            
            logger.info(f"Notification created for user {user_id}: {notification_type}")
            return notification
            
        except Exception as e:
            logger.error(f"Error creating notification: {str(e)}")
            db.session.rollback()
            return None
    
    @staticmethod
    def send_email_notification(user_id, notification_type, message, action_url=None, data=None):
        """
        Send email notification to user if preferences allow
        
        Args:
            user_id (int): User ID
            notification_type (str): Type of notification
            message (str): Notification message
            action_url (str): Action URL
            data (dict): Additional data
        """
        try:
            user = User.query.get(user_id)
            if not user or not user.email:
                logger.warning(f"User {user_id} not found or has no email")
                return
            
            # Check user preferences
            preferences = user.notification_preferences or {}
            
            # Map notification type to preference key
            pref_key = f'email_{notification_type}s'
            
            # Check if email notifications are enabled for this type
            if not preferences.get(pref_key, True):
                logger.info(f"Email notifications disabled for {user_id} - {notification_type}")
                return
            
            # For now, we're not actually sending emails (to avoid SMTP setup)
            # In production, use flask-mail or similar
            logger.info(f"Email notification would be sent to {user.email}")
            
            # Mark notification as email sent (when actually implemented)
            # notification.is_email_sent = True
            # db.session.commit()
            
        except Exception as e:
            logger.error(f"Error sending email notification: {str(e)}")
    
    @staticmethod
    def notify_item_added_to_cart(user_id, item_id):
        """
        Notify user when item is added to cart (quick action)
        
        Args:
            user_id (int): User ID
            item_id (int): Item ID
        """
        item = Item.query.get(item_id)
        if not item:
            return None
        
        message = f"✓ '{item.name}' added to your cart"
        
        return NotificationService.create_notification(
            user_id=user_id,
            message=message,
            notification_type='cart',
            category='quick_action',
            action_url=f'/cart',
            data={'item_id': item_id},
            priority='normal',
            send_email=False  # Quick actions don't send emails
        )
    
    @staticmethod
    def notify_order_placed(user_id, order_id):
        """
        Notify user when order is placed
        
        Args:
            user_id (int): User ID
            order_id (int): Order ID
        """
        order = Order.query.get(order_id)
        if not order:
            return None
        
        message = f"📦 Order #{order_id} confirmed! Total: ₦{order.total_amount}"
        
        return NotificationService.create_notification(
            user_id=user_id,
            message=message,
            notification_type='order',
            category='status_update',
            action_url=f'/orders/{order_id}',
            data={'order_id': order_id},
            priority='high',
            send_email=True
        )
    
    @staticmethod
    def notify_order_status_update(user_id, order_id, status):
        """
        Notify user of order status change
        
        Args:
            user_id (int): User ID
            order_id (int): Order ID
            status (str): New order status
        """
        order = Order.query.get(order_id)
        if not order:
            return None
        
        status_messages = {
            'processing': '⚙️ Your order is being processed',
            'shipped': '🚚 Your order has been shipped!',
            'delivered': '✅ Your order has been delivered!',
            'cancelled': '❌ Your order has been cancelled',
            'completed': '🎉 Order completed successfully!',
            'pending': '⏳ Order is pending'
        }
        
        message = status_messages.get(status, f'Order status: {status}')
        
        return NotificationService.create_notification(
            user_id=user_id,
            message=message,
            notification_type='order',
            category='status_update',
            action_url=f'/orders/{order_id}',
            data={'order_id': order_id, 'status': status},
            priority='high',
            send_email=True
        )
    



    @staticmethod
    def notify_recommendation(user_id, item_name, item_id):
        """
        Notify user of personalized recommendation
        
        Args:
            user_id (int): User ID
            item_name (str): Name of recommended item
            item_id (int): Item ID
        """
        message = f"💡 Check out '{item_name}' - based on your interests"
        
        return NotificationService.create_notification(
            user_id=user_id,
            message=message,
            notification_type='recommendation',
            category='recommendation',
            action_url=f'/items/{item_id}',
            data={'item_id': item_id},
            priority='low',
            send_email=False  # Recommendations don't send emails unless opt-in
        )
    
    @staticmethod
    def get_user_notifications(user_id, limit=20, unread_only=False, notification_type=None):
        """
        Retrieve user's notifications
        
        Args:
            user_id (int): User ID
            limit (int): Number of notifications to return
            unread_only (bool): Only return unread notifications
            notification_type (str): Filter by notification type
            
        Returns:
            list: List of notifications
        """
        query = Notification.query.filter_by(user_id=user_id)
        
        if unread_only:
            query = query.filter_by(is_read=False)
        
        if notification_type:
            query = query.filter_by(notification_type=notification_type)
        
        return query.order_by(Notification.timestamp.desc()).limit(limit).all()
    
    @staticmethod
    def get_unread_count(user_id):
        """
        Get count of unread notifications for user
        
        Args:
            user_id (int): User ID
            
        Returns:
            int: Number of unread notifications
        """
        return Notification.query.filter_by(
            user_id=user_id,
            is_read=False
        ).count()
    
    @staticmethod
    def mark_as_read(notification_id, user_id=None):
        """
        Mark notification as read
        
        Args:
            notification_id (int): Notification ID
            user_id (int): Optional user ID for validation
            
        Returns:
            bool: Success status
        """
        try:
            notification = Notification.query.get(notification_id)
            if not notification:
                return False
            
            if user_id and notification.user_id != user_id:
                return False
            
            notification.is_read = True
            db.session.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error marking notification as read: {str(e)}")
            return False
    
    @staticmethod
    def mark_all_as_read(user_id):
        """
        Mark all notifications as read for user
        
        Args:
            user_id (int): User ID
            
        Returns:
            int: Number of notifications marked as read
        """
        try:
            count = Notification.query.filter_by(
                user_id=user_id,
                is_read=False
            ).update({'is_read': True})
            db.session.commit()
            return count
            
        except Exception as e:
            logger.error(f"Error marking all notifications as read: {str(e)}")
            return 0
    
    @staticmethod
    def delete_notification(notification_id, user_id=None):
        """
        Delete a notification
        
        Args:
            notification_id (int): Notification ID
            user_id (int): Optional user ID for validation
            
        Returns:
            bool: Success status
        """
        try:
            notification = Notification.query.get(notification_id)
            if not notification:
                return False
            
            if user_id and notification.user_id != user_id:
                return False
            
            db.session.delete(notification)
            db.session.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error deleting notification: {str(e)}")
            return False
    
    @staticmethod
    def clear_old_notifications(days=30):
        """
        Clear read notifications older than specified days
        
        Args:
            days (int): Number of days to keep notifications
            
        Returns:
            int: Number of notifications deleted
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            count = Notification.query.filter(
                Notification.is_read == True,
                Notification.timestamp < cutoff_date
            ).delete()
            db.session.commit()
            return count
            
        except Exception as e:
            logger.error(f"Error clearing old notifications: {str(e)}")
            return 0
    
    @staticmethod
    def update_user_preferences(user_id, preferences):
        """
        Update user's notification preferences
        
        Args:
            user_id (int): User ID
            preferences (dict): New preferences
            
        Returns:
            bool: Success status
        """
        try:
            user = User.query.get(user_id)
            if not user:
                return False
            
            # Merge with existing preferences
            current_prefs = user.notification_preferences or {}
            current_prefs.update(preferences)
            user.notification_preferences = current_prefs
            
            db.session.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error updating notification preferences: {str(e)}")
            return False
    
    @staticmethod
    def get_user_preferences(user_id):
        """
        Get user's notification preferences
        
        Args:
            user_id (int): User ID
            
        Returns:
            dict: User preferences
        """
        user = User.query.get(user_id)
        if not user:
            return {}
        
        return user.notification_preferences or {}


# Convenience functions for quick access
def create_notification(user_id, message, **kwargs):
    """Create a notification"""
    return NotificationService.create_notification(user_id, message, **kwargs)


def notify_cart_item(user_id, item_id):
    """Notify item added to cart"""
    return NotificationService.notify_item_added_to_cart(user_id, item_id)


def notify_order(user_id, order_id):
    """Notify order placed"""
    return NotificationService.notify_order_placed(user_id, order_id)


def notify_order_status(user_id, order_id, status):
    """Notify order status update"""
    return NotificationService.notify_order_status_update(user_id, order_id, status)


def get_unread_count(user_id):
    """Get unread notification count"""
    return NotificationService.get_unread_count(user_id)


def get_notifications(user_id, limit=20):
    """Get user notifications"""
    return NotificationService.get_user_notifications(user_id, limit)
