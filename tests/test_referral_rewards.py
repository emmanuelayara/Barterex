import os
import unittest

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from app import app, db
from models import CreditTransaction, Notification, Referral, User
from referral_rewards import REFERRAL_MILESTONE_BONUS, award_referral_bonus
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

    def test_each_milestone_awards_500_once(self):
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
