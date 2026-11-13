import re
import tempfile
import unittest
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

from flask import url_for
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

from app import app, db, limiter, load_user
from models import Admin, CreditTransaction, Notification, Payment, User
from paystack_payment_service import PaystackPaymentService
from routes.auth import generate_reset_token, verify_reset_token
from services.account_security import request_email_change, confirm_email_change
from services.email_two_factor import fingerprint


class SecurityHardeningTests(unittest.TestCase):
    def setUp(self):
        self.previous_csrf = app.config['WTF_CSRF_ENABLED']
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.context = app.app_context()
        self.context.push()
        self.previous_limiter = limiter.enabled
        limiter.enabled = False
        db.drop_all()
        db.create_all()
        self.user = User(
            username='security-user', email='security@example.com',
            password_hash=generate_password_hash('OriginalSecure!123'), email_verified=True,
            credits=50, phone_number='08012345678', address='Test road', city='Lagos', state='Lagos',
        )
        self.admin = Admin(username='security-admin', email='admin@example.com', password='test', is_super_admin=True)
        db.session.add_all([self.user, self.admin])
        db.session.commit()
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = self.user.get_id()
            session['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        limiter.enabled = self.previous_limiter
        app.config['WTF_CSRF_ENABLED'] = self.previous_csrf
        self.context.pop()

    def payment(self):
        payment = Payment(
            user_id=self.user.id, amount_naira=1000, credits_purchased=1000,
            paystack_reference='real-test-reference', status='pending',
        )
        db.session.add(payment)
        db.session.commit()
        return payment

    def response(self, **overrides):
        data = {'status': 'success', 'amount': 100000, 'currency': 'NGN', 'reference': 'real-test-reference'}
        data.update(overrides)
        return Mock(status_code=200, json=lambda: {'status': True, 'data': data})

    def test_one_successful_payment_is_credited_once(self):
        payment = self.payment()
        with patch.object(PaystackPaymentService, 'TEST_MODE', False), \
             patch.object(PaystackPaymentService, 'get_auth_header', return_value={}), \
             patch('paystack_payment_service.requests.get', return_value=self.response()) as gateway, \
             patch('notifications.notify_credit_purchase'):
            first = PaystackPaymentService.verify_payment(payment.paystack_reference)
            second = PaystackPaymentService.verify_payment(payment.paystack_reference)
        self.assertTrue(first['success'])
        self.assertTrue(second['success'])
        self.assertEqual(second['credits_added'], 0)
        self.assertEqual(self.user.credits, 1050)
        self.assertEqual(CreditTransaction.query.filter_by(payment_id=payment.id).count(), 1)
        gateway.assert_called_once()

    def test_new_payment_reference_uses_barterxpress_brand(self):
        response = Mock(status_code=200)
        response.json.side_effect = lambda: {
            'status': True, 'data': {
                'reference': gateway.call_args.kwargs['json']['reference'],
                'authorization_url': 'https://checkout.paystack.com/test',
                'access_code': 'test-access-code',
            },
        }
        with patch.object(PaystackPaymentService, 'TEST_MODE', False), \
             patch.object(PaystackPaymentService, 'get_auth_header', return_value={}), \
             patch('paystack_payment_service.requests.post', return_value=response) as gateway:
            result = PaystackPaymentService.initiate_payment(self.user.id, 1000)
        self.assertTrue(result['success'])
        self.assertTrue(result['reference'].startswith(f'barterxpress-{self.user.id}-'))
        self.assertRegex(result['reference'], r'\A[A-Za-z0-9.=-]+\Z')
        self.assertEqual(Payment.query.one().paystack_reference, result['reference'])
        self.assertEqual(gateway.call_args.kwargs['json']['reference'], result['reference'])

    def test_amount_currency_and_reference_must_match(self):
        payment = self.payment()
        for mismatch in [{'amount': 100}, {'currency': 'USD'}, {'reference': 'wrong-reference'}]:
            with self.subTest(mismatch=mismatch), \
                 patch.object(PaystackPaymentService, 'TEST_MODE', False), \
                 patch.object(PaystackPaymentService, 'get_auth_header', return_value={}), \
                 patch('paystack_payment_service.requests.get', return_value=self.response(**mismatch)):
                self.assertFalse(PaystackPaymentService.verify_payment(payment.paystack_reference)['success'])
                self.assertEqual(self.user.credits, 50)
                self.assertEqual(CreditTransaction.query.count(), 0)

    def test_payment_claim_and_unique_ledger_block_duplicates(self):
        payment = self.payment()
        self.assertTrue(PaystackPaymentService._claim_payment(payment))
        self.assertFalse(PaystackPaymentService._claim_payment(payment))
        db.session.rollback()
        db.session.add(CreditTransaction(user_id=self.user.id, payment_id=payment.id, amount=1000))
        db.session.commit()
        db.session.add(CreditTransaction(user_id=self.user.id, payment_id=payment.id, amount=1000))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_payment_failure_rolls_back_claim_and_credit(self):
        payment = self.payment()
        with patch.object(PaystackPaymentService, 'TEST_MODE', False), \
             patch.object(PaystackPaymentService, 'get_auth_header', return_value={}), \
             patch('paystack_payment_service.requests.get', return_value=self.response()), \
             patch.object(db.session, 'commit', side_effect=RuntimeError('test commit failure')):
            result = PaystackPaymentService.verify_payment(payment.paystack_reference)
        self.assertFalse(result['success'])
        self.assertEqual(self.user.credits, 50)
        self.assertEqual(payment.status, 'pending')
        self.assertEqual(CreditTransaction.query.count(), 0)

    def test_notification_injection_is_blocked_and_old_payloads_are_escaped(self):
        payload = '<img src=x onerror=alert(1)>'
        response = self.client.post('/api/notifications/recommendation', json={
            'recipient_id': self.user.id, 'item_id': 1, 'item_name': payload,
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Notification.query.count(), 0)
        db.session.add(Notification(user_id=self.user.id, message=payload))
        db.session.commit()
        with app.test_request_context():
            path = url_for('user.notifications')
        page = self.client.get(path).get_data(as_text=True)
        self.assertIn('&lt;img', page)
        self.assertNotIn(payload, page)

    def test_staff_controls_do_not_interpolate_usernames_into_javascript(self):
        self.user.username = "';alert(1);//"
        self.user.is_banned = True
        self.user.appeal_message = 'Please review this account ban.'
        from datetime import datetime
        self.user.unban_request_date = datetime.utcnow()
        db.session.commit()
        staff = app.test_client()
        with staff.session_transaction() as session:
            session['admin_id'] = self.admin.id
            session['admin_mfa'] = fingerprint(self.admin)
        for path in ['/admin/users', '/admin/pending_appeals']:
            page = staff.get(path).get_data(as_text=True)
            for handler in re.findall(r'onclick="([^"]*)"', page):
                self.assertNotIn('alert(1)', handler)

    def test_csrf_required_for_form_and_json_mutations(self):
        app.config['WTF_CSRF_ENABLED'] = True
        self.assertEqual(self.client.post('/settings', data={'form_type': 'profile'}).status_code, 400)
        self.assertEqual(self.client.post('/api/notifications/recommendation', json={}).status_code, 400)
        page = self.client.get('/settings').get_data(as_text=True)
        token = re.search(r'<meta name="csrf-token" content="([^"]+)"', page).group(1)
        response = self.client.post('/api/notifications/recommendation', json={}, headers={'X-CSRFToken': token})
        self.assertEqual(response.status_code, 403)
        # Gateway webhook is exempt only because it authenticates the raw payload signature.
        self.assertEqual(self.client.post('/payments/webhook', json={}).status_code, 401)

    def test_banned_session_cannot_access_settings_or_financial_routes(self):
        self.user.is_banned = True
        db.session.commit()
        self.assertIn('/banned', self.client.get('/settings').location)
        self.assertEqual(self.client.post('/api/notifications/recommendation', json={}).status_code, 403)
        self.assertEqual(self.client.get('/banned').status_code, 200)
        self.assertEqual(self.client.post('/request_unban', data={'appeal_message': 'Please reconsider my account restriction.'}).status_code, 302)

    def test_email_change_requires_password_and_new_inbox_confirmation(self):
        with app.test_request_context('/'), patch('routes.auth.send_email_async') as send:
            self.assertIsNotNone(request_email_change(self.user, 'new@example.com', 'wrong')[1])
            self.assertEqual(self.user.email, 'security@example.com')
            requested, error = request_email_change(self.user, 'new@example.com', 'OriginalSecure!123')
            self.assertTrue(requested)
            self.assertIsNone(error)
            self.assertEqual(self.user.email, 'security@example.com')
            self.assertEqual(send.call_count, 2)
            html = send.call_args_list[0].args[2]
            token = re.search(r'/confirm-email-change/([^"]+)', html).group(1)
            old_id = self.user.get_id()
            self.assertTrue(confirm_email_change(token))
            self.assertEqual(self.user.email, 'new@example.com')
            self.assertTrue(self.user.email_verified)
            self.assertIsNone(load_user(old_id))
            self.assertFalse(confirm_email_change(token))

    def test_both_profile_routes_reject_unauthenticated_email_replacement(self):
        with app.test_request_context():
            paths = [url_for('user.profile_settings'), url_for('user.settings')]
        for path in paths:
            self.client.post(path, data={
                'form_type': 'profile', 'email': 'stolen@example.com',
                'phone_number': '08012345678', 'address': 'Test road', 'city': 'Lagos', 'state': 'Lagos',
            })
            self.assertEqual(self.user.email, 'security@example.com')
            self.assertTrue(self.user.email_verified)

    def test_password_reset_consumes_link_and_revokes_old_sessions(self):
        token = generate_reset_token(self.user.email)
        old_id = self.user.get_id()
        self.assertEqual(verify_reset_token(token), self.user.email)
        result = self.client.post(f'/reset_password/{token}', data={
            'password': 'ReplacementSecure!456', 'confirm_password': 'ReplacementSecure!456',
        })
        self.assertEqual(result.status_code, 302)
        self.assertIsNone(verify_reset_token(token))
        self.assertIsNone(load_user(old_id))
        self.assertIsNotNone(load_user(self.user.get_id()))

    def test_settings_password_change_logs_out_without_error(self):
        old_id = self.user.get_id()
        other_client = app.test_client()
        with other_client.session_transaction() as session:
            session['_user_id'] = old_id
            session['_fresh'] = True
        response = self.client.post('/settings', data={
            'form_type': 'password', 'current_password': 'OriginalSecure!123',
            'new_password': 'ReplacementSecure!456', 'confirm_password': 'ReplacementSecure!456',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/login'))
        self.assertTrue(check_password_hash(self.user.password_hash, 'ReplacementSecure!456'))
        self.assertIsNone(load_user(old_id))
        with self.client.session_transaction() as session:
            self.assertNotIn('_user_id', session)
            self.assertTrue(any('Password changed successfully' in message for _, message in session['_flashes']))
        self.assertIn('/login', other_client.get('/settings').location)

    def test_settings_wrong_password_does_not_change_credentials_or_log_out(self):
        old_id = self.user.get_id()
        response = self.client.post('/settings', data={
            'form_type': 'password', 'current_password': 'wrong',
            'new_password': 'ReplacementSecure!456', 'confirm_password': 'ReplacementSecure!456',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/settings'))
        self.assertTrue(check_password_hash(self.user.password_hash, 'OriginalSecure!123'))
        self.assertEqual(self.user.get_id(), old_id)
        with self.client.session_transaction() as session:
            self.assertEqual(session['_user_id'], old_id)

    def test_legacy_reset_links_are_rejected(self):
        token = URLSafeTimedSerializer(app.config['SECRET_KEY']).dumps(self.user.email, salt='password-reset-salt')
        self.assertIsNone(verify_reset_token(token))

    def test_2fa_cannot_be_enabled_by_unverified_legacy_toggle(self):
        self.user.two_factor_enabled = True
        db.session.commit()
        result = self.client.post('/account/2fa/setup', data={'verification_code': '123456'})
        self.assertEqual(result.status_code, 302)
        page = self.client.get('/account/security').get_data(as_text=True)
        self.assertIn('Email two-step verification: Enabled', page)
        self.assertIn('Email code to disable', page)
        from account_management import enable_2fa
        self.assertFalse(enable_2fa(self.user.id)[0])

    def test_private_identity_download_requires_specific_staff_permission(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(app.config, {'IDENTITY_DOCUMENT_FOLDER': folder}):
            Path(folder, 'identity.pdf').write_bytes(b'%PDF-test-document')
            self.user.government_id_document = 'identity.pdf'
            db.session.commit()
            url = f'/admin/users/{self.user.id}/identity-document'
            self.assertEqual(app.test_client().get(url).status_code, 302)
            self.assertEqual(self.client.get(url).status_code, 302)
            staff = app.test_client()
            self.admin.is_super_admin = False
            self.admin.permission_list = ['users.view']
            db.session.commit()
            with staff.session_transaction() as session:
                session['admin_id'] = self.admin.id
                session['admin_mfa'] = fingerprint(self.admin)
            self.assertEqual(staff.get(url).status_code, 403)
            self.admin.permission_list = ['users.verify_identity']
            db.session.commit()
            response = staff.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn('attachment', response.headers['Content-Disposition'])
            self.assertIn('no-store', response.headers['Cache-Control'])
            response.close()
            self.assertEqual(self.client.get('/static/uploads/verification/identity.pdf').status_code, 404)

    def test_verified_identity_cannot_be_used_by_two_accounts(self):
        from datetime import datetime
        self.user.id_verified_at = datetime.utcnow()
        self.user.verified_identity_hash = 'b' * 64
        db.session.commit()
        db.session.add(User(
            username='duplicate', email='duplicate@example.com', password_hash='test',
            verified_identity_hash='b' * 64,
        ))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_startup_rejects_missing_or_known_fallback_signing_key(self):
        for key in ['', 'dev-key-change-in-production']:
            with self.subTest(key=key):
                environment = dict(os.environ, SECRET_KEY=key, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
                result = subprocess.run(
                    [sys.executable, '-c', 'import app'], cwd=app.root_path,
                    env=environment, capture_output=True, timeout=30,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b'SECRET_KEY must be', result.stderr)

    def test_private_document_relocation_and_path_traversal_guard(self):
        from services.identity_documents import document_path, relocate_legacy_documents
        with tempfile.TemporaryDirectory() as root:
            public = Path(root) / 'static' / 'uploads' / 'verification'
            public.mkdir(parents=True)
            source = public / 'legacy.pdf'
            source.write_bytes(b'%PDF-test')
            self.user.government_id_document = source.name
            db.session.commit()
            private = Path(root) / 'private'
            with patch.object(app, 'root_path', root), patch.dict(app.config, {'IDENTITY_DOCUMENT_FOLDER': str(private)}):
                self.assertEqual(relocate_legacy_documents(), 1)
                self.assertFalse(source.exists())
                self.assertTrue(document_path('legacy.pdf').is_file())
                self.assertEqual(relocate_legacy_documents(), 0)
                for name in ['../legacy.pdf', '..\\legacy.pdf']:
                    with self.assertRaises(ValueError):
                        document_path(name)

    def test_staff_identity_review_requires_confirmation_and_rejects_duplicate_nin(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(app.config, {'IDENTITY_DOCUMENT_FOLDER': folder}):
            Path(folder, 'identity.pdf').write_bytes(b'%PDF-test-document')
            self.user.government_id_document = 'identity.pdf'
            self.user.nin = '12345678901'
            duplicate = User(
                username='second-identity', email='second-identity@example.com', password_hash='test',
                nin='12345678901', government_id_document='identity.pdf', email_verified=True,
            )
            db.session.add(duplicate)
            db.session.commit()
            staff = app.test_client()
            with staff.session_transaction() as session:
                session['admin_id'] = self.admin.id
                session['admin_mfa'] = fingerprint(self.admin)
            path = f'/admin/users/{self.user.id}/verify-identity'
            self.assertEqual(staff.post(path).status_code, 302)
            self.assertIsNone(self.user.id_verified_at)
            self.assertEqual(staff.post(path, data={'identity_checked': 'yes'}).status_code, 302)
            self.assertIsNotNone(self.user.id_verified_at)
            self.assertEqual(len(self.user.verified_identity_hash), 64)
            staff.post(f'/admin/users/{duplicate.id}/verify-identity', data={'identity_checked': 'yes'})
            self.assertIsNone(duplicate.id_verified_at)
            self.assertIsNone(duplicate.verified_identity_hash)
