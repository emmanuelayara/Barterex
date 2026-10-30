import os
import importlib.util
from pathlib import Path
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from app import app, db
from flask import g
from models import Admin, AuditLog, Item, ItemVideo, ReservationCreditEntry, User
from services import video_publishing as jobs
from services import youtube_publisher as youtube


class VideoPublishingTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.context = app.app_context()
        self.context.push()
        db.create_all()
        user = User(username='publisher-owner', email='owner@example.com', password_hash='x')
        admin = Admin(username='publisher-admin', email='admin@example.com', password='x', is_super_admin=True)
        db.session.add_all([user, admin])
        db.session.flush()
        item = Item(
            user_id=user.id, name='Publishing camera', category='Electronics',
            ai_estimated_value=250, status='pending_activation', is_approved=False, is_available=False,
        )
        db.session.add(item)
        db.session.flush()
        video = ItemVideo(
            item_id=item.id, uploaded_by_id=user.id, status='pending',
            temp_video_url='item-videos/test/source.mp4',
        )
        db.session.add(video)
        db.session.commit()
        self.user_id, self.admin_id, self.item_id, self.video_id = user.id, admin.id, item.id, video.id
        email = patch('routes.auth.send_email_async')
        self.email = email.start()
        self.addCleanup(email.stop)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def video(self):
        return db.session.get(ItemVideo, self.video_id)

    def client(self, allowed=True):
        client = app.test_client()
        g.pop('_login_user', None)
        with client.session_transaction() as session:
            session['admin_id'] = self.admin_id
        if not allowed:
            admin = db.session.get(Admin, self.admin_id)
            admin.is_super_admin = False
            admin.permission_list = ['messages.manage']
            db.session.commit()
        return client

    def queue(self):
        jobs.queue_video(self.video(), self.admin_id)
        db.session.commit()

    def make_due(self):
        self.video().publish_next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()

    @staticmethod
    def upload(*args, **kwargs):
        kwargs['on_session']('https://www.googleapis.com/upload/test-session')
        kwargs['on_progress'](60)
        kwargs['on_result']('abcdefghijk')
        return 'abcdefghijk'

    def run_worker(self, ready=True, upload=None):
        with patch.object(jobs.video_service, 'download_bytes', return_value=b'video'), \
             patch.object(youtube, 'upload_video', side_effect=upload or self.upload) as publish, \
             patch.object(youtube, 'get_video_status', return_value=ready), \
             patch.object(jobs.video_service, 'delete_object') as delete:
            self.assertTrue(jobs.run_next_job())
            delete.assert_not_called()
        return publish

    def test_approval_only_queues_durable_work_and_duplicate_click_is_safe(self):
        with patch.object(youtube, 'upload_video') as upload:
            client = self.client()
            client.post(f'/admin/video-review/{self.video_id}/approve')
            client.post(f'/admin/video-review/{self.video_id}/approve')
        upload.assert_not_called()
        self.assertEqual(self.video().status, 'queued')
        self.assertEqual(db.session.get(User, self.user_id).provisional_credits, 0)
        self.assertEqual(AuditLog.query.filter_by(action_type='queue_activation_video').count(), 1)

    def test_success_commits_activation_before_cleanup_and_retries_deletion(self):
        self.queue()
        self.run_worker()
        self.assertEqual(self.video().status, 'approved')
        self.assertIsNotNone(self.video().temp_video_url)
        self.assertEqual(db.session.get(User, self.user_id).provisional_credits, 250)
        self.assertEqual(ReservationCreditEntry.query.filter_by(entry_type='activation').count(), 1)
        with patch.object(jobs.video_service, 'delete_object', return_value=False):
            jobs.run_next_job()
        self.assertEqual(self.video().status, 'approved')
        self.assertEqual(self.video().cleanup_attempts, 1)
        self.video().cleanup_next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()
        with patch.object(jobs.video_service, 'delete_object', return_value=True):
            jobs.run_next_job()
        self.assertIsNone(self.video().temp_video_url)
        self.assertIsNotNone(self.video().temp_copy_deleted_at)
        self.assertEqual(ReservationCreditEntry.query.filter_by(entry_type='activation').count(), 1)

    def test_crash_after_session_commit_resumes_same_session(self):
        self.queue()

        def interrupted(*args, **kwargs):
            kwargs['on_session']('https://www.googleapis.com/upload/test-session')
            kwargs['on_progress'](55)
            raise ConnectionError('lost upload response')

        self.run_worker(upload=interrupted)
        self.assertEqual(self.video().status, 'retry_wait')
        self.assertEqual(self.video().publish_progress, 55)
        saved_session = self.video().upload_session_uri
        self.make_due()
        publish = self.run_worker()
        self.assertEqual(publish.call_args.kwargs['session_uri'], saved_session)
        self.assertEqual(self.video().status, 'approved')

    def test_activation_failure_reuses_committed_youtube_id_without_reupload(self):
        self.queue()
        with patch.object(jobs, 'activate_item', side_effect=RuntimeError('database interrupted')):
            self.run_worker()
        self.assertEqual(self.video().youtube_video_id, 'abcdefghijk')
        self.assertEqual(self.video().status, 'retry_wait')
        self.assertIsNotNone(self.video().temp_video_url)
        self.assertEqual(ReservationCreditEntry.query.count(), 0)
        self.make_due()
        publish = self.run_worker()
        publish.assert_not_called()
        self.assertEqual(self.video().status, 'approved')
        self.assertEqual(ReservationCreditEntry.query.count(), 1)

    def test_activation_commit_failure_rolls_back_credit_and_retains_source(self):
        self.queue()
        commit = db.session.commit
        interrupted = False

        def commit_with_failure():
            nonlocal interrupted
            if not interrupted and any(
                isinstance(obj, ItemVideo) and obj.status == 'approved' for obj in db.session.dirty
            ):
                interrupted = True
                raise RuntimeError('commit failed after activation was staged')
            return commit()

        with patch.object(db.session, 'commit', side_effect=commit_with_failure):
            self.run_worker()
        self.assertTrue(interrupted)
        self.assertEqual(self.video().status, 'retry_wait')
        self.assertEqual(self.video().youtube_video_id, 'abcdefghijk')
        self.assertIsNotNone(self.video().temp_video_url)
        self.assertEqual(ReservationCreditEntry.query.count(), 0)
        self.assertEqual(db.session.get(User, self.user_id).provisional_credits, 0)
        self.make_due()
        publish = self.run_worker()
        publish.assert_not_called()
        self.assertEqual(ReservationCreditEntry.query.count(), 1)

    def test_lost_final_id_commit_retains_session_for_recovery(self):
        self.queue()
        save = jobs._save

        def save_without_final_id(video_id, token, **values):
            if 'youtube_video_id' in values:
                raise RuntimeError('DB unavailable while recording final response')
            return save(video_id, token, **values)

        with patch.object(jobs, '_save', side_effect=save_without_final_id):
            self.run_worker()
        saved_session = self.video().upload_session_uri
        self.assertTrue(saved_session)
        self.assertIsNone(self.video().youtube_video_id)
        self.assertIsNotNone(self.video().temp_video_url)
        self.assertEqual(ReservationCreditEntry.query.count(), 0)
        self.make_due()
        publish = self.run_worker()
        self.assertEqual(publish.call_args.kwargs['session_uri'], saved_session)
        self.assertEqual(self.video().status, 'approved')

    def test_rejection_commits_before_worker_cleanup(self):
        with patch.object(jobs.video_service, 'delete_object') as delete:
            response = self.client().post(
                f'/admin/video-review/{self.video_id}/reject',
                data={'rejection_reason': 'Please show the item working.'},
            )
        self.assertEqual(response.status_code, 302)
        delete.assert_not_called()
        self.assertEqual(self.video().status, 'rejected')
        self.assertEqual(db.session.get(Item, self.item_id).status, 'valuation_only')
        with patch.object(jobs.video_service, 'delete_object', return_value=True):
            jobs.run_next_job()
        self.assertIsNone(self.video().temp_video_url)
        self.assertEqual(ReservationCreditEntry.query.count(), 0)

    def test_source_change_after_session_creation_stops_before_resume(self):
        self.queue()
        self.video().upload_source_sha256 = '0' * 64
        self.video().upload_session_uri = 'https://www.googleapis.com/upload/old-session'
        db.session.commit()
        publish = self.run_worker()
        publish.assert_not_called()
        self.assertEqual(self.video().status, 'publish_failed')

    def test_retry_does_not_erase_resumable_state(self):
        self.queue()
        video = self.video()
        video.status = 'publish_failed'
        video.upload_session_uri = 'https://www.googleapis.com/upload/preserved'
        video.publish_attempts = 5
        db.session.commit()
        response = self.client().post(f'/admin/video-review/{self.video_id}/retry')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.video().status, 'queued')
        self.assertEqual(self.video().publish_attempts, 0)
        self.assertEqual(self.video().upload_session_uri, 'https://www.googleapis.com/upload/preserved')

    def test_processing_wait_does_not_activate_or_reupload(self):
        self.queue()
        self.run_worker(ready=False)
        self.assertEqual(self.video().publish_phase, 'processing')
        self.assertEqual(self.video().publish_attempts, 0)
        self.assertFalse(db.session.get(Item, self.item_id).is_available)
        self.make_due()
        publish = self.run_worker()
        publish.assert_not_called()
        self.assertEqual(self.video().status, 'approved')

    def test_five_errors_stop_retries_and_notify_owner_and_admin(self):
        self.queue()
        for attempt in range(5):
            self.make_due()
            self.run_worker(upload=Mock(side_effect=youtube.PublishingError('API unavailable')))
            self.assertEqual(self.video().publish_attempts, attempt + 1)
        self.assertEqual(self.video().status, 'publish_failed')
        self.assertIsNone(self.video().publish_next_attempt_at)
        self.assertGreaterEqual(self.email.call_count, 2)
        self.assertFalse(jobs.run_next_job())
        self.assertEqual(ReservationCreditEntry.query.count(), 0)
        self.assertIsNotNone(self.video().temp_video_url)

    def test_revoked_youtube_token_shows_reauthorization_instructions(self):
        from google.auth.exceptions import RefreshError
        self.queue()
        self.run_worker(upload=Mock(side_effect=RefreshError(
            'invalid_grant: Token has been expired or revoked.', {})))
        video = self.video()
        self.assertEqual(video.status, 'retry_wait')
        self.assertIn('get_youtube_refresh_token.py', video.publish_error)

    def test_expired_session_blocks_reupload_and_can_link_existing_channel_video(self):
        self.queue()
        self.run_worker(upload=Mock(side_effect=youtube.PublishingError('Session unavailable', permanent=True)))
        self.assertEqual(self.video().status, 'publish_failed')
        with patch.object(youtube, 'get_video_status', return_value=True):
            response = self.client().post(
                f'/admin/video-review/{self.video_id}/reconcile',
                data={'youtube_video_id': 'abcdefghijk'},
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.video().youtube_video_id, 'abcdefghijk')
        publish = self.run_worker()
        publish.assert_not_called()
        self.assertEqual(self.video().status, 'approved')

    def test_lease_fences_workers_and_expired_claim_is_recovered(self):
        self.queue()
        video_id, first_token = jobs._claim()
        self.assertIsNone(jobs._claim())
        self.video().publish_lease_until = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()
        _, second_token = jobs._claim()
        self.assertNotEqual(first_token, second_token)
        with self.assertRaises(jobs.LeaseLost):
            jobs._save(video_id, first_token, publish_progress=99)
        jobs._save(video_id, second_token, publish_progress=10)
        self.assertEqual(self.video().publish_progress, 10)

    def test_queue_failure_ui_user_status_and_restricted_admin_permissions(self):
        self.queue()
        self.run_worker(upload=Mock(side_effect=youtube.PublishingError('Needs attention', permanent=True)))
        client = self.client()
        page = client.get('/admin/video-review')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Needs attention', page.data)
        self.assertIn(b'Retry saved publishing job', page.data)
        self.assertNotIn(self.video().upload_session_uri or b'secret-session', page.data)
        client = app.test_client()
        g.pop('_login_user', None)
        with client.session_transaction() as session:
            session['_user_id'] = str(self.user_id)
            session['_fresh'] = True
        page = client.get('/my_valuations')
        self.assertIn(b'You do not need to upload it again', page.data)
        restricted = self.client(allowed=False)
        self.assertEqual(restricted.post(f'/admin/video-review/{self.video_id}/retry').status_code, 403)
        self.assertEqual(restricted.post(f'/admin/video-review/{self.video_id}/reconcile').status_code, 403)

    def test_worker_command_handles_empty_queue(self):
        result = app.test_cli_runner().invoke(args=['video-publishing-worker', '--once'])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn('No jobs due.', result.output)


