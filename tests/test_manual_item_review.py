import io
import importlib.util
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from PIL import Image
from flask import g
from app import app, db, limiter
from models import Admin, Item, ItemVideo, User, VerificationIntake, ReservationCreditEntry, ClearingInventoryItem, PickupStation, Reservation, Order
from services.item_activation_service import activate_item


class ManualReviewTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.ctx = app.app_context()
        self.ctx.push()
        db.drop_all()
        db.create_all()
        self.user = User(
            username='manual-user', email='manual@example.com', password_hash='test',
            phone_number='12345', address='Test road', city='Lagos', state='Lagos',
            id_verification_status='submitted',
        )
        self.admin = Admin(username='boss', email='boss@example.com', password='test', is_super_admin=True)
        db.session.add_all([self.user, self.admin])
        db.session.flush()
        self.item = Item(
            name='Test phone', category='Phones & Gadgets', condition='Brand New',
            user_id=self.user.id, uploaded_by_id=self.user.id,
            status='manual_review_pending', manual_review_requested=True,
            ai_estimated_value=50,
        )
        db.session.add(self.item)
        db.session.commit()
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.user.id)
            session['_fresh'] = True
        self.reviewer = app.test_client()
        with self.reviewer.session_transaction() as session:
            session['admin_id'] = self.admin.id
        self.email = patch('routes.auth.send_email_async').start()
        if limiter:
            self.previous_limiter = limiter.enabled
            limiter.enabled = False

    def tearDown(self):
        patch.stopall()
        if limiter:
            limiter.enabled = self.previous_limiter
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def choose(self, choice):
        return self.client.post(f'/items/{self.item.id}/manual-custody', data={
            'custody_choice': choice, 'consent': '1',
        })

    def verify(self, value='500', outcome='passed'):
        return self.reviewer.post(f'/admin/manual-review/{self.item.id}/verify', data={
            'value': value, 'outcome': outcome, 'received_location': 'Office',
            'observed_condition': 'Brand New', 'serial_check': 'not_applicable',
            'identity_confirmed': 'yes', 'intake_notes': 'Physical functionality inspected.',
        })

    def test_unverified_item_cannot_activate_or_obtain_upload_url(self):
        self.assertEqual(self.client.get('/my_valuations').status_code, 200)
        with self.assertRaises(ValueError):
            self.item.activation_credit_amount()
        response = self.client.post(f'/items/{self.item.id}/activate/request-upload-url', json={'content_type': 'video/mp4'})
        self.assertEqual(response.status_code, 400)
        self.client.post(f'/items/{self.item.id}/trade-this-item', data={'ownership_confirmed': '1'})
        self.assertEqual(self.item.status, 'manual_review_pending')
        self.assertEqual(ReservationCreditEntry.query.count(), 0)

    def test_home_choice_uses_manual_value_and_grants_provisional_once_after_video(self):
        self.assertEqual(self.choose('home').status_code, 302)
        self.assertEqual(self.verify().status_code, 302)
        db.session.refresh(self.item)
        self.assertEqual(self.item.status, 'valuation_only')
        self.assertEqual(self.item.activation_credit_amount(), 500)
        self.assertEqual(self.user.credits, 0)
        self.assertEqual(self.user.provisional_credits, 0)
        self.assertTrue(self.item.can_submit_activation_video())
        self.assertEqual(activate_item(self.item.id, 'https://youtu.be/abcdefghijk'), 500)
        db.session.commit()
        self.assertEqual(self.user.provisional_credits, 500)
        self.assertEqual(self.user.credits, 0)
        self.reviewer.post('/admin/fix-missing-credits')
        self.assertEqual(self.user.credits, 0)
        with self.assertRaises(ValueError):
            activate_item(self.item.id, 'https://youtu.be/abcdefghijk')
        self.assertEqual(VerificationIntake.query.one().custody_events[-1].custodian_name, self.user.username)

    def test_company_choice_transfers_ownership_and_grants_spendable_only_after_video(self):
        self.choose('company')
        self.verify()
        db.session.refresh(self.item)
        self.assertIsNone(self.item.user_id)
        self.assertEqual(self.item.owner_type, 'barterex')
        self.assertFalse(self.item.is_available)
        self.assertEqual(self.user.credits, 0)
        self.assertEqual(ClearingInventoryItem.query.one().status, 'awaiting_activation')
        response = self.client.get('/my_valuations')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Trade This Item', response.data)
        with patch('services.video_service.generate_upload_url', return_value={'success': True}):
            self.assertEqual(self.client.post(
                f'/items/{self.item.id}/activate/request-upload-url', json={'content_type': 'video/mp4'},
            ).status_code, 200)
        self.assertEqual(activate_item(self.item.id, 'https://youtu.be/abcdefghijk'), 500)
        db.session.commit()
        self.assertEqual(self.user.credits, 500)
        self.assertEqual(self.user.provisional_credits, 0)
        self.assertEqual(ReservationCreditEntry.query.one().balance_type, 'spendable')
        self.assertEqual(ClearingInventoryItem.query.one().status, 'held_for_resale')
        self.assertTrue(self.item.is_available)

    def test_invalid_value_failed_inspection_and_missing_consent_do_not_unlock(self):
        self.verify()
        self.assertEqual(VerificationIntake.query.count(), 0)
        self.choose('home')
        for value in ('nan', 'inf', '-5', '0'):
            self.verify(value)
            self.assertEqual(VerificationIntake.query.count(), 0)
        self.verify(outcome='failed')
        db.session.refresh(self.item)
        self.assertIsNone(self.item.manual_verified_at)
        self.assertFalse(self.item.can_submit_activation_video())
        self.assertEqual(self.user.credits, 0)

    def test_manual_upload_skips_ai_and_is_private(self):
        def image():
            stream = io.BytesIO()
            Image.new('RGB', (30, 30), 'blue').save(stream, 'PNG')
            stream.seek(0)
            return stream, 'test.png'
        with tempfile.TemporaryDirectory() as folder, \
             patch.dict(app.config, {'UPLOAD_FOLDER': folder}), \
             patch('routes.items.start_ai_valuation') as valuation, \
             patch('image_analyzer.analyze_image_url', return_value={}):
            response = self.client.post('/upload', data={
                'name': 'Manual test item', 'description': 'A detailed test description for this item.',
                'category': 'Phones & Gadgets', 'condition': 'Brand New',
                'manual_review': '1', 'images': [image() for _ in range(6)],
            })
        self.assertEqual(response.status_code, 302)
        uploaded = Item.query.filter_by(name='Manual test item').one()
        self.assertEqual(uploaded.status, 'manual_review_pending')
        self.assertTrue(uploaded.manual_review_requested)
        self.assertFalse(uploaded.is_available)
        self.assertIsNone(uploaded.ai_estimated_value)
        valuation.assert_not_called()

    def test_company_purchase_route_completes_and_does_not_repay_uploader(self):
        self.choose('company')
        self.verify()
        activate_item(self.item.id, 'https://youtu.be/abcdefghijk')
        buyer = User(username='buyer', email='buyer@example.com', password_hash='test',
                     credits=1000, phone_number='12345', address='Test road', city='Lagos', state='Lagos')
        station = PickupStation(name='Office', state='Lagos', city='Lagos', address='Test road')
        db.session.add_all([buyer, station])
        db.session.commit()
        g.pop('_login_user', None)
        with self.client.session_transaction() as session:
            session['_user_id'] = str(buyer.id)
        self.assertIn(b'physically verified', self.client.get(f'/item/{self.item.id}').data)
        self.assertIn(b'completes this purchase immediately', self.client.get(
            f'/item/{self.item.id}/choose-backing-assets').data)
        response = self.client.post(f'/item/{self.item.id}/reserve', data={
            'funding_mode': 'spendable', 'delivery_method': 'pickup', 'pickup_station_id': station.id,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, '/my_orders')
        self.assertEqual(Reservation.query.one().status, 'completed')
        self.assertEqual(Order.query.one().user_id, buyer.id)
        self.assertEqual(self.user.credits, 500)
        self.assertEqual(buyer.credits, 500)
        self.assertEqual(self.item.user_id, buyer.id)
        self.assertEqual(self.item.clearing_inventory.status, 'sold')

    def test_serial_is_physically_recorded_and_video_cannot_replace_it(self):
        self.choose('home')
        self.reviewer.post(f'/admin/manual-review/{self.item.id}/verify', data={
            'value': '500', 'outcome': 'passed', 'received_location': 'Office',
            'observed_condition': 'Brand New', 'serial_check': 'matched',
            'observed_serial_number': 'ABC-123', 'identity_confirmed': 'yes',
        })
        db.session.refresh(self.item)
        self.assertEqual(self.item.serial_number, 'ABC-123')
        self.client.post(f'/items/{self.item.id}/trade-this-item', data={
            'serial_number': 'ALTERED', 'ownership_confirmed': '1', 'object_name': 'test',
        })
        self.assertEqual(self.item.status, 'valuation_only')
        self.assertEqual(self.item.serial_number, 'ABC-123')

    def test_permission_csrf_and_legacy_status_routes_cannot_bypass_review(self):
        self.choose('home')
        self.admin.is_super_admin = False
        self.admin.permission_list = ['items.review']
        db.session.commit()
        self.assertEqual(self.reviewer.get('/admin/manual-review').status_code, 403)
        self.assertEqual(self.verify().status_code, 403)
        self.admin.permission_list = ['items.manual_review']
        db.session.commit()
        self.assertEqual(self.reviewer.get('/admin/manual-review').status_code, 200)
        with patch.dict(app.config, {'WTF_CSRF_ENABLED': True}):
            self.verify()
        self.assertEqual(VerificationIntake.query.count(), 0)
        self.admin.is_super_admin = True
        db.session.commit()
        self.reviewer.post(f'/admin/approve/{self.item.id}', data={'value': '500'})
        self.reviewer.post('/admin/update-status', data={'item_id': self.item.id, 'status': 'approved'})
        self.assertEqual(self.item.status, 'manual_review_pending')
        self.assertEqual(self.user.credits, 0)
        self.assertEqual(self.user.provisional_credits, 0)

    def test_company_uploader_declaration_and_custody_cannot_be_changed_after_pass(self):
        self.choose('company')
        self.verify()
        response = self.client.get('/my_valuations')
        self.assertIn(b'I confirm I transferred this item', response.data)
        self.assertNotIn(b'I confirm I own this item', response.data)
        self.choose('home')
        db.session.refresh(self.item)
        self.assertEqual(self.item.manual_custody_choice, 'company')
        other = User(username='other', email='other@example.com', password_hash='test')
        db.session.add(other)
        db.session.commit()
        g.pop('_login_user', None)
        with self.client.session_transaction() as session:
            session['_user_id'] = str(other.id)
        self.assertEqual(self.client.post(f'/items/{self.item.id}/activate/request-upload-url',
                                         json={'content_type': 'video/mp4'}).status_code, 404)

    def test_consent_required_and_video_review_uses_physical_value(self):
        self.client.post(f'/items/{self.item.id}/manual-custody', data={'custody_choice': 'company'})
        self.assertIsNone(self.item.manual_custody_consent_at)
        with patch.dict(app.config, {'WTF_CSRF_ENABLED': True}):
            self.choose('company')
        self.assertIsNone(self.item.manual_custody_consent_at)
        self.choose('company')
        self.verify()
        self.item.status = 'pending_activation'
        video = ItemVideo(item_id=self.item.id, uploaded_by_id=self.user.id,
                          temp_video_url='activation-videos/test.mp4', status='pending')
        db.session.add(video)
        db.session.commit()
        with patch('services.video_service.generate_read_url', return_value='https://example.com/preview'):
            response = self.reviewer.get('/admin/video-review')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Physically verified activation value ᗸ500'.encode(), response.data)
        self.assertNotIn(b'AI activation value', response.data)


class ManualReviewMigrationTests(unittest.TestCase):
    def test_existing_rows_upgrade_and_direct_acquisitions_block_downgrade(self):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from sqlalchemy import create_engine, inspect
        path = Path(__file__).resolve().parent.parent / 'migrations' / 'versions' / 'add_manual_item_review.py'
        spec = importlib.util.spec_from_file_location('manual_review_migration', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        engine = create_engine('sqlite:///:memory:')
        with engine.begin() as connection:
            connection.exec_driver_sql('CREATE TABLE item (id INTEGER PRIMARY KEY, status VARCHAR(50))')
            connection.exec_driver_sql("INSERT INTO item VALUES (1, 'approved')")
            connection.exec_driver_sql('CREATE TABLE clearing_inventory_item (id INTEGER PRIMARY KEY, reservation_id INTEGER NOT NULL, reservation_asset_id INTEGER NOT NULL)')
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                self.assertEqual(connection.exec_driver_sql('SELECT status, manual_review_requested FROM item').one(),
                                 ('approved', 0))
                connection.exec_driver_sql('INSERT INTO clearing_inventory_item VALUES (1, NULL, NULL)')
                with self.assertRaises(RuntimeError):
                    migration.downgrade()
                connection.exec_driver_sql('DELETE FROM clearing_inventory_item WHERE id=1')
                connection.exec_driver_sql('UPDATE item SET manual_review_requested = true')
                with self.assertRaises(RuntimeError):
                    migration.downgrade()
                connection.exec_driver_sql('UPDATE item SET manual_review_requested = false')
                migration.downgrade()
                self.assertNotIn('manual_review_requested', {c['name'] for c in inspect(connection).get_columns('item')})
                self.assertFalse(inspect(connection).get_columns('clearing_inventory_item')[1]['nullable'])
        engine.dispose()
