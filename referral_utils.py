"""Profile eligibility and compatibility helpers for referral rewards."""

from app import db
from models import User
from referral_rewards import award_referral_bonus


def is_profile_complete(user):
    return bool(user and all(
        value and str(value).strip()
        for value in [user.email, user.phone_number, user.address, user.city, user.state]
    ))


def award_referral_signup_bonus(referred_user):
    if not referred_user or not is_profile_complete(referred_user):
        return {'success': False, 'message': 'Profile is incomplete.', 'referrer': None, 'amount': 0}
    result = award_referral_bonus(referred_user.id, 'signup')
    db.session.commit()
    return {
        'success': result['success'], 'message': result['message'],
        'referrer': db.session.get(User, result['referrer_id']) if result['referrer_id'] else None,
        'amount': result['amount_awarded'],
    }


def check_and_award_pending_bonuses(user):
    return award_referral_signup_bonus(user)