class YouTubeResumableTests(unittest.TestCase):
    def response(self, status, *, headers=None, data=None):
        return Mock(status_code=status, headers=headers or {}, json=Mock(return_value=data or {}))

    def run_upload(self, responses, session_uri=None):
        client = Mock()
        client.get.return_value = self.response(200, data={'items': [{'id': 'official'}]})
        client.post.return_value = self.response(
            200, headers={'Location': 'https://www.googleapis.com/upload/test-session'},
        )
        client.put.side_effect = responses
        calls = []
        with patch.object(youtube, '_authorized_session') as session:
            session.return_value.__enter__.return_value = client
            youtube.upload_video(
                b'video', 'Camera', session_uri=session_uri,
                on_session=lambda uri: calls.append(('session', uri)),
                on_progress=lambda pct: calls.append(('progress', pct)),
                on_result=lambda video_id: calls.append(('result', video_id)),
            )
        return client, calls

    def test_unlisted_session_is_saved_before_chunks_and_result_is_saved(self):
        client, calls = self.run_upload([
            self.response(308),
            self.response(200, data={'id': 'abcdefghijk'}),
        ])
        self.assertEqual(client.post.call_args.kwargs['json']['status']['privacyStatus'], 'unlisted')
        self.assertEqual(calls[0][0], 'session')
        self.assertEqual(calls[-1], ('result', 'abcdefghijk'))
        self.assertEqual(client.put.call_args.kwargs['headers']['Content-Range'], 'bytes 0-4/5')

    def test_resuming_lost_final_response_does_not_start_another_insert(self):
        client, calls = self.run_upload(
            [self.response(200, data={'id': 'abcdefghijk'})],
            session_uri='https://www.googleapis.com/upload/test-session',
        )
        client.post.assert_not_called()
        client.get.assert_not_called()
        self.assertEqual(client.put.call_count, 1)
        self.assertEqual(calls, [('result', 'abcdefghijk')])

    def test_resuming_partial_upload_sends_only_remaining_bytes(self):
        client, calls = self.run_upload(
            [self.response(308, headers={'Range': 'bytes=0-1'}),
             self.response(200, data={'id': 'abcdefghijk'})],
            session_uri='https://www.googleapis.com/upload/test-session',
        )
        self.assertEqual(client.put.call_args.kwargs['data'], b'deo')
        self.assertIn(('progress', 40), calls)

    def test_expired_session_never_creates_replacement_or_deletes_source(self):
        with self.assertRaises(youtube.PublishingError) as raised:
            self.run_upload(
                [self.response(404)], session_uri='https://www.googleapis.com/upload/test-session',
            )
        self.assertTrue(raised.exception.permanent)

    def test_new_session_is_durably_saved_before_any_video_bytes_are_sent(self):
        client = Mock()
        client.get.return_value = self.response(200, data={'items': [{'id': 'official'}]})
        client.post.return_value = self.response(
            200, headers={'Location': 'https://www.googleapis.com/upload/test-session'},
        )
        with patch.object(youtube, '_authorized_session') as session:
            session.return_value.__enter__.return_value = client
            with self.assertRaisesRegex(RuntimeError, 'DB unavailable'):
                youtube.upload_video(
                    b'video', 'Camera', on_session=Mock(side_effect=RuntimeError('DB unavailable')),
                    on_progress=Mock(), on_result=Mock(),
                )
        client.put.assert_not_called()

    def test_new_upload_requires_an_accessible_official_channel(self):
        for channels, expected, message in (
            ([], '', 'no accessible YouTube channel'),
            ([{'id': 'other'}], 'official', 'does not match YOUTUBE_CHANNEL_ID'),
        ):
            with self.subTest(channels=channels, expected=expected):
                client = Mock()
                client.get.return_value = self.response(200, data={'items': channels})
                on_session, on_progress, on_result = Mock(), Mock(), Mock()
                with patch.dict(os.environ, {'YOUTUBE_CHANNEL_ID': expected}), \
                     patch.object(youtube, '_authorized_session') as session:
                    session.return_value.__enter__.return_value = client
                    with self.assertRaisesRegex(youtube.PublishingError, message) as raised:
                        youtube.upload_video(
                            b'video', 'Camera', on_session=on_session,
                            on_progress=on_progress, on_result=on_result,
                        )
                self.assertTrue(raised.exception.permanent)
                client.post.assert_not_called()
                client.put.assert_not_called()
                on_session.assert_not_called()
                on_progress.assert_not_called()
                on_result.assert_not_called()

    def test_status_check_requires_matching_submission_and_waits_for_processing(self):
        client = Mock()
        client.get.side_effect = [
            self.response(200, data={'items': [{'id': 'official'}]}),
            self.response(200, data={'items': [{
                'snippet': {'channelId': 'official', 'description': 'reference'},
                'status': {'privacyStatus': 'unlisted', 'uploadStatus': 'uploaded'},
                'processingDetails': {'processingStatus': 'processing'},
            }]}),
        ]
        with patch.dict(os.environ, {'YOUTUBE_CHANNEL_ID': 'official'}), \
             patch.object(youtube, '_authorized_session') as session:
            session.return_value.__enter__.return_value = client
            self.assertFalse(youtube.get_video_status('abcdefghijk', expected_reference='reference'))

    def test_channel_check_rejects_public_or_foreign_videos(self):
        for channel, privacy in (('foreign', 'unlisted'), ('official', 'public')):
            with self.subTest(channel=channel, privacy=privacy):
                client = Mock()
                client.get.side_effect = [
                    self.response(200, data={'items': [{'id': 'official'}]}),
                    self.response(200, data={'items': [{
                        'snippet': {'channelId': channel},
                        'status': {'privacyStatus': privacy, 'uploadStatus': 'processed'},
                    }]}),
                ]
                with patch.object(youtube, '_authorized_session') as session:
                    session.return_value.__enter__.return_value = client
                    with self.assertRaises(youtube.PublishingError):
                        youtube.get_video_status('abcdefghijk')


