"""
Trading Points and Level Management System
Handles earning points, calculating levels, awarding rewards, and notifications
"""

from app import db
from models import User, Notification
from datetime import datetime
from logger_config import setup_logger
from rank_rewards import get_tier_info, get_tier_badge

logger = setup_logger(__name__)

# ==================== CONSTANTS ====================

# Points awarded
POINTS_PER_UPLOAD_APPROVAL = 10  # Points for item upload approved
POINTS_PER_PURCHASE = 20  # Points for completed purchase

# Level thresholds - points needed to reach each level
LEVEL_THRESHOLDS = {
    1: 0,      # Level 1: Beginner (0 points)
    2: 100,    # Level 2: Beginner (100 points)
    3: 200,    # Level 3: Beginner (200 points)
    4: 300,    # Level 4: Beginner (300 points)
    5: 400,    # Level 5: Beginner (400 points)
    6: 500,    # Level 6: Novice (500 points)
    7: 700,    # Level 7: Novice (700 points)
    8: 900,    # Level 8: Novice (900 points)
    9: 1100,   # Level 9: Novice (1100 points)
    10: 1300,  # Level 10: Novice (1300 points)
    11: 1500,  # Level 11: Intermediate (1500 points)
    12: 1800,  # Level 12: Intermediate (1800 points)
    13: 2100,  # Level 13: Intermediate (2100 points)
    14: 2400,  # Level 14: Intermediate (2400 points)
    15: 2700,  # Level 15: Intermediate (2700 points)
    16: 3000,  # Level 16: Advanced (3000 points)
    17: 3500,  # Level 17: Advanced (3500 points)
    18: 4000,  # Level 18: Advanced (4000 points)
    19: 4500,  # Level 19: Advanced (4500 points)
    20: 5000,  # Level 20: Advanced (5000 points)
    21: 6000,  # Level 21: Expert (6000 points)
    22: 7000,  # Level 22: Expert (7000 points)
    23: 8000,  # Level 23: Expert (8000 points)
    24: 9000,  # Level 24: Expert (9000 points)
    25: 10000, # Level 25: Expert (10000 points)
    26: 11000, # Level 26: Expert (11000 points)
    27: 12000, # Level 27: Expert (12000 points)
    28: 13000, # Level 28: Expert (13000 points)
    29: 14000, # Level 29: Expert (14000 points)
    30: 15000, # Level 30: Expert (15000 points)
}

# Reward per level (credits)
CREDITS_PER_LEVEL_UP = 300

# Level ranges for tier names
def get_level_tier(level):
    """Get tier name based on level - uses rank_rewards module"""
    tier_info = get_tier_info(level)
    return tier_info['name']


def calculate_level_from_points(points):
    """Calculate user level from total trading points"""
    if points < 0:
        points = 0
    
    # Find the highest level the user qualifies for
    current_level = 1
    for level in sorted(LEVEL_THRESHOLDS.keys(), reverse=True):
        if points >= LEVEL_THRESHOLDS[level]:
            current_level = level
            break
    
    return min(current_level, 30)  # Max level 30


def get_points_to_next_level(current_points):
    """Calculate points needed to reach next level"""
    current_level = calculate_level_from_points(current_points)
    next_level = min(current_level + 1, 30)  # Cap at level 30
    
    if next_level not in LEVEL_THRESHOLDS:
        return 0  # Already at max
    
    points_needed = LEVEL_THRESHOLDS[next_level] - current_points
    return max(0, points_needed)


def award_points_for_upload(user, item_name):
    """
    Award points when user's item gets approved
    
    Args:
        user: User object
        item_name: Name of the approved item
        
    Returns:
        dict with level_up info if applicable
    """
    try:
        old_level = user.level
        old_points = user.trading_points
        
        # Award points
        user.trading_points += POINTS_PER_UPLOAD_APPROVAL
        new_level = calculate_level_from_points(user.trading_points)
        user.level = new_level
        
        db.session.add(user)
        db.session.flush()  # Flush to get updated values
        
        level_up_info = None
        if new_level > old_level:
            # Award credits for level up
            user.credits += CREDITS_PER_LEVEL_UP
            db.session.add(user)
            
            level_up_info = {
                'old_level': old_level,
                'new_level': new_level,
                'old_tier': get_level_tier(old_level),
                'new_tier': get_level_tier(new_level),
                'credits_awarded': CREDITS_PER_LEVEL_UP,
                'points': user.trading_points
            }
            
            logger.info(
                f"User leveled up! User ID: {user.id}, Username: {user.username}, "
                f"Level: {old_level} → {new_level} ({get_level_tier(new_level)}), "
                f"Points: {old_points} → {user.trading_points}, "
                f"Credits Awarded: {CREDITS_PER_LEVEL_UP}"
            )
        else:
            logger.info(
                f"Points awarded for upload approval. User ID: {user.id}, Username: {user.username}, "
                f"Item: '{item_name}', Points: {POINTS_PER_UPLOAD_APPROVAL}, "
                f"Total Points: {user.trading_points}"
            )
        
        return level_up_info
        
    except Exception as e:
        logger.error(f"Error awarding upload points to user {user.id}: {str(e)}", exc_info=True)
        db.session.rollback()
        return None


