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
from services.email_two_factor import fingerprint
from models import Admin, Item, ItemImage, ItemVideo, User, VerificationIntake, ReservationCreditEntry, ClearingInventoryItem, PickupStation, Reservation, Order, Payment
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
        self.station = PickupStation(name='Lagos Office', state='Lagos', city='Lagos', address='Test road')
        db.session.add_all([self.user, self.admin, self.station])
        db.session.flush()
        self.item = Item(
            name='Test phone', category='Phones & Gadgets', condition='Brand New',
            user_id=self.user.id, uploaded_by_id=self.user.id,
            status='manual_review_pending', manual_review_requested=True,
            manual_station_id=self.station.id,
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
            session['admin_mfa'] = fingerprint(self.admin)
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

    def test_manual_review_displays_all_photos_with_full_size_links(self):
        from html.parser import HTMLParser

        class PhotoLinks(HTMLParser):
            def __init__(self):
                super().__init__()
                self.links = []
                self.images = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'a' and attrs.get('aria-label', '').startswith('View Test phone photo'):
                    self.links.append(attrs)
                if tag == 'img' and attrs.get('alt', '').startswith('Test phone - submitted photo'):
                    self.images.append(attrs)

        self.item.image_url = 'front.jpg'
        db.session.add_all([
            ItemImage(item_id=self.item.id, image_url='back.jpg', order_index=1),
            ItemImage(item_id=self.item.id, image_url='front.jpg', order_index=0, is_primary=True),
            ItemImage(item_id=self.item.id, image_url='side.jpg', order_index=2),
        ])
        db.session.commit()
        with tempfile.TemporaryDirectory() as folder, patch('app.get_upload_root_path', return_value=folder):
            for filename in ('front.jpg', 'back.jpg', 'side.jpg'):
                Image.new('RGB', (30, 30), 'blue').save(Path(folder) / filename, 'JPEG')
            response = self.reviewer.get('/admin/manual-review')
        self.assertEqual(response.status_code, 200)
        parser = PhotoLinks()
        parser.feed(response.get_data(as_text=True))
        self.assertEqual(len(parser.links), 3)
        self.assertEqual([link['href'] for link in parser.links], [img['src'] for img in parser.images])
        self.assertTrue(parser.links[0]['href'].endswith('/front.jpg'))
        self.assertTrue(parser.links[1]['href'].endswith('/back.jpg'))
        self.assertTrue(parser.links[2]['href'].endswith('/side.jpg'))
        for link in parser.links:
            self.assertEqual(link['target'], '_blank')
            self.assertIn('noopener', link['rel'])

    def test_manual_review_supports_legacy_photo_and_empty_gallery(self):
        self.item.image_url = 'legacy.jpg'
        db.session.commit()
        with tempfile.TemporaryDirectory() as folder, patch('app.get_upload_root_path', return_value=folder):
            Image.new('RGB', (30, 30), 'blue').save(Path(folder) / 'legacy.jpg', 'JPEG')
            response = self.reviewer.get('/admin/manual-review')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Test phone - submitted photo 1', response.data)
        self.assertIn(b'legacy.jpg', response.data)
        self.item.image_url = None
        db.session.commit()
        response = self.reviewer.get('/admin/manual-review')
        self.assertIn(b'No submitted photos are available for this item.', response.data)

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

    def test_manual_custody_consent_requires_complete_account(self):
        self.user.id_verification_status = 'not_submitted'
        db.session.commit()
        page = self.client.get('/my-manual-verifications').get_data(as_text=True)
        self.assertIn('Submit identity details to trade', page)
        self.assertNotIn('Save custody choice', page)
        response = self.client.post(f'/items/{self.item.id}/manual-custody', data={
            'custody_choice': 'company', 'consent': '1',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('#verification', response.location)
        db.session.refresh(self.item)
        self.assertIsNone(self.item.manual_custody_choice)
        self.assertIsNone(self.item.manual_custody_consent_at)

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
                'manual_review': '1', 'manual_station_id': str(self.station.id), 'images': [image() for _ in range(6)],
            })
        self.assertEqual(response.status_code, 302)
        uploaded = Item.query.filter_by(name='Manual test item').one()
        self.assertEqual(uploaded.status, 'manual_review_pending')
        self.assertEqual(uploaded.manual_station_id, self.station.id)
        self.assertTrue(uploaded.manual_review_requested)
        self.assertFalse(uploaded.is_available)
        self.assertIsNone(uploaded.ai_estimated_value)
        valuation.assert_not_called()

    def test_station_selection_legacy_visibility_and_admin_gate(self):
        self.item.manual_station_id = None
        db.session.commit()
        self.choose('home')
        page = self.client.get('/my-manual-verifications')
        self.assertIn(b'No station selected', page.data)
        self.assertIn(b'Test phone', page.data)
        self.assertNotIn(b'Test phone', self.client.get('/my_valuations').data)
        self.assertIn(b'Not selected', self.reviewer.get('/admin/manual-review').data)
        self.verify()
        self.assertEqual(VerificationIntake.query.count(), 0)
        self.client.post(f'/items/{self.item.id}/manual-station', data={'station_id': self.station.id})
        db.session.refresh(self.item)
        self.assertEqual(self.item.manual_station_id, self.station.id)
        self.assertIn(b'Lagos Office', self.reviewer.get('/admin/manual-review').data)
        self.verify()
        self.assertIn(b'Test phone', self.client.get('/my_valuations').data)
        self.assertNotIn(b'Test phone', self.client.get('/my-manual-verifications').data)
        self.client.post(f'/items/{self.item.id}/manual-station', data={'station_id': self.station.id})
        db.session.refresh(self.item)
        self.assertEqual(self.item.status, 'valuation_only')

    def test_tracker_navigation_and_valuation_badge_exclude_pending_manual_items(self):
        response = self.client.get('/settings')
        self.assertIn(b'Manual Verifications', response.data)
        page = self.client.get('/my_valuations')
        self.assertIn(b'My Manual Verifications', page.data)
        self.assertNotIn(b'Valuations (1 pending)', page.data)
        self.assertIn(b'Test phone', self.client.get('/my-manual-verifications').data)

    def test_tracker_uses_edit_controls_for_saved_choices(self):
        page = self.client.get('/my-manual-verifications').get_data(as_text=True)
        self.assertIn('aria-label="Edit verification station for Test phone"', page)
        self.assertNotIn('aria-label="Edit custody choice for Test phone"', page)
        self.assertIn('name="consent" value="1" required', page)
        self.choose('company')
        page = self.client.get('/my-manual-verifications').get_data(as_text=True)
        self.assertIn('aria-label="Edit custody choice for Test phone"', page)
        self.assertIn('Transfer to Barter Express', page)
        self.assertEqual(page.count('<details class="manual-editor">'), 2)
        self.verify(outcome='failed')
        page = self.client.get('/my-manual-verifications').get_data(as_text=True)
        self.assertNotIn('aria-label="Edit verification station for Test phone"', page)
        self.assertIn('aria-label="Edit custody choice for Test phone"', page)

    def test_legacy_missing_station_has_visible_selection_form(self):
        self.item.manual_station_id = None
        db.session.commit()
        page = self.client.get('/my-manual-verifications').get_data(as_text=True)
        self.assertIn('No station selected', page)
        self.assertIn('name="station_id" required', page)
        self.assertNotIn('aria-label="Edit verification station for Test phone"', page)

    def test_tracker_forms_and_pagination_are_accessible(self):
        from html.parser import HTMLParser

        class TrackerMarkup(HTMLParser):
            def __init__(self):
                super().__init__()
                self.select_depth = 0
                self.links_inside_select = []
                self.forms = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'select':
                    self.select_depth += 1
                if tag == 'a' and self.select_depth:
                    self.links_inside_select.append(attrs)
                if tag == 'form':
                    self.forms.append(attrs)

            def handle_endtag(self, tag):
                if tag == 'select':
                    self.select_depth -= 1

        db.session.add_all([
            Item(name=f'Pending item {index}', category='Phones & Gadgets', condition='Brand New',
                 user_id=self.user.id, uploaded_by_id=self.user.id, status='manual_review_pending',
                 manual_review_requested=True, manual_station_id=self.station.id)
            for index in range(10)
        ])
        db.session.commit()
        response = self.client.get('/my-manual-verifications')
        html = response.get_data(as_text=True)
        parser = TrackerMarkup()
        parser.feed(html)
        self.assertIn('manual-verifications.css', html)
        self.assertIn('aria-label="Manual verification pages"', html)
        self.assertIn('Page 1 of 2', html)
        self.assertEqual(len(parser.forms), 20)
        self.assertEqual(parser.links_inside_select, [])
        self.assertTrue(all(form['method'] == 'post' for form in parser.forms))
        second = self.client.get('/my-manual-verifications?page=2').get_data(as_text=True)
        self.assertIn('Test phone', second)
        self.assertIn('Page 2 of 2', second)
        self.assertIn('Previous', second)

    def test_station_changes_are_owner_scoped_and_locked_after_review(self):
        other_station = PickupStation(name='Second', state='Lagos', city='Lagos', address='Second road')
        foreign_station = PickupStation(name='Abuja', state='Abuja', city='Abuja', address='Road')
        db.session.add_all([other_station, foreign_station])
        db.session.commit()
        for invalid in ('', '999999', str(foreign_station.id)):
            self.client.post(f'/items/{self.item.id}/manual-station', data={'station_id': invalid})
            db.session.refresh(self.item)
            self.assertEqual(self.item.manual_station_id, self.station.id)
        self.client.post(f'/items/{self.item.id}/manual-station', data={'station_id': other_station.id})
        db.session.refresh(self.item)
        self.assertEqual(self.item.manual_station_id, other_station.id)
        self.choose('home')
        self.verify(outcome='failed')
        self.assertIn(b'Last review failed', self.client.get('/my-manual-verifications').data)
        self.client.post(f'/items/{self.item.id}/manual-station', data={'station_id': self.station.id})
        db.session.refresh(self.item)
        self.assertEqual(self.item.manual_station_id, other_station.id)
        other = User(username='other-user', email='other2@example.com', password_hash='test', state='Lagos')
        db.session.add(other)
        db.session.commit()
        g.pop('_login_user', None)
        with self.client.session_transaction() as session:
            session['_user_id'] = str(other.id)
        self.assertEqual(self.client.post(f'/items/{self.item.id}/manual-station',
                                          data={'station_id': self.station.id}).status_code, 404)

    def test_station_csrf_and_deletion_guard(self):
        with patch.dict(app.config, {'WTF_CSRF_ENABLED': True}):
            response = self.client.post(f'/items/{self.item.id}/manual-station', data={'station_id': self.station.id})
            self.assertEqual(response.status_code, 400)
        db.session.refresh(self.item)
        self.assertEqual(self.item.manual_station_id, self.station.id)
        self.reviewer.post(f'/admin/pickup_stations/delete/{self.station.id}')
        self.assertIsNotNone(db.session.get(PickupStation, self.station.id))
        self.reviewer.post(f'/admin/pickup_stations/edit/{self.station.id}', data={
            'name': 'Changed', 'state': 'Lagos', 'city': 'Lagos', 'address': 'New road',
        })
        db.session.refresh(self.station)
        self.assertEqual(self.station.name, 'Lagos Office')

    def test_manual_upload_requires_station_in_profile_state(self):
        foreign = PickupStation(name='Abuja', state='Abuja', city='Abuja', address='Road')
        db.session.add(foreign)
        db.session.commit()
        def image():
            stream = io.BytesIO()
            Image.new('RGB', (30, 30), 'blue').save(stream, 'PNG')
            stream.seek(0)
            return stream, 'test.png'
        for station_id in ('', '999999', str(foreign.id)):
            response = self.client.post('/upload', headers={'X-Requested-With': 'XMLHttpRequest'}, data={
                'name': 'Invalid station item', 'description': 'A detailed test description for this item.',
                'category': 'Phones & Gadgets', 'condition': 'Brand New', 'manual_review': '1',
                'manual_station_id': station_id, 'images': [image() for _ in range(6)],
            })
            self.assertEqual(response.status_code, 400)
            self.assertIn('verification station', response.get_json()['error'])
            self.assertIsNone(Item.query.filter_by(name='Invalid station item').first())
        self.user.state = None
        db.session.commit()
        response = self.client.post('/upload', headers={'X-Requested-With': 'XMLHttpRequest'}, data={
            'name': 'Invalid station item', 'description': 'A detailed test description for this item.',
            'category': 'Phones & Gadgets', 'condition': 'Brand New', 'manual_review': '1',
            'manual_station_id': str(self.station.id), 'images': [image() for _ in range(6)],
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'No stations are available in your profile state', self.client.get('/upload').data)
        self.assertIsNone(Item.query.filter_by(name='Invalid station item').first())

    def test_manual_ajax_upload_redirects_to_manual_tracker(self):
        def image():
            stream = io.BytesIO()
            Image.new('RGB', (30, 30), 'blue').save(stream, 'PNG')
            stream.seek(0)
            return stream, 'test.png'
        with tempfile.TemporaryDirectory() as folder, \
             patch.dict(app.config, {'UPLOAD_FOLDER': folder}), \
             patch('routes.items.notify_admins'), \
             patch('image_analyzer.analyze_image_url', return_value={}):
            response = self.client.post('/upload', headers={'X-Requested-With': 'XMLHttpRequest'}, data={
                'name': 'AJAX manual item', 'description': 'A detailed test description for this item.',
                'category': 'Phones & Gadgets', 'condition': 'Brand New', 'manual_review': '1',
                'manual_station_id': str(self.station.id), 'images': [image() for _ in range(6)],
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['redirect_url'], '/my-manual-verifications')
        self.assertEqual(Item.query.filter_by(name='AJAX manual item').one().manual_station_id, self.station.id)

    def test_station_refresh_uses_current_profile_state(self):
        other = PickupStation(name='Abuja Office', state='Abuja', city='Abuja', address='Road')
        db.session.add(other)
        db.session.commit()
        response = self.client.get('/manual-verification-stations')
        self.assertEqual([station['id'] for station in response.get_json()['stations']], [self.station.id])
        self.user.state = 'Abuja'
        db.session.commit()
        response = self.client.get('/manual-verification-stations')
        self.assertEqual(response.get_json()['state'], 'Abuja')
        self.assertEqual([station['id'] for station in response.get_json()['stations']], [other.id])
        g.pop('_login_user', None)
        self.assertEqual(app.test_client().get('/manual-verification-stations').status_code, 302)

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
        self.assertIn(b'accept the final terms and pay the service fee', self.client.get(
            f'/item/{self.item.id}/choose-backing-assets').data)
        response = self.client.post(f'/item/{self.item.id}/reserve', data={
            'funding_mode': 'spendable', 'delivery_method': 'pickup', 'pickup_station_id': station.id,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, f'/order/{Order.query.one().id}')
        self.assertEqual(Reservation.query.one().status, 'active')
        self.assertEqual(self.item.owner_type, 'barterex')
        reservation = Reservation.query.one()
        from paystack_payment_service import PaystackPaymentService
        with patch.object(PaystackPaymentService, 'TEST_MODE', True):
            self.client.post(f'/order/{Order.query.one().id}/service-fee', data={
                'accept_terms': 'yes', 'purchase_value': str(reservation.purchase_value),
                'service_fee': f'{reservation.service_fee_naira:.2f}',
            })
            payment = Payment.query.filter_by(purpose='reservation_service_fee').one()
            result = PaystackPaymentService.verify_payment(payment.paystack_reference)
            self.assertTrue(result['success'], result)
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
    def test_manual_station_migration_preserves_existing_items(self):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from sqlalchemy import create_engine, inspect
        path = Path(__file__).resolve().parent.parent / 'migrations' / 'versions' / 'add_manual_verification_station.py'
        spec = importlib.util.spec_from_file_location('manual_station_migration', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        engine = create_engine('sqlite:///:memory:')
        with engine.begin() as connection:
            connection.exec_driver_sql('CREATE TABLE pickup_station (id INTEGER PRIMARY KEY)')
            connection.exec_driver_sql('CREATE TABLE item (id INTEGER PRIMARY KEY, status VARCHAR(50))')
            connection.exec_driver_sql("INSERT INTO item VALUES (1, 'manual_review_pending')")
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                self.assertEqual(connection.exec_driver_sql('SELECT status, manual_station_id FROM item').one(),
                                 ('manual_review_pending', None))
                self.assertEqual(inspect(connection).get_foreign_keys('item')[0]['referred_table'], 'pickup_station')
                connection.exec_driver_sql('INSERT INTO pickup_station VALUES (1)')
                connection.exec_driver_sql('UPDATE item SET manual_station_id=1 WHERE id=1')
                with self.assertRaises(RuntimeError):
                    migration.downgrade()
                connection.exec_driver_sql('UPDATE item SET manual_station_id=NULL WHERE id=1')
                migration.downgrade()
                self.assertNotIn('manual_station_id', {c['name'] for c in inspect(connection).get_columns('item')})
        engine.dispose()

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
