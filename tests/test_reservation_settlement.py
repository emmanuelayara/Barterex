import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from app import app, db
from models import (
    Admin,
    ClearingInventoryItem,
    CreditTransaction,
    Item,
    Order,
    OrderItem,
    Payment,
    Reservation,
    ReservationAsset,
    ReservationCreditEntry,
    ReservationRevaluation,
    User,
    VerificationIntake,
)
from services.reservation_service import (
    BACKING_ASSET_CONSENT_VERSION,
    LEGACY_BACKING_ASSET_CONSENT_VERSION,
    cancel_reservation,
    add_reservation_backing_assets,
    cover_reservation_shortfall,
    create_reservation,
    get_reservation_shortfall,
    release_expired_reservations,
    respond_to_failed_seller_title_transfer,
    respond_to_reservation_revaluation,
    verify_backing_asset,
    verify_seller_item,
)
from paystack_payment_service import PaystackPaymentService


class ReservationSettlementTests(unittest.TestCase):
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

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _create_reservation(self, purchase_value, backing_values):
        buyer = User(
            username='buyer',
            email='buyer@example.com',
            password_hash='test-hash',
            credits=25,
            provisional_credits=sum(backing_values),
        )
        seller = User(
            username='seller',
            email='seller@example.com',
            password_hash='test-hash',
            credits=0,
            provisional_credits=purchase_value,
        )
        db.session.add_all([buyer, seller])
        db.session.flush()

        seller_item = Item(
            name='Requested item',
            category='Electronics',
            user_id=seller.id,
            value=purchase_value,
            status='approved',
            is_approved=True,
            is_available=True,
            provisional_credit_amount=purchase_value,
            provisional_credit_settled=False,
        )
        backing_items = [
            Item(
                name=f'Backing item {index}',
                category='Electronics',
                user_id=buyer.id,
                value=value,
                status='approved',
                is_approved=True,
                is_available=True,
                provisional_credit_amount=value,
                provisional_credit_settled=False,
            )
            for index, value in enumerate(backing_values)
        ]
        db.session.add_all([seller_item, *backing_items])
        db.session.commit()

        reservation, error = create_reservation(
            buyer, seller_item, [item.id for item in backing_items], consent_confirmed=True
        )
        self.assertIsNone(error)
        self.assertIsNotNone(reservation)
        return buyer, seller, seller_item, reservation

    def _complete_reservation(self, reservation):
        for asset in reservation.backing_assets:
            ok, error = verify_backing_asset(asset, passed=True)
            self.assertTrue(ok, error)

        ok, error = verify_seller_item(reservation, passed=True)
        self.assertTrue(ok, error)

    def test_exact_backing_does_not_issue_change_and_settles_assets(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=300,
            backing_values=[300],
        )

        with patch('trading_points.award_points_for_purchase', return_value=None):
            self._complete_reservation(reservation)

        db.session.refresh(buyer)
        db.session.refresh(seller)
        db.session.refresh(seller_item)
        backing_item = reservation.backing_assets[0].item
        db.session.refresh(backing_item)

        self.assertEqual(reservation.status, 'completed')
        self.assertEqual(buyer.credits, 25)
        self.assertEqual(buyer.provisional_credits, 0)
        self.assertEqual(seller.credits, 300)
        self.assertEqual(
            [(entry.balance_type, entry.entry_type, entry.amount) for entry in
             ReservationCreditEntry.query.filter_by(
                 reservation_id=reservation.id
             ).order_by(ReservationCreditEntry.id).all()],
            [
                ('provisional', 'hold', -300),
                ('spendable_held', 'hold', 300),
                ('provisional', 'settlement', -300),
                ('spendable', 'settlement', 300),
                ('spendable_held', 'purchase', -300),
            ],
        )
        self.assertTrue(seller_item.provisional_credit_settled)
        self.assertTrue(backing_item.provisional_credit_settled)
        self.assertEqual(backing_item.owner_type, 'barterex')
        self.assertIsNone(backing_item.user_id)
        self.assertEqual(
            ClearingInventoryItem.query.filter_by(item_id=backing_item.id).one().status,
            'held_for_resale',
        )
        seller_transaction = CreditTransaction.query.filter_by(
            user_id=seller.id,
            reason='reservation_settlement',
        ).one()
        self.assertEqual(seller_transaction.amount, 300)
        self.assertEqual(seller_transaction.balance_before, 0)
        self.assertEqual(seller_transaction.balance_after, 300)
        order = Order.query.filter_by(reservation_id=reservation.id).one()
        self.assertEqual(order.status, 'Pending')
        self.assertEqual(order.delivery_method, 'pickup')
        self.assertEqual(OrderItem.query.filter_by(order_id=order.id, item_id=seller_item.id).count(), 1)
        self.assertEqual(
            CreditTransaction.query.filter_by(
                user_id=buyer.id,
                reason='reservation_purchase',
            ).count(),
            1,
        )
        buyer_purchase = CreditTransaction.query.filter_by(
            user_id=buyer.id,
            reason='reservation_purchase',
        ).one()
        self.assertEqual(buyer_purchase.amount, 300)
        duplicate_seller_ok, duplicate_seller_error = verify_seller_item(reservation, passed=True)
        duplicate_asset_ok, duplicate_asset_error = verify_backing_asset(
            ReservationAsset.query.filter_by(reservation_id=reservation.id).one(),
            passed=True,
        )
        self.assertFalse(duplicate_seller_ok)
        self.assertIn('no longer active', duplicate_seller_error)
        self.assertFalse(duplicate_asset_ok)
        self.assertIn('no longer active', duplicate_asset_error)
        self.assertEqual(
            CreditTransaction.query.filter_by(
                user_id=seller.id,
                reason='reservation_settlement',
            ).count(),
            1,
        )

    def test_spendable_reservation_holds_and_spends_balance_without_backing_assets(self):
        buyer = User(
            username='spendable-buyer',
            email='spendable@example.com',
            password_hash='test-hash',
            credits=500,
            provisional_credits=0,
        )
        seller = User(
            username='spendable-seller',
            email='seller-spendable@example.com',
            password_hash='test-hash',
            credits=0,
            provisional_credits=300,
        )
        db.session.add_all([buyer, seller])
        db.session.flush()
        seller_item = Item(
            name='Spendable reservation item',
            category='Electronics',
            user_id=seller.id,
            value=300,
            status='approved',
            is_approved=True,
            is_available=True,
            provisional_credit_amount=300,
            provisional_credit_settled=False,
        )
        db.session.add(seller_item)
        db.session.commit()

        reservation, error = create_reservation(
            buyer,
            seller_item,
            [],
            funding_mode='spendable',
            delivery_method='home delivery',
            delivery_address='12 Test Street, Lagos',
        )
        self.assertIsNone(error)
        self.assertEqual(reservation.backing_assets, [])
        self.assertEqual(buyer.credits, 200)
        self.assertEqual(reservation.spendable_credits_held, 300)
        self.assertEqual(reservation.delivery_fee_status, 'quote_pending')

        ok, error = verify_seller_item(reservation, passed=True)
        self.assertTrue(ok, error)
        db.session.refresh(buyer)
        self.assertEqual(reservation.status, 'completed')
        self.assertEqual(buyer.credits, 200)
        self.assertEqual(reservation.spendable_credits_held, 0)
        order = Order.query.filter_by(reservation_id=reservation.id).one()
        self.assertEqual(order.delivery_method, 'home delivery')
        self.assertEqual(order.delivery_address, '12 Test Street, Lagos')
        self.assertEqual(order.status, 'Pending')

    def test_failed_spendable_reservation_releases_held_balance(self):
        buyer = User(
            username='release-buyer',
            email='release@example.com',
            password_hash='test-hash',
            credits=500,
            provisional_credits=0,
        )
        seller = User(
            username='release-seller',
            email='release-seller@example.com',
            password_hash='test-hash',
            credits=0,
            provisional_credits=300,
        )
        db.session.add_all([buyer, seller])
        db.session.flush()
        seller_item = Item(
            name='Failed requested item',
            category='Electronics',
            user_id=seller.id,
            value=300,
            status='approved',
            is_approved=True,
            is_available=True,
            provisional_credit_amount=300,
            provisional_credit_settled=False,
        )
        db.session.add(seller_item)
        db.session.commit()
        reservation, error = create_reservation(
            buyer, seller_item, [], funding_mode='spendable'
        )
        self.assertIsNone(error)
        self.assertEqual(buyer.credits, 200)

        ok, error = verify_seller_item(reservation, passed=False)
        self.assertTrue(ok, error)
        db.session.refresh(buyer)
        self.assertEqual(reservation.status, 'cancelled')
        self.assertEqual(buyer.credits, 500)
        self.assertEqual(reservation.spendable_credits_held, 0)
        self.assertEqual(Order.query.filter_by(reservation_id=reservation.id).count(), 0)

    def test_delivery_fee_payment_is_not_credited_and_is_idempotent(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=300,
            backing_values=[300],
        )
        reservation.delivery_method = 'home delivery'
        reservation.delivery_address = '12 Test Street, Lagos'
        reservation.delivery_quote_naira = 250
        reservation.delivery_fee_status = 'awaiting_payment'
        db.session.commit()
        original_balance = buyer.credits

        with patch.object(PaystackPaymentService, 'TEST_MODE', True):
            initiated = PaystackPaymentService.initiate_delivery_fee_payment(reservation, buyer)
            repeated_initiation = PaystackPaymentService.initiate_delivery_fee_payment(reservation, buyer)
            self.assertTrue(initiated['success'])
            self.assertEqual(repeated_initiation['payment_id'], initiated['payment_id'])
            payment = Payment.query.get(initiated['payment_id'])
            verified = PaystackPaymentService.verify_payment(payment.paystack_reference)
            repeated = PaystackPaymentService.verify_payment(payment.paystack_reference)

        db.session.refresh(buyer)
        db.session.refresh(reservation)
        self.assertTrue(verified['success'])
        self.assertTrue(repeated['success'])
        self.assertEqual(verified['credits_added'], 0)
        self.assertEqual(buyer.credits, original_balance)
        self.assertEqual(reservation.delivery_fee_status, 'paid')
        self.assertEqual(payment.purpose, 'reservation_delivery_fee')

    def test_home_delivery_quote_and_dispatch_gate(self):
        buyer = User(
            username='home-buyer',
            email='home-buyer@example.com',
            password_hash='test-hash',
            credits=500,
            provisional_credits=0,
        )
        seller = User(
            username='home-seller',
            email='home-seller@example.com',
            password_hash='test-hash',
            credits=0,
            provisional_credits=300,
        )
        db.session.add_all([buyer, seller])
        db.session.flush()
        seller_item = Item(
            name='Home delivery requested item',
            category='Electronics',
            user_id=seller.id,
            value=300,
            status='approved',
            is_approved=True,
            is_available=True,
            provisional_credit_amount=300,
            provisional_credit_settled=False,
        )
        db.session.add(seller_item)
        db.session.commit()
        reservation, error = create_reservation(
            buyer,
            seller_item,
            [],
            funding_mode='spendable',
            delivery_method='home delivery',
            delivery_address='12 Test Street, Lagos',
        )
        self.assertIsNone(error)
        ok, error = verify_seller_item(reservation, passed=True)
        self.assertTrue(ok, error)

        admin = Admin(
            username='fulfillment-admin',
            email='fulfillment-admin@example.com',
            is_super_admin=True,
            password='test-hash',
        )
        db.session.add(admin)
        db.session.commit()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session['admin_id'] = admin.id
            response = client.post(
                f'/admin/settlement-queue/{reservation.id}/delivery-quote',
                data={'amount_naira': '250.00'},
            )
            self.assertEqual(response.status_code, 302)
            db.session.refresh(reservation)
            self.assertEqual(reservation.delivery_quote_naira, 250.0)
            self.assertEqual(reservation.delivery_fee_status, 'awaiting_payment')

            order = Order.query.filter_by(reservation_id=reservation.id).one()
            response = client.post(f'/admin/update_order_status/{order.id}')
            self.assertEqual(response.status_code, 302)
            db.session.refresh(order)
            self.assertEqual(order.status, 'Pending')

        with patch.object(PaystackPaymentService, 'TEST_MODE', True):
            initiated = PaystackPaymentService.initiate_delivery_fee_payment(reservation, buyer)
            payment = Payment.query.get(initiated['payment_id'])
            verified = PaystackPaymentService.verify_payment(payment.paystack_reference)
        self.assertTrue(verified['success'])

        with app.test_client() as client:
            with client.session_transaction() as session:
                session['admin_id'] = admin.id
            response = client.post(f'/admin/update_order_status/{order.id}')
        self.assertEqual(response.status_code, 302)
        db.session.refresh(order)
        self.assertEqual(order.status, 'Shipped')

    def test_home_service_blocks_backing_item_verification_until_fee_is_paid(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=300,
            backing_values=[300],
        )
        reservation.delivery_method = 'home delivery'
        reservation.delivery_address = '12 Test Street, Lagos'
        reservation.delivery_quote_naira = 250
        reservation.delivery_fee_status = 'awaiting_payment'
        db.session.commit()
        ok, error = verify_backing_asset(reservation.backing_assets[0], passed=True)
        self.assertFalse(ok)
        self.assertIn('must pay', error)
        self.assertEqual(reservation.backing_assets[0].verification_status, 'not_submitted')

        with patch.object(PaystackPaymentService, 'TEST_MODE', True):
            initiated = PaystackPaymentService.initiate_delivery_fee_payment(reservation, buyer)
            payment = Payment.query.get(initiated['payment_id'])
            verified = PaystackPaymentService.verify_payment(payment.paystack_reference)
        self.assertTrue(verified['success'])
        ok, error = verify_backing_asset(reservation.backing_assets[0], passed=True)
        self.assertTrue(ok, error)

    def test_backing_title_waits_until_requested_item_passes(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=100,
            backing_values=[100],
        )
        backing_item = reservation.backing_assets[0].item

        ok, error = verify_seller_item(reservation, passed=True)
        self.assertTrue(ok, error)
        self.assertEqual(reservation.status, 'active')
        self.assertEqual(backing_item.owner_type, 'user')
        self.assertEqual(ClearingInventoryItem.query.count(), 0)

        ok, error = verify_backing_asset(reservation.backing_assets[0], passed=True)
        self.assertTrue(ok, error)

        db.session.refresh(reservation)
        db.session.refresh(backing_item)
        self.assertEqual(reservation.status, 'completed')
        self.assertEqual(backing_item.owner_type, 'barterex')

    def test_reservation_verification_records_intake_and_receipt(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=100,
            backing_values=[100],
        )
        admin = Admin(
            username='verification-admin',
            email='verification-admin@example.com',
            is_super_admin=True,
            password='test-hash',
        )
        db.session.add(admin)
        db.session.commit()
        details = {
            'received_location': 'Main Station',
            'observed_condition': 'Like New',
            'observed_serial_number': None,
            'serial_check': 'not_applicable',
            'identity_confirmed': 'yes',
            'accessories_received': 'None',
            'intake_notes': 'Identity and condition checked.',
        }

        ok, error = verify_seller_item(
            reservation,
            passed=True,
            intake_details=details,
            admin_id=admin.id,
        )

        self.assertTrue(ok, error)
        intake = VerificationIntake.query.filter_by(
            item_id=seller_item.id,
            workflow_type='reservation_seller_item',
        ).one()
        self.assertEqual(intake.reservation_id, reservation.id)
        self.assertEqual(intake.received_location, 'Main Station')
        self.assertEqual(intake.outcome, 'passed')
        self.assertEqual(len(intake.custody_events), 1)

    def test_legacy_reservation_keeps_original_immediate_transfer_behavior(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=100,
            backing_values=[100],
        )
        reservation.backing_asset_consent_version = LEGACY_BACKING_ASSET_CONSENT_VERSION
        db.session.commit()
        backing_item = reservation.backing_assets[0].item

        ok, error = verify_backing_asset(reservation.backing_assets[0], passed=True)
        self.assertTrue(ok, error)
        self.assertEqual(backing_item.owner_type, 'barterex')

        ok, error = verify_seller_item(reservation, passed=False)
        self.assertTrue(ok, error)
        db.session.refresh(reservation)
        self.assertEqual(reservation.status, 'cancelled')
        self.assertEqual(backing_item.owner_type, 'barterex')
        self.assertEqual(reservation.backing_asset_consent_version, LEGACY_BACKING_ASSET_CONSENT_VERSION)

    def test_excess_backing_is_credited_as_change_and_all_assets_settle(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=250,
            backing_values=[180, 120],
        )

        with patch('trading_points.award_points_for_purchase', return_value=None):
            self._complete_reservation(reservation)

        db.session.refresh(buyer)
        db.session.refresh(seller)
        db.session.refresh(seller_item)

        self.assertEqual(reservation.status, 'completed')
        self.assertEqual(buyer.credits, 75)
        self.assertEqual(buyer.provisional_credits, 0)
        self.assertEqual(seller.credits, 250)
        self.assertTrue(seller_item.provisional_credit_settled)
        buyer_backing_credit = ReservationCreditEntry.query.filter_by(
            reservation_id=reservation.id,
            user_id=buyer.id,
            balance_type='spendable',
            entry_type='settlement',
        ).one()
        self.assertEqual(buyer_backing_credit.amount, 50)
        self.assertEqual(buyer_backing_credit.balance_before, 25)
        self.assertEqual(buyer_backing_credit.balance_after, 75)
        self.assertEqual(reservation.spendable_credits_held, 0)

        for asset in reservation.backing_assets:
            db.session.refresh(asset.item)
            self.assertTrue(asset.item.provisional_credit_settled)

    def test_reservation_rejects_backing_above_available_provisional_balance(self):
        buyer = User(
            username='buyer',
            email='buyer@example.com',
            password_hash='test-hash',
            credits=25,
            provisional_credits=99,
        )
        seller = User(
            username='seller',
            email='seller@example.com',
            password_hash='test-hash',
            credits=0,
            provisional_credits=100,
        )
        db.session.add_all([buyer, seller])
        db.session.flush()

        seller_item = Item(
            name='Requested item',
            category='Electronics',
            user_id=seller.id,
            value=100,
            status='approved',
            is_approved=True,
            is_available=True,
        )
        backing_item = Item(
            name='Backing item',
            category='Electronics',
            user_id=buyer.id,
            value=100,
            status='approved',
            is_approved=True,
            is_available=True,
            provisional_credit_amount=100,
            provisional_credit_settled=False,
        )
        db.session.add_all([seller_item, backing_item])
        db.session.commit()

        reservation, error = create_reservation(
            buyer, seller_item, [backing_item.id], consent_confirmed=True
        )

        self.assertIsNone(reservation)
        self.assertIn('available provisional BXC', error)
        db.session.refresh(buyer)
        db.session.refresh(backing_item)
        db.session.refresh(seller_item)
        self.assertEqual(buyer.provisional_credits, 99)
        self.assertTrue(backing_item.is_available)
        self.assertTrue(seller_item.is_available)
        self.assertEqual(ReservationCreditEntry.query.count(), 0)

    def test_reservation_requires_explicit_backing_asset_surrender_consent(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=100,
            backing_values=[100],
        )
        cancel_reservation(reservation, buyer)
        backing_item = reservation.backing_assets[0].item
        db.session.refresh(buyer)

        new_reservation, error = create_reservation(
            buyer, seller_item, [backing_item.id], consent_confirmed=False
        )

        self.assertIsNone(new_reservation)
        self.assertIn('title-transfer terms', error)
        self.assertEqual(Reservation.query.count(), 1)
        self.assertEqual(buyer.provisional_credits, 100)
        self.assertTrue(backing_item.is_available)

    def test_backing_asset_cannot_be_held_by_two_reservations(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=100,
            backing_values=[100],
        )
        other_seller = User(
            username='other-seller',
            email='other-seller@example.com',
            password_hash='test-hash',
            provisional_credits=100,
        )
        db.session.add(other_seller)
        db.session.flush()
        other_item = Item(
            name='Another requested item',
            category='Electronics',
            user_id=other_seller.id,
            value=100,
            status='approved',
            is_approved=True,
            is_available=True,
        )
        db.session.add(other_item)
        db.session.commit()

        second_reservation, error = create_reservation(
            buyer,
            other_item,
            [reservation.backing_assets[0].item_id],
            consent_confirmed=True,
        )

        self.assertIsNone(second_reservation)
        self.assertIn('no longer available to use as collateral', error)
        self.assertEqual(
            ReservationCreditEntry.query.filter_by(user_id=buyer.id, entry_type='hold').count(),
            1,
        )
        self.assertEqual(buyer.provisional_credits, 0)

    def test_reservation_creation_rolls_back_all_changes_if_commit_fails(self):
        buyer = User(
            username='buyer',
            email='buyer@example.com',
            password_hash='test-hash',
            provisional_credits=100,
        )
        seller = User(
            username='seller',
            email='seller@example.com',
            password_hash='test-hash',
            provisional_credits=100,
        )
        db.session.add_all([buyer, seller])
        db.session.flush()
        seller_item = Item(
            name='Requested item',
            category='Electronics',
            user_id=seller.id,
            value=100,
            status='approved',
            is_approved=True,
            is_available=True,
        )
        backing_item = Item(
            name='Backing item',
            category='Electronics',
            user_id=buyer.id,
            value=100,
            status='approved',
            is_approved=True,
            is_available=True,
            provisional_credit_amount=100,
            provisional_credit_settled=False,
        )
        db.session.add_all([seller_item, backing_item])
        db.session.commit()

        with patch('services.reservation_service.db.session.commit', side_effect=RuntimeError('commit failed')):
            with self.assertRaisesRegex(RuntimeError, 'commit failed'):
                create_reservation(
                    buyer, seller_item, [backing_item.id], consent_confirmed=True
                )

        db.session.refresh(buyer)
        db.session.refresh(seller_item)
        db.session.refresh(backing_item)
        self.assertEqual(Reservation.query.count(), 0)
        self.assertEqual(ReservationCreditEntry.query.count(), 0)
        self.assertEqual(buyer.provisional_credits, 100)
        self.assertTrue(seller_item.is_available)
        self.assertTrue(backing_item.is_available)
        self.assertIsNone(backing_item.locked_for_reservation_id)

    def test_any_failed_backing_asset_cancels_and_releases_reservation(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=100,
            backing_values=[200, 100],
        )
        assets_by_amount = {asset.amount: asset for asset in reservation.backing_assets}

        passed, error = verify_backing_asset(assets_by_amount[200], passed=True)
        self.assertTrue(passed, error)
        failed, error = verify_backing_asset(assets_by_amount[100], passed=False)
        self.assertTrue(failed, error)

        db.session.refresh(buyer)
        db.session.refresh(seller_item)
        db.session.refresh(reservation)
        self.assertEqual(reservation.status, 'cancelled')
        self.assertEqual(buyer.provisional_credits, 300)
        self.assertEqual(buyer.credits, 25)
        release_entries = ReservationCreditEntry.query.filter_by(
            reservation_id=reservation.id,
            user_id=buyer.id,
            entry_type='release',
        ).all()
        self.assertEqual(
            sum(entry.amount for entry in release_entries if entry.balance_type == 'provisional'),
            300,
        )
        self.assertFalse(
            ReservationCreditEntry.query.filter_by(
                reservation_id=reservation.id,
                user_id=buyer.id,
                balance_type='spendable',
                entry_type='release',
            ).first()
        )
        self.assertTrue(seller_item.is_available)
        db.session.refresh(assets_by_amount[200].item)
        db.session.refresh(assets_by_amount[100].item)
        self.assertTrue(assets_by_amount[200].item.is_available)
        self.assertEqual(assets_by_amount[200].item.owner_type, 'user')
        self.assertFalse(assets_by_amount[100].item.is_available)
        self.assertEqual(assets_by_amount[100].item.status, 'failed_verification')

    def test_duplicate_verification_is_rejected_without_repeating_side_effects(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=100,
            backing_values=[100],
        )
        asset = reservation.backing_assets[0]
        backing_item = asset.item

        ok, error = verify_backing_asset(asset, passed=True)
        self.assertTrue(ok, error)
        reliability_after_first_verification = buyer.reliability_score

        duplicate_ok, duplicate_error = verify_backing_asset(asset, passed=False)

        self.assertFalse(duplicate_ok)
        self.assertIn('already been verified', duplicate_error)
        self.assertEqual(buyer.reliability_score, reliability_after_first_verification)
        self.assertEqual(reservation.status, 'active')
        cancel_ok, cancel_error = cancel_reservation(reservation, buyer)
        self.assertFalse(cancel_ok)
        self.assertIn('Verification has already started', cancel_error)
        self.assertEqual(buyer.provisional_credits, 0)
        self.assertEqual(buyer.credits, 25)
        self.assertEqual(backing_item.owner_type, 'user')
        self.assertEqual(backing_item.user_id, buyer.id)

    def test_failed_seller_item_cancels_and_restores_buyer_provisional_balance(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=100,
            backing_values=[100],
        )
        backing_item = reservation.backing_assets[0].item

        ok, error = verify_seller_item(reservation, passed=False, notes='Condition mismatch')

        self.assertTrue(ok, error)
        db.session.refresh(buyer)
        db.session.refresh(seller_item)
        db.session.refresh(backing_item)
        db.session.refresh(reservation)
        self.assertEqual(reservation.status, 'cancelled')
        self.assertEqual(buyer.provisional_credits, 100)
        self.assertEqual(buyer.credits, 25)
        self.assertFalse(seller_item.is_available)
        self.assertEqual(seller_item.status, 'failed_verification')
        self.assertTrue(backing_item.is_available)

    def test_failed_requested_item_waits_for_buyer_title_transfer_decision(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=100,
            backing_values=[200],
        )
        backing_item = reservation.backing_assets[0].item

        ok, error = verify_backing_asset(reservation.backing_assets[0], passed=True)
        self.assertTrue(ok, error)
        ok, error = verify_seller_item(reservation, passed=False, notes='Condition mismatch')
        self.assertTrue(ok, error)

        db.session.refresh(buyer)
        db.session.refresh(backing_item)
        db.session.refresh(reservation)
        self.assertEqual(reservation.status, 'awaiting_consent')
        self.assertEqual(reservation.backing_asset_consent_version, BACKING_ASSET_CONSENT_VERSION)
        self.assertEqual(buyer.provisional_credits, 0)
        self.assertEqual(buyer.credits, 25)
        self.assertEqual(reservation.spendable_credits_held, 0)
        self.assertEqual(backing_item.owner_type, 'user')
        self.assertEqual(backing_item.user_id, buyer.id)
        self.assertEqual(ClearingInventoryItem.query.filter_by(item_id=backing_item.id).count(), 0)
        self.assertFalse(backing_item.is_available)
        self.assertIsNotNone(reservation.title_transfer_decision_expires_at)

    def test_buyer_can_confirm_title_transfer_after_requested_item_fails(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=100,
            backing_values=[200],
        )
        backing_item = reservation.backing_assets[0].item
        verify_backing_asset(reservation.backing_assets[0], passed=True)
        verify_seller_item(reservation, passed=False, notes='Condition mismatch')

        ok, error = respond_to_failed_seller_title_transfer(reservation, buyer, accepted=True)

        self.assertTrue(ok, error)
        db.session.refresh(buyer)
        db.session.refresh(backing_item)
        db.session.refresh(reservation)
        self.assertEqual(reservation.status, 'cancelled')
        self.assertEqual(reservation.title_transfer_decision, 'accepted')
        self.assertEqual(buyer.provisional_credits, 0)
        self.assertEqual(buyer.credits, 225)
        self.assertEqual(backing_item.owner_type, 'barterex')
        self.assertIsNone(backing_item.user_id)
        self.assertEqual(ClearingInventoryItem.query.filter_by(item_id=backing_item.id).count(), 1)
        self.assertEqual(reservation.spendable_credits_held, 0)

    def test_buyer_can_decline_title_transfer_after_requested_item_fails(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=100,
            backing_values=[200],
        )
        backing_item = reservation.backing_assets[0].item
        verify_backing_asset(reservation.backing_assets[0], passed=True)
        verify_seller_item(reservation, passed=False, notes='Condition mismatch')

        ok, error = respond_to_failed_seller_title_transfer(reservation, buyer, accepted=False)

        self.assertTrue(ok, error)
        db.session.refresh(buyer)
        db.session.refresh(backing_item)
        db.session.refresh(reservation)
        self.assertEqual(reservation.status, 'cancelled')
        self.assertEqual(reservation.title_transfer_decision, 'declined')
        self.assertEqual(buyer.provisional_credits, 200)
        self.assertEqual(buyer.credits, 25)
        self.assertEqual(backing_item.owner_type, 'user')
        self.assertEqual(backing_item.user_id, buyer.id)
        self.assertTrue(backing_item.is_available)
        self.assertEqual(ClearingInventoryItem.query.filter_by(item_id=backing_item.id).count(), 0)

    def test_title_transfer_timeout_restores_item_and_provisional_bxc(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=100,
            backing_values=[200],
        )
        backing_item = reservation.backing_assets[0].item
        verify_backing_asset(reservation.backing_assets[0], passed=True)
        verify_seller_item(reservation, passed=False, notes='Condition mismatch')
        reservation.title_transfer_decision_expires_at = reservation.created_at - timedelta(seconds=1)
        db.session.commit()

        self.assertEqual(release_expired_reservations(), 1)

        db.session.refresh(buyer)
        db.session.refresh(backing_item)
        db.session.refresh(reservation)
        self.assertEqual(reservation.status, 'cancelled')
        self.assertEqual(reservation.title_transfer_decision, 'expired')
        self.assertEqual(buyer.provisional_credits, 200)
        self.assertEqual(backing_item.owner_type, 'user')
        self.assertTrue(backing_item.is_available)
        self.assertEqual(ClearingInventoryItem.query.filter_by(item_id=backing_item.id).count(), 0)

    def test_expired_reservation_releases_assets_and_penalizes_non_submitters(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=100,
            backing_values=[100],
        )
        reservation.expires_at = reservation.created_at - timedelta(seconds=1)
        db.session.commit()

        released_count = release_expired_reservations()

        db.session.refresh(buyer)
        db.session.refresh(seller)
        db.session.refresh(seller_item)
        db.session.refresh(reservation)
        self.assertEqual(released_count, 1)
        self.assertEqual(reservation.status, 'expired')
        self.assertEqual(buyer.provisional_credits, 100)
        self.assertEqual(buyer.credits, 25)
        self.assertEqual(buyer.reliability_score, 90)
        self.assertEqual(seller.reliability_score, 90)
        self.assertTrue(seller_item.is_available)
        self.assertTrue(reservation.backing_assets[0].item.is_available)
        self.assertEqual(release_expired_reservations(), 0)
        self.assertEqual(
            ReservationCreditEntry.query.filter_by(
                reservation_id=reservation.id,
                entry_type='release',
            ).count(),
            1,
        )

    def test_user_can_cancel_before_verification_and_refund_is_audited_once(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=100,
            backing_values=[100],
        )

        ok, error = cancel_reservation(reservation, buyer)

        self.assertTrue(ok, error)
        db.session.refresh(buyer)
        db.session.refresh(reservation)
        self.assertEqual(reservation.status, 'cancelled')
        self.assertEqual(buyer.provisional_credits, 100)
        entry = ReservationCreditEntry.query.filter_by(
            reservation_id=reservation.id,
            entry_type='release',
        ).one()
        self.assertEqual((entry.amount, entry.balance_before, entry.balance_after), (100, 0, 100))
        ok, error = cancel_reservation(reservation, buyer)
        self.assertFalse(ok)
        self.assertIn('no longer active', error)
        self.assertEqual(
            ReservationCreditEntry.query.filter_by(
                reservation_id=reservation.id,
                entry_type='release',
            ).count(),
            1,
        )

    def test_failed_seller_verification_audits_provisional_release(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=100,
            backing_values=[100],
        )

        ok, error = verify_seller_item(reservation, passed=False)

        self.assertTrue(ok, error)
        entry = ReservationCreditEntry.query.filter_by(
            reservation_id=reservation.id,
            entry_type='release',
            balance_type='provisional',
        ).one()
        self.assertEqual((entry.amount, entry.balance_before, entry.balance_after), (100, 0, 100))

    def test_settlement_rolls_back_fully_if_seller_provisional_balance_is_inconsistent(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=100,
            backing_values=[100],
        )
        asset = reservation.backing_assets[0]
        ok, error = verify_backing_asset(asset, passed=True)
        self.assertTrue(ok, error)
        seller.provisional_credits = 0
        db.session.commit()

        with self.assertRaisesRegex(ValueError, 'seller.*provisional BXC balance'):
            verify_seller_item(reservation, passed=True)

        db.session.refresh(reservation)
        db.session.refresh(seller_item)
        db.session.refresh(seller)
        db.session.refresh(buyer)
        self.assertEqual(reservation.status, 'active')
        self.assertEqual(reservation.seller_item_verification_status, 'not_submitted')
        self.assertEqual(seller_item.user_id, seller.id)
        self.assertEqual(seller.credits, 0)
        self.assertEqual(buyer.credits, 25)
        self.assertEqual(
            ReservationCreditEntry.query.filter_by(
                reservation_id=reservation.id,
                entry_type='settlement',
            ).count(),
            0,
        )

    def test_seller_revaluation_requires_both_acceptances_and_shortfall_funding(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=300,
            backing_values=[300],
        )
        buyer.credits = 100
        db.session.commit()

        ok, error = verify_seller_item(reservation, passed=True, revised_value=350)
        self.assertTrue(ok, error)
        proposal = ReservationRevaluation.query.filter_by(
            reservation_id=reservation.id
        ).one()
        asset = reservation.backing_assets[0]
        self.assertEqual(proposal.status, 'pending')
        self.assertEqual(asset.item.owner_type, 'user')

        ok, error = verify_backing_asset(asset, passed=True)
        self.assertTrue(ok, error)
        self.assertEqual(asset.item.owner_type, 'user')

        ok, error = respond_to_reservation_revaluation(proposal.id, buyer, accepted=True)
        self.assertTrue(ok, error)
        self.assertEqual(proposal.status, 'pending')
        ok, error = respond_to_reservation_revaluation(proposal.id, seller, accepted=True)
        self.assertTrue(ok, error)

        db.session.refresh(reservation)
        db.session.refresh(seller)
        self.assertEqual(proposal.status, 'applied')
        self.assertEqual(reservation.purchase_value, 350)
        self.assertEqual(seller_item.value, 350)
        self.assertEqual(seller.provisional_credits, 350)
        self.assertEqual(reservation.status, 'active')
        self.assertEqual(get_reservation_shortfall(reservation), 50)
        self.assertEqual(reservation.revaluation_shortfall_expires_at is not None, True)

        ok, error = cover_reservation_shortfall(reservation, buyer, 50)
        self.assertTrue(ok, error)
        db.session.refresh(reservation)
        db.session.refresh(buyer)
        db.session.refresh(seller)
        self.assertEqual(reservation.status, 'completed')
        self.assertEqual(reservation.spendable_credits_held, 0)
        self.assertEqual(buyer.credits, 50)
        self.assertEqual(seller.credits, 350)
        self.assertEqual(seller.provisional_credits, 0)

    def test_rejected_backing_revaluation_releases_item_and_opens_shortfall_window(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=300,
            backing_values=[300],
        )
        asset = reservation.backing_assets[0]
        ok, error = verify_backing_asset(asset, passed=True, revised_value=250)
        self.assertTrue(ok, error)
        proposal = ReservationRevaluation.query.filter_by(
            reservation_id=reservation.id
        ).one()
        ok, error = respond_to_reservation_revaluation(proposal.id, buyer, accepted=False)
        self.assertTrue(ok, error)

        db.session.refresh(buyer)
        db.session.refresh(reservation)
        db.session.refresh(asset.item)
        self.assertEqual(proposal.status, 'declined')
        self.assertTrue(asset.excluded_from_settlement)
        self.assertEqual(asset.item.owner_type, 'user')
        self.assertTrue(asset.item.is_available)
        self.assertEqual(buyer.provisional_credits, 300)
        self.assertEqual(reservation.provisional_credits_used, 0)
        self.assertEqual(get_reservation_shortfall(reservation), 300)
        self.assertIsNotNone(reservation.revaluation_shortfall_expires_at)

    def test_revaluation_timeout_excludes_backing_item_and_preserves_reservation(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=300,
            backing_values=[300],
        )
        reservation.expires_at = datetime.utcnow() + timedelta(hours=1)
        seller_item.reservation_expires_at = reservation.expires_at
        db.session.commit()
        asset = reservation.backing_assets[0]
        ok, error = verify_backing_asset(asset, passed=True, revised_value=250)
        self.assertTrue(ok, error)
        proposal = ReservationRevaluation.query.filter_by(
            reservation_id=reservation.id
        ).one()
        self.assertEqual(
            proposal.decision_expires_at - proposal.proposed_at,
            timedelta(hours=24),
        )
        self.assertEqual(reservation.expires_at, proposal.decision_expires_at)
        proposal.decision_expires_at = proposal.proposed_at - timedelta(seconds=1)
        db.session.commit()

        released = release_expired_reservations()

        db.session.refresh(reservation)
        db.session.refresh(asset)
        db.session.refresh(buyer)
        self.assertEqual(released, 1)
        self.assertEqual(reservation.status, 'active')
        self.assertEqual(proposal.status, 'expired')
        self.assertTrue(asset.excluded_from_settlement)
        self.assertEqual(buyer.provisional_credits, 300)
        self.assertGreater(reservation.revaluation_shortfall_expires_at, proposal.decision_expires_at)

    def test_seller_revaluation_rejection_uses_renewed_title_consent(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=300,
            backing_values=[300],
        )
        asset = reservation.backing_assets[0]
        ok, error = verify_backing_asset(asset, passed=True)
        self.assertTrue(ok, error)
        ok, error = verify_seller_item(reservation, passed=True, revised_value=350)
        self.assertTrue(ok, error)
        proposal = ReservationRevaluation.query.filter_by(
            reservation_id=reservation.id
        ).one()

        ok, error = respond_to_reservation_revaluation(proposal.id, buyer, accepted=True)
        self.assertTrue(ok, error)
        ok, error = respond_to_reservation_revaluation(proposal.id, seller, accepted=False)
        self.assertTrue(ok, error)
        db.session.refresh(reservation)
        db.session.refresh(seller_item)
        self.assertEqual(reservation.status, 'awaiting_consent')
        self.assertTrue(seller_item.is_available)
        self.assertEqual(asset.item.owner_type, 'user')

        ok, error = respond_to_failed_seller_title_transfer(reservation, buyer, accepted=False)
        self.assertTrue(ok, error)
        db.session.refresh(reservation)
        db.session.refresh(buyer)
        self.assertEqual(reservation.status, 'cancelled')
        self.assertEqual(buyer.provisional_credits, 300)

    def test_insufficient_seller_provisional_for_downward_revaluation_never_goes_negative(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=300,
            backing_values=[300],
        )
        asset = reservation.backing_assets[0]
        ok, error = verify_backing_asset(asset, passed=True)
        self.assertTrue(ok, error)
        seller.provisional_credits = 0
        db.session.commit()
        ok, error = verify_seller_item(reservation, passed=True, revised_value=200)
        self.assertTrue(ok, error)
        proposal = ReservationRevaluation.query.filter_by(
            reservation_id=reservation.id
        ).one()
        ok, error = respond_to_reservation_revaluation(proposal.id, buyer, accepted=True)
        self.assertTrue(ok, error)
        ok, error = respond_to_reservation_revaluation(proposal.id, seller, accepted=True)
        self.assertTrue(ok, error)

        db.session.refresh(reservation)
        db.session.refresh(seller)
        db.session.refresh(seller_item)
        self.assertEqual(reservation.status, 'awaiting_consent')
        self.assertTrue(reservation.seller_item_revaluation_failed)
        self.assertEqual(seller.provisional_credits, 0)
        self.assertEqual(seller_item.provisional_credit_amount, 300)
        self.assertEqual(seller_item.value, 300)

    def test_buyer_can_add_backing_asset_to_cover_revaluation_shortfall(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=300,
            backing_values=[300],
        )
        initial_asset = reservation.backing_assets[0]
        ok, error = verify_backing_asset(initial_asset, passed=True, revised_value=250)
        self.assertTrue(ok, error)
        proposal = ReservationRevaluation.query.filter_by(
            reservation_id=reservation.id
        ).one()
        ok, error = respond_to_reservation_revaluation(proposal.id, buyer, accepted=False)
        self.assertTrue(ok, error)

        extra_item = Item(
            name='Additional backing item',
            category='Electronics',
            user_id=buyer.id,
            value=300,
            status='approved',
            is_approved=True,
            is_available=True,
            provisional_credit_amount=300,
            provisional_credit_settled=False,
        )
        db.session.add(extra_item)
        db.session.commit()
        ok, error = add_reservation_backing_assets(
            reservation,
            buyer,
            [extra_item.id],
            consent_confirmed=True,
        )
        self.assertTrue(ok, error)
        added_asset = ReservationAsset.query.filter_by(
            reservation_id=reservation.id,
            item_id=extra_item.id,
        ).one()
        ok, error = verify_backing_asset(added_asset, passed=True)
        self.assertTrue(ok, error)
        ok, error = verify_seller_item(reservation, passed=True)
        self.assertTrue(ok, error)

        db.session.refresh(reservation)
        db.session.refresh(extra_item)
        self.assertEqual(reservation.status, 'completed')
        self.assertEqual(extra_item.owner_type, 'barterex')

    def test_buyer_and_seller_can_view_pending_revaluation_decisions(self):
        buyer, seller, seller_item, reservation = self._create_reservation(
            purchase_value=300,
            backing_values=[300],
        )
        ok, error = verify_seller_item(reservation, passed=True, revised_value=350)
        self.assertTrue(ok, error)

        client = app.test_client()
        with client.session_transaction() as flask_session:
            flask_session['_user_id'] = str(buyer.id)
            flask_session['_fresh'] = True
        buyer_page = client.get('/my-revaluations')
        self.assertEqual(buyer_page.status_code, 200)
        self.assertIn('Requested item', buyer_page.get_data(as_text=True))

        buyer_reservations = client.get('/my_reservations')
        self.assertEqual(buyer_reservations.status_code, 200)
        self.assertIn('Review revaluation proposals', buyer_reservations.get_data(as_text=True))

        with client.session_transaction() as flask_session:
            flask_session['_user_id'] = str(seller.id)
            flask_session['_fresh'] = True
        seller_page = client.get('/my-revaluations')
        self.assertEqual(seller_page.status_code, 200)
        self.assertIn('Accept revised value', seller_page.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
