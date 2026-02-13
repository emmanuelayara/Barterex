"""
Referral and bonus management utilities
"""

from models import User, Referral, CreditTransaction, Notification
from app import db
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def is_profile_complete(user):
    """
    Check if a user's profile is complete with all required information.
    
    Required fields:
    - email (always required for registration)
    - phone_number (for contact purposes)
    - address (for delivery)
    - city (for location)
    - state (for location)
    
    Args:
        user: User object to check
    
    Returns:
        bool: True if profile is complete, False otherwise
    """
    if not user:
        return False
    
    required_fields = [
        user.email,
        user.phone_number,
        user.address,
        user.city,
        user.state
    ]
    
    # Check if all required fields are populated (non-empty, non-None)
    for field in required_fields:
        if not field or (isinstance(field, str) and not field.strip()):
            return False
    
    return True


def award_referral_signup_bonus(referred_user):
    """
    Award ₦100 referral bonus to the user who referred the given user,
    when the referred user completes their profile.
    
    Args:
        referred_user: The user object who just completed their profile
        
    Returns:
        dict: Status information with keys:
            - 'success': bool - whether bonus was awarded
            - 'message': str - description of what happened
            - 'referrer': User object or None - the user who received bonus
            - 'amount': int - amount awarded (0 if not awarded)
    """
    if not referred_user:
        return {
            'success': False,
            'message': 'Invalid user',
            'referrer': None,
            'amount': 0
        }
    
    try:
        # Find the referral record
        referral = Referral.query.filter_by(
            referred_user_id=referred_user.id,
            signup_bonus_earned=False
        ).first()
        
        if not referral:
            return {
                'success': False,
                'message': 'No pending referral bonus found',
                'referrer': None,
                'amount': 0
            }
        
        referrer = referral.referrer
        
        if not referrer:
            logger.warning(f"Referral record {referral.id} has invalid referrer")
            return {
                'success': False,
                'message': 'Referrer not found',
                'referrer': None,
                'amount': 0
            }
        
        # Award the bonus
        BONUS_AMOUNT = 100
        referrer.credits += BONUS_AMOUNT
        referrer.referral_bonus_earned += BONUS_AMOUNT
        
        # Mark bonus as earned
        referral.signup_bonus_earned = True
        referral.signup_bonus_earned_at = datetime.utcnow()
        
        # Log the transaction
        transaction = CreditTransaction(
            user_id=referrer.id,
            amount=BONUS_AMOUNT,
            transaction_type='referral_signup_bonus'
        )
        
        # Create notification for referrer
        notification = Notification(
            user_id=referrer.id,
            message=f'🎉 {referred_user.username} completed their profile! You earned ₦{BONUS_AMOUNT} referral bonus.',
            notification_type='referral',
            category='reward'
        )
        
        db.session.add(transaction)
        db.session.add(notification)
        db.session.commit()
        
        logger.info(
            f"Referral signup bonus awarded - "
            f"Referrer: {referrer.username} (ID: {referrer.id}), "
            f"Referred: {referred_user.username} (ID: {referred_user.id}), "
            f"Amount: ₦{BONUS_AMOUNT}"
        )
        
        return {
            'success': True,
            'message': f'✅ Referral bonus of ₦{BONUS_AMOUNT} awarded to {referrer.username}',
            'referrer': referrer,
            'amount': BONUS_AMOUNT
        }
        
    except Exception as e:
        logger.error(f"Error awarding referral bonus for user {referred_user.id}: {str(e)}", exc_info=True)
        db.session.rollback()
        return {
            'success': False,
            'message': f'Error processing referral bonus: {str(e)}',
            'referrer': None,
            'amount': 0
        }


def check_and_award_pending_bonuses(user):
    """
    Check if user has a pending referral bonus and award it if profile is complete.
    
    Args:
        user: The user object to check
        
    Returns:
        dict: Result dictionary from award_referral_signup_bonus or status if no action taken
    """
    if not user:
        return {
            'success': False,
            'message': 'Invalid user',
            'referrer': None,
            'amount': 0
        }
    
    # Check if profile is complete
    if not is_profile_complete(user):
        return {
            'success': False,
            'message': 'Profile not yet complete - bonus will be awarded when all required fields are filled',
            'referrer': None,
            'amount': 0
        }
    
    # Profile is complete, try to award bonus
    return award_referral_signup_bonus(user)
