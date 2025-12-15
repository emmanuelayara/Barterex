"""
Referral rewards system for handling referral bonuses.
Awards credits to referrer when referred user completes specific actions.
"""

from datetime import datetime
from app import db
from models import User, Referral, CreditTransaction, Notification


def award_referral_bonus(referred_user_id, bonus_type, amount=100):
    """
    Award referral bonus credits to the referrer.
    
    Args:
        referred_user_id (int): ID of the user who was referred
        bonus_type (str): Type of bonus - 'signup', 'item_upload', or 'purchase'
        amount (int): Amount of credits to award (default 100)
    
    Returns:
        dict: {
            'success': bool,
            'referrer_id': int or None,
            'amount_awarded': int,
            'message': str
        }
    """
    try:
        # Check if this user was referred
        referral = Referral.query.filter_by(referred_user_id=referred_user_id).first()
        
        if not referral:
            return {
                'success': False,
                'referrer_id': None,
                'amount_awarded': 0,
                'message': 'User was not referred by anyone'
            }
        
        # Determine which bonus flag to check based on bonus_type
        bonus_field_map = {
            'signup': 'signup_bonus_earned',
            'item_upload': 'item_upload_bonus_earned',
            'purchase': 'purchase_bonus_earned'
        }
        
        bonus_field = bonus_field_map.get(bonus_type)
        date_field_map = {
            'item_upload': 'item_upload_bonus_date',
            'purchase': 'purchase_bonus_date'
        }
        date_field = date_field_map.get(bonus_type)
        
        if not bonus_field:
            return {
                'success': False,
                'referrer_id': None,
                'amount_awarded': 0,
                'message': f'Invalid bonus type: {bonus_type}'
            }
        
        # Check if bonus has already been awarded
        if getattr(referral, bonus_field):
            return {
                'success': False,
                'referrer_id': referral.referrer_id,
                'amount_awarded': 0,
                'message': f'{bonus_type.capitalize()} bonus already awarded for this referral'
            }
        
        # Get referrer
        referrer = User.query.get(referral.referrer_id)
        if not referrer:
            return {
                'success': False,
                'referrer_id': None,
                'amount_awarded': 0,
                'message': 'Referrer not found'
            }
        
        # Award credits to referrer
        referrer.credits += amount
        setattr(referral, bonus_field, True)
        
        # Set the date field if it exists
        if date_field:
            setattr(referral, date_field, datetime.utcnow())
        
        # Create credit transaction record
        transaction = CreditTransaction(
            user_id=referrer.id,
            amount=amount,
            transaction_type=f'referral_{bonus_type}_bonus'
        )
        db.session.add(transaction)
        
        # Create notification for referrer
        referred_user = User.query.get(referred_user_id)
        bonus_descriptions = {
            'signup': 'signed up',
            'item_upload': 'uploaded an approved item',
            'purchase': 'made a purchase'
        }
        bonus_desc = bonus_descriptions.get(bonus_type, 'completed an action')
        
        notification = Notification(
            user_id=referrer.id,
            message=f'🎉 Referral bonus earned! {referred_user.username} {bonus_desc}. You earned ₦{amount} credits!',
            notification_type='referral',
            category='reward'
        )
        db.session.add(notification)
        
        # NOTE: Do NOT commit here - let the caller's transaction manager handle commits
        # to ensure all changes (item approval + referral bonus) are atomic
        
        return {
            'success': True,
            'referrer_id': referrer.id,
            'amount_awarded': amount,
            'message': f'{bonus_type.capitalize()} bonus of ₦{amount} awarded to {referrer.username}'
        }
    
    except Exception as e:
        db.session.rollback()
        return {
            'success': False,
            'referrer_id': None,
            'amount_awarded': 0,
            'message': f'Error awarding referral bonus: {str(e)}'
        }
