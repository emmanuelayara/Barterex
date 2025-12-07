"""
Account Management Utilities
Handles password changes, 2FA, GDPR compliance, activity logging, and security features
"""

from datetime import datetime, timedelta
from flask import request
import secrets
import json
import csv
import io
from functools import wraps

from app import db
from models import User, ActivityLog, SecuritySettings
from werkzeug.security import generate_password_hash, check_password_hash


# ==================== ACTIVITY LOGGING ==================== #

def get_client_ip():
    """Get the client's IP address from the request"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr


def get_user_agent():
    """Get the user agent from the request"""
    return request.user_agent.string[:500] if request.user_agent else None


def log_activity(user_id, activity_type, description=None, status='success'):
    """
    Log user activity for audit trail and security
    
    Args:
        user_id: The user's ID
        activity_type: Type of activity (login, logout, password_change, etc.)
        description: Optional description
        status: 'success' or 'failed'
    """
    try:
        log = ActivityLog(
            user_id=user_id,
            activity_type=activity_type,
            description=description,
            ip_address=get_client_ip(),
            user_agent=get_user_agent(),
            timestamp=datetime.utcnow(),
            status=status
        )
        db.session.add(log)
        db.session.commit()
        return True
    except Exception as e:
        print(f"Error logging activity: {e}")
        return False


def get_activity_history(user_id, days=30, limit=100):
    """
    Get user's activity history
    
    Args:
        user_id: The user's ID
        days: How many days back to retrieve
        limit: Maximum number of records
    
    Returns:
        List of ActivityLog objects
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    return ActivityLog.query.filter(
        ActivityLog.user_id == user_id,
        ActivityLog.timestamp >= start_date
    ).order_by(ActivityLog.timestamp.desc()).limit(limit).all()


# ==================== PASSWORD MANAGEMENT ==================== #

def validate_password_strength(password, strength_level='medium'):
    """
    Validate password strength based on configured level
    
    Args:
        password: The password to validate
        strength_level: 'weak', 'medium', or 'strong'
    
    Returns:
        Tuple (is_valid: bool, message: str)
    """
    errors = []
    
    if strength_level in ['weak', 'medium', 'strong']:
        if len(password) < 8:
            errors.append("Password must be at least 8 characters")
    
    if strength_level in ['medium', 'strong']:
        if not any(char.isdigit() for char in password):
            errors.append("Password must contain at least one number")
        if not any(char in "!@#$%^&*()_+-=[]{}|;:,.<>?" for char in password):
            errors.append("Password must contain at least one special character")
    
    if strength_level == 'strong':
        if len(password) < 12:
            errors.append("Strong password must be at least 12 characters")
        if not any(char.isupper() for char in password):
            errors.append("Password must contain at least one uppercase letter")
    
    if errors:
        return False, " | ".join(errors)
    return True, "Password strength is acceptable"


def change_password(user_id, current_password, new_password, strength_level='medium'):
    """
    Change user's password
    
    Args:
        user_id: The user's ID
        current_password: Current password (for verification)
        new_password: New password
        strength_level: Required password strength
    
    Returns:
        Tuple (success: bool, message: str)
    """
    user = User.query.get(user_id)
    if not user:
        return False, "User not found"
    
    # Verify current password
    if not check_password_hash(user.password_hash, current_password):
        log_activity(user_id, 'password_change_failed', 'Incorrect current password', status='failed')
        return False, "Current password is incorrect"
    
    # Validate new password strength
    is_valid, message = validate_password_strength(new_password, strength_level)
    if not is_valid:
        return False, message
    
    # Check if new password is same as old
    if check_password_hash(user.password_hash, new_password):
        return False, "New password must be different from current password"
    
    # Update password
    user.password_hash = generate_password_hash(new_password)
    user.last_password_change = datetime.utcnow()
    user.password_change_required = False
    db.session.commit()
    
    log_activity(user_id, 'password_changed', 'User changed their password')
    return True, "Password changed successfully"


# ==================== 2FA (Two-Factor Authentication) ==================== #

def generate_2fa_secret():
    """Generate a random secret for 2FA"""
    return secrets.token_hex(16)


def enable_2fa(user_id):
    """Enable 2FA for a user"""
    user = User.query.get(user_id)
    if not user:
        return False, "User not found"
    
    secret = generate_2fa_secret()
    user.two_factor_secret = secret
    user.two_factor_enabled = True
    db.session.commit()
    
    log_activity(user_id, 'two_factor_enabled', '2FA enabled on account')
    return True, secret


def disable_2fa(user_id):
    """Disable 2FA for a user"""
    user = User.query.get(user_id)
    if not user:
        return False, "User not found"
    
    user.two_factor_enabled = False
    user.two_factor_secret = None
    db.session.commit()
    
    log_activity(user_id, 'two_factor_disabled', '2FA disabled on account')
    return True, "2FA disabled"


# ==================== GDPR COMPLIANCE ==================== #

def request_data_export(user_id):
    """Request user data export for GDPR compliance"""
    user = User.query.get(user_id)
    if not user:
        return False, "User not found"
    
    if user.data_export_requested:
        return False, "Data export already requested. Processing..."
    
    user.data_export_requested = True
    user.data_export_date = datetime.utcnow()
    db.session.commit()
    
    log_activity(user_id, 'data_export_requested', 'User requested data export')
    return True, "Data export requested. You'll receive an email with your data within 48 hours"


