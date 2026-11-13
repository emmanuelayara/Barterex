import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from app import app, db, limiter
from models import Admin, CreditTransaction, Item, Order, Payment, User, PickupStation, Reservation
from paystack_payment_service import PaystackPaymentService
from services.reservation_service import (
    accept_final_terms, calculate_service_fee, create_reservation,
    release_expired_reservations, verify_seller_item, verify_backing_asset,
    send_reservation_deadline_reminders, _settle_reservation,
)


class ServiceFeeTests(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        self.old_csrf = app.config['WTF_CSRF_ENABLED']
        app.config['WTF_CSRF_ENABLED'] = False
        self.old_limiter = limiter.enabled
        limiter.enabled = False
        db.drop_all()
        db.create_all()
        self.buyer = User(username='fee-buyer', email='fee@example.com', password_hash='test',
                          credits=500000, provisional_credits=0, state='Lagos')
        self.seller = User(username='fee-seller', email='seller@example.com', password_hash='test',
                           credits=0, provisional_credits=100000)
        db.session.add_all([self.buyer, self.seller])
        db.session.flush()
        self.item = Item(name='Fee test item', category='Electronics', user_id=self.seller.id,
                         value=100000, status='approved', is_approved=True, is_available=True,
                         provisional_credit_amount=100000, provisional_credit_settled=False)
        db.session.add(self.item)
        db.session.commit()
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.buyer.id)
            session['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        limiter.enabled = self.old_limiter
        app.config['WTF_CSRF_ENABLED'] = self.old_csrf
        self.context.pop()

    def reserve(self, verified=False):
        reservation, error = create_reservation(self.buyer, self.item, [], funding_mode='spendable')
        self.assertIsNone(error)
        if verified:
            ok, error = verify_seller_item(reservation, passed=True)
            self.assertTrue(ok, error)
        return reservation

    def accept(self, reservation):
        ok, error = accept_final_terms(reservation, self.buyer, str(reservation.purchase_value),
                                       f'{reservation.service_fee_naira:.2f}')
        self.assertTrue(ok, error)

    def initialize(self, reservation):
        self.accept(reservation)
        with patch.object(PaystackPaymentService, 'TEST_MODE', True):
            result = PaystackPaymentService.initiate_service_fee_payment(reservation, self.buyer)
        self.assertTrue(result['success'], result)
        return result

    def test_fee_boundaries_and_rounding(self):
        for value, expected in [(1, '1000'), (19999, '1000'), (20000, '1000'),
                                (20001, '1000.05'), (100000, '5000'), (200000, '10000'),
                                (300000, '10000'), ('24691.3', '1234.57')]:
            with self.subTest(value=value):
                self.assertEqual(calculate_service_fee(value), Decimal(expected))
        for value in (0, -1, 'NaN', 'Infinity'):
            with self.subTest(invalid=value), self.assertRaises(ValueError):
                calculate_service_fee(value)

    def test_verification_starts_48_hour_window_without_settling(self):
        reservation = self.reserve()
        self.assertEqual(reservation.service_fee_naira, 5000)
        self.assertEqual(reservation.service_fee_status, 'awaiting_verification')
        self.assertIsNone(reservation.order)
        ok, error = accept_final_terms(reservation, self.buyer, '100000', '5000.00')
        self.assertFalse(ok)
        with patch.object(PaystackPaymentService, 'TEST_MODE', True):
            self.assertFalse(PaystackPaymentService.initiate_service_fee_payment(reservation, self.buyer)['success'])
        before = datetime.utcnow()
        verify_seller_item(reservation, passed=True)
        self.assertEqual(reservation.service_fee_status, 'awaiting_acceptance')
        self.assertTrue(before + timedelta(hours=48) <= reservation.expires_at <= datetime.utcnow() + timedelta(hours=48))
        self.assertEqual(reservation.order.status, 'Awaiting Final Acceptance')
        self.assertEqual(reservation.order.credits_used, 0)
        self.assertEqual(self.item.user_id, self.seller.id)
        self.assertEqual(self.seller.credits, 0)
        with self.assertRaises(ValueError):
            _settle_reservation(reservation)

    def test_card_and_transfer_checkout_uses_saved_email_amount_and_same_link(self):
        reservation = self.reserve(verified=True)
        self.accept(reservation)
        response = Mock(status_code=200, text='mock')
        response.json.return_value = {'status': True, 'data': {
            'authorization_url': 'https://checkout.paystack.com/service-fee',
        }}
        with patch.object(PaystackPaymentService, 'TEST_MODE', False), \
             patch.object(PaystackPaymentService, 'get_auth_header', return_value={}), \
             patch('paystack_payment_service.requests.post', return_value=response) as post, \
             patch('paystack_payment_service.notify_user') as email:
            first = PaystackPaymentService.initiate_service_fee_payment(reservation, self.buyer)
            repeated = PaystackPaymentService.initiate_service_fee_payment(reservation, self.buyer)
        self.assertEqual(first, repeated)
        post.assert_called_once()
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['email'], self.buyer.email)
        self.assertEqual(payload['amount'], 500000)
        self.assertEqual(payload['channels'], ['card', 'bank_transfer'])
        self.assertTrue(payload['reference'].startswith('barterxpress_service_'))
        self.assertEqual(payload['metadata']['order_id'], reservation.order.id)
        self.assertEqual(Payment.query.one().credits_purchased, 0)
        self.assertEqual(Payment.query.one().purpose, 'reservation_service_fee')
        email.assert_called_once()
        self.assertEqual(email.call_args.kwargs['cta_url'], first['payment_link'])
        page = self.client.get(f'/order/{reservation.order.id}')
        self.assertIn(first['payment_link'].encode(), page.data)
        self.assertNotIn(b'Download Receipt', page.data)

    def test_verified_payment_settles_exactly_once_and_never_credits_wallet(self):
        reservation = self.reserve(verified=True)
        result = self.initialize(reservation)
        with patch.object(PaystackPaymentService, 'TEST_MODE', True), \
             patch('trading_points.award_points_for_purchase', return_value=None):
            first = PaystackPaymentService.verify_payment(result['reference'])
            second = PaystackPaymentService.verify_payment(result['reference'])
        self.assertTrue(first['success'], first)
        self.assertTrue(second['success'])
        self.assertEqual(first['credits_added'], 0)
        self.assertEqual(self.buyer.credits, 400000)
        self.assertEqual(self.seller.credits, 100000)
        self.assertEqual(reservation.status, 'completed')
        self.assertEqual(reservation.service_fee_status, 'paid')
        self.assertEqual(self.item.user_id, self.buyer.id)
        self.assertEqual(Order.query.count(), 1)
        self.assertEqual(reservation.order.status, 'Pending')
        self.assertEqual(len(reservation.order.items), 1)
        self.assertEqual(CreditTransaction.query.filter_by(reason='reservation_purchase').count(), 1)
        self.assertEqual(CreditTransaction.query.filter_by(payment_id=result['payment_id']).count(), 0)

    def test_terms_are_owner_scoped_and_stale_values_rejected(self):
        reservation = self.reserve(verified=True)
        for user, value, fee in [(self.seller, '100000', '5000.00'),
                                 (self.buyer, '90000', '5000.00'),
                                 (self.buyer, '100000', '4500.00')]:
            with self.subTest(user=user.id, value=value, fee=fee):
                ok, error = accept_final_terms(reservation, user, value, fee)
                self.assertFalse(ok)
                self.assertIsNone(reservation.final_terms_accepted_at)
        page = self.client.get(f'/order/{reservation.order.id}')
        self.assertIn(b'Accept and continue to payment', page.data)
        self.assertIn(b'Full details are in your email', page.data)
        self.assertNotIn(b'5% of the agreed value', page.data)
        self.assertIn(b'Orders, 1 pending', page.data)
        response = self.client.post(f'/order/{reservation.order.id}/service-fee', data={})
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(reservation.final_terms_accepted_at)

    def test_expiry_releases_bxc_and_late_payment_does_not_reopen(self):
        reservation = self.reserve(verified=True)
        result = self.initialize(reservation)
        reservation.expires_at = reservation.service_fee_deadline = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()
        release_expired_reservations()
        self.assertEqual(reservation.status, 'expired')
        self.assertEqual(reservation.order.status, 'Cancelled')
        self.assertEqual(self.buyer.credits, 500000)
        with patch.object(PaystackPaymentService, 'TEST_MODE', True):
            verified = PaystackPaymentService.verify_payment(result['reference'])
        self.assertTrue(verified['success'], verified)
        self.assertEqual(reservation.status, 'expired')
        self.assertEqual(reservation.order.status, 'Cancelled')
        self.assertEqual(self.item.user_id, self.seller.id)
        self.assertEqual(self.buyer.credits, 500000)
        self.assertEqual(Payment.query.one().status, 'completed')

    def test_existing_reservations_remain_fee_exempt(self):
        reservation = self.reserve()
        reservation.service_fee_status = 'not_required'
        reservation.service_fee_naira = None
        db.session.commit()
        with patch('trading_points.award_points_for_purchase', return_value=None):
            ok, error = verify_seller_item(reservation, passed=True)
        self.assertTrue(ok, error)
        self.assertEqual(reservation.status, 'completed')
        self.assertEqual(Payment.query.count(), 0)

    def test_pending_order_cannot_be_dispatched_or_released(self):
        reservation = self.reserve(verified=True)
        admin = Admin(username='fee-admin', email='admin@example.com', password='test', is_super_admin=True)
        db.session.add(admin)
        db.session.commit()
        from services.email_two_factor import fingerprint
        with self.client.session_transaction() as session:
            session['admin_id'] = admin.id
            session['admin_mfa'] = fingerprint(admin)
        response = self.client.post(f'/admin/update_order_status/{reservation.order.id}')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(reservation.order.status, 'Awaiting Final Acceptance')
        from services.verification_intake_service import record_order_delivery_custody, IntakeValidationError
        reservation.order.status = 'Delivered'
        with self.assertRaises(IntakeValidationError):
            record_order_delivery_custody(reservation.order, admin.id)

    def test_acceptance_route_emails_exact_checkout_link_once_and_does_not_extend_deadline(self):
        reservation = self.reserve(verified=True)
        deadline = reservation.service_fee_deadline
        response = Mock(status_code=200, text='mock')
        response.json.return_value = {'status': True, 'data': {
            'authorization_url': 'https://checkout.paystack.com/accepted-order',
        }}
        with patch.object(PaystackPaymentService, 'TEST_MODE', False), \
             patch.object(PaystackPaymentService, 'get_auth_header', return_value={}), \
             patch('paystack_payment_service.requests.post', return_value=response) as post, \
             patch('routes.auth.send_email_async') as email:
            accepted = self.client.post(f'/order/{reservation.order.id}/service-fee', data={
                'accept_terms': 'yes', 'purchase_value': '100000', 'service_fee': '5000.00',
            })
            retry = self.client.post(f'/order/{reservation.order.id}/service-fee')
        self.assertEqual(accepted.status_code, 302)
        self.assertEqual(retry.status_code, 302)
        post.assert_called_once()
        email.assert_called_once()
        self.assertIn('href="https://checkout.paystack.com/accepted-order"', email.call_args.kwargs['html_body'])
        for detail in ('5% of the agreed', 'NGN 1,000', 'NGN 10,000', '100,000 BXC',
                       '48-hour window', 'card or bank transfer', 'does not reopen'):
            self.assertIn(detail, email.call_args.kwargs['html_body'])
        self.assertEqual(email.call_args.kwargs['recipients'], [self.buyer.email])
        self.assertEqual(reservation.service_fee_deadline, deadline)
        self.assertEqual(reservation.service_fee_status, 'awaiting_payment')
        self.assertEqual(reservation.final_terms_version, 'service_fee_v1')

    def test_live_verification_rejects_mismatches_then_accepts_bank_transfer_once(self):
        reservation = self.reserve(verified=True)
        initialized = self.initialize(reservation)
        reference = initialized['reference']
        data = {'status': 'success', 'amount': 500000, 'currency': 'NGN',
                'reference': reference, 'channel': 'bank_transfer'}
        with patch.object(PaystackPaymentService, 'TEST_MODE', False), \
             patch.object(PaystackPaymentService, 'get_auth_header', return_value={}), \
             patch('trading_points.award_points_for_purchase', return_value=None):
            for mismatch in ({'amount': 5000}, {'currency': 'USD'}, {'reference': 'wrong'}):
                response = Mock(status_code=200)
                response.json.return_value = {'status': True, 'data': {**data, **mismatch}}
                with self.subTest(mismatch=mismatch), \
                     patch('paystack_payment_service.requests.get', return_value=response):
                    self.assertFalse(PaystackPaymentService.verify_payment(reference)['success'])
                    self.assertEqual(reservation.service_fee_status, 'awaiting_payment')
                    self.assertEqual(self.item.user_id, self.seller.id)
            response.json.return_value = {'status': True, 'data': data}
            with patch('paystack_payment_service.requests.get', return_value=response) as gateway:
                first = PaystackPaymentService.verify_payment(reference)
                duplicate = PaystackPaymentService.verify_payment(reference)
            self.assertTrue(first['success'], first)
            self.assertTrue(duplicate['success'])
            gateway.assert_called_once()
        self.assertEqual(Payment.query.one().payment_method, 'bank_transfer')
        self.assertEqual(self.buyer.credits, 400000)

    def test_revaluation_updates_final_fee_and_waits_for_bxc_shortfall(self):
        from services.reservation_service import respond_to_reservation_revaluation, cover_reservation_shortfall
        reservation = self.reserve()
        verify_seller_item(reservation, passed=True, revised_value=120000)
        proposal = reservation.revaluations[0]
        for user in (self.buyer, self.seller):
            ok, error = respond_to_reservation_revaluation(proposal.id, user, accepted=True)
            self.assertTrue(ok, error)
        self.assertIsNotNone(reservation.service_fee_deadline)
        self.assertIsNone(reservation.order)
        ok, error = cover_reservation_shortfall(reservation, self.buyer, 20000)
        self.assertTrue(ok, error)
        self.assertEqual(reservation.purchase_value, 120000)
        self.assertEqual(reservation.service_fee_naira, 6000)
        self.assertEqual(reservation.service_fee_status, 'awaiting_acceptance')
        ok, error = accept_final_terms(reservation, self.buyer, '100000', '5000.00')
        self.assertFalse(ok)

    def test_unknown_initialization_outcome_is_not_retried_as_second_charge(self):
        import requests
        reservation = self.reserve(verified=True)
        self.accept(reservation)
        with patch.object(PaystackPaymentService, 'TEST_MODE', False), \
             patch.object(PaystackPaymentService, 'get_auth_header', return_value={}), \
             patch('paystack_payment_service.requests.post', side_effect=requests.Timeout('test')) as gateway:
            first = PaystackPaymentService.initiate_service_fee_payment(reservation, self.buyer)
            retry = PaystackPaymentService.initiate_service_fee_payment(reservation, self.buyer)
        self.assertFalse(first['success'])
        self.assertFalse(retry['success'])
        gateway.assert_called_once()
        self.assertEqual(Payment.query.count(), 1)
        self.assertEqual(reservation.status, 'active')
        self.assertEqual(reservation.service_fee_status, 'awaiting_payment')

    def test_other_user_cannot_accept_or_confirm_order_payment(self):
        reservation = self.reserve(verified=True)
        initialized = self.initialize(reservation)
        from flask import g
        g.pop('_login_user', None)
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.seller.id)
        response = self.client.post(f'/order/{reservation.order.id}/service-fee')
        self.assertEqual(response.status_code, 404)
        response = self.client.get(f"/payments/verify-payment/{initialized['reference']}")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Payment.query.one().status, 'test_pending')

    def test_migration_preserves_existing_terms_and_guards_downgrade(self):
        import importlib.util
        from pathlib import Path
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from sqlalchemy import create_engine, inspect
        path = Path(app.root_path) / 'migrations' / 'versions' / 'add_reservation_service_fee.py'
        spec = importlib.util.spec_from_file_location('service_fee_migration', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        engine = create_engine('sqlite:///:memory:')
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql('CREATE TABLE reservation (id INTEGER PRIMARY KEY, status VARCHAR(20))')
                connection.exec_driver_sql("INSERT INTO reservation VALUES (1, 'active'), (2, 'completed')")
                with Operations.context(MigrationContext.configure(connection)):
                    migration.upgrade()
                    self.assertEqual(connection.exec_driver_sql(
                        'SELECT service_fee_status, service_fee_naira, final_terms_accepted_at FROM reservation'
                    ).all(), [('not_required', None, None), ('not_required', None, None)])
                    connection.exec_driver_sql(
                        "UPDATE reservation SET service_fee_status='awaiting_verification' WHERE id=1"
                    )
                    with self.assertRaises(RuntimeError):
                        migration.downgrade()
                    connection.exec_driver_sql(
                        "UPDATE reservation SET service_fee_status='not_required' WHERE id=1"
                    )
                    migration.downgrade()
                    self.assertNotIn('service_fee_status', {c['name'] for c in inspect(connection).get_columns('reservation')})
        finally:
            engine.dispose()

    def test_browser_payment_return_redirects_to_order_not_wallet(self):
        reservation = self.reserve(verified=True)
        initialized = self.initialize(reservation)
        with patch.object(PaystackPaymentService, 'TEST_MODE', True), \
             patch('trading_points.award_points_for_purchase', return_value=None):
            response = self.client.get(f"/payments/verify-payment/{initialized['reference']}")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, f'/order/{reservation.order.id}')
        self.assertEqual(reservation.status, 'completed')
        self.assertEqual(self.buyer.credits, 400000)

    def test_cancelled_checkout_returns_to_order_without_cancelling_reservation(self):
        reservation = self.reserve(verified=True)
        initialized = self.initialize(reservation)
        response = self.client.get(f"/payments/cancel?reference={initialized['reference']}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'/order/{reservation.order.id}'.encode(), response.data)
        self.assertIn(b'This does not cancel your reservation', response.data)
        self.assertNotIn(b'Your account has not been charged', response.data)
        self.assertEqual(reservation.status, 'active')
        self.assertEqual(Payment.query.one().status, 'test_pending')

    def test_failed_service_verification_returns_order_navigation_not_wallet_funding(self):
        reservation = self.reserve(verified=True)
        initialized = self.initialize(reservation)
        with patch.object(PaystackPaymentService, 'verify_payment', return_value={
            'success': False, 'error': 'Payment is still pending',
        }):
            for path in (f"/payments/verify-payment/{initialized['reference']}",
                         f"/payments/webhook?reference={initialized['reference']}"):
                with self.subTest(path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(b'Service-fee payment not confirmed', response.data)
                    self.assertIn(b'/my_orders', response.data)
                    self.assertNotIn(b'/payments/fund-account', response.data)

    def test_service_payment_webhook_completes_without_browser_session(self):
        reservation = self.reserve(verified=True)
        initialized = self.initialize(reservation)
        from flask import g
        g.pop('_login_user', None)
        with patch.object(PaystackPaymentService, 'TEST_MODE', True), \
             patch.object(PaystackPaymentService, 'verify_webhook_signature', return_value=True), \
             patch('trading_points.award_points_for_purchase', return_value=None):
            for _ in range(2):
                response = app.test_client().post('/payments/webhook', json={
                    'event': 'charge.success', 'data': {'reference': initialized['reference']},
                }, headers={'x-paystack-signature': 'mocked-signature'})
                self.assertEqual(response.status_code, 200)
        self.assertEqual(reservation.status, 'completed')
        self.assertEqual(Order.query.count(), 1)
        self.assertEqual(self.buyer.credits, 400000)
        self.assertEqual(CreditTransaction.query.filter_by(reason='reservation_purchase').count(), 1)

    def test_non_collection_reservation_requests_are_rejected_without_side_effects(self):
        for method in ('home delivery', 'home', 'courier', ''):
            with self.subTest(method=method):
                reservation, error = create_reservation(
                    self.buyer, self.item, [], funding_mode='spendable',
                    delivery_method=method, delivery_address='An old test address',
                )
                self.assertIsNone(reservation)
                self.assertIn('Only verification-centre collection', error)
                with patch.object(User, 'is_profile_complete', return_value=True), patch(
                    'paystack_payment_service.requests.post'
                ) as provider:
                    response = self.client.post(f'/item/{self.item.id}/reserve', data={
                        'funding_mode': 'spendable', 'delivery_method': method,
                        'delivery_address': 'An old test address',
                    })
                self.assertEqual(response.status_code, 302)
                provider.assert_not_called()
                self.assertEqual(Reservation.query.count(), 0)
                self.assertEqual(Payment.query.count(), 0)
                self.assertEqual(self.buyer.credits, 500000)
                self.assertTrue(self.item.is_available)

    def test_reservation_chooser_has_only_centres_and_disables_when_none_exist(self):
        with patch.object(User, 'is_profile_complete', return_value=True):
            page = self.client.get(f'/item/{self.item.id}/choose-backing-assets')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'No verification centres are available', page.data)
        self.assertIn(b'id="confirmBtn" disabled', page.data)
        self.assertIn(b'Update your profile', page.data)
        for text in (b'home delivery', b'home-service', b'delivery_address', b'5,000 home'):
            self.assertNotIn(text, page.data)
        station = PickupStation(name='Only Centre', address='Centre Road', city='Ikeja', state='Lagos')
        db.session.add(station)
        db.session.commit()
        with patch.object(User, 'is_profile_complete', return_value=True):
            page = self.client.get(f'/item/{self.item.id}/choose-backing-assets')
            missing = self.client.post(f'/item/{self.item.id}/reserve', data={
                'funding_mode': 'spendable', 'delivery_method': 'pickup',
            })
        self.assertIn(b'Only Centre', page.data)
        self.assertIn(b'name="delivery_method" value="pickup"', page.data)
        self.assertEqual(missing.status_code, 302)
        self.assertEqual(Reservation.query.count(), 0)

    def historical_logistics_booking(self, status='active'):
        reservation = Reservation(
            user_id=self.buyer.id, item_id=self.item.id, funding_mode='spendable',
            purchase_value=100000, provisional_credits_used=0,
            delivery_method='home delivery', delivery_address='Old test address',
            delivery_quote_naira=5000, delivery_fee_status='awaiting_payment',
            status=status, expires_at=datetime.utcnow() + timedelta(hours=12),
        )
        db.session.add(reservation)
        db.session.flush()
        payment = Payment(
            user_id=self.buyer.id, reservation_id=reservation.id, amount_naira=5000,
            credits_purchased=0, purpose='reservation_delivery_fee', status='test_pending',
            paystack_reference=f'TEST_retired_{reservation.id}',
            payment_metadata={'mode': 'test'},
        )
        db.session.add(payment)
        db.session.commit()
        return reservation, payment

    def test_retired_payment_entry_points_never_call_provider_or_reuse_link(self):
        reservation, payment = self.historical_logistics_booking()
        with patch('paystack_payment_service.requests.post') as provider:
            result = PaystackPaymentService.initiate_delivery_fee_payment(reservation, self.buyer)
            direct = PaystackPaymentService._initiate_reservation_fee(
                reservation, self.buyer, 'reservation_delivery_fee',
            )
            response = self.client.post(f'/reservation/{reservation.id}/delivery-fee')
        self.assertFalse(result['success'])
        self.assertFalse(direct['success'])
        self.assertEqual(response.status_code, 302)
        self.assertIn('/my_reservations', response.location)
        provider.assert_not_called()
        self.assertEqual(Payment.query.count(), 1)
        self.assertEqual(payment.status, 'test_pending')
        page = self.client.get('/my_reservations')
        self.assertNotIn(f'/reservation/{reservation.id}/delivery-fee'.encode(), page.data)
        self.assertIn(b'Retired test booking', page.data)

    def test_historical_logistics_confirmations_reconcile_without_credit_or_settlement(self):
        for status in ('active', 'cancelled', 'expired'):
            with self.subTest(status=status):
                reservation, payment = self.historical_logistics_booking(status)
                with patch.object(PaystackPaymentService, 'TEST_MODE', True), patch(
                    'paystack_payment_service.notify_admins'
                ) as admins:
                    result = PaystackPaymentService.verify_payment(payment.paystack_reference)
                    repeated = PaystackPaymentService.verify_payment(payment.paystack_reference)
                self.assertTrue(result['success'], result)
                self.assertTrue(repeated['success'], repeated)
                self.assertEqual(result['credits_added'], 0)
                self.assertEqual(reservation.status, status)
                self.assertEqual(payment.status, 'completed')
                self.assertIn('reconciliation', payment.error_message)
                admins.assert_called_once()
                self.assertEqual(self.buyer.credits, 500000)
                self.assertEqual(self.item.user_id, self.seller.id)
                self.assertEqual(CreditTransaction.query.count(), 0)
                self.assertEqual(Order.query.count(), 0)

    def test_historical_logistics_payment_still_validates_provider_amount_and_currency(self):
        reservation, payment = self.historical_logistics_booking()
        payment.status = 'pending'
        payment.paystack_reference = 'archived-logistics-reference'
        db.session.commit()
        for currency, amount in (('USD', 500000), ('NGN', 499999)):
            with self.subTest(currency=currency, amount=amount):
                response = Mock(status_code=200, text='mock')
                response.json.return_value = {'status': True, 'data': {
                    'status': 'success', 'currency': currency, 'amount': amount,
                    'reference': payment.paystack_reference,
                }}
                with patch.object(PaystackPaymentService, 'TEST_MODE', False), patch.object(
                    PaystackPaymentService, 'get_auth_header', return_value={}
                ), patch('paystack_payment_service.requests.get', return_value=response):
                    result = PaystackPaymentService.verify_payment(payment.paystack_reference)
                self.assertFalse(result['success'])
                self.assertEqual(payment.status, 'pending')
                self.assertEqual(reservation.delivery_fee_status, 'awaiting_payment')

    def test_retired_booking_cannot_be_inspected_paid_settled_or_released(self):
        reservation = self.item_backed_reservation()
        reservation.delivery_method = 'home delivery'
        db.session.commit()
        for verify, subject in ((verify_seller_item, reservation),
                                (verify_backing_asset, reservation.backing_assets[0])):
            ok, error = verify(subject, passed=True)
            self.assertFalse(ok)
            self.assertIn('collection', error)
        reservation.delivery_method = 'pickup'
        db.session.commit()
        verify_seller_item(reservation, passed=True)
        verify_backing_asset(reservation.backing_assets[0], passed=True)
        initialized = self.initialize(reservation)
        reservation.delivery_method = 'home delivery'
        reservation.order.delivery_method = 'home delivery'
        db.session.commit()
        with patch('paystack_payment_service.requests.post') as provider:
            result = PaystackPaymentService.initiate_service_fee_payment(reservation, self.buyer)
        self.assertFalse(result['success'])
        provider.assert_not_called()
        self.assertIsNone(reservation.service_fee_payment_link)
        with self.assertRaises(ValueError):
            _settle_reservation(reservation)
        page = self.client.get(f'/order/{reservation.order.id}')
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b'Accept and continue to payment', page.data)
        self.assertNotIn(b'Get payment link', page.data)
        admin = Admin(username='retired-admin', email='retired@example.com', password='test', is_super_admin=True)
        db.session.add(admin)
        db.session.commit()
        from services.email_two_factor import fingerprint
        with self.client.session_transaction() as session:
            session['admin_id'] = admin.id
            session['admin_mfa'] = fingerprint(admin)
        old_status = reservation.order.status
        self.client.post(f'/admin/update_order_status/{reservation.order.id}')
        self.assertEqual(reservation.order.status, old_status)
        self.client.post(f'/admin/settlement-queue/{reservation.id}/delivery-quote', data={'amount_naira': '5000'})
        self.assertIsNone(reservation.delivery_quote_naira)
        self.assertEqual(reservation.delivery_fee_status, 'not_required')
        page = self.client.get('/admin/settlement-queue')
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b'Apply standard fee', page.data)
        from services.verification_intake_service import record_order_delivery_custody, IntakeValidationError
        reservation.order.status = 'Delivered'
        with self.assertRaisesRegex(IntakeValidationError, 'collection'):
            record_order_delivery_custody(reservation.order, admin.id)
        with patch.object(PaystackPaymentService, 'TEST_MODE', True), patch(
            'paystack_payment_service.notify_admins'
        ) as admins:
            result = PaystackPaymentService.verify_payment(initialized['reference'])
        self.assertTrue(result['success'], result)
        self.assertEqual(reservation.status, 'active')
        self.assertEqual(self.item.user_id, self.seller.id)
        self.assertIn('retired', Payment.query.one().error_message)
        admins.assert_called_once()

    def item_backed_reservation(self):
        self.buyer.provisional_credits = 100000
        backing = Item(name='Buyer backing phone', category='Electronics', user_id=self.buyer.id,
                       value=100000, status='approved', is_approved=True, is_available=True,
                       provisional_credit_amount=100000, provisional_credit_settled=False)
        station = PickupStation(name='Collection Centre', address='10 Station Road', city='Ikeja', state='Lagos')
        db.session.add_all([backing, station])
        db.session.commit()
        reservation, error = create_reservation(
            self.buyer, self.item, [backing.id], consent_confirmed=True,
            delivery_method='pickup', pickup_station_id=station.id,
        )
        self.assertIsNone(error)
        return reservation

    def test_station_buyer_is_invited_only_after_reserved_item_passes(self):
        with patch('routes.auth.send_email_async') as email:
            reservation = self.item_backed_reservation()
            self.assertNotIn([self.buyer.email], [call.kwargs['recipients'] for call in email.call_args_list])
            seller_email = next(call.kwargs['html_body'] for call in email.call_args_list
                                if call.kwargs['recipients'] == [self.seller.email])
            self.assertIn('Collection Centre', seller_email)
            self.assertIn('10 Station Road', seller_email)
            email.reset_mock()
            asset = reservation.backing_assets[0]
            ok, error = verify_backing_asset(asset, passed=True)
            self.assertFalse(ok)
            self.assertIn('Verify the reserved item', error)
            self.assertEqual(asset.verification_status, 'not_submitted')
            self.assertIsNone(reservation.service_fee_deadline)
            before = datetime.utcnow()
            ok, error = verify_seller_item(reservation, passed=True)
            self.assertTrue(ok, error)
            invitations = [call.kwargs['html_body'] for call in email.call_args_list
                           if call.kwargs['recipients'] == [self.buyer.email]]
            self.assertEqual(len(invitations), 1)
            for text in ('Collection Centre', 'Bring your backing item', '48 hours', 'Paystack'):
                self.assertIn(text, invitations[0])
            self.assertTrue(before + timedelta(hours=48) <= reservation.expires_at <= datetime.utcnow() + timedelta(hours=48))
            self.assertIsNone(reservation.order)
            self.assertEqual(reservation.status, 'active')
            page = self.client.get('/my_reservations')
            self.assertIn(b'Bring your backing items for inspection', page.data)

    def test_backing_verification_and_payment_do_not_restart_collection_window(self):
        reservation = self.item_backed_reservation()
        verify_seller_item(reservation, passed=True)
        deadline = datetime.utcnow() + timedelta(minutes=30)
        reservation.expires_at = reservation.service_fee_deadline = deadline
        db.session.commit()
        ok, error = verify_backing_asset(reservation.backing_assets[0], passed=True)
        self.assertTrue(ok, error)
        self.assertEqual(reservation.service_fee_deadline, deadline)
        self.assertEqual(reservation.expires_at, deadline)
        self.assertEqual(reservation.service_fee_status, 'awaiting_acceptance')
        self.assertEqual(self.item.user_id, self.seller.id)
        initialized = self.initialize(reservation)
        with patch.object(PaystackPaymentService, 'TEST_MODE', True), patch(
            'trading_points.award_points_for_purchase', return_value=None
        ):
            result = PaystackPaymentService.verify_payment(initialized['reference'])
        self.assertTrue(result['success'], result)
        self.assertEqual(reservation.status, 'completed')
        self.assertEqual(self.item.user_id, self.buyer.id)
        self.assertEqual(reservation.order.status, 'Pending')

    def test_seller_failure_never_invites_or_acquires_buyer_backing_items(self):
        reservation = self.item_backed_reservation()
        with patch('routes.auth.send_email_async') as email:
            verify_seller_item(reservation, passed=False)
        self.assertFalse(any('visit the verification centre' in call.kwargs['subject']
                             for call in email.call_args_list))
        self.assertIsNone(reservation.service_fee_deadline)
        self.assertEqual(reservation.status, 'cancelled')
        self.assertEqual(reservation.backing_assets[0].item.owner_type, 'user')
        self.assertEqual(self.buyer.provisional_credits, 100000)
        self.assertEqual(Payment.query.count(), 0)

    def test_collection_deadline_caps_backing_revaluation_and_shortfall(self):
        from services.reservation_service import respond_to_reservation_revaluation
        reservation = self.item_backed_reservation()
        verify_seller_item(reservation, passed=True)
        deadline = datetime.utcnow() + timedelta(minutes=30)
        reservation.expires_at = reservation.service_fee_deadline = deadline
        db.session.commit()
        ok, error = verify_backing_asset(reservation.backing_assets[0], passed=True, revised_value=90000)
        self.assertTrue(ok, error)
        proposal = reservation.revaluations[0]
        self.assertEqual(proposal.decision_expires_at, deadline)
        ok, error = respond_to_reservation_revaluation(proposal.id, self.buyer, accepted=False)
        self.assertTrue(ok, error)
        self.assertEqual(reservation.revaluation_shortfall_expires_at, deadline)
        self.assertEqual(reservation.expires_at, deadline)
        self.assertIsNone(reservation.order)

    def test_station_reminders_wait_for_seller_then_remind_buyer_once(self):
        reservation = self.item_backed_reservation()
        reservation.expires_at = datetime.utcnow() + timedelta(hours=5)
        db.session.commit()
        with patch('services.reservation_service._notice') as notice:
            send_reservation_deadline_reminders()
        self.assertEqual([call.args[0] for call in notice.call_args_list], [self.seller.id])
        verify_seller_item(reservation, passed=True)
        reservation.expires_at = reservation.service_fee_deadline = datetime.utcnow() + timedelta(hours=5)
        db.session.commit()
        with patch('services.reservation_service._notice') as notice:
            self.assertEqual(send_reservation_deadline_reminders(), 1)
            self.assertEqual(send_reservation_deadline_reminders(), 0)
        self.assertEqual([call.args[0] for call in notice.call_args_list], [self.buyer.id])
