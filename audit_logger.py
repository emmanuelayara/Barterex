"""
Utility functions for logging admin actions to the audit log
"""
import json
from flask import request, session
from app import db
from models import AuditLog
import logging

logger = logging.getLogger(__name__)


def log_audit_action(action_type, target_type, target_id=None, target_name=None, 
                     description=None, reason=None, before_value=None, after_value=None):
    """
    Log an admin action to the audit log
    
    Args:
        action_type: Type of action (e.g., 'approve_item', 'ban_user', 'edit_credits')
        target_type: Type of target (e.g., 'user', 'item', 'order')
        target_id: ID of the affected object
        target_name: Name of the affected object (for reference)
        description: What was done
        reason: Why it was done
        before_value: Previous state (dict or JSON string)
        after_value: New state (dict or JSON string)
    """
    try:
        admin_id = session.get('admin_id')
        if not admin_id:
            logger.warning(f"Audit log attempted without admin session: {action_type}")
            return
        
        # Get admin IP address
        ip_address = request.remote_addr if request else None
        
        # Convert dicts to JSON strings if needed
        if isinstance(before_value, dict):
            before_value = json.dumps(before_value)
        if isinstance(after_value, dict):
            after_value = json.dumps(after_value)
        
        audit_log = AuditLog(
            admin_id=admin_id,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            description=description,
            reason=reason,
            before_value=before_value,
            after_value=after_value,
            ip_address=ip_address
        )
        
        db.session.add(audit_log)
        db.session.commit()
        
        logger.info(f"Audit logged: {action_type} on {target_type} {target_id} by admin {admin_id}")
        
    except Exception as e:
        logger.error(f"Error logging audit action: {str(e)}", exc_info=True)
        # Don't raise - audit logging failures shouldn't block operations
        db.session.rollback()


def log_item_approval(item_id, item_name, value):
    """Log item approval"""
    log_audit_action(
        action_type='approve_item',
        target_type='item',
        target_id=item_id,
        target_name=item_name,
        description=f'Item approved with value {value} credits',
        after_value={'value': value, 'status': 'approved', 'is_available': True}
    )


def log_item_rejection(item_id, item_name, reason):
    """Log item rejection"""
    log_audit_action(
        action_type='reject_item',
        target_type='item',
        target_id=item_id,
        target_name=item_name,
        description='Item rejected',
        reason=reason,
        after_value={'status': 'rejected', 'is_available': False}
    )


def log_user_ban(user_id, username, reason):
    """Log user ban"""
    log_audit_action(
        action_type='ban_user',
        target_type='user',
        target_id=user_id,
        target_name=username,
        description=f'User banned',
        reason=reason,
        after_value={'is_banned': True}
    )


def log_user_unban(user_id, username):
    """Log user unban"""
    log_audit_action(
        action_type='unban_user',
        target_type='user',
        target_id=user_id,
        target_name=username,
        description='User unbanned',
        after_value={'is_banned': False}
    )


def log_credits_edit(user_id, username, amount_before, amount_after, reason):
    """Log credit adjustment"""
    log_audit_action(
        action_type='edit_credits',
        target_type='user',
        target_id=user_id,
        target_name=username,
        description=f'Credits adjusted from {amount_before} to {amount_after}',
        reason=reason,
        before_value={'credits': amount_before},
        after_value={'credits': amount_after}
    )


def log_order_status_change(order_id, order_name, old_status, new_status):
    """Log order status change"""
    log_audit_action(
        action_type='update_order_status',
        target_type='order',
        target_id=order_id,
        target_name=order_name,
        description=f'Order status changed from {old_status} to {new_status}',
        before_value={'status': old_status},
        after_value={'status': new_status}
    )
