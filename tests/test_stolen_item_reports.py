import importlib.util
import io
import os
import re
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from PIL import Image
from sqlalchemy import create_engine, inspect, text
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app import app, db, limiter
from models import Admin, AuditLog, Item, StolenItemReport, StolenReportEvidence, User


class StolenItemReportTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
        if limiter:
            self.limiter_enabled = limiter.enabled
            limiter.enabled = False
        self.ctx = app.app_context()
        self.ctx.push()
        db.drop_all()
        db.create_all()
        self.reporter = User(username='reporter', email='reporter@example.com', password_hash='test')
        self.seller = User(username='seller', email='seller@example.com', password_hash='test')
        self.admin = Admin(username='reviewer', email='reviewer@example.com', password='test')
        self.admin.permission_list = ['reports.manage']
        self.other_admin = Admin(username='support', email='support@example.com', password='test')
        self.other_admin.permission_list = ['messages.manage']
        db.session.add_all([self.reporter, self.seller, self.admin, self.other_admin])
        db.session.flush()
        self.item = Item(
            name='Test phone', category='Electronics', user_id=self.seller.id,
            status='approved', is_available=True, is_approved=True, value=500,
            condition='Like New', description='A test phone',
        )
        db.session.add(self.item)
        db.session.commit()
        self.url = f'/item/{self.item.id}/report-stolen'
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.reporter.id)
            session['_fresh'] = True
        self.alert = patch('routes.items.notify_admins').start()

    def tearDown(self):
        patch.stopall()
        if limiter:
            limiter.enabled = self.limiter_enabled
        app.config['WTF_CSRF_ENABLED'] = False
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def data(self, **overrides):
        data = {
            'details': 'This is my stolen phone. The original receipt contains the matching serial number.',
            'serial_number': 'PRIVATE-SERIAL-123',
            'declaration': 'y',
        }
        data.update(overrides)
        return data

    def image(self):
        image = io.BytesIO()
        Image.new('RGB', (20, 20), 'blue').save(image, format='PNG')
        image.seek(0)
        return image

    def admin_client(self, admin=None):
        client = app.test_client()
        with client.session_transaction() as session:
            session['admin_id'] = (admin or self.admin).id
        return client

    def create_report(self):
        response = self.client.post(self.url, data=self.data(evidence=(self.image(), 'receipt.png')))
        self.assertEqual(response.status_code, 302)
        from flask import url_for
        with app.test_request_context():
            self.assertEqual(response.location, url_for('user.dashboard'))
        return StolenItemReport.query.one()

    def test_item_link_and_login_required(self):
        response = self.client.get(f'/item/{self.item.id}')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn(self.url, html)
        description_end = html.index('</div>', html.index('<div class="description-section">'))
        report_link = html.index(f'href="{self.url}"')
        self.assertLess(description_end, report_link)
        self.assertLess(report_link, html.index('<div class="action-section">'))
        from flask import g
        g.pop('_login_user', None)
        guest = app.test_client()
        for response in (guest.get(self.url), guest.post(self.url, data=self.data())):
            self.assertEqual(response.status_code, 302)
            self.assertIn('login', response.location)
        self.assertEqual(StolenItemReport.query.count(), 0)

    def test_submission_is_private_alerts_admin_and_leaves_listing_unchanged(self):
        report = self.create_report()
        self.assertEqual(report.reporter_id, self.reporter.id)
        self.assertEqual(report.item_id, self.item.id)
        self.assertEqual(report.contact_email, self.reporter.email)
        self.assertEqual(report.status, 'pending')
        self.assertEqual(report.evidence[0].content_type, 'image/png')
        self.assertEqual(report.evidence[0].data, self.image().getvalue())
        self.alert.assert_called_once()
        args, kwargs = self.alert.call_args
        self.assertEqual(args[0], 'reports.manage')
        self.assertEqual(kwargs['report_id'], report.id)
        self.assertNotIn(report.serial_number, str(self.alert.call_args))
        self.assertEqual(self.item.status, 'approved')
        self.assertTrue(self.item.is_available)
        self.assertEqual(self.reporter.credits, 0)
        self.assertEqual(self.seller.credits, 0)
        public = app.test_client().get(f'/item/{self.item.id}').get_data(as_text=True)
        self.assertNotIn(report.serial_number, public)
        self.assertNotIn(report.details, public)
        self.assertNotIn('receipt.png', public)

    def test_images_or_identifiers_are_required(self):
        response = self.client.post(self.url, data=self.data(serial_number=''))
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'Provide an evidence image', response.data)
        self.assertEqual(StolenItemReport.query.count(), 0)
        response = self.client.post(self.url, data=self.data(
            serial_number='', evidence=(self.image(), 'photo.png'),
        ))
        self.assertEqual(response.status_code, 302)

    def test_invalid_images_size_and_count_are_rejected_atomically(self):
        from services.stolen_report_service import MAX_EVIDENCE_BYTES
        cases = [
            [(io.BytesIO(b'<svg onload="alert(1)"/>'), 'fake.png')],
            [(io.BytesIO(b'not an image'), 'fake.jpg')],
            [(io.BytesIO(b'x' * (MAX_EVIDENCE_BYTES + 1)), 'big.png')],
            [(self.image(), 'image.png') for _ in range(6)],
            [(self.image(), 'valid.png'), (io.BytesIO(b'broken'), 'bad.png')],
        ]
        for files in cases:
            with self.subTest(count=len(files)):
                response = self.client.post(self.url, data=self.data(evidence=files))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(StolenItemReport.query.count(), 0)
                self.assertEqual(StolenReportEvidence.query.count(), 0)
        self.alert.assert_not_called()

    def test_validation_requires_valid_identifiers_details_and_declaration(self):
        for overrides in (
            {'imei': 'not-valid'}, {'details': 'short'}, {'details': ' ' * 35},
            {'declaration': ''}, {'serial_number': 's' * 121}, {'details': 'x' * 5001},
        ):
            with self.subTest(overrides=list(overrides)):
                response = self.client.post(self.url, data=self.data(**overrides))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(StolenItemReport.query.count(), 0)
        self.assertEqual(self.client.post(
            self.url, data=self.data(serial_number='', imei='123456789012345'),
        ).status_code, 302)

    def test_one_open_report_per_reporter_and_item(self):
        report = self.create_report()
        response = self.client.post(self.url, data=self.data())
        self.assertEqual(response.status_code, 409)
        self.assertEqual(StolenItemReport.query.count(), 1)
        report.status = 'dismissed'
        db.session.commit()
        self.assertEqual(self.client.post(self.url, data=self.data()).status_code, 302)
        self.assertEqual(StolenItemReport.query.count(), 2)

    def test_evidence_and_reviews_are_restricted_to_reviewers(self):
        report = self.create_report()
        evidence = report.evidence[0]
        paths = [
            '/admin/stolen-reports',
            f'/admin/stolen-reports/{report.id}',
            f'/admin/stolen-reports/{report.id}/evidence/{evidence.id}',
        ]
        for path in paths:
            self.assertEqual(app.test_client().get(path).status_code, 302)
            self.assertEqual(self.client.get(path).status_code, 302)
            self.assertEqual(self.admin_client(self.other_admin).get(path).status_code, 403)
            self.assertEqual(self.admin_client().get(path).status_code, 200)
        response = self.admin_client().get(paths[-1])
        self.assertEqual(response.data, self.image().getvalue())
        self.assertIn('attachment;', response.headers['Content-Disposition'])
        self.assertIn('private', response.headers['Cache-Control'])
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(self.admin_client().get(
            f'/admin/stolen-reports/{report.id + 1}/evidence/{evidence.id}',
        ).status_code, 404)
        self.assertEqual(self.admin_client().get('/admin/stolen-reports?status=invalid').status_code, 400)
        self.assertEqual(self.admin_client(self.other_admin).post(
            paths[1], data={'status': 'confirmed', 'review_notes': 'Looks legitimate.'},
        ).status_code, 403)

    def test_review_tracks_admin_audit_and_badge_without_restricting_item(self):
        report = self.create_report()
        client = self.admin_client()
        body = client.get('/admin/dashboard').get_data(as_text=True)
        self.assertIn('data-pending-queue="stolen_reports" aria-label="1 pending">1</span>', body)
        path = f'/admin/stolen-reports/{report.id}'
        for status in ('under_review', 'confirmed', 'dismissed', 'pending'):
            response = client.post(path, data={'status': status, 'review_notes': 'Evidence checked against identifying marks.'})
            self.assertEqual(response.status_code, 302)
            db.session.refresh(report)
            self.assertEqual(report.status, status)
            self.assertEqual(report.reviewed_by_id, self.admin.id)
            self.assertIsNotNone(report.reviewed_at)
            self.assertTrue(self.item.is_available)
            self.assertEqual(self.item.status, 'approved')
            badge = 'data-pending-queue="stolen_reports"'
            body = client.get('/admin/dashboard').get_data(as_text=True)
            if status in StolenItemReport.PENDING_STATUSES:
                self.assertIn(badge, body)
            else:
                self.assertNotIn(badge, body)
        self.assertEqual(AuditLog.query.filter_by(action_type='review_stolen_report').count(), 4)
        for status, notes in (('invalid', 'long enough notes'), ('confirmed', 'short')):
            self.assertEqual(client.post(path, data={'status': status, 'review_notes': notes}).status_code, 400)
        db.session.refresh(report)
        self.assertEqual(report.status, 'pending')

    def test_report_and_review_posts_require_csrf(self):
        report = self.create_report()
        app.config['WTF_CSRF_ENABLED'] = True
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.post(self.url, data=self.data()).status_code, 400)
        self.assertEqual(self.admin_client().post(
            f'/admin/stolen-reports/{report.id}', data={'status': 'confirmed', 'review_notes': 'Review done'},
        ).status_code, 400)
        self.assertEqual(StolenItemReport.query.count(), 1)
        db.session.refresh(report)
        self.assertEqual(report.status, 'pending')

    def test_no_access_after_permission_revocation(self):
        report = self.create_report()
        client = self.admin_client()
        self.assertEqual(client.get(f'/admin/stolen-reports/{report.id}').status_code, 200)
        self.admin.permission_list = []
        db.session.commit()
        self.assertEqual(client.get(f'/admin/stolen-reports/{report.id}').status_code, 403)

    def test_valid_csrf_submissions_work_end_to_end(self):
        from flask import g
        app.config['WTF_CSRF_ENABLED'] = True
        g.pop('csrf_token', None)
        html = self.client.get(self.url).get_data(as_text=True)
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
        self.assertEqual(self.client.post(
            self.url, data=self.data(csrf_token=token),
        ).status_code, 302)
        report = StolenItemReport.query.one()
        client = self.admin_client()
        g.pop('csrf_token', None)
        path = f'/admin/stolen-reports/{report.id}'
        html = client.get(path).get_data(as_text=True)
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
        self.assertEqual(client.post(path, data={
            'status': 'under_review', 'review_notes': 'Checking ownership documents.',
            'csrf_token': token,
        }).status_code, 302)
        db.session.refresh(report)
        self.assertEqual(report.status, 'under_review')

    def test_database_failure_does_not_save_partial_report(self):
        from sqlalchemy.exc import SQLAlchemyError
        self.assertEqual(self.client.get(self.url).status_code, 200)
        with patch.object(db.session, 'commit', side_effect=SQLAlchemyError('DB unavailable')):
            response = self.client.post(
                self.url, data=self.data(evidence=(self.image(), 'receipt.png')),
            )
        self.assertEqual(response.status_code, 500)
        self.assertIn(b'Your report could not be saved', response.data)
        self.assertEqual(StolenItemReport.query.count(), 0)
        self.assertEqual(StolenReportEvidence.query.count(), 0)

    def test_claim_text_is_escaped_in_admin_review(self):
        response = self.client.post(self.url, data=self.data(
            details='<script>alert("claim")</script> This is a private ownership claim.',
        ))
        self.assertEqual(response.status_code, 302)
        report = StolenItemReport.query.one()
        response = self.admin_client().get(f'/admin/stolen-reports/{report.id}')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'<script>alert("claim")</script>', response.data)
        self.assertIn(b'&lt;script&gt;', response.data)

    def test_persistent_submission_limit_returns_429_without_saving(self):
        for _ in range(5):
            db.session.add(StolenItemReport(
                item_id=self.item.id, reporter_id=self.reporter.id,
                item_name=self.item.name, contact_email=self.reporter.email,
                details='Previously reviewed claim.', status='dismissed',
            ))
        db.session.commit()
        self.assertEqual(self.client.post(self.url, data=self.data()).status_code, 429)
        self.assertEqual(StolenItemReport.query.count(), 5)
        self.alert.assert_not_called()


