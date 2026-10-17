import os
import unittest
from unittest.mock import patch

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from app import app, db
from models import Admin, CustodyEvent, Item, User, VerificationIntake
from services.verification_intake_service import (
    IntakeValidationError,
    create_verification_intake,
    record_custody_handoff,
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
            status='trade_requested',
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
            workflow_type='trade_preverification',
            outcome='passed',
        )
        db.session.commit()

        self.assertEqual(intake.item_id, self.item.id)
        self.assertEqual(intake.workflow_type, 'trade_preverification')
        self.assertEqual(intake.outcome, 'passed')
        self.assertEqual(intake.observed_serial_number, 'SERIAL-123')
        self.assertTrue(intake.identity_confirmed)
        self.assertEqual(len(intake.custody_events), 1)
        receipt = intake.custody_events[0]
        self.assertEqual(receipt.event_type, 'received')
        self.assertEqual(receipt.to_location, 'Barter Express Main Station')
        self.assertEqual(receipt.custodian_name, self.admin.username)
        self.assertEqual(receipt.recorded_by_admin_id, self.admin.id)

    def test_preverification_approval_route_records_intake_and_receipt(self):
        client = app.test_client()
        with client.session_transaction() as flask_session:
            flask_session['admin_id'] = self.admin.id
            flask_session['admin_username'] = self.admin.username

        response = client.post(
            f'/admin/pre-verification/{self.item.id}/approve',
            data=dict(self.details, final_value='125', preverification_notes='Approved'),
        )

        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.item)
        self.assertEqual(self.item.status, 'preverification_approved')
        intake = VerificationIntake.query.filter_by(item_id=self.item.id).one()
        self.assertEqual(intake.workflow_type, 'trade_preverification')
        self.assertEqual(intake.outcome, 'passed')
        self.assertEqual(CustodyEvent.query.filter_by(intake_id=intake.id).count(), 1)

    def test_standard_item_approval_route_records_intake(self):
        self.item.status = 'pending'
        self.item.is_approved = False
        self.item.is_available = False
        db.session.commit()
        client = app.test_client()
        with client.session_transaction() as flask_session:
            flask_session['admin_id'] = self.admin.id
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

    def test_passing_item_requires_confirmed_identity_and_matching_serial(self):
        incorrect_identity = dict(self.details, identity_confirmed='no')
        with self.assertRaisesRegex(IntakeValidationError, 'positively identified'):
            create_verification_intake(
                self.item,
                self.admin.id,
                incorrect_identity,
                workflow_type='trade_preverification',
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
                workflow_type='trade_preverification',
                outcome='passed',
            )
        self.assertEqual(VerificationIntake.query.count(), 0)
        self.assertEqual(CustodyEvent.query.count(), 0)

    def test_failed_inspection_records_identity_and_serial_mismatch(self):
        intake = create_verification_intake(
            self.item,
            self.admin.id,
            dict(self.details, identity_confirmed='no', serial_check='mismatch'),
            workflow_type='trade_preverification',
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
            workflow_type='trade_preverification',
            outcome='passed',
        )
        db.session.commit()
        client = app.test_client()
        with client.session_transaction() as flask_session:
            flask_session['admin_id'] = self.admin.id
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


if __name__ == '__main__':
    unittest.main()
