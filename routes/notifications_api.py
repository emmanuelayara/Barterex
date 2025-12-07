"""
Notifications Blueprint - API endpoints and routes for notification system
Handles real-time notifications, preferences, and notification management
"""

from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from models import db, User, Notification, Order
from notifications import NotificationService
from functools import wraps
import json
import logging

logger = logging.getLogger(__name__)

notifications_bp = Blueprint('notifications', __name__, url_prefix='/api/notifications')


def handle_errors(f):
    """Decorator to handle API errors"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {f.__name__}: {str(e)}")
            return jsonify({'error': str(e)}), 500
    return decorated_function


# ============================================================================
# REAL-TIME NOTIFICATION ENDPOINTS
# ============================================================================

@notifications_bp.route('/toast', methods=['POST'])
@login_required
@handle_errors
def send_toast():
    """
    Send toast notification to current user (quick action feedback)
    Used for client-side toast notification from server actions
    """
    data = request.get_json()
    message = data.get('message', 'Action completed')
    notification_type = data.get('type', 'info')  # success, error, warning, info
    duration = data.get('duration', 3000)
    
    return jsonify({
        'status': 'success',
        'toast': {
            'message': message,
            'type': notification_type,
            'duration': duration
        }
    })


@notifications_bp.route('/real-time', methods=['GET'])
@login_required
@handle_errors
def get_realtime_notifications():
    """
    Get unread notifications for real-time updates (polling fallback)
    Used by frontend for real-time notification polling
    """
    limit = request.args.get('limit', 10, type=int)
    notification_type = request.args.get('type', None)
    
    notifications = NotificationService.get_user_notifications(
        current_user.id,
        limit=limit,
        unread_only=True,
        notification_type=notification_type
    )
    
    unread_count = NotificationService.get_unread_count(current_user.id)
    
    return jsonify({
        'status': 'success',
        'unread_count': unread_count,
        'notifications': [{
            'id': n.id,
            'message': n.message,
            'type': n.notification_type,
            'category': n.category,
            'timestamp': n.timestamp.isoformat(),
            'priority': n.priority,
            'action_url': n.action_url,
            'data': n.data or {}
        } for n in notifications]
    })


@notifications_bp.route('/unread-count', methods=['GET'])
@login_required
@handle_errors
def get_unread_count():
    """Get count of unread notifications"""
    count = NotificationService.get_unread_count(current_user.id)
    
    return jsonify({
        'status': 'success',
        'unread_count': count
    })


# ============================================================================
# ORDER STATUS NOTIFICATIONS
# ============================================================================

@notifications_bp.route('/order-status', methods=['POST'])
@login_required
@handle_errors
def send_order_status():
    """
    Send order status update notification
    POST data: { order_id, status }
    """
    data = request.get_json()
    order_id = data.get('order_id')
    status = data.get('status')
    
    if not order_id or not status:
        return jsonify({'error': 'order_id and status required'}), 400
    
    order = Order.query.get(order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    
    # Verify current user owns the order or is admin
    if order.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Create notification
    notification = NotificationService.notify_order_status_update(
        order.user_id,
        order_id,
        status
    )
    
    if notification:
        return jsonify({
            'status': 'success',
            'message': 'Order status notification sent',
            'notification_id': notification.id
        }), 201
    else:
        return jsonify({'error': 'Failed to create notification'}), 500


@notifications_bp.route('/order-placed', methods=['POST'])
@login_required
@handle_errors
def send_order_placed():
    """
    Send order placed notification
    POST data: { order_id }
    """
    data = request.get_json()
    order_id = data.get('order_id')
    
    if not order_id:
        return jsonify({'error': 'order_id required'}), 400
    
    order = Order.query.get(order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    
    # Create notification
    notification = NotificationService.notify_order_placed(
        order.user_id,
        order_id
    )
    
    if notification:
        return jsonify({
            'status': 'success',
            'message': 'Order confirmation notification sent',
            'notification_id': notification.id
        }), 201
    else:
        return jsonify({'error': 'Failed to create notification'}), 500


# ============================================================================
# CART NOTIFICATIONS
# ============================================================================

@notifications_bp.route('/cart/item-added', methods=['POST'])
@login_required
@handle_errors
def send_item_added_to_cart():
    """
    Send notification for item added to cart
    POST data: { item_id }
    """
    data = request.get_json()
    item_id = data.get('item_id')
    
    if not item_id:
        return jsonify({'error': 'item_id required'}), 400
    
    notification = NotificationService.notify_item_added_to_cart(
        current_user.id,
        item_id
    )
    
    if notification:
        return jsonify({
            'status': 'success',
            'message': 'Item added notification',
            'notification_id': notification.id
        }), 201
    else:
        return jsonify({'error': 'Failed to create notification'}), 500


# ============================================================================
# NOTIFICATION MANAGEMENT
# ============================================================================

@notifications_bp.route('/mark-read/<int:notification_id>', methods=['POST'])
@login_required
@handle_errors
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    success = NotificationService.mark_as_read(notification_id, current_user.id)
    
    if success:
        return jsonify({
            'status': 'success',
            'message': 'Notification marked as read'
        })
    else:
        return jsonify({'error': 'Notification not found or unauthorized'}), 404


@notifications_bp.route('/mark-all-read', methods=['POST'])
@login_required
@handle_errors
def mark_all_read():
    """Mark all notifications as read for current user"""
    count = NotificationService.mark_all_as_read(current_user.id)
    
    return jsonify({
        'status': 'success',
        'message': f'{count} notifications marked as read',
        'count': count
    })


@notifications_bp.route('/delete/<int:notification_id>', methods=['DELETE', 'POST'])
@login_required
@handle_errors
def delete_notification(notification_id):
    """Delete a notification"""
    success = NotificationService.delete_notification(notification_id, current_user.id)
    
    if success:
        return jsonify({
            'status': 'success',
            'message': 'Notification deleted'
        })
    else:
        return jsonify({'error': 'Notification not found or unauthorized'}), 404


# ============================================================================
# NOTIFICATION PREFERENCES
# ============================================================================

@notifications_bp.route('/preferences', methods=['GET'])
@login_required
@handle_errors
def get_preferences():
    """Get user's notification preferences"""
    preferences = NotificationService.get_user_preferences(current_user.id)
    
    return jsonify({
        'status': 'success',
        'preferences': preferences
    })


