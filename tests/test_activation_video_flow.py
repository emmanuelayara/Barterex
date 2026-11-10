import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from app import app, db, limiter
from models import Admin, Item, ItemVideo, ReservationCreditEntry, User
from services.video_service import build_object_name
from services.video_publishing import run_next_job


class ActivationVideoFlowTests(unittest.TestCase):
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
        self.previous_limiter = limiter.enabled
        limiter.enabled = False
        db.drop_all()
        db.create_all()
        self.owner = User(
            username='video-owner',
            email='video-owner@example.com',
            password_hash='test-hash',
            phone_number='12345', address='Test road', city='Lagos', state='Lagos',
            id_verification_status='submitted',
        )
        self.admin = Admin(
            username='video-admin',
            email='video-admin@example.com',
            is_super_admin=True,
            password='test-hash',
        )
        db.session.add_all([self.owner, self.admin])
        db.session.flush()
        self.item = Item(
            name='Video test item',
            category='Electronics',
            user_id=self.owner.id,
            value=125,
            ai_estimated_value=125,
            ai_valuated_at=datetime.utcnow(),
            status='valuation_only',
            is_approved=False,
            is_available=False,
        )
        db.session.add(self.item)
        db.session.commit()
        self.owner_id, self.item_id = self.owner.id, self.item.id
        email = patch('routes.auth.send_email_async')
        email.start()
        self.addCleanup(email.stop)

    def tearDown(self):
        limiter.enabled = self.previous_limiter
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login_owner(self, client):
        with client.session_transaction() as session:
            session['_user_id'] = str(self.owner.id)
            session['_fresh'] = True

    def test_valuation_page_prompts_for_video_before_trade_submission(self):
        client = app.test_client()
        self._login_owner(client)

        response = client.get('/my_valuations')
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Camera recording only; gallery videos are not allowed.', page)
        self.assertIn('Start Recording', page)
        self.assertIn('item-camera-dialog activation-camera-dialog', page)
        self.assertIn('css/camera.css', page)
        self.assertIn('cameraDialog.showModal()', page)
        self.assertIn('Stop &amp; Review', page)
        self.assertIn("cameraDialog.addEventListener('cancel'", page)
        self.assertIn('MediaRecorder', page)
        self.assertNotIn('type="file"', page)
        self.assertIn('Retake Video', page)
        self.assertIn('playsinline', page)
        self.assertIn('.video-submit-form [hidden] { display: none !important; }', page)
        self.assertIn('This recording has no audio.', page)
        self.assertIn("visibilitychange", page)
        self.assertIn('60 seconds', page)
        self.assertIn('video-submit-form', page)
        self.assertIn('video-submit-form no-loading', page)
        self.assertIn('activate/request-upload-url', page)
        self.assertIn('Upload video &amp; submit for review', page)
        self.assertNotIn('Pre-Verification', page)

    def test_trade_request_requires_uploaded_video(self):
        client = app.test_client()
        self._login_owner(client)

        response = client.post(
            f'/items/{self.item.id}/trade-this-item',
            data={'ownership_confirmed': '1'},
        )

        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.item)
        self.assertEqual(self.item.status, 'valuation_only')
        self.assertEqual(ItemVideo.query.count(), 0)

    def test_valuation_expiry_boundary_matches_database_filter(self):
        now = datetime(2026, 11, 9, 12, 0)
        for age, expired in (
            (timedelta(days=30) - timedelta(microseconds=1), False),
            (timedelta(days=30), True),
            (timedelta(days=30) + timedelta(microseconds=1), True),
        ):
            with self.subTest(age=age):
                self.item.ai_valuated_at = now - age
                db.session.commit()
                self.assertEqual(self.item.valuation_is_expired(now), expired)
                self.assertEqual(
                    Item.query.filter(Item.unexpired_valuation_filter(now)).count(),
                    0 if expired else 1,
                )
                self.assertEqual(self.item.valuation_expires_at,
                                 self.item.ai_valuated_at + timedelta(days=30))

    def test_valuation_page_shows_countdown_and_hides_expired_records(self):
        client = app.test_client()
        self._login_owner(client)
        response = client.get('/my_valuations')
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.item.name, page)
        self.assertIn('data-valuation-expires=', page)
        self.assertIn('Expires in 29d', page)
        self.assertIn('data-server-now=', page)
        self.assertIn('class="page-container mp valuations-page"', page)
        self.assertIn('title="Expires ', page)
        self.assertIn('Saved valuations expire after 30 days.', page)
        self.assertIn('aria-label="Valuations, 1 pending"', page)

        self.item.ai_valuated_at = datetime.utcnow() - timedelta(days=31)
        db.session.commit()
        page = client.get('/my_valuations').get_data(as_text=True)
        self.assertNotIn(self.item.name, page)
        self.assertNotIn('data-valuation-expires=', page)
        self.assertIn('No current valuations to show.', page)
        self.assertNotIn('aria-label="Valuations, 1 pending"', page)
        db.session.refresh(self.item)
        self.assertEqual(self.item.status, 'valuation_only')
        self.assertEqual(self.item.ai_estimated_value, 125)
        self.assertEqual(Item.query.count(), 1)

    def test_expired_valuation_cannot_get_video_url_or_submit_trade(self):
        client = app.test_client()
        self._login_owner(client)
        self.item.ai_valuated_at = datetime.utcnow() - timedelta(days=30)
        db.session.commit()
        self.assertFalse(self.item.can_submit_activation_video())
        with patch('services.video_service.generate_upload_url') as signed, patch(
            'services.video_service.validate_uploaded_object'
        ) as validate:
            response = client.post(
                f'/items/{self.item.id}/activate/request-upload-url',
                json={'content_type': 'video/mp4'},
            )
            self.assertEqual(response.status_code, 403)
            self.assertIn('valuation has expired', response.get_json()['error'])
            self.assertEqual(response.get_json()['redirect_url'], '/upload')
            response = client.post(
                f'/items/{self.item.id}/trade-this-item',
                data={'ownership_confirmed': '1', 'object_name': 'test'},
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.location, '/upload')
            signed.assert_not_called()
            validate.assert_not_called()
        db.session.refresh(self.item)
        self.assertEqual(self.item.status, 'valuation_only')
        self.assertFalse(self.item.ownership_confirmed)
        self.assertEqual(ItemVideo.query.count(), 0)

    def test_expiry_does_not_change_submitted_or_pending_items(self):
        client = app.test_client()
        self._login_owner(client)
        self.item.ai_valuated_at = datetime.utcnow() - timedelta(days=90)
        for status in ('pending_activation', 'manual_review_pending', 'approved'):
            with self.subTest(status=status):
                self.item.status = status
                db.session.commit()
                self.assertIsNone(self.item.valuation_expires_at)
                self.assertFalse(self.item.valuation_is_expired())
                self.assertEqual(Item.query.filter(
                    Item.unexpired_valuation_filter(datetime.utcnow())
                ).count(), 1)
                if status in Item.LIFECYCLE_STATUSES:
                    page = client.get('/my_valuations').get_data(as_text=True)
                    self.assertIn(self.item.name, page)
                    self.assertNotIn('data-valuation-expires=', page)
        self.item.status = 'valuation_only'
        self.item.ai_estimated_value = None
        self.item.verification_status = 'pending_valuation'
        db.session.commit()
        self.assertFalse(self.item.valuation_is_expired())
        self.assertIn(self.item.name, client.get('/my_valuations').get_data(as_text=True))

    def test_manual_valuation_uses_inspection_date_and_preserves_company_acquisition(self):
        now = datetime.utcnow()
        self.item.manual_review_requested = True
        self.item.manual_custody_choice = 'home'
        self.item.ai_valuated_at = now - timedelta(days=90)
        self.item.manual_verified_at = now - timedelta(days=1)
        db.session.commit()
        self.assertEqual(self.item.valuation_expires_at, now + timedelta(days=29))
        self.assertFalse(self.item.valuation_is_expired(now))
        self.item.manual_verified_at = now - timedelta(days=30)
        db.session.commit()
        self.assertTrue(self.item.valuation_is_expired(now))
        self.item.manual_custody_choice = 'company'
        db.session.commit()
        self.assertIsNone(self.item.valuation_expires_at)
        self.assertFalse(self.item.valuation_is_expired(now))
        self.assertTrue(self.item.can_submit_activation_video())
        self.assertEqual(Item.query.filter(Item.unexpired_valuation_filter(now)).count(), 1)

    def test_undated_legacy_valuation_requires_fresh_upload(self):
        self.item.ai_valuated_at = None
        db.session.commit()
        self.assertTrue(self.item.valuation_is_expired())
        self.assertFalse(self.item.can_submit_activation_video())
        self.assertEqual(Item.query.filter(
            Item.unexpired_valuation_filter(datetime.utcnow())
        ).count(), 0)

    def test_previously_submitted_item_can_replace_rejected_video_after_30_days(self):
        self.item.ai_valuated_at = datetime.utcnow() - timedelta(days=45)
        db.session.add(ItemVideo(
            item_id=self.item.id, uploaded_by_id=self.owner.id,
            temp_video_url='rejected-test-video', status='rejected',
        ))
        db.session.commit()
        self.assertFalse(self.item.valuation_is_expired())
        self.assertTrue(self.item.can_submit_activation_video())
        self.assertEqual(Item.query.filter(
            Item.unexpired_valuation_filter(datetime.utcnow())
        ).count(), 1)
        client = app.test_client()
        self._login_owner(client)
        page = client.get('/my_valuations').get_data(as_text=True)
        self.assertIn(self.item.name, page)
        self.assertIn('<details class="trade-details">', page)
        self.assertNotIn('data-valuation-expires=', page)

    def test_expired_records_are_filtered_before_pagination(self):
        for index in range(12):
            db.session.add(Item(
                name=f'Expired saved item {index}', category='Electronics',
                user_id=self.owner.id, status='valuation_only',
                ai_estimated_value=125, ai_valuated_at=datetime.utcnow() - timedelta(days=31),
            ))
        db.session.commit()
        client = app.test_client()
        self._login_owner(client)
        with patch('routes.user.render_template', return_value='ok') as render:
            self.assertEqual(client.get('/my_valuations').status_code, 200)
        pagination = render.call_args.kwargs['items']
        self.assertEqual(pagination.total, 1)
        self.assertEqual(pagination.pages, 1)
        self.assertEqual(pagination.items, [self.item])
        self.assertEqual(Item.query.count(), 13)

    def test_trade_and_signed_upload_require_profile_then_identity_submission(self):
        client = app.test_client()
        self._login_owner(client)
        for field, target, expected in (
            ('phone_number', 'edit=profile', 'Complete your profile'),
            ('id_verification_status', '#verification', 'Submit your NIN'),
        ):
            with self.subTest(field=field):
                old = getattr(self.owner, field)
                setattr(self.owner, field, None if field == 'phone_number' else 'not_submitted')
                db.session.commit()
                page = client.get('/my_valuations').get_data(as_text=True)
                self.assertIn('Before trading, complete your profile', page)
                self.assertNotIn('<details class="trade-details">', page)
                with patch('services.video_service.generate_upload_url') as signed, patch(
                    'services.video_service.validate_uploaded_object'
                ) as validate:
                    response = client.post(
                        f'/items/{self.item.id}/activate/request-upload-url',
                        json={'content_type': 'video/mp4'},
                    )
                    self.assertEqual(response.status_code, 403)
                    self.assertIn(expected, response.get_json()['error'])
                    self.assertIn(target, response.get_json()['redirect_url'])
                    signed.assert_not_called()
                    response = client.post(
                        f'/items/{self.item.id}/trade-this-item',
                        data={'ownership_confirmed': '1', 'object_name': 'test'},
                    )
                    self.assertEqual(response.status_code, 302)
                    self.assertIn(target, response.location)
                    validate.assert_not_called()
                db.session.refresh(self.item)
                self.assertEqual(self.item.status, 'valuation_only')
                self.assertFalse(self.item.ownership_confirmed)
                self.assertEqual(ItemVideo.query.count(), 0)
                setattr(self.owner, field, old)
                db.session.commit()
        self.assertIn('<details class="trade-details">', client.get('/my_valuations').get_data(as_text=True))

    def test_trade_request_rejects_an_invalid_video_object(self):
        client = app.test_client()
        self._login_owner(client)

        with patch(
            'services.video_service.validate_uploaded_object',
            return_value={'success': False, 'error': 'The video upload could not be found.'},
        ):
            response = client.post(
                f'/items/{self.item.id}/trade-this-item',
                data={
                    'ownership_confirmed': '1',
                    'object_name': build_object_name(self.item.id, 'video/mp4'),
                },
            )

        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.item)
        self.assertEqual(self.item.status, 'valuation_only')
        self.assertEqual(ItemVideo.query.count(), 0)

    def test_first_trade_submission_records_uploaded_video_for_review(self):
        client = app.test_client()
        self._login_owner(client)
        object_name = build_object_name(self.item.id, 'video/mp4')

        with patch(
            'services.video_service.validate_uploaded_object',
            return_value={'success': True},
        ):
            response = client.post(
                f'/items/{self.item.id}/trade-this-item',
                data={
                    'ownership_confirmed': '1',
                    'serial_number': 'SERIAL-55',
                    'object_name': object_name,
                },
            )

        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.item)
        video = ItemVideo.query.one()
        self.assertEqual(self.item.status, 'pending_activation')
        self.assertTrue(self.item.ownership_confirmed)
        self.assertEqual(video.status, 'pending')
        self.assertEqual(video.temp_video_url, object_name)

    def test_upload_url_can_be_requested_before_video_review(self):
        client = app.test_client()
        self._login_owner(client)
        object_name = build_object_name(self.item.id, 'video/mp4')

        with patch(
            'services.video_service.generate_upload_url',
            return_value={
                'success': True,
                'upload_url': 'https://storage.example/upload',
                'object_name': object_name,
            },
        ):
            response = client.post(
                f'/items/{self.item.id}/activate/request-upload-url',
                json={'content_type': 'video/mp4'},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['object_name'], object_name)

    def _pending_video(self):
        self.item.status = 'pending_activation'
        video = ItemVideo(
            item_id=self.item.id,
            uploaded_by_id=self.owner.id,
            temp_video_url=build_object_name(self.item.id, 'video/mp4'),
            status='pending',
        )
        db.session.add(video)
        db.session.commit()
        client = app.test_client()
        with client.session_transaction() as session:
            session['admin_id'] = self.admin.id
        return client, video

    def test_approval_lists_at_ai_value_and_grants_credits_once(self):
        self.item.value = 999
        self.item.ai_estimated_value = 250.4
        self.owner.provisional_credits = 50
        client, video = self._pending_video()
        video_id = video.id
        def publish_video(*args, **kwargs):
            kwargs['on_session']('https://www.googleapis.com/upload/session')
            kwargs['on_result']('published01')
            return 'published01'

        with patch('services.video_service.download_bytes', return_value=b'video'), \
             patch('services.video_service.delete_object', return_value=True), \
             patch('services.youtube_publisher.upload_video', side_effect=publish_video) as publish, \
             patch('services.youtube_publisher.get_video_status', return_value=True):
            response = client.post(f'/admin/video-review/{video_id}/approve')
            self.assertEqual(response.status_code, 302)
            self.assertEqual(db.session.get(ItemVideo, video_id).status, 'queued')
            publish.assert_not_called()
            client.post(f'/admin/video-review/{video_id}/approve')
            run_next_job()
            publish.assert_called_once()
            run_next_job()  # Cleanup only, never another upload or credit.

        self.owner = db.session.get(User, self.owner_id)
        self.item = db.session.get(Item, self.item_id)
        video = db.session.get(ItemVideo, video_id)
        self.assertEqual(self.owner.provisional_credits, 300)
        self.assertEqual(self.owner.credits, 0)
        self.assertEqual(self.item.value, 250)
        self.assertEqual(self.item.provisional_credit_amount, 250)
        self.assertTrue(self.item.is_available)
        self.assertEqual(video.status, 'approved')
        entry = ReservationCreditEntry.query.filter_by(item_id=self.item.id).one()
        self.assertEqual((entry.amount, entry.balance_before, entry.balance_after), (250, 50, 300))

        # Public marketplace access proves other users can discover the item.
        response = app.test_client().get('/marketplace')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.item.name, response.get_data(as_text=True))

    def test_approval_blocks_invalid_ai_values_before_publishing_or_crediting(self):
        client, video = self._pending_video()
        for value in (None, 0, -10, float('inf'), float('nan'), 0.1):
            with self.subTest(value=value):
                self.item.ai_estimated_value = value
                db.session.commit()
                with patch('services.youtube_publisher.upload_video') as publish, \
                     patch('services.video_service.download_bytes') as download:
                    response = client.post(f'/admin/video-review/{video.id}/approve')
                    self.assertEqual(response.status_code, 302)
                    publish.assert_not_called()
                    download.assert_not_called()
                db.session.refresh(video)
                self.assertEqual(video.status, 'pending')
                self.assertEqual(self.owner.provisional_credits, 0)
                self.assertFalse(self.item.is_available)
                self.assertEqual(ReservationCreditEntry.query.count(), 0)

    def test_failed_publishing_does_not_activate_or_grant_credits(self):
        client, video = self._pending_video()
        video_id = video.id
        from services.youtube_publisher import PublishingError
        with patch('services.video_service.download_bytes', return_value=b'video'), \
             patch('services.youtube_publisher.upload_video', side_effect=PublishingError('Publishing unavailable')):
            client.post(f'/admin/video-review/{video_id}/approve')
            run_next_job()
        video = db.session.get(ItemVideo, video_id)
        self.assertEqual(video.status, 'retry_wait')
        self.assertFalse(db.session.get(Item, self.item_id).is_available)
        self.assertEqual(db.session.get(User, self.owner_id).provisional_credits, 0)
        self.assertEqual(ReservationCreditEntry.query.count(), 0)


if __name__ == '__main__':
    unittest.main()