def award_points_for_purchase(user, order_number):
    """
    Award points when user completes a purchase
    
    Args:
        user: User object
        order_number: Order number for reference
        
    Returns:
        dict with level_up info if applicable
    """
    try:
        old_level = user.level
        old_points = user.trading_points
        
        # Award points
        user.trading_points += POINTS_PER_PURCHASE
        new_level = calculate_level_from_points(user.trading_points)
        user.level = new_level
        
        db.session.add(user)
        db.session.flush()  # Flush to get updated values
        
        level_up_info = None
        if new_level > old_level:
            # Award credits for level up
            user.credits += CREDITS_PER_LEVEL_UP
            db.session.add(user)
            
            level_up_info = {
                'old_level': old_level,
                'new_level': new_level,
                'old_tier': get_level_tier(old_level),
                'new_tier': get_level_tier(new_level),
                'credits_awarded': CREDITS_PER_LEVEL_UP,
                'points': user.trading_points
            }
            
            logger.info(
                f"User leveled up! User ID: {user.id}, Username: {user.username}, "
                f"Level: {old_level} → {new_level} ({get_level_tier(new_level)}), "
                f"Points: {old_points} → {user.trading_points}, "
                f"Credits Awarded: {CREDITS_PER_LEVEL_UP}"
            )
        else:
            logger.info(
                f"Points awarded for purchase. User ID: {user.id}, Username: {user.username}, "
                f"Order: {order_number}, Points: {POINTS_PER_PURCHASE}, "
                f"Total Points: {user.trading_points}"
            )
        
        return level_up_info
        
    except Exception as e:
        logger.error(f"Error awarding purchase points to user {user.id}: {str(e)}", exc_info=True)
        db.session.rollback()
        return None


def create_level_up_notification(user, level_up_info):
    """
    Create notification and send email for level up
    
    Args:
        user: User object
        level_up_info: Dict with level_up details from award_points_*
    """
    if not level_up_info:
        return
    
    try:
        new_level = level_up_info['new_level']
        new_tier = level_up_info['new_tier']
        credits_awarded = level_up_info['credits_awarded']
        
        # Get tier badge icon
        tier_badge = get_tier_badge(new_level)
        
        # Create notification with badge icon
        message = (
            f"{tier_badge} Congratulations! You've reached Level {new_level} ({new_tier})! "
            f"You earned {credits_awarded} credits as a reward. Keep trading to reach higher levels!"
        )
        
        notification = Notification(
            user_id=user.id,
            message=message,
            notification_type='achievement',
            category='status_update',
            priority='high',
            data={
                'level': new_level,
                'tier': new_tier,
                'badge': tier_badge,
                'credits_awarded': credits_awarded,
                'total_points': level_up_info['points']
            }
        )
        
        db.session.add(notification)
        db.session.commit()
        
        # Send email notification
        from routes.auth import send_email_async
        from flask import render_template
        from datetime import datetime as dt
        
        email_data = {
            'username': user.username,
            'level': new_level,
            'tier': new_tier,
            'credits_awarded': credits_awarded,
            'total_points': level_up_info['points'],
            'new_balance': user.credits,
            'now': dt.utcnow()
        }
        
        try:
            html = render_template('emails/level_up_notification.html', **email_data)
            send_email_async(
                subject=f"🎉 Level Up! You've Reached Level {new_level}",
                recipients=[user.email],
                html_body=html
            )
            logger.info(f"Level up email sent to {user.username}")
        except Exception as e:
            logger.warning(f"Could not send level up email to {user.username}: {str(e)}")
        
        logger.info(f"Level up notification created for user {user.id} ({user.username}) - Level {new_level}")
        
    except Exception as e:
        logger.error(f"Error creating level up notification for user {user.id}: {str(e)}", exc_info=True)
        db.session.rollback()
