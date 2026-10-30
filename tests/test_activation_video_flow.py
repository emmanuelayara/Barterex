import os
import unittest
from unittest.mock import patch

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from app import app, db
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
        db.drop_all()
        db.create_all()
        self.owner = User(
            username='video-owner',
            email='video-owner@example.com',
            password_hash='test-hash',
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
        self.assertIn('Use your camera or choose a video from your device', page)
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
