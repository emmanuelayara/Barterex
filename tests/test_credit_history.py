import os
import unittest
from datetime import datetime, timedelta

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from app import app, db
from models import (
    CreditTransaction,
    Item,
    Payment,
    Reservation,
    ReservationCreditEntry,
    User,
)


class CreditHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        )

    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()

        self.user = User(
            username='history-user',
            email='history@example.com',
            password_hash='test-hash',
            credits=450,
            provisional_credits=75,
        )
        seller = User(
            username='history-seller',
            email='seller-history@example.com',
            password_hash='test-hash',
        )
        db.session.add_all([self.user, seller])
        db.session.flush()
        self.item = Item(
            name='History item',
            category='Electronics',
            user_id=seller.id,
            status='approved',
            is_approved=True,
            is_available=False,
            value=125,
        )
        db.session.add(self.item)
        db.session.flush()
        self.reservation = Reservation(
            user_id=self.user.id,
            item_id=self.item.id,
            provisional_credits_used=0,
            purchase_value=125,
            spendable_credits_held=125,
            clearing_mode='company_inventory',
            funding_mode='spendable',
            delivery_method='home delivery',
            delivery_address='12 Test Street, Lagos',
            delivery_quote_naira=250,
            delivery_fee_status='awaiting_payment',
            status='active',
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        db.session.add(self.reservation)
        db.session.flush()
        db.session.add_all([
            CreditTransaction(
                user_id=self.user.id,
                amount=50,
                transaction_type='admin_credit',
                reason='admin_credit',
                description='Account adjustment',
                balance_before=400,
                balance_after=450,
            ),
            ReservationCreditEntry(
                reservation_id=self.reservation.id,
                user_id=self.user.id,
                item_id=self.item.id,
                balance_type='spendable_held',
                entry_type='hold',
                amount=125,
                balance_before=0,
                balance_after=125,
            ),
            Payment(
                user_id=self.user.id,
                amount_naira=250,
                credits_purchased=0,
                status='pending',
                purpose='reservation_delivery_fee',
                reservation_id=self.reservation.id,
                paystack_reference='delivery-ref-123',
            ),
        ])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_history_shows_separate_current_balances_and_pending_status(self):
        client = app.test_client()
        with client.session_transaction() as flask_session:
            flask_session['_user_id'] = str(self.user.id)
            flask_session['_fresh'] = True

        response = client.get('/credit-history')

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn('Spendable BXC available', page)
        self.assertIn('ᗸ450', page)
        self.assertIn('Provisional BXC available', page)
        self.assertIn('ᗸ75', page)
        self.assertIn('Spendable BXC on hold', page)
        self.assertIn('ᗸ125', page)
        self.assertIn('Your Balance Before:', page)
        self.assertIn('Payment Status', page)
        self.assertIn('Awaiting payment', page)
        self.assertIn('Reservation active · verification pending', page)
        self.assertIn('Home fee:', page)
        self.assertIn('Awaiting Payment', page)
        self.assertIn('₦250.00', page)

    def test_zero_balance_snapshot_is_not_reported_as_missing(self):
        transaction = CreditTransaction(
            user_id=self.user.id,
            amount=10,
            transaction_type='credit',
            reason='test_zero',
            balance_before=0,
            balance_after=10,
        )
        db.session.add(transaction)
        db.session.commit()
        client = app.test_client()
        with client.session_transaction() as flask_session:
            flask_session['_user_id'] = str(self.user.id)
            flask_session['_fresh'] = True

        response = client.get('/credit-history')
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('ᗸ0', page)
        self.assertNotIn('<em>Not recorded</em>', page)


if __name__ == '__main__':
    unittest.main()
