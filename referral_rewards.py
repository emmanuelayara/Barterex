"""Referral milestones gated by verified customers and settled purchases."""

from datetime import datetime

from flask import current_app

from app import db
from models import User, Referral, CreditTransaction, Notification, Reservation, Order

REFERRAL_MILESTONE_BONUS = 500
BONUS_FIELDS = {
    'signup': 'signup_bonus_earned',
    'item_upload': 'item_upload_bonus_earned',
    'purchase': 'purchase_bonus_earned',
}


def has_qualifying_purchase(user):
    return Reservation.query.join(Order, Order.reservation_id == Reservation.id).filter(
        Reservation.user_id == user.id,
        Reservation.status == 'completed',
        Reservation.purchase_value > 0,
        Order.cancelled.is_(False),
    ).first() is not None


def award_referral_bonus(referred_user_id, bonus_type, amount=REFERRAL_MILESTONE_BONUS):
    """Caller owns the transaction: claim each milestone atomically with its credit."""
    field = BONUS_FIELDS.get(bonus_type)
    if not field:
        raise ValueError('Invalid referral milestone.')
    referral = Referral.query.filter_by(referred_user_id=referred_user_id).first()
    result = {
        'success': False, 'referrer_id': referral.referrer_id if referral else None,
        'amount_awarded': 0, 'message': 'No eligible unpaid referral milestone.',
    }
    if not referral or referral.referrer_id == referred_user_id:
        return result
    friend = db.session.get(User, referred_user_id)
    referrer = db.session.get(User, referral.referrer_id)
    if not friend or not referrer or friend.is_banned or referrer.is_banned:
        return result
    if bonus_type == 'item_upload':
        referral.item_upload_qualified = True
        db.session.flush()
    if (
        not friend.email_verified or not friend.id_verified_at or not friend.verified_identity_hash
        or not has_qualifying_purchase(friend)
    ):
        result['message'] = 'Referral rewards are pending verified identity and a settled purchase.'
        return result
    if bonus_type == 'signup' and not friend.is_profile_complete():
        return result
    if bonus_type == 'item_upload' and not referral.item_upload_qualified:
        return result
    updates = {field: True}
    date_field = {
        'signup': 'signup_bonus_earned_at', 'item_upload': 'item_upload_bonus_date',
        'purchase': 'purchase_bonus_date',
    }[bonus_type]
    updates[date_field] = datetime.utcnow()
    claimed = Referral.query.filter(
        Referral.id == referral.id, getattr(Referral, field).is_(False),
    ).update(updates, synchronize_session='fetch')
    if not claimed:
        return result
    User.query.filter_by(id=referrer.id).update({
        User.credits: User.credits + amount,
        User.referral_bonus_earned: User.referral_bonus_earned + amount,
    }, synchronize_session=False)
    db.session.refresh(referrer)
    db.session.add(CreditTransaction(
        user_id=referrer.id, amount=amount, transaction_type=f'referral_{bonus_type}_bonus',
        description=f'Referral {bonus_type.replace("_", " ")} reward',
        balance_before=referrer.credits - amount, balance_after=referrer.credits,
    ))
    db.session.add(Notification(
        user_id=referrer.id,
        message=f'Referral reward: {friend.username} qualified for the {bonus_type.replace("_", " ")} milestone. You earned {amount} BXC.',
        notification_type='referral', category='reward',
    ))
    current_app.logger.info('Referral milestone awarded: referral=%s milestone=%s amount=%s', referral.id, bonus_type, amount)
    return {
        'success': True, 'referrer_id': referrer.id, 'amount_awarded': amount,
        'message': f'Referral bonus of {amount} BXC awarded.',
    }


def award_pending_referral_bonuses(user):
    """Reevaluate milestones at settlement, profile completion and ID review."""
    referral = Referral.query.filter_by(referred_user_id=user.id).first()
    if not referral:
        return []
    milestones = ['signup', 'purchase']
    if referral.item_upload_qualified:
        milestones.append('item_upload')
    return [award_referral_bonus(user.id, milestone) for milestone in milestones]
