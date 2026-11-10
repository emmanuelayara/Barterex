import os
import unittest
from datetime import datetime, timedelta

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from app import app, db
from models import CreditTransaction, Notification, Referral, User, Item, Reservation, Order
from referral_rewards import REFERRAL_MILESTONE_BONUS, award_referral_bonus, award_pending_referral_bonuses
from referral_utils import check_and_award_pending_bonuses


class ReferralRewardTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.context = app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.referrer = User(
            username='referrer', email='referrer@example.com',
            password_hash='test', credits=0, referral_bonus_earned=0,
        )
        self.friend = User(
            username='friend', email='friend@example.com', password_hash='test',
            credits=0, phone_number='12345', address='Test road',
            city='Lagos', state='Lagos',
        )
        db.session.add_all([self.referrer, self.friend])
        db.session.flush()
        self.referral = Referral(
            referrer_id=self.referrer.id, referred_user_id=self.friend.id,
            referral_code_used='TEST',
        )
        db.session.add(self.referral)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def qualify_friend(self):
        self.friend.email_verified = True
        self.friend.id_verified_at = datetime.utcnow()
        self.friend.verified_identity_hash = 'a' * 64
        item = Item(name='Purchased item', category='Electronics', user_id=self.referrer.id, value=500)
        db.session.add(item)
        db.session.flush()
        reservation = Reservation(
            user_id=self.friend.id, item_id=item.id, provisional_credits_used=0,
            purchase_value=500, status='completed', expires_at=datetime.utcnow() + timedelta(days=1),
        )
        db.session.add(reservation)
        db.session.flush()
        db.session.add(Order(
            user_id=self.friend.id, reservation_id=reservation.id, order_number='REF-QUALIFIED',
            total_credits=500, credits_used=500, delivery_method='pickup',
        ))
        db.session.commit()

    def test_each_milestone_awards_500_once(self):
        self.qualify_friend()
        self.assertEqual(REFERRAL_MILESTONE_BONUS, 500)
        signup = check_and_award_pending_bonuses(self.friend)
        self.assertTrue(signup['success'])
        self.assertEqual(signup['amount'], 500)
        self.assertEqual(self.referrer.referral_bonus_earned, 500)
        self.assertFalse(check_and_award_pending_bonuses(self.friend)['success'])
        for milestone in ['item_upload', 'purchase']:
            with self.subTest(milestone=milestone):
                result = award_referral_bonus(self.friend.id, milestone)
                self.assertTrue(result['success'])
                self.assertEqual(result['amount_awarded'], 500)
                db.session.commit()
                self.assertFalse(award_referral_bonus(self.friend.id, milestone)['success'])
        self.assertEqual(self.referrer.credits, 1500)
        self.assertEqual(self.friend.credits, 0)
        self.assertEqual(CreditTransaction.query.count(), 3)
        self.assertEqual({row.amount for row in CreditTransaction.query.all()}, {500})
        self.assertEqual(Notification.query.count(), 3)
        for notification in Notification.query.all():
            self.assertIn('500', notification.message)
        self.assertTrue(self.referral.signup_bonus_earned)
        self.assertTrue(self.referral.item_upload_bonus_earned)
        self.assertTrue(self.referral.purchase_bonus_earned)
        self.assertIsNotNone(self.referral.signup_bonus_earned_at)
        self.assertIsNotNone(self.referral.item_upload_bonus_date)
        self.assertIsNotNone(self.referral.purchase_bonus_date)

    def test_existing_paid_milestone_is_not_topped_up(self):
        self.qualify_friend()
        self.referral.signup_bonus_earned = True
        self.referrer.credits = 100
        db.session.add(CreditTransaction(
            user_id=self.referrer.id, amount=100, transaction_type='referral_signup_bonus',
        ))
        db.session.commit()
        self.assertFalse(check_and_award_pending_bonuses(self.friend)['success'])
        self.assertFalse(award_referral_bonus(self.friend.id, 'signup')['success'])
        self.assertEqual(self.referrer.credits, 100)
        result = award_referral_bonus(self.friend.id, 'purchase')
        db.session.commit()
        self.assertEqual(result['amount_awarded'], 500)
        self.assertEqual(self.referrer.credits, 600)
        self.assertEqual(sorted(row.amount for row in CreditTransaction.query.all()), [100, 500])

    def test_incomplete_profile_does_not_award_bonus(self):
        self.friend.address = None
        db.session.commit()
        self.assertFalse(check_and_award_pending_bonuses(self.friend)['success'])
        self.assertEqual(self.referrer.credits, 0)
        self.assertEqual(CreditTransaction.query.count(), 0)

    def test_profile_and_approval_wait_for_identity_and_settlement(self):
        self.assertFalse(check_and_award_pending_bonuses(self.friend)['success'])
        self.assertFalse(award_referral_bonus(self.friend.id, 'item_upload')['success'])
        db.session.commit()
        self.assertTrue(self.referral.item_upload_qualified)
        self.assertFalse(self.referral.item_upload_bonus_earned)
        self.assertEqual(self.referrer.credits, 0)
        self.qualify_friend()
        award_pending_referral_bonuses(self.friend)
        db.session.commit()
        self.assertEqual(self.referrer.credits, 1500)
        award_pending_referral_bonuses(self.friend)
        db.session.commit()
        self.assertEqual(self.referrer.credits, 1500)

    def test_cancelled_purchase_does_not_qualify(self):
        self.qualify_friend()
        Order.query.one().cancelled = True
        db.session.commit()
        self.assertFalse(award_referral_bonus(self.friend.id, 'purchase')['success'])
        self.assertEqual(self.referrer.credits, 0)

    def test_unverified_or_banned_customer_does_not_qualify(self):
        self.qualify_friend()
        self.friend.id_verified_at = None
        db.session.commit()
        self.assertFalse(award_referral_bonus(self.friend.id, 'purchase')['success'])
        self.friend.id_verified_at = datetime.utcnow()
        self.friend.is_banned = True
        db.session.commit()
        self.assertFalse(award_referral_bonus(self.friend.id, 'purchase')['success'])
