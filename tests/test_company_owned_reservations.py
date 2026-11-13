import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import requests
from flask import g

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from app import app, db, limiter
from models import (
    ClearingInventoryItem,
    CreditTransaction,
    Item,
    Order,
    Payment,
    PickupStation,
    Reservation,
    ReservationAsset,
    Trade,
    User,
)
from services.reservation_service import (
    cancel_reservation,
    create_reservation,
    release_expired_reservations,
    verify_backing_asset,
)
from paystack_payment_service import PaystackPaymentService


class CompanyOwnedReservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            WTF_CSRF_ENABLED=False,
        )

    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()
        self.notification_patches = [
            patch('services.reservation_service._notice'),
            patch('services.reservation_service.notify_admins'),
        ]
        for notification_patch in self.notification_patches:
            notification_patch.start()
        self.previous_limiter = limiter.enabled
        limiter.enabled = False

    def tearDown(self):
        for notification_patch in self.notification_patches:
            notification_patch.stop()
        limiter.enabled = self.previous_limiter
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _create_company_item(self, buyer_credits=0, buyer_provisional=0):
        buyer = User(
            username='company-buyer',
            email='company-buyer@example.com',
            password_hash='test-hash',
            credits=buyer_credits,
            provisional_credits=buyer_provisional,
        )
        former_owner = User(
            username='former-owner',
            email='former-owner@example.com',
            password_hash='test-hash',
            credits=0,
            provisional_credits=0,
        )
        db.session.add_all([buyer, former_owner])
        db.session.flush()

        company_item = Item(
            name='Company-owned item',
            category='Electronics',
            user_id=None,
            owner_type='barterex',
            value=250,
            status='approved',
            is_approved=True,
            is_available=True,
            provisional_credit_settled=True,
        )
        inventory_record = ClearingInventoryItem(
            item=company_item,
            source_user_id=former_owner.id,
            acquisition_value=250,
            status='held_for_resale',
        )
        db.session.add_all([company_item, inventory_record])
        db.session.commit()
        return buyer, former_owner, company_item, inventory_record

    def _create_backing_item(self, buyer, value=250):
        backing_item = Item(
            name='Buyer backing item',
            category='Electronics',
            user_id=buyer.id,
            value=value,
            status='approved',
            is_approved=True,
            is_available=True,
            provisional_credit_amount=value,
            provisional_credit_settled=False,
        )
        db.session.add(backing_item)
        db.session.commit()
        return backing_item

    def _home_reservation(self):
        buyer, former_owner, item, inventory = self._create_company_item(buyer_credits=500)
        reservation, error = create_reservation(
            buyer, item, [], funding_mode='spendable', delivery_method='home delivery',
            delivery_address='12 Test Street, Lagos',
        )
        self.assertIsNone(error)
        self.assertEqual(reservation.status, 'active')
        self.assertEqual(reservation.delivery_quote_naira, 5000)
        self.assertEqual(reservation.delivery_fee_status, 'awaiting_payment')
        self.assertEqual(Order.query.count(), 0)
        self.assertEqual(item.owner_type, 'barterex')
        self.assertEqual(inventory.status, 'held_for_resale')
        return buyer, former_owner, item, inventory, reservation

    def _login(self, buyer):
        g.pop('_login_user', None)
        client = app.test_client()
        with client.session_transaction() as session:
            session['_user_id'] = str(buyer.id)
            session['_fresh'] = True
        return client

    def test_home_company_purchase_settles_once_only_after_payment(self):
        buyer, former_owner, item, inventory, reservation = self._home_reservation()
        with patch.object(PaystackPaymentService, 'TEST_MODE', True), patch(
            'trading_points.award_points_for_purchase', return_value=None
        ) as points:
            initiated = PaystackPaymentService.initiate_delivery_fee_payment(reservation, buyer)
            payment = db.session.get(Payment, initiated['payment_id'])
            result = PaystackPaymentService.verify_payment(payment.paystack_reference)
            repeated = PaystackPaymentService.verify_payment(payment.paystack_reference)
        self.assertTrue(result['success'])
        self.assertTrue(repeated['success'])
        self.assertEqual(result['credits_added'], 0)
        self.assertEqual(points.call_count, 1)
        self.assertEqual(reservation.status, 'completed')
        self.assertEqual(reservation.delivery_fee_status, 'paid')
        self.assertEqual(buyer.credits, 250)
        self.assertEqual(former_owner.credits, 0)
        self.assertEqual(item.user_id, buyer.id)
        self.assertEqual(inventory.status, 'sold')
        self.assertEqual(Order.query.count(), 1)
        self.assertEqual(Order.query.one().logistics_fee_naira, 5000)
        self.assertEqual(CreditTransaction.query.filter_by(reason='reservation_purchase').count(), 1)
        self.assertEqual(CreditTransaction.query.filter_by(reason='paystack_payment').count(), 0)

    def test_home_reservation_route_immediately_redirects_to_payment(self):
        buyer, former_owner, item, inventory = self._create_company_item(buyer_credits=500)
        client = self._login(buyer)
        with patch.object(User, 'is_profile_complete', return_value=True), patch.object(
            PaystackPaymentService, 'TEST_MODE', True
        ):
            response = client.post(f'/item/{item.id}/reserve', data={
                'funding_mode': 'spendable', 'delivery_method': 'home delivery',
                'delivery_address': '12 Test Street, Lagos', 'amount_naira': '100',
            })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/payments/verify-payment/TEST_', response.location)
        payment = Payment.query.one()
        self.assertEqual(payment.amount_naira, 5000)
        self.assertEqual(payment.credits_purchased, 0)
        self.assertEqual(payment.purpose, 'reservation_delivery_fee')
        self.assertEqual(Reservation.query.one().status, 'active')
        self.assertEqual(Order.query.count(), 0)

    def test_station_reservation_route_requires_no_payment(self):
        buyer, former_owner, item, inventory = self._create_company_item(buyer_credits=500)
        buyer.state = 'Lagos'
        station = PickupStation(name='Test Station', state='Lagos', city='Ikeja', address='Test Address')
        db.session.add(station)
        db.session.commit()
        client = self._login(buyer)
        with patch.object(User, 'is_profile_complete', return_value=True), patch.object(
            PaystackPaymentService, 'initiate_delivery_fee_payment'
        ) as initialize:
            response = client.post(f'/item/{item.id}/reserve', data={
                'funding_mode': 'spendable', 'delivery_method': 'pickup',
                'pickup_station_id': station.id,
            })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/my_orders', response.location)
        initialize.assert_not_called()
        self.assertEqual(Payment.query.count(), 0)
        self.assertEqual(Reservation.query.one().delivery_fee_status, 'not_required')
        self.assertIsNone(Reservation.query.one().delivery_quote_naira)

    def test_home_initialization_failure_preserves_reservation_and_retry(self):
        buyer, former_owner, item, inventory = self._create_company_item(buyer_credits=500)
        client = self._login(buyer)
        with patch.object(User, 'is_profile_complete', return_value=True), patch.object(
            PaystackPaymentService, 'initiate_delivery_fee_payment',
            return_value={'success': False, 'error': 'Payment gateway unavailable'},
        ):
            response = client.post(f'/item/{item.id}/reserve', data={
                'funding_mode': 'spendable', 'delivery_method': 'home delivery',
                'delivery_address': '12 Test Street, Lagos',
            })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/my_reservations', response.location)
        reservation = Reservation.query.one()
        self.assertEqual(reservation.status, 'active')
        self.assertEqual(reservation.delivery_fee_status, 'awaiting_payment')
        page = client.get(response.location)
        self.assertIn(b'Payment gateway unavailable', page.data)
        self.assertIn(b'Pay home-service fee', page.data)
        with patch.object(PaystackPaymentService, 'TEST_MODE', True):
            retried = client.post(f'/reservation/{reservation.id}/delivery-fee')
        self.assertEqual(retried.status_code, 302)
        self.assertIn('/payments/verify-payment/TEST_', retried.location)

    def test_home_live_initialization_charges_exact_kobo_and_reuses_link(self):
        buyer, _, _, _, reservation = self._home_reservation()
        response = Mock(status_code=200, text='mock')
        response.json.return_value = {'status': True, 'data': {
            'authorization_url': 'https://checkout.paystack.com/test',
        }}
        with patch.object(PaystackPaymentService, 'TEST_MODE', False), patch.object(
            PaystackPaymentService, 'get_auth_header', return_value={}
        ), patch('paystack_payment_service.requests.post', return_value=response) as post:
            initiated = PaystackPaymentService.initiate_delivery_fee_payment(reservation, buyer)
            retried = PaystackPaymentService.initiate_delivery_fee_payment(reservation, buyer)
        self.assertTrue(initiated['success'])
        self.assertEqual(initiated['payment_link'], retried['payment_link'])
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs['json']['amount'], 500000)
        self.assertEqual(post.call_args.kwargs['json']['currency'], 'NGN')
        self.assertTrue(initiated['reference'].startswith(f'barterxpress_delivery_{reservation.id}_'))
        self.assertEqual(post.call_args.kwargs['json']['reference'], initiated['reference'])
        self.assertEqual(Payment.query.count(), 1)

    def test_unknown_initialization_outcome_does_not_create_second_charge(self):
        buyer, _, _, _, reservation = self._home_reservation()
        with patch.object(PaystackPaymentService, 'TEST_MODE', False), patch.object(
            PaystackPaymentService, 'get_auth_header', return_value={}
        ), patch('paystack_payment_service.requests.post', side_effect=requests.Timeout('mock')) as post:
            result = PaystackPaymentService.initiate_delivery_fee_payment(reservation, buyer)
            retry = PaystackPaymentService.initiate_delivery_fee_payment(reservation, buyer)
        self.assertFalse(result['success'])
        self.assertFalse(retry['success'])
        self.assertEqual(post.call_count, 1)
        self.assertEqual(Payment.query.count(), 1)
        self.assertEqual(Payment.query.one().status, 'pending')

    def test_late_payment_does_not_reopen_cancelled_or_expired_reservation(self):
        for status in ('cancelled', 'expired'):
            with self.subTest(status=status):
                db.session.remove()
                db.drop_all()
                db.create_all()
                buyer, former_owner, item, inventory, reservation = self._home_reservation()
                with patch.object(PaystackPaymentService, 'TEST_MODE', True):
                    initiated = PaystackPaymentService.initiate_delivery_fee_payment(reservation, buyer)
                    if status == 'cancelled':
                        ok, error = cancel_reservation(reservation, buyer)
                        self.assertTrue(ok, error)
                    else:
                        reservation.expires_at = datetime.utcnow() - timedelta(seconds=1)
                        db.session.commit()
                    with patch('paystack_payment_service.notify_admins') as admins:
                        result = PaystackPaymentService.verify_payment(initiated['reference'])
                        repeated = PaystackPaymentService.verify_payment(initiated['reference'])
                self.assertTrue(result['success'])
                self.assertTrue(repeated['success'])
                admins.assert_called_once()
                self.assertEqual(reservation.status, status)
                self.assertEqual(reservation.delivery_fee_status, 'paid')
                self.assertEqual(buyer.credits, 500)
                self.assertEqual(Order.query.count(), 0)
                self.assertEqual(item.owner_type, 'barterex')
                self.assertTrue(item.is_available)
                self.assertEqual(inventory.status, 'held_for_resale')
                self.assertFalse(PaystackPaymentService.initiate_delivery_fee_payment(reservation, buyer)['success'])

    def test_home_fee_rejects_other_user_and_amount_mismatch(self):
        buyer, former_owner, _, _, reservation = self._home_reservation()
        self.assertFalse(PaystackPaymentService.initiate_delivery_fee_payment(
            reservation, former_owner
        )['success'])
        with patch.object(PaystackPaymentService, 'TEST_MODE', True):
            initiated = PaystackPaymentService.initiate_delivery_fee_payment(reservation, buyer)
            payment = db.session.get(Payment, initiated['payment_id'])
            payment.amount_naira = 100
            db.session.commit()
            retry = PaystackPaymentService.initiate_delivery_fee_payment(reservation, buyer)
            self.assertFalse(retry['success'])
            with self.assertRaisesRegex(ValueError, 'does not match'):
                PaystackPaymentService._complete_delivery_fee_payment(payment, 'test_card')
        self.assertEqual(reservation.delivery_fee_status, 'awaiting_payment')
        self.assertEqual(Order.query.count(), 0)

    def test_live_verification_rejects_wrong_currency_or_amount(self):
        buyer, _, _, _, reservation = self._home_reservation()
        payment = Payment(
            user_id=buyer.id, amount_naira=5000, credits_purchased=0,
            status='pending', purpose='reservation_delivery_fee',
            reservation_id=reservation.id, paystack_reference='mock-home-fee',
        )
        db.session.add(payment)
        db.session.commit()
        for currency, amount in (('USD', 500000), ('NGN', 499999)):
            with self.subTest(currency=currency, amount=amount):
                response = Mock(status_code=200, text='mock')
                response.json.return_value = {'status': True, 'data': {
                    'status': 'success', 'currency': currency, 'amount': amount,
                }}
                with patch.object(PaystackPaymentService, 'TEST_MODE', False), patch.object(
                    PaystackPaymentService, 'get_auth_header', return_value={}
                ), patch('paystack_payment_service.requests.get', return_value=response):
                    result = PaystackPaymentService.verify_payment(payment.paystack_reference)
                self.assertFalse(result['success'])
                self.assertEqual(reservation.delivery_fee_status, 'awaiting_payment')
                self.assertEqual(reservation.status, 'active')
                self.assertEqual(Order.query.count(), 0)

    def test_spendable_purchase_completes_without_payment_to_former_owner(self):
        buyer, former_owner, item, inventory_record = self._create_company_item(
            buyer_credits=500
        )

        with patch('trading_points.award_points_for_purchase', return_value=None):
            reservation, error = create_reservation(
                buyer, item, [], funding_mode='spendable'
            )

        self.assertIsNone(error)
        db.session.refresh(buyer)
        db.session.refresh(former_owner)
        db.session.refresh(item)
        db.session.refresh(inventory_record)
        self.assertEqual(reservation.status, 'completed')
        self.assertEqual(buyer.credits, 250)
        self.assertEqual(former_owner.credits, 0)
        self.assertEqual(former_owner.provisional_credits, 0)
        self.assertEqual(
            CreditTransaction.query.filter_by(user_id=former_owner.id).count(), 0
        )
        self.assertEqual(CreditTransaction.query.filter_by(
            user_id=buyer.id, reason='reservation_purchase'
        ).count(), 1)
        self.assertEqual(item.user_id, buyer.id)
        self.assertEqual(item.owner_type, 'user')
        self.assertFalse(item.is_available)
        self.assertEqual(inventory_record.status, 'sold')
        self.assertEqual(inventory_record.source_user_id, former_owner.id)
        self.assertIsNone(inventory_record.reservation_asset_id)
        self.assertEqual(Order.query.filter_by(reservation_id=reservation.id).count(), 1)
        self.assertEqual(Trade.query.filter_by(item_id=item.id).count(), 0)

    def test_item_backed_purchase_settles_after_backing_verification(self):
        buyer, former_owner, item, inventory_record = self._create_company_item(
            buyer_credits=80,
            buyer_provisional=250,
        )
        backing_item = self._create_backing_item(buyer)
        reservation, error = create_reservation(
            buyer,
            item,
            [backing_item.id],
            funding_mode='item_backed',
            consent_confirmed=True,
        )
        self.assertIsNone(error)
        self.assertEqual(reservation.status, 'active')
        self.assertEqual(reservation.seller_item_verification_status, 'passed')

        with patch('trading_points.award_points_for_purchase', return_value=None):
            ok, error = verify_backing_asset(
                ReservationAsset.query.filter_by(reservation_id=reservation.id).one(),
                passed=True,
            )

        self.assertTrue(ok, error)
        db.session.refresh(buyer)
        db.session.refresh(former_owner)
        db.session.refresh(item)
        db.session.refresh(inventory_record)
        self.assertEqual(reservation.status, 'completed')
        self.assertEqual(buyer.credits, 80)
        self.assertEqual(buyer.provisional_credits, 0)
        self.assertEqual(former_owner.credits, 0)
        self.assertEqual(
            CreditTransaction.query.filter_by(user_id=former_owner.id).count(), 0
        )
        self.assertEqual(CreditTransaction.query.filter_by(
            user_id=buyer.id, reason='reservation_purchase'
        ).count(), 1)
        self.assertEqual(item.user_id, buyer.id)
        self.assertEqual(inventory_record.status, 'sold')
        self.assertEqual(inventory_record.source_user_id, former_owner.id)
        self.assertEqual(Trade.query.filter_by(item_id=item.id).count(), 0)
        self.assertEqual(Order.query.filter_by(reservation_id=reservation.id).count(), 1)

    def test_cancellation_releases_funding_and_relists_company_item(self):
        buyer, former_owner, item, inventory_record = self._create_company_item(
            buyer_credits=50,
            buyer_provisional=250,
        )
        backing_item = self._create_backing_item(buyer)
        reservation, error = create_reservation(
            buyer,
            item,
            [backing_item.id],
            funding_mode='item_backed',
            consent_confirmed=True,
        )
        self.assertIsNone(error)

        ok, error = cancel_reservation(reservation, buyer)

        self.assertTrue(ok, error)
        db.session.refresh(buyer)
        db.session.refresh(item)
        db.session.refresh(backing_item)
        db.session.refresh(inventory_record)
        self.assertEqual(reservation.status, 'cancelled')
        self.assertEqual(buyer.provisional_credits, 250)
        self.assertEqual(item.owner_type, 'barterex')
        self.assertIsNone(item.user_id)
        self.assertTrue(item.is_available)
        self.assertEqual(inventory_record.status, 'held_for_resale')
        self.assertIsNone(inventory_record.reservation_id)
        self.assertIsNone(inventory_record.reservation_asset_id)
        self.assertTrue(backing_item.is_available)
        self.assertIsNone(backing_item.locked_for_reservation_id)
        self.assertEqual(former_owner.id, inventory_record.source_user_id)

    def test_expiry_releases_funding_and_relists_company_item(self):
        buyer, former_owner, item, inventory_record = self._create_company_item(
            buyer_credits=50,
            buyer_provisional=250,
        )
        backing_item = self._create_backing_item(buyer)
        reservation, error = create_reservation(
            buyer,
            item,
            [backing_item.id],
            funding_mode='item_backed',
            consent_confirmed=True,
        )
        self.assertIsNone(error)
        reservation.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()

        self.assertEqual(release_expired_reservations(item_id=item.id), 1)

        db.session.refresh(buyer)
        db.session.refresh(item)
        db.session.refresh(backing_item)
        db.session.refresh(inventory_record)
        self.assertEqual(reservation.status, 'expired')
        self.assertEqual(buyer.provisional_credits, 250)
        self.assertEqual(item.owner_type, 'barterex')
        self.assertTrue(item.is_available)
        self.assertEqual(inventory_record.status, 'held_for_resale')
        self.assertTrue(backing_item.is_available)
        self.assertEqual(former_owner.id, inventory_record.source_user_id)

    def test_failed_backing_verification_releases_company_item_for_resale(self):
        buyer, former_owner, item, inventory_record = self._create_company_item(
            buyer_credits=50,
            buyer_provisional=250,
        )
        backing_item = self._create_backing_item(buyer)
        reservation, error = create_reservation(
            buyer,
            item,
            [backing_item.id],
            funding_mode='item_backed',
            consent_confirmed=True,
        )
        self.assertIsNone(error)
        asset = ReservationAsset.query.filter_by(reservation_id=reservation.id).one()

        ok, error = verify_backing_asset(asset, passed=False)

        self.assertTrue(ok, error)
        db.session.refresh(buyer)
        db.session.refresh(item)
        db.session.refresh(inventory_record)
        self.assertEqual(reservation.status, 'cancelled')
        self.assertEqual(buyer.provisional_credits, 250)
        self.assertEqual(item.owner_type, 'barterex')
        self.assertTrue(item.is_available)
        self.assertEqual(inventory_record.status, 'held_for_resale')
        self.assertEqual(former_owner.id, inventory_record.source_user_id)


if __name__ == '__main__':
    unittest.main()