@notifications_bp.route('/preferences', methods=['PUT', 'POST'])
@login_required
@handle_errors
def update_preferences():
    """Update user's notification preferences"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    success = NotificationService.update_user_preferences(current_user.id, data)
    
    if success:
        updated_prefs = NotificationService.get_user_preferences(current_user.id)
        return jsonify({
            'status': 'success',
            'message': 'Preferences updated',
            'preferences': updated_prefs
        })
    else:
        return jsonify({'error': 'Failed to update preferences'}), 500


# ============================================================================
# LISTING NOTIFICATIONS (for sellers)
# ============================================================================



@notifications_bp.route('/recommendation', methods=['POST'])
@login_required
@handle_errors
def send_recommendation():
    """
    Send recommendation notification
    POST data: { recipient_id, item_name, item_id }
    """
    data = request.get_json()
    recipient_id = data.get('recipient_id')
    item_name = data.get('item_name')
    item_id = data.get('item_id')
    
    if not recipient_id or not item_name or not item_id:
        return jsonify({
            'error': 'recipient_id, item_name, and item_id required'
        }), 400
    
    notification = NotificationService.notify_recommendation(
        recipient_id,
        item_name,
        item_id
    )
    
    if notification:
        return jsonify({
            'status': 'success',
            'message': 'Recommendation sent',
            'notification_id': notification.id
        }), 201
    else:
        return jsonify({'error': 'Failed to create notification'}), 500


# ============================================================================
# BULK OPERATIONS
# ============================================================================

@notifications_bp.route('/clear-old', methods=['POST'])
@login_required
@handle_errors
def clear_old_notifications():
    """
    Clear old read notifications (admin only)
    POST data: { days: 30 }
    """
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    data = request.get_json() or {}
    days = data.get('days', 30)
    
    count = NotificationService.clear_old_notifications(days)
    
    return jsonify({
        'status': 'success',
        'message': f'{count} old notifications cleared',
        'count': count
    })


# ============================================================================
# NOTIFICATION LISTING (for UI)
# ============================================================================

@notifications_bp.route('/list', methods=['GET'])
@login_required
@handle_errors
def list_notifications():
    """
    Get user's notifications for UI listing
    Query params: limit, offset, type, category
    """
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)
    notification_type = request.args.get('type', None)
    category = request.args.get('category', None)
    
    query = Notification.query.filter_by(user_id=current_user.id)
    
    if notification_type:
        query = query.filter_by(notification_type=notification_type)
    
    if category:
        query = query.filter_by(category=category)
    
    total = query.count()
    
    notifications = query.order_by(
        Notification.timestamp.desc()
    ).limit(limit).offset(offset).all()
    
    return jsonify({
        'status': 'success',
        'total': total,
        'limit': limit,
        'offset': offset,
        'notifications': [{
            'id': n.id,
            'message': n.message,
            'type': n.notification_type,
            'category': n.category,
            'timestamp': n.timestamp.isoformat(),
            'priority': n.priority,
            'is_read': n.is_read,
            'action_url': n.action_url,
            'data': n.data or {}
        } for n in notifications]
    })
