import os
import unittest
from unittest.mock import patch

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from app import app, db
from models import CreditTransaction, Notification, User
from trading_points import (
    LEVEL_THRESHOLDS, award_points_for_purchase, award_points_for_upload,
    create_level_up_notification, get_level_tier,
)


class TradingTierRewardTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.context = app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.user = User(
            username='tier-user', email='tier@example.com', password_hash='test',
            credits=50, level=1, trading_points=0, tier='Beginner',
        )
        db.session.add(self.user)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def prepare_boundary(self, level, points_to_add):
        self.user.level = level - 1
        self.user.tier = get_level_tier(level - 1)
        self.user.trading_points = LEVEL_THRESHOLDS[level] - points_to_add
        db.session.commit()

    def test_all_tier_entries_on_both_award_paths(self):
        for award, points in [(award_points_for_upload, 10), (award_points_for_purchase, 20)]:
            for entry_level in [6, 11, 16, 21]:
                with self.subTest(path=award.__name__, entry_level=entry_level):
                    self.prepare_boundary(entry_level, points)
                    before = self.user.credits
                    result = award(self.user, 'test')
                    db.session.commit()
                    self.assertEqual(self.user.level, entry_level)
                    self.assertEqual(self.user.tier, get_level_tier(entry_level))
                    self.assertEqual(self.user.credits, before + 1300)
                    self.assertEqual(result['credits_awarded'], 1300)
                    self.assertEqual(result['tier_bonus'], 1000)
                    self.assertEqual(result['tiers_entered'], [get_level_tier(entry_level)])
                    tier_transaction = CreditTransaction.query.filter_by(
                        transaction_type='tier_entry_bonus',
                    ).order_by(CreditTransaction.id.desc()).first()
                    self.assertEqual(tier_transaction.amount, 1000)
                    self.assertEqual(tier_transaction.balance_before, before + 300)
                    self.assertEqual(tier_transaction.balance_after, before + 1300)
                    self.assertIn(get_level_tier(entry_level), tier_transaction.description)
                    self.assertIsNone(award(self.user, 'next activity'))
                    db.session.commit()
                    self.assertEqual(self.user.credits, before + 1300)

    def test_same_tier_level_up_retains_300_reward(self):
        for award, points in [(award_points_for_upload, 10), (award_points_for_purchase, 20)]:
            with self.subTest(path=award.__name__):
                self.prepare_boundary(7, points)
                before = self.user.credits
                result = award(self.user, 'test')
                db.session.commit()
                self.assertEqual(result['credits_awarded'], 300)
                self.assertEqual(result['tier_bonus'], 0)
                self.assertEqual(result['tiers_entered'], [])
                self.assertEqual(self.user.credits, before + 300)
        self.assertEqual(CreditTransaction.query.filter_by(transaction_type='tier_entry_bonus').count(), 0)

    def test_starting_beginner_and_max_level_do_not_award_tier_bonus(self):
        self.assertIsNone(award_points_for_upload(self.user, 'first upload'))
        self.user.level = 30
        self.user.tier = 'Expert'
        self.user.trading_points = 15000
        db.session.commit()
        self.assertIsNone(award_points_for_purchase(self.user, 'max level purchase'))
        db.session.commit()
        self.assertEqual(self.user.credits, 50)
        self.assertEqual(CreditTransaction.query.count(), 0)

    def test_tier_bonus_rolls_back_with_points_and_level_reward(self):
        self.prepare_boundary(6, 10)
        award_points_for_upload(self.user, 'test')
        db.session.flush()
        db.session.rollback()
        self.assertEqual(self.user.credits, 50)
        self.assertEqual(self.user.level, 5)
        self.assertEqual(self.user.trading_points, 490)
        self.assertEqual(CreditTransaction.query.count(), 0)

    def test_notification_and_email_show_total_and_tier_bonus(self):
        self.prepare_boundary(6, 20)
        result = award_points_for_purchase(self.user, 'test')
        db.session.commit()
        with app.test_request_context('/'), patch('trading_points.send_email_async') as send:
            create_level_up_notification(self.user, result)
        notification = Notification.query.one()
        self.assertIn('1300 BXC', notification.message)
        self.assertIn('1000', notification.message)
        self.assertLessEqual(len(notification.message), 255)
        self.assertEqual(notification.data['credits_awarded'], 1300)
        self.assertEqual(notification.data['tier_bonus'], 1000)
        send.assert_called_once()
        html = send.call_args.kwargs['html_body']
        self.assertIn('1300 BXC', html)
        self.assertIn('1000 BXC for entering a new tier', html)

    def test_new_tier_uses_level_boundary_not_stale_tier_label(self):
        self.prepare_boundary(6, 10)
        self.user.tier = 'Novice'
        result = award_points_for_upload(self.user, 'test')
        self.assertEqual(result['tier_bonus'], 1000)

    def test_multiple_crossed_tiers_each_receive_bonus(self):
        with patch('trading_points.POINTS_PER_UPLOAD_APPROVAL', 1500):
            result = award_points_for_upload(self.user, 'test')
        db.session.commit()
        self.assertEqual(result['tiers_entered'], ['Novice', 'Intermediate'])
        self.assertEqual(result['tier_bonus'], 2000)
        self.assertEqual(result['credits_awarded'], 2300)
        self.assertEqual(self.user.credits, 2350)
        self.assertEqual(CreditTransaction.query.filter_by(transaction_type='tier_entry_bonus').count(), 2)