class StolenReportMigrationTests(unittest.TestCase):
    def test_upgrade_roundtrip_and_private_data_survives_parent_deletion(self):
        migration_path = Path(__file__).resolve().parents[1] / 'migrations' / 'versions' / 'add_stolen_item_reports.py'
        spec = importlib.util.spec_from_file_location('report_migration', migration_path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        engine = create_engine('sqlite:///:memory:')
        with engine.begin() as conn:
            conn.execute(text('PRAGMA foreign_keys=ON'))
            for table in ('item', 'user', 'admin'):
                conn.execute(text(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY)'))
                conn.execute(text(f'INSERT INTO "{table}" (id) VALUES (1)'))
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
            conn.execute(text(
                "INSERT INTO stolen_item_report (id,item_id,reporter_id,item_name,contact_email,details,status,created_at) "
                "VALUES (1,1,1,'Phone','test@example.com','Claim','pending',CURRENT_TIMESTAMP)"
            ))
            conn.execute(text('DELETE FROM item WHERE id=1'))
            conn.execute(text('DELETE FROM "user" WHERE id=1'))
            row = conn.execute(text('SELECT item_id,reporter_id,item_name FROM stolen_item_report')).one()
            self.assertEqual(tuple(row), (None, None, 'Phone'))
            with Operations.context(MigrationContext.configure(conn)):
                migration.downgrade()
            self.assertNotIn('stolen_item_report', inspect(conn).get_table_names())
            self.assertNotIn('stolen_report_evidence', inspect(conn).get_table_names())
        engine.dispose()
