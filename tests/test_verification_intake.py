import os
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from app import app, db
from services.email_two_factor import fingerprint
from models import Admin, CustodyEvent, Item, Order, OrderItem, Reservation, User, VerificationIntake
from services.verification_intake_service import (
    IntakeValidationError,
    create_verification_intake,
    record_custody_handoff,
    record_order_delivery_custody,
    reconcile_delivered_order_custody,
)


class VerificationIntakeTests(unittest.TestCase):
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
        self.admin = Admin(
            username='intake-admin',
            email='intake-admin@example.com',
            is_super_admin=True,
            password='test-hash',
        )
        self.owner = User(
            username='item-owner',
            email='item-owner@example.com',
            password_hash='test-hash',
        )
        db.session.add_all([self.admin, self.owner])
        db.session.flush()
        self.item = Item(
            name='Test device',
            ai_estimated_value=125,
            category='Electronics',
            condition='Like New',
            serial_number='SERIAL-123',
            user_id=self.owner.id,
            status='approved',
        )
        db.session.add(self.item)
        db.session.commit()
        self.details = {
            'received_location': 'Barter Express Main Station',
            'observed_condition': 'Like New',
            'observed_serial_number': 'SERIAL-123',
            'serial_check': 'matched',
            'identity_confirmed': 'yes',
            'accessories_received': 'Charger',
            'intake_notes': 'Powers on and screen is intact.',
        }

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_intake_creates_snapshot_and_initial_custody_event(self):
        intake = create_verification_intake(
            self.item,
            self.admin.id,
            self.details,
            workflow_type='reservation_seller_item',
            outcome='passed',
        )
        db.session.commit()

        self.assertEqual(intake.item_id, self.item.id)
        self.assertEqual(intake.workflow_type, 'reservation_seller_item')
        self.assertEqual(intake.outcome, 'passed')
        self.assertEqual(intake.observed_serial_number, 'SERIAL-123')
        self.assertTrue(intake.identity_confirmed)
        self.assertEqual(len(intake.custody_events), 1)
        receipt = intake.custody_events[0]
        self.assertEqual(receipt.event_type, 'received')
        self.assertEqual(receipt.to_location, 'Barter Express Main Station')
        self.assertEqual(receipt.custodian_name, self.admin.username)
        self.assertEqual(receipt.recorded_by_admin_id, self.admin.id)

    def test_standard_item_approval_route_records_intake(self):
        self.item.status = 'pending'
        self.item.is_approved = False
        self.item.is_available = False
        db.session.commit()
        client = app.test_client()
        with client.session_transaction() as flask_session:
            flask_session['admin_id'] = self.admin.id
            flask_session['admin_mfa'] = fingerprint(self.admin)
            flask_session['admin_username'] = self.admin.username

        with patch('trading_points.award_points_for_upload', return_value=None), \
             patch('referral_rewards.award_referral_bonus', return_value={'success': False}), \
             patch('routes.auth.send_email_async'), \
             patch('routes.admin.report_verification', return_value=None):
            response = client.post(
                f'/admin/approve/{self.item.id}',
                data=dict(
                    self.details,
                    value='125',
                    video_url='',
                ),
            )

        self.assertEqual(response.status_code, 302)
        intake = VerificationIntake.query.filter_by(item_id=self.item.id).one()
        self.assertEqual(intake.workflow_type, 'standard_item_verification')
        self.assertEqual(intake.outcome, 'passed')
        self.assertEqual(CustodyEvent.query.filter_by(intake_id=intake.id).count(), 1)

    def test_missing_serial_is_saved_on_passed_inspection_across_workflows(self):
        for workflow in ('reservation_seller_item', 'reservation_backing_item', 'manual_valuation'):
            with self.subTest(workflow=workflow):
                self.item.serial_number = '   '
                db.session.commit()
                intake = create_verification_intake(
                    self.item, self.admin.id,
                    dict(self.details, observed_serial_number='  OBSERVED-123  '),
                    workflow_type=workflow, outcome='passed',
                )
                db.session.commit()
                db.session.refresh(self.item)
                self.assertEqual(self.item.serial_number, 'OBSERVED-123')
                self.assertEqual(intake.observed_serial_number, 'OBSERVED-123')
                self.assertEqual(intake.inspected_by_admin_id, self.admin.id)

    def test_missing_serial_is_not_saved_on_failed_or_invalid_inspection(self):
        self.item.serial_number = None
        db.session.commit()
        for details, message in (
            (dict(self.details, observed_serial_number=''), 'physically observed'),
            (dict(self.details, observed_serial_number='x' * 101), '100 characters'),
            (dict(self.details, identity_confirmed='no'), 'positively identified'),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(IntakeValidationError, message):
                    create_verification_intake(
                        self.item, self.admin.id, details,
                        workflow_type='reservation_seller_item', outcome='passed',
                    )
                self.assertIsNone(self.item.serial_number)
                self.assertEqual(VerificationIntake.query.count(), 0)
        intake = create_verification_intake(
            self.item, self.admin.id, self.details,
            workflow_type='reservation_seller_item', outcome='failed',
        )
        db.session.commit()
        self.assertIsNone(self.item.serial_number)
        self.assertEqual(intake.observed_serial_number, 'SERIAL-123')

    def test_existing_serial_cannot_be_overwritten(self):
        with self.assertRaisesRegex(IntakeValidationError, 'differs from'):
            create_verification_intake(
                self.item, self.admin.id,
                dict(self.details, observed_serial_number='REPLACEMENT'),
                workflow_type='reservation_seller_item', outcome='passed',
            )
        self.assertEqual(self.item.serial_number, 'SERIAL-123')
        self.assertEqual(VerificationIntake.query.count(), 0)

    def test_passing_item_requires_confirmed_identity_and_matching_serial(self):
        incorrect_identity = dict(self.details, identity_confirmed='no')
        with self.assertRaisesRegex(IntakeValidationError, 'positively identified'):
            create_verification_intake(
                self.item,
                self.admin.id,
                incorrect_identity,
                workflow_type='reservation_seller_item',
                outcome='passed',
            )

        serial_mismatch = dict(
            self.details,
            observed_serial_number='SERIAL-999',
            serial_check='mismatch',
        )
        with self.assertRaisesRegex(IntakeValidationError, 'serial-number mismatch'):
            create_verification_intake(
                self.item,
                self.admin.id,
                serial_mismatch,
                workflow_type='reservation_seller_item',
                outcome='passed',
            )
        self.assertEqual(VerificationIntake.query.count(), 0)
        self.assertEqual(CustodyEvent.query.count(), 0)

    def test_failed_inspection_records_identity_and_serial_mismatch(self):
        intake = create_verification_intake(
            self.item,
            self.admin.id,
            dict(self.details, identity_confirmed='no', serial_check='mismatch'),
            workflow_type='reservation_seller_item',
            outcome='failed',
        )
        db.session.commit()

        self.assertEqual(intake.outcome, 'failed')
        self.assertFalse(intake.identity_confirmed)
        self.assertEqual(intake.serial_check, 'mismatch')

    def test_custody_handoff_appends_event_with_previous_location(self):
        intake = create_verification_intake(
            self.item,
            self.admin.id,
            self.details,
            workflow_type='reservation_seller_item',
            outcome='passed',
        )
        db.session.flush()
        first_event_id = intake.custody_events[0].id
        event = record_custody_handoff(
            intake,
            self.admin.id,
            'Barter Express Secure Store',
            'Inventory Manager',
            'Moved to locked storage.',
        )
        db.session.commit()

        self.assertEqual(CustodyEvent.query.count(), 2)
        self.assertEqual(event.event_type, 'handed_off')
        self.assertEqual(event.from_location, 'Barter Express Main Station')
        self.assertEqual(event.to_location, 'Barter Express Secure Store')
        self.assertEqual(event.custodian_name, 'Inventory Manager')
        self.assertEqual(event.recorded_by_admin_id, self.admin.id)
        self.assertEqual(CustodyEvent.query.get(first_event_id).event_type, 'received')

    def test_custody_handoff_route_records_staff_and_receiver(self):
        intake = create_verification_intake(
            self.item,
            self.admin.id,
            self.details,
            workflow_type='reservation_seller_item',
            outcome='passed',
        )
        db.session.commit()
        client = app.test_client()
        with client.session_transaction() as flask_session:
            flask_session['admin_id'] = self.admin.id
            flask_session['admin_mfa'] = fingerprint(self.admin)
            flask_session['admin_username'] = self.admin.username

        response = client.post(
            f'/admin/verification-intake/{intake.id}/custody',
            data={
                'to_location': 'Secure store',
                'custodian_name': 'Inventory manager',
                'notes': 'Placed in locked storage.',
            },
        )

        self.assertEqual(response.status_code, 302)
        handoff = CustodyEvent.query.filter_by(intake_id=intake.id).order_by(
            CustodyEvent.id.desc()
        ).first()
        self.assertEqual(handoff.event_type, 'handed_off')
        self.assertEqual(handoff.recorded_by_admin_id, self.admin.id)
        self.assertEqual(handoff.custodian_name, 'Inventory manager')
        page_response = client.get('/admin/verification-intake')
        self.assertEqual(page_response.status_code, 200)
        self.assertIn(b'Test device', page_response.data)

    def test_custody_handoff_requires_location_and_receiver_name(self):
        intake = create_verification_intake(
            self.item,
            self.admin.id,
            self.details,
            workflow_type='reservation_backing_item',
            outcome='passed',
        )
        with self.assertRaisesRegex(IntakeValidationError, 'new item location'):
            record_custody_handoff(intake, self.admin.id, '', 'Inventory Manager')
        with self.assertRaisesRegex(IntakeValidationError, 'receiving custodian name'):
            record_custody_handoff(intake, self.admin.id, 'Secure store', '')
        self.assertEqual(CustodyEvent.query.count(), 1)

    def _delivery_fixture(self, method='pickup'):
        buyer = User(username='delivery-buyer', email='buyer@example.com', password_hash='x')
        db.session.add(buyer)
        db.session.flush()
        reservation = Reservation(
            user_id=buyer.id, item_id=self.item.id, status='completed',
            provisional_credits_used=125, delivery_method=method,
            delivery_fee_status='paid' if method == 'home delivery' else 'not_required',
            expires_at=datetime.utcnow() + timedelta(days=1),
        )
        db.session.add(reservation)
        db.session.flush()
        intake = create_verification_intake(
            self.item, self.admin.id, self.details,
            workflow_type='reservation_seller_item', outcome='passed', reservation=reservation,
        )
        order = Order(
            user_id=buyer.id, reservation_id=reservation.id, order_number='DELIVERY-TEST',
            status='Out for Delivery' if method == 'home delivery' else 'Ready for Pickup',
            delivery_method=method, date_ordered=datetime.utcnow(),
        )
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderItem(order_id=order.id, item_id=self.item.id))
        db.session.commit()
        client = app.test_client()
        with client.session_transaction() as session:
            session['admin_id'] = self.admin.id
            session['admin_mfa'] = fingerprint(self.admin)
        return client, order, intake, buyer

    def _assert_delivery_closes_custody(self, method):
        client, order, intake, buyer = self._delivery_fixture(method)
        with patch('trading_points.award_points_for_purchase', return_value=None) as points:
            response = client.post(f'/admin/update_order_status/{order.id}')
            self.assertEqual(response.status_code, 302)
            response = client.post(f'/admin/update_order_status/{order.id}')
            self.assertEqual(response.status_code, 302)
            points.assert_called_once()
        db.session.refresh(order)
        self.assertEqual(order.status, 'Delivered')
        self.assertIsNotNone(order.actual_delivery_date)
        events = CustodyEvent.query.filter_by(intake_id=intake.id).order_by(CustodyEvent.id).all()
        self.assertEqual([event.event_type for event in events], ['received', 'released_to_buyer'])
        self.assertEqual(events[-1].custodian_name, buyer.username)
        self.assertEqual(events[-1].recorded_by_admin_id, self.admin.id)
        self.assertEqual(events[-1].from_location, self.details['received_location'])
        self.assertEqual(events[-1].to_location, 'Released to buyer')
        self.assertIn(order.order_number, events[-1].notes)
        active = client.get('/admin/verification-intake').get_data(as_text=True)
        self.assertNotIn('Test device', active)
        history = client.get('/admin/verification-intake?view=history').get_data(as_text=True)
        self.assertIn('Test device', history)
        self.assertIn('Final recipient', history)
        self.assertIn('Released to buyer', history)
        self.assertNotIn(f'action="/admin/verification-intake/{intake.id}/custody"', history)
        with self.assertRaisesRegex(IntakeValidationError, 'closed'):
            record_custody_handoff(intake, self.admin.id, 'Office', 'Staff')

    def test_retired_home_delivery_does_not_release_custody(self):
        client, order, intake, buyer = self._delivery_fixture('home delivery')
        with patch('trading_points.award_points_for_purchase') as points:
            response = client.post(f'/admin/update_order_status/{order.id}')
        self.assertEqual(response.status_code, 302)
        points.assert_not_called()
        self.assertEqual(order.status, 'Out for Delivery')
        self.assertIsNone(order.actual_delivery_date)
        self.assertEqual(CustodyEvent.query.filter_by(intake_id=intake.id).count(), 1)
        order.status = 'Delivered'
        db.session.commit()
        self.assertEqual(reconcile_delivered_order_custody(self.admin.id), (0, []))

    def test_station_collection_closes_custody_once(self):
        self._assert_delivery_closes_custody('pickup')

    def test_failed_custody_write_rolls_back_delivery_and_date(self):
        client, order, intake, buyer = self._delivery_fixture()
        with patch(
            'services.verification_intake_service.record_order_delivery_custody',
            side_effect=IntakeValidationError('Cannot record handoff'),
        ), patch('trading_points.award_points_for_purchase') as points:
            response = client.post(f'/admin/update_order_status/{order.id}')
        self.assertEqual(response.status_code, 302)
        points.assert_not_called()
        db.session.refresh(order)
        self.assertEqual(order.status, 'Ready for Pickup')
        self.assertIsNone(order.actual_delivery_date)
        self.assertEqual(CustodyEvent.query.filter_by(intake_id=intake.id).count(), 1)

    def test_backfill_keeps_history_and_does_not_release_backing_or_new_intake(self):
        client, order, intake, buyer = self._delivery_fixture()
        backing = Item(name='Backing item', category='Electronics', user_id=buyer.id)
        db.session.add(backing)
        db.session.flush()
        backing_intake = create_verification_intake(
            backing, self.admin.id, dict(self.details, serial_check='not_applicable'),
            workflow_type='reservation_backing_item', outcome='passed',
        )
        later = create_verification_intake(
            self.item, self.admin.id, self.details,
            workflow_type='reservation_seller_item', outcome='passed',
        )
        later.received_at = order.date_ordered + timedelta(days=1)
        order.status = 'Delivered'
        db.session.commit()
        response = client.post('/admin/verification-intake/synchronize-deliveries')
        self.assertEqual(response.status_code, 302)
        self.assertIn('view=history', response.location)
        self.assertEqual(CustodyEvent.query.filter_by(intake_id=intake.id, event_type='released_to_buyer').count(), 1)
        self.assertEqual(CustodyEvent.query.filter_by(intake_id=later.id).count(), 1)
        self.assertEqual(CustodyEvent.query.filter_by(intake_id=backing_intake.id).count(), 1)
        self.assertIsNone(order.actual_delivery_date)
        recorded, missing = reconcile_delivered_order_custody(self.admin.id)
        db.session.commit()
        self.assertEqual(recorded, 0)
        self.assertEqual(missing, [])
        active = client.get('/admin/verification-intake').get_data(as_text=True)
        self.assertIn('Test device', active)
        self.assertIn('Backing item', active)

    def test_same_second_inspection_matches_sqlite_order_timestamp(self):
        client, order, intake, buyer = self._delivery_fixture()
        order.date_ordered = intake.received_at.replace(microsecond=0)
        order.status = 'Delivered'
        db.session.commit()
        recorded, missing = record_order_delivery_custody(order, self.admin.id)
        db.session.commit()
        self.assertEqual(recorded, 1)
        self.assertEqual(missing, [])

    def test_cancelled_order_cannot_release_custody(self):
        client, order, intake, buyer = self._delivery_fixture()
        order.cancelled = True
        db.session.commit()
        response = client.post(f'/admin/update_order_status/{order.id}')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(order.status, 'Ready for Pickup')
        self.assertEqual(CustodyEvent.query.filter_by(intake_id=intake.id).count(), 1)

    def test_missing_legacy_intake_is_reported_without_fabrication(self):
        client, order, intake, buyer = self._delivery_fixture()
        legacy_item = Item(name='Legacy item', category='Electronics', user_id=buyer.id)
        db.session.add(legacy_item)
        db.session.flush()
        db.session.add(OrderItem(order_id=order.id, item_id=legacy_item.id))
        order.status = 'Delivered'
        db.session.commit()
        recorded, missing = record_order_delivery_custody(order, self.admin.id, historical=True)
        db.session.commit()
        self.assertEqual(recorded, 1)
        self.assertEqual(missing, [legacy_item.id])
        self.assertEqual(VerificationIntake.query.filter_by(item_id=legacy_item.id).count(), 0)
        self.assertEqual(CustodyEvent.query.filter_by(item_id=legacy_item.id).count(), 0)

    def test_history_is_read_only_and_reconciliation_requires_permission(self):
        client, order, intake, buyer = self._delivery_fixture()
        newer = create_verification_intake(
            self.item, self.admin.id, self.details,
            workflow_type='reservation_seller_item', outcome='passed',
        )
        db.session.commit()
        with self.assertRaisesRegex(IntakeValidationError, 'historical'):
            record_custody_handoff(intake, self.admin.id, 'Office', 'Staff')
        all_records = client.get('/admin/verification-intake?view=all').get_data(as_text=True)
        self.assertNotIn(f'action="/admin/verification-intake/{intake.id}/custody"', all_records)
        self.assertIn(f'action="/admin/verification-intake/{newer.id}/custody"', all_records)
        self.admin.is_super_admin = False
        self.admin.permission_list = ['inventory.view']
        db.session.commit()
        response = client.post('/admin/verification-intake/synchronize-deliveries')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(CustodyEvent.query.filter_by(event_type='released_to_buyer').count(), 0)


if __name__ == '__main__':
    unittest.main()