def export_user_data(user_id):
    """
    Generate comprehensive user data export for GDPR
    
    Returns:
        Dictionary containing all user data
    """
    user = User.query.get(user_id)
    if not user:
        return None
    
    return {
        'profile': {
            'username': user.username,
            'email': user.email,
            'phone': user.phone_number,
            'address': user.address,
            'city': user.city,
            'state': user.state,
            'credits': user.credits,
            'account_created': user.created_at.isoformat() if user.created_at else None,
            'last_login': user.last_login.isoformat() if user.last_login else None,
        },
        'security': {
            'two_factor_enabled': user.two_factor_enabled,
            'last_password_change': user.last_password_change.isoformat() if user.last_password_change else None,
        },
        'activity': [
            {
                'type': log.activity_type,
                'description': log.description,
                'timestamp': log.timestamp.isoformat(),
                'ip_address': log.ip_address,
                'status': log.status
            }
            for log in user.activity_logs[-100:]  # Last 100 activities
        ],
        'export_timestamp': datetime.utcnow().isoformat()
    }


def export_user_data_csv(user_id):
    """Generate CSV export of user activity logs"""
    user = User.query.get(user_id)
    if not user:
        return None
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow(['Activity Type', 'Description', 'IP Address', 'Status', 'Timestamp'])
    
    # Activity logs
    for log in get_activity_history(user_id, days=365, limit=1000):
        writer.writerow([
            log.activity_type,
            log.description,
            log.ip_address,
            log.status,
            log.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        ])
    
    return output.getvalue()


def request_account_deletion(user_id):
    """Request account deletion (GDPR right to be forgotten)"""
    user = User.query.get(user_id)
    if not user:
        return False, "User not found"
    
    if user.account_deletion_requested:
        return False, "Account deletion already requested"
    
    user.account_deletion_requested = True
    user.account_deletion_date = datetime.utcnow() + timedelta(days=30)  # 30-day delay for recovery
    db.session.commit()
    
    log_activity(user_id, 'account_deletion_requested', 'User requested account deletion')
    return True, f"Account deletion scheduled for {user.account_deletion_date.strftime('%Y-%m-%d')}"


def cancel_account_deletion(user_id):
    """Cancel a pending account deletion request"""
    user = User.query.get(user_id)
    if not user:
        return False, "User not found"
    
    if not user.account_deletion_requested:
        return False, "No deletion request found"
    
    user.account_deletion_requested = False
    user.account_deletion_date = None
    db.session.commit()
    
    log_activity(user_id, 'account_deletion_cancelled', 'User cancelled account deletion')
    return True, "Account deletion cancelled"


def delete_user_account(user_id):
    """Permanently delete user account and associated data"""
    user = User.query.get(user_id)
    if not user:
        return False, "User not found"
    
    try:
        # Log the deletion
        log_activity(user_id, 'account_deleted', 'Account permanently deleted')
        
        # Delete user and all related data (cascade delete)
        db.session.delete(user)
        db.session.commit()
        
        return True, "Account deleted permanently"
    except Exception as e:
        db.session.rollback()
        return False, f"Error deleting account: {str(e)}"


# ==================== SECURITY SETTINGS ==================== #

def init_security_settings(user_id):
    """Initialize security settings for a new user"""
    settings = SecuritySettings.query.filter_by(user_id=user_id).first()
    if not settings:
        settings = SecuritySettings(user_id=user_id)
        db.session.add(settings)
        db.session.commit()
    return settings


def update_security_settings(user_id, **kwargs):
    """Update security settings for a user"""
    settings = SecuritySettings.query.filter_by(user_id=user_id).first()
    if not settings:
        init_security_settings(user_id)
        settings = SecuritySettings.query.filter_by(user_id=user_id).first()
    
    for key, value in kwargs.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
    
    settings.updated_at = datetime.utcnow()
    db.session.commit()
    
    return settings


def add_trusted_device(user_id, device_fingerprint, device_name=''):
    """Add a trusted device for security"""
    settings = SecuritySettings.query.filter_by(user_id=user_id).first()
    if not settings:
        init_security_settings(user_id)
        settings = SecuritySettings.query.filter_by(user_id=user_id).first()
    
    devices = settings.trusted_devices or []
    
    # Add new device
    device = {
        'fingerprint': device_fingerprint,
        'name': device_name,
        'added_date': datetime.utcnow().isoformat(),
        'last_used': datetime.utcnow().isoformat()
    }
    
    devices.append(device)
    settings.trusted_devices = devices
    db.session.commit()
    
    return True


def add_trusted_ip(user_id, ip_address):
    """Add an IP to the whitelist"""
    settings = SecuritySettings.query.filter_by(user_id=user_id).first()
    if not settings:
        init_security_settings(user_id)
        settings = SecuritySettings.query.filter_by(user_id=user_id).first()
    
    ips = settings.ip_whitelist or []
    
    if ip_address not in ips:
        ips.append({
            'address': ip_address,
            'added_date': datetime.utcnow().isoformat()
        })
        settings.ip_whitelist = ips
        db.session.commit()
    
    return True


def get_security_score(user_id):
    """Calculate security score for user (0-100)"""
    user = User.query.get(user_id)
    if not user:
        return 0
    
    score = 50  # Base score
    
    # Password age bonus
    if user.last_password_change:
        days_since_change = (datetime.utcnow() - user.last_password_change).days
        if days_since_change < 90:
            score += 10
        elif days_since_change > 180:
            score -= 10
    
    # 2FA bonus
    if user.two_factor_enabled:
        score += 20
    
    # Activity logging (regular activity is good)
    activity_count = len(user.activity_logs[-30:])  # Last 30 days
    if activity_count > 0:
        score += 10
    
    # Security settings
    settings = user.security_settings
    if settings:
        if settings.alert_on_new_device:
            score += 5
        if settings.alert_on_location_change:
            score += 5
    
    return min(score, 100)