class VideoPublishingMigrationTests(unittest.TestCase):
    def test_upgrade_preserves_existing_states_and_downgrade_preserves_old_fields(self):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from sqlalchemy import create_engine, inspect

        path = Path(__file__).resolve().parent.parent / 'migrations' / 'versions' / 'add_durable_video_publishing.py'
        spec = importlib.util.spec_from_file_location('durable_video_migration', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        engine = create_engine('sqlite:///:memory:')
        with engine.begin() as connection:
            connection.exec_driver_sql(
                'CREATE TABLE item_video (id INTEGER PRIMARY KEY, status VARCHAR(20), youtube_video_id VARCHAR(50))',
            )
            connection.exec_driver_sql(
                "INSERT INTO item_video VALUES (1, 'pending', NULL), (2, 'approved', 'abcdefghijk')",
            )
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                rows = connection.exec_driver_sql(
                    'SELECT status, publish_attempts, publish_progress FROM item_video ORDER BY id',
                ).all()
                self.assertEqual(rows, [('pending', 0, 0), ('approved', 0, 0)])
                migration.downgrade()
                self.assertEqual(
                    {column['name'] for column in inspect(connection).get_columns('item_video')},
                    {'id', 'status', 'youtube_video_id'},
                )
        engine.dispose()


if __name__ == '__main__':
    unittest.main()
