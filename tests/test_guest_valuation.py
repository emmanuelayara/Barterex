import io
import os
import re
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from PIL import Image
from flask import g
from werkzeug.security import generate_password_hash

from app import app, db, limiter
from models import GuestValuation, Item, ItemImage, User
from services import guest_valuation_service as guests
from services.guest_valuation_service import GUEST_COOKIE, run_valuation

PASSWORD = 'OriginalSecure!123'
AI_RESPONSE = {
    'success': True, 'fair_value': 250000.0, 'confidence_score': 90, 'total_comparables': 12,
    'value_range': {'min': 220000.0, 'max': 280000.0},
    'risk_assessment': {'score': 5, 'level': 'LOW', 'flags': []},
    'credits': {'status': 'APPROVED'}, 'sources_used': ['market'],
}


def jpeg(index):
    data = io.BytesIO()
    Image.new('RGB', (30, 30), (index * 20 % 255, 80, 160)).save(data, 'JPEG')
    data.seek(0)
    return data, f'item-camera-{index}.jpg'


class GuestValuationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.context = app.app_context()
        self.context.push()
        self.previous_limiter = limiter.enabled
        limiter.enabled = False
        db.create_all()
        self.queued = []
        self.valuate = patch('valuator_client.client.valuate', return_value=AI_RESPONSE).start()
        for target, replacement in (
            ('routes.guest_valuation.valuator_enabled', lambda: True),
            ('services.guest_valuation_service.storage_root', lambda: os.path.join(self.folder, 'guests')),
            ('valuator_client.queue_valuator_task', lambda fn, *args: self.queued.append(args[0]) or True),
            ('image_analyzer.analyze_image_url', lambda url: {}),
            ('routes.auth.send_email_async', lambda **kwargs: None),
        ):
            patch(target, replacement).start()
        patch.dict(app.config, {
            'UPLOAD_FOLDER': os.path.join(self.folder, 'uploads'), 'SESSION_COOKIE_SECURE': False,
        }).start()
        self.client = app.test_client()

    def tearDown(self):
        patch.stopall()
        limiter.enabled = self.previous_limiter
        db.session.remove()
        db.drop_all()
        self.context.pop()
        shutil.rmtree(self.folder, ignore_errors=True)

    # --- helpers -------------------------------------------------------------------------------
    def submit(self, client=None, photos=6, **overrides):
        data = {
            'name': 'iPhone 12 128GB', 'condition': 'Fairly Used', 'usage_duration': '2 years',
            'category': 'Phones & Gadgets',
            'description': 'Black iPhone 12, battery health 86 percent, small scratch on the back.',
            **overrides,
        }
        data['images'] = [jpeg(i) for i in range(photos)]
        return (client or self.client).post('/value/start', data=data, content_type='multipart/form-data')

    def run_jobs(self):
        while self.queued:
            run_valuation(self.queued.pop(0))
        db.session.expire_all()

    def record(self):
        return GuestValuation.query.order_by(GuestValuation.id.desc()).first()

    def make_user(self, name='ada', verified=True):
        user = User(username=name, email=f'{name}@example.com', password_hash=generate_password_hash(PASSWORD),
                    email_verified=verified, credits=1000, first_login=False)
        db.session.add(user)
        db.session.commit()
        return user

    def login(self, client, user):
        return client.post('/login', data={'credential': user.email, 'password': PASSWORD})

    def register(self, client, name='newbie'):
        return client.post('/register', data={
            'username': name, 'email': f'{name}@example.com', 'password': PASSWORD, 'confirm_password': PASSWORD,
        })

    def verify_email(self, client, email):
        user = User.query.filter_by(email=email).one()
        client.get(f'/verify-email/{user.email_verification_token}')
        db.session.expire_all()
        return user

    def ready_guest_client(self):
        client = app.test_client()
        self.assertEqual(self.submit(client).status_code, 200)
        self.run_jobs()
        return client

    # --- guest flow ----------------------------------------------------------------------------
    def test_guest_gets_one_private_estimate(self):
        response = self.submit()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['redirect_url'].endswith('/value/result'))
        token = self.client.get_cookie(GUEST_COOKIE).value
        record = self.record()
        self.assertEqual(record.status, 'processing')
        self.assertNotEqual(record.token_hash, token)
        self.assertEqual(record.token_hash, guests.hash_token(token))
        self.assertEqual(len(record.image_file_list()), 6)
        self.assertNotIn('static', guests.record_dir(record.id))
        self.assertIn('Estimating your item', self.client.get('/value/result').get_data(as_text=True))

        self.run_jobs()
        self.assertEqual(self.record().status, 'ready')
        status = self.client.get('/value/status').get_json()
        self.assertEqual(status['status'], 'ready')
        self.assertEqual(status['result']['estimated_value'], 250000.0)
        self.assertNotIn('risk', str(status))
        self.assertIn('250,000', self.client.get('/value/result').get_data(as_text=True))

        again = self.submit()
        self.assertEqual(again.status_code, 409)
        self.assertEqual(GuestValuation.query.count(), 1)
        self.assertEqual(self.valuate.call_count, 1)
        self.assertEqual(Item.query.count(), 0)

    def test_result_and_photos_are_only_visible_with_the_guest_token(self):
        self.submit()
        self.run_jobs()
        stranger = app.test_client()
        self.assertEqual(stranger.get('/value/photo/0').status_code, 404)
        self.assertEqual(stranger.get('/value/status').status_code, 404)
        self.assertEqual(stranger.get('/value/result').status_code, 302)
        stranger.set_cookie(GUEST_COOKIE, 'guess-of-the-token')
        self.assertEqual(stranger.get('/value/photo/0').status_code, 404)

        owner = self.client.get('/value/photo/0')
        self.assertEqual(owner.status_code, 200)
        self.assertEqual(owner.mimetype, 'image/jpeg')
        self.assertEqual(self.client.get('/value/photo/99').status_code, 404)
        for path in ('/value/result', '/value/status', '/value/photo/0', '/value/start'):
            self.assertEqual(self.client.get(path).headers.get('X-Robots-Tag'), 'noindex, nofollow', path)

    def test_invalid_submissions_are_rejected_without_saving(self):
        self.assertEqual(self.submit(photos=5).status_code, 400)
        self.assertEqual(self.submit(description='too short').status_code, 400)
        self.assertEqual(self.submit(category='Weapons').status_code, 400)
        bad = self.client.post('/value/start', data={
            'name': 'iPhone 12', 'condition': 'Brand New', 'category': 'Phones & Gadgets',
            'description': 'A boxed phone with every accessory included.',
            'images': [(io.BytesIO(b'not an image'), f'p{i}.jpg') for i in range(6)],
        }, content_type='multipart/form-data')
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(GuestValuation.query.count(), 0)
        self.assertFalse(os.path.exists(os.path.join(self.folder, 'guests')) and os.listdir(os.path.join(self.folder, 'guests')))

    def test_failed_estimate_can_be_retried(self):
        self.valuate.return_value = {'success': False, 'error': 'valuator exploded'}
        self.submit()
        self.run_jobs()
        self.assertEqual(self.record().status, 'failed')
        status = self.client.get('/value/status').get_json()
        self.assertEqual(status['status'], 'failed')
        self.assertNotIn('exploded', status['error'])

        self.valuate.return_value = AI_RESPONSE
        self.assertEqual(self.submit().status_code, 200)
        self.run_jobs()
        self.assertEqual(GuestValuation.query.count(), 1)
        self.assertEqual(self.record().status, 'ready')

    # --- claiming --------------------------------------------------------------------------------
    def test_registration_keeps_the_estimate_through_email_verification_on_another_device(self):
        guest = self.ready_guest_client()
        record_id = self.record().id
        self.assertEqual(self.register(guest).status_code, 302)
        user = User.query.filter_by(email='newbie@example.com').one()
        self.assertEqual(self.record().pending_user_id, user.id)
        self.assertGreater(self.record().expires_at, datetime.utcnow() + timedelta(hours=47))
        self.assertFalse(user.email_verified)
        self.assertIsNone(guests.claim_for_user(user))   # unverified accounts cannot claim

        other_device = app.test_client()                  # no guest cookie here
        self.verify_email(other_device, user.email)
        response = self.login(other_device, user)
        self.assertEqual(response.status_code, 302)
        item = Item.query.one()
        self.assertTrue(response.location.endswith(f'/my_valuations#item-{item.id}'))

        db.session.refresh(user)
        self.assertEqual((item.user_id, item.uploaded_by_id, item.status), (user.id, user.id, 'valuation_only'))
        self.assertFalse(item.is_approved)
        self.assertFalse(item.is_available)
        self.assertIsNone(item.value)
        self.assertIsNone(item.provisional_credit_amount)
        self.assertFalse(item.credited)
        self.assertEqual((user.credits, user.provisional_credits), (1000, 0))
        self.assertEqual(item.ai_estimated_value, 250000.0)
        self.assertEqual(item.name, 'iPhone 12 128GB')
        self.assertEqual(ItemImage.query.filter_by(item_id=item.id).count(), 6)
        upload_root = app.config['UPLOAD_FOLDER']
        self.assertTrue(all(os.path.isfile(os.path.join(upload_root, image.image_url)) for image in item.images))
        self.assertFalse(os.path.exists(guests.record_dir(record_id)))
        self.assertEqual(self.valuate.call_count, 1)

        claimed = db.session.get(GuestValuation, record_id)
        self.assertEqual((claimed.status, claimed.claimed_by_user_id, claimed.claimed_item_id), ('claimed', user.id, item.id))
        page = other_device.get(response.location)
        self.assertIn('iPhone 12 128GB', page.get_data(as_text=True))

        other_device.get('/logout')
        self.login(other_device, user)
        self.assertEqual(Item.query.count(), 1)

    def test_login_attaches_the_browsers_estimate_to_an_existing_account(self):
        user = self.make_user()
        guest = self.ready_guest_client()
        response = self.login(guest, user)
        item = Item.query.one()
        self.assertTrue(response.location.endswith(f'/my_valuations#item-{item.id}'))
        self.assertEqual(item.user_id, user.id)
        self.assertEqual(self.valuate.call_count, 1)
        self.assertIsNone(guest.get_cookie(GUEST_COOKIE))

    def test_two_factor_login_claims_only_after_the_code_is_verified(self):
        user = self.make_user()
        user.two_factor_enabled = True
        db.session.commit()
        guest = self.ready_guest_client()

        with patch('services.email_two_factor.mail.send') as send:
            response = self.login(guest, user)
            self.assertIn('/two-factor/verify', response.location)
            self.assertEqual(Item.query.count(), 0)
            self.assertEqual(self.record().status, 'ready')
            code = re.search(r'code is (\d{6})', send.call_args.args[0].body).group(1)
            response = guest.post('/two-factor/verify', data={'code': code})

        item = Item.query.one()
        self.assertIn(f'/my_valuations#item-{item.id}', response.location)
        self.assertEqual(item.user_id, user.id)
        self.assertEqual(item.ai_estimated_value, 250000.0)
        self.assertEqual(ItemImage.query.filter_by(item_id=item.id).count(), 6)
        self.assertFalse(item.is_approved or item.is_available or item.credited)
        db.session.refresh(user)
        self.assertEqual((user.credits, user.provisional_credits), (1000, 0))
        self.assertIsNone(guest.get_cookie(GUEST_COOKIE))
        self.assertEqual(self.valuate.call_count, 1)

    def test_logged_in_visitor_can_save_the_estimate_from_the_result_page(self):
        token = self.ready_guest_client().get_cookie(GUEST_COOKIE).value
        user = self.make_user()
        member = app.test_client()
        with member.session_transaction() as state:
            state['_user_id'] = user.get_id()
            state['_fresh'] = True
        member.set_cookie(GUEST_COOKIE, token)
        g.pop('_login_user', None)   # the test's shared app context caches the previous anonymous request's user
        self.assertIn('Save to my account', member.get('/value/result').get_data(as_text=True))
        self.assertTrue(member.get('/value/start').location.endswith('/upload'))
        response = member.post('/value/claim')
        self.assertEqual(Item.query.one().user_id, user.id)
        self.assertIn('/my_valuations#item-', response.location)
        self.assertEqual(member.post('/value/claim').status_code, 302)
        self.assertEqual(Item.query.count(), 1)

    def test_a_record_can_only_be_claimed_once(self):
        first, second = self.make_user('first'), self.make_user('second')
        guest = self.ready_guest_client()
        token = guest.get_cookie(GUEST_COOKIE).value
        self.assertIsNotNone(guests.claim_for_user(first, token))
        self.assertIsNone(guests.claim_for_user(second, token))
        self.assertEqual(Item.query.count(), 1)
        self.assertEqual(guests.claim_for_user(first, token).id, Item.query.one().id)   # same user: just reopened
        self.assertEqual(Item.query.count(), 1)
        self.assertIsNone(guests._claim_record(second, self.record().id, datetime.utcnow()))

    def test_registered_account_has_priority_over_other_logins_on_the_same_browser(self):
        guest = self.ready_guest_client()
        self.register(guest)
        intruder = self.make_user('intruder')
        self.login(guest, intruder)
        self.assertEqual(Item.query.count(), 0)
        self.assertEqual(self.record().status, 'ready')

    def test_claim_while_the_estimate_is_still_running_uses_the_single_ai_call(self):
        user = self.make_user()
        guest = app.test_client()
        self.submit(guest)
        folder = guests.record_dir(self.record().id)
        self.login(guest, user)
        item = Item.query.one()
        self.assertIsNone(item.ai_valuated_at)
        self.assertEqual(item.verification_status, 'pending_valuation')
        self.assertIsNone(item.ai_estimated_value)
        self.assertTrue(os.path.isdir(folder))  # the queued job still needs these originals

        self.run_jobs()
        db.session.refresh(item)
        self.assertEqual(item.ai_estimated_value, 250000.0)
        self.assertIsNotNone(item.ai_valuated_at)
        self.assertFalse(item.is_approved or item.is_available)
        self.assertEqual(self.valuate.call_count, 1)
        self.assertEqual(self.valuate.call_args.kwargs['image_count'], 6)
        self.assertEqual(len(self.valuate.call_args.kwargs['images']), 6)
        self.assertFalse(os.path.exists(folder))

    def test_claim_during_photo_encoding_preserves_all_job_inputs(self):
        from valuator_client import encode_image_file_to_base64

        user = self.make_user()
        self.submit()
        token = self.client.get_cookie(GUEST_COOKIE).value
        folder = guests.record_dir(self.record().id)
        claimed_items = []

        def encode_then_claim(path):
            encoded = encode_image_file_to_base64(path)
            if not claimed_items:
                claimed_items.append(guests.claim_for_user(user, token))
            return encoded

        with patch('valuator_client.encode_image_file_to_base64', side_effect=encode_then_claim):
            self.run_jobs()

        self.assertEqual(len(claimed_items), 1)
        self.assertIsNotNone(claimed_items[0])
        item = Item.query.one()
        self.assertEqual(item.ai_estimated_value, 250000.0)
        self.assertFalse(item.is_approved or item.is_available)
        self.assertEqual(ItemImage.query.filter_by(item_id=item.id).count(), 6)
        self.assertEqual(self.valuate.call_count, 1)
        self.assertEqual(self.valuate.call_args.kwargs['image_count'], 6)
        self.assertEqual(len(self.valuate.call_args.kwargs['images']), 6)
        self.assertFalse(os.path.exists(folder))

    def test_failed_job_after_claim_cleans_originals_and_keeps_item_photos(self):
        user = self.make_user()
        self.submit()
        folder = guests.record_dir(self.record().id)
        self.login(self.client, user)
        self.valuate.return_value = {'success': False, 'error': 'temporary valuation failure'}

        self.run_jobs()

        item = Item.query.one()
        self.assertIsNone(item.ai_estimated_value)
        self.assertEqual(item.verification_status, 'valuation_unavailable')
        self.assertIsNotNone(item.ai_valuated_at)
        self.assertFalse(item.is_approved or item.is_available)
        self.assertFalse(os.path.exists(folder))
        self.assertEqual(len(item.images), 6)
        self.assertTrue(all(os.path.isfile(os.path.join(app.config['UPLOAD_FOLDER'], image.image_url))
                            for image in item.images))
        self.assertEqual(len(self.valuate.call_args.kwargs['images']), 6)

    # --- expiry ----------------------------------------------------------------------------------
    def test_unclaimed_records_and_photos_expire(self):
        guest = self.ready_guest_client()
        token = guest.get_cookie(GUEST_COOKIE).value
        record = self.record()
        folder = guests.record_dir(record.id)
        self.assertTrue(os.path.isdir(folder))
        self.assertEqual(guests.purge_expired(), 0)

        record.expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()
        self.assertIsNone(guests.find_by_token(token))
        self.assertIsNone(guests.claim_for_user(self.make_user(), token))
        self.assertEqual(guest.get('/value/photo/0').status_code, 404)
        self.assertEqual(guests.purge_expired(), 1)
        self.assertEqual(GuestValuation.query.count(), 0)
        self.assertFalse(os.path.exists(folder))

    def test_verification_resend_extends_but_never_beyond_the_cap(self):
        guest = self.ready_guest_client()
        self.register(guest)
        user = User.query.filter_by(email='newbie@example.com').one()
        record = self.record()
        record.created_at = datetime.utcnow() - timedelta(days=6, hours=23)
        record.expires_at = datetime.utcnow() + timedelta(hours=1)
        db.session.commit()
        guests.keep_for_pending_user(user)
        self.assertEqual(self.record().expires_at, record.created_at + guests.MAX_RECORD_LIFETIME)

    def test_stale_processing_record_is_reported_as_failed(self):
        self.submit()
        record = self.record()
        record.created_at = datetime.utcnow() - timedelta(hours=1)
        db.session.commit()
        self.assertEqual(self.client.get('/value/status').get_json()['status'], 'failed')

    def test_logged_in_users_are_sent_to_the_regular_upload(self):
        user = self.make_user()
        with self.client.session_transaction() as state:
            state['_user_id'] = user.get_id()
            state['_fresh'] = True
        self.assertTrue(self.client.get('/value/start').location.endswith('/upload'))
        self.assertEqual(self.submit().status_code, 409)
        self.assertEqual(GuestValuation.query.count(), 0)

    def test_public_start_page_and_value_page_entry_point(self):
        page = self.client.get('/value/start')
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn('id="cameraPanel"', html)
        self.assertNotIn('type="file"', html)
        for shared in ('id="aiValuationOverlay"', 'id="aiLoaderPhrase"', 'js/valuation-loader.js',
                       'css/valuation-loader.css', 'data-status-url="/value/status"'):
            self.assertIn(shared, html)
        value_page = self.client.get('/check-item-value').get_data(as_text=True)
        self.assertIn('/value/start?category=Phones', value_page)


if __name__ == '__main__':
    unittest.main()
