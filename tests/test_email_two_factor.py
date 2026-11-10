import importlib.util
import re
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from smtplib import SMTPException
from unittest.mock import patch

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from werkzeug.security import generate_password_hash

from app import app, db, limiter, load_user
from models import Admin, EmailLoginChallenge, SystemSettings, User
from routes.auth import generate_reset_token
from services.account_security import confirm_email_change, request_email_change
from services.email_two_factor import fingerprint


class EmailTwoFactorTests(unittest.TestCase):
    def setUp(self):
        self.old_csrf = app.config['WTF_CSRF_ENABLED']
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.context = app.app_context()
        self.context.push()
        self.old_limiter = limiter.enabled
        limiter.enabled = False
        db.drop_all()
        db.create_all()
        self.password = 'OriginalSecure!123'
        self.user = User(
            username='factor-user', email='factor@example.com', email_verified=True,
            password_hash=generate_password_hash(self.password), first_login=False,
        )
        self.admin = Admin(
            username='factor-admin', email='admin-factor@example.com',
            password=generate_password_hash(self.password), is_super_admin=True,
        )
        db.session.add_all([self.user, self.admin])
        db.session.commit()
        self.client = app.test_client()
        self.mail_patch = patch('services.email_two_factor.mail.send')
        self.send = self.mail_patch.start()

    def tearDown(self):
        self.mail_patch.stop()
        db.session.remove()
        db.drop_all()
        limiter.enabled = self.old_limiter
        app.config['WTF_CSRF_ENABLED'] = self.old_csrf
        self.context.pop()

    def authenticated_user(self, client=None):
        client = client or self.client
        with client.session_transaction() as state:
            state['_user_id'] = self.user.get_id()
            state['_fresh'] = True
        return client

    def enable_user(self):
        self.user.two_factor_enabled = True
        db.session.commit()

    def user_login(self, client=None, next_page=''):
        return (client or self.client).post('/login' + next_page, data={
            'credential': self.user.email, 'password': self.password, 'remember_me': 'y',
        })

    def admin_login(self):
        return self.client.post('/admin/login', data={'email': self.admin.email, 'password': self.password})

    def code(self):
        return re.search(r'code is (\d{6})', self.send.call_args.args[0].body).group(1)

    def verify(self, code=None, client=None):
        return (client or self.client).post('/two-factor/verify', data={'code': code or self.code()})

    def age_send(self):
        challenge = EmailLoginChallenge.query.one()
        challenge.last_sent_at = datetime.utcnow() - timedelta(seconds=61)
        db.session.commit()

    def test_unenrolled_user_keeps_existing_login_flow(self):
        result = self.user_login()
        self.assertIn('/dashboard', result.location)
        self.send.assert_not_called()
        with self.client.session_transaction() as state:
            self.assertEqual(state['_user_id'], self.user.get_id())

    def test_enabled_user_has_no_session_before_code_and_no_remember_bypass(self):
        self.enable_user()
        self.assertIn('/two-factor/verify', self.user_login().location)
        self.assertEqual(self.client.get('/settings').status_code, 302)
        with self.client.session_transaction() as state:
            self.assertNotIn('_user_id', state)
            self.assertNotIn(self.code(), str(state))
        page = self.client.get('/two-factor/verify')
        self.assertEqual(page.status_code, 200)
        self.assertIn('f***@example.com', page.get_data(as_text=True))
        self.assertIn('/dashboard', self.verify().location)
        self.assertEqual(self.client.get('/settings').status_code, 200)
        self.assertIsNone(self.client.get_cookie('remember_token'))

    def test_wrong_password_never_sends_a_code(self):
        self.enable_user()
        self.client.post('/login', data={'credential': self.user.email, 'password': 'wrong'})
        self.send.assert_not_called()
        self.assertEqual(EmailLoginChallenge.query.count(), 0)

    def test_admin_password_alone_does_not_authorize_even_super_admin(self):
        self.assertIn('/two-factor/verify', self.admin_login().location)
        with self.client.session_transaction() as state:
            self.assertNotIn('admin_id', state)
        self.assertEqual(self.client.get('/admin/users').status_code, 302)
        self.assertEqual(self.client.get('/two-factor/verify').status_code, 200)
        self.assertIn('/admin/dashboard', self.verify().location)
        with self.client.session_transaction() as state:
            self.assertEqual(state['admin_id'], self.admin.id)
            self.assertEqual(state['admin_mfa'], fingerprint(self.admin))
        self.assertEqual(self.client.get('/admin/users').status_code, 200)

    def test_admin_can_complete_code_during_maintenance(self):
        settings = SystemSettings.get_settings()
        settings.maintenance_mode = True
        db.session.commit()
        self.assertIn('/two-factor/verify', self.admin_login().location)
        self.assertEqual(self.client.get('/two-factor/verify').status_code, 200)
        self.assertIn('/admin/dashboard', self.verify().location)
        self.assertEqual(self.client.get('/admin/users').status_code, 200)

    def test_existing_admin_session_without_second_factor_is_rejected(self):
        with self.client.session_transaction() as state:
            state['admin_id'] = self.admin.id
        self.assertIn('/admin/login', self.client.get('/admin/users').location)
        with self.client.session_transaction() as state:
            self.assertNotIn('admin_id', state)

    def test_non_super_admin_also_requires_code(self):
        self.admin.is_super_admin = False
        db.session.commit()
        self.assertIn('/two-factor/verify', self.admin_login().location)
        self.assertIn('/admin/dashboard', self.verify().location)
        self.assertEqual(self.client.get('/admin/users').status_code, 403)

    def test_admin_proof_is_invalid_after_password_or_email_change(self):
        self.admin_login()
        self.verify()
        self.admin.email = 'changed-admin@example.com'
        db.session.commit()
        self.assertIn('/admin/login', self.client.get('/admin/users').location)

    def test_deactivated_admin_cannot_finish_challenge(self):
        self.admin_login()
        self.admin.is_active = False
        db.session.commit()
        self.verify()
        with self.client.session_transaction() as state:
            self.assertNotIn('admin_id', state)

    def test_enrollment_requires_password_then_code_and_revokes_old_sessions(self):
        old_id = self.user.get_id()
        other = self.authenticated_user(app.test_client())
        self.authenticated_user()
        self.assertEqual(self.client.get('/account/2fa/setup').status_code, 200)
        self.client.post('/account/2fa/setup', data={'current_password': 'wrong'})
        self.send.assert_not_called()
        self.assertFalse(self.user.two_factor_enabled)
        response = self.client.post('/account/2fa/setup', data={'current_password': self.password})
        self.assertIn('/two-factor/verify', response.location)
        self.assertFalse(self.user.two_factor_enabled)
        self.assertIn('/login', self.verify().location)
        self.assertTrue(self.user.two_factor_enabled)
        self.assertIsNone(load_user(old_id))
        self.assertEqual(other.get('/settings').status_code, 302)
        self.assertEqual(self.client.get('/settings').status_code, 302)

    def test_disable_requires_both_password_and_existing_email_code(self):
        self.enable_user()
        self.authenticated_user()
        self.client.post('/account/2fa/disable', data={'current_password': 'wrong'})
        self.send.assert_not_called()
        self.client.post('/account/2fa/disable', data={'current_password': self.password})
        self.assertTrue(self.user.two_factor_enabled)
        self.verify('not-a-code')
        self.assertTrue(self.user.two_factor_enabled)
        self.verify()
        self.assertFalse(self.user.two_factor_enabled)
        self.assertEqual(self.client.get('/settings').status_code, 302)

    def test_unverified_email_cannot_enroll(self):
        self.user.email_verified = False
        db.session.commit()
        self.authenticated_user()
        self.client.post('/account/2fa/setup', data={'current_password': self.password})
        self.send.assert_not_called()
        self.assertFalse(self.user.two_factor_enabled)

    def test_code_is_single_use_and_stored_as_keyed_hash_only(self):
        self.enable_user()
        self.user_login()
        challenge = EmailLoginChallenge.query.one()
        self.assertNotIn(self.code(), challenge.code_hash)
        with self.client.session_transaction() as state:
            pending = dict(state['email_2fa_pending'])
        self.verify()
        self.assertTrue(EmailLoginChallenge.query.one().consumed)
        self.assertIsNone(EmailLoginChallenge.query.one().code_hash)
        self.client.get('/logout')
        with self.client.session_transaction() as state:
            state['email_2fa_pending'] = pending
        self.verify()
        with self.client.session_transaction() as state:
            self.assertNotIn('_user_id', state)

    def test_code_cannot_be_used_in_another_browser_without_binding(self):
        self.enable_user()
        self.user_login()
        other = app.test_client()
        with self.client.session_transaction() as state:
            token = state['email_2fa_pending']['token']
        with other.session_transaction() as state:
            state['email_2fa_pending'] = {'token': token, 'binding': 'wrong-browser'}
        self.verify(client=other)
        with other.session_transaction() as state:
            self.assertNotIn('_user_id', state)
        self.assertFalse(EmailLoginChallenge.query.one().consumed)
        self.assertIn('/dashboard', self.verify().location)

    def test_expired_code_is_rejected(self):
        self.enable_user()
        self.user_login()
        EmailLoginChallenge.query.one().expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()
        self.verify()
        with self.client.session_transaction() as state:
            self.assertNotIn('_user_id', state)

    def test_five_failed_attempts_lock_even_correct_code(self):
        self.enable_user()
        self.user_login()
        for _ in range(5):
            self.verify('bad-code')
        self.verify()
        self.assertEqual(EmailLoginChallenge.query.one().attempts, 5)
        with self.client.session_transaction() as state:
            self.assertNotIn('_user_id', state)
        self.age_send()
        self.user_login()
        self.assertEqual(self.send.call_count, 1)

    def test_resend_cooldown_old_code_invalidation_and_budget_preservation(self):
        self.enable_user()
        with patch('services.email_two_factor.secrets.randbelow', side_effect=[123456, 654321]):
            self.user_login()
            old_code = self.code()
            self.client.post('/two-factor/verify', data={'action': 'resend'})
            self.assertEqual(self.send.call_count, 1)
            self.verify('bad-code')
            self.age_send()
            self.client.post('/two-factor/verify', data={'action': 'resend'})
        self.assertEqual(self.send.call_count, 2)
        self.assertEqual(EmailLoginChallenge.query.one().attempts, 1)
        self.verify(old_code)
        self.assertFalse(EmailLoginChallenge.query.one().consumed)
        self.assertIn('/dashboard', self.verify().location)

    def test_send_limit_survives_restarted_signin_and_resets_after_window(self):
        self.enable_user()
        for _ in range(5):
            if EmailLoginChallenge.query.count():
                self.age_send()
            self.user_login(client=app.test_client())
        self.age_send()
        self.user_login()
        self.assertEqual(self.send.call_count, 5)
        record = EmailLoginChallenge.query.one()
        record.window_started_at = datetime.utcnow() - timedelta(minutes=16)
        record.attempts = 5
        db.session.commit()
        self.user_login()
        self.assertEqual(self.send.call_count, 6)
        self.assertEqual(EmailLoginChallenge.query.one().attempts, 0)

    def test_delivery_failure_never_grants_login_or_leaves_valid_code(self):
        self.enable_user()
        self.send.side_effect = SMTPException('delivery failed')
        self.user_login()
        record = EmailLoginChallenge.query.one()
        self.assertTrue(record.consumed)
        self.assertIsNone(record.code_hash)
        with self.client.session_transaction() as state:
            self.assertNotIn('_user_id', state)
            self.assertNotIn('email_2fa_pending', state)

    def test_delivery_failure_cannot_enable_two_factor_or_authorize_admin(self):
        self.send.side_effect = SMTPException('delivery failed')
        self.authenticated_user()
        self.client.post('/account/2fa/setup', data={'current_password': self.password})
        self.assertFalse(self.user.two_factor_enabled)
        self.admin_login()
        with self.client.session_transaction() as state:
            self.assertNotIn('admin_id', state)
            self.assertNotIn('_user_id', state)
            self.assertNotIn('email_2fa_pending', state)

    def test_accounts_locked_after_password_check_cannot_finish_code(self):
        self.enable_user()
        for account, login in [(self.user, self.user_login), (self.admin, self.admin_login)]:
            with self.subTest(account=type(account).__name__):
                login()
                account.account_locked_until = datetime.utcnow() + timedelta(minutes=15)
                db.session.commit()
                self.verify()
                with self.client.session_transaction() as state:
                    self.assertNotIn('_user_id', state)
                    self.assertNotIn('admin_id', state)

    def test_cancel_does_not_change_settings_or_authenticate(self):
        self.enable_user()
        self.user_login()
        self.client.post('/two-factor/verify', data={'action': 'cancel'})
        self.assertTrue(EmailLoginChallenge.query.one().consumed)
        self.verify()
        with self.client.session_transaction() as state:
            self.assertNotIn('_user_id', state)

    def test_password_change_invalidates_pending_code(self):
        self.enable_user()
        self.user_login()
        self.user.password_hash = generate_password_hash('ReplacementSecure!456')
        db.session.commit()
        self.verify()
        with self.client.session_transaction() as state:
            self.assertNotIn('_user_id', state)

    def test_password_reset_does_not_disable_second_factor(self):
        self.enable_user()
        token = generate_reset_token(self.user.email)
        replacement = 'ReplacementSecure!456'
        self.client.post(f'/reset_password/{token}', data={'password': replacement, 'confirm_password': replacement})
        self.assertTrue(self.user.two_factor_enabled)
        self.password = replacement
        self.assertIn('/two-factor/verify', self.user_login().location)

    def test_email_change_cannot_redirect_second_factor_to_unverified_inbox(self):
        with app.test_request_context('/'), patch('routes.auth.send_email_async') as send:
            requested, error = request_email_change(self.user, 'changed@example.com', self.password)
            self.assertTrue(requested)
            token = re.search(r'/confirm-email-change/([^"]+)', send.call_args_list[0].args[2]).group(1)
            self.enable_user()
            self.assertFalse(confirm_email_change(token))
            requested, error = request_email_change(self.user, 'attacker@example.com', self.password)
            self.assertFalse(requested)
            self.assertIn('current inbox', error)
            self.assertEqual(self.user.email, 'factor@example.com')

    def test_banned_enrolled_user_must_verify_then_has_appeal_only_access(self):
        self.enable_user()
        self.user.is_banned = True
        db.session.commit()
        self.assertIn('/two-factor/verify', self.user_login().location)
        self.assertIn('/banned', self.verify().location)
        self.assertEqual(self.client.get('/banned').status_code, 200)
        self.assertIn('/banned', self.client.get('/settings').location)

    def test_next_redirect_is_preserved_but_external_redirect_is_rejected(self):
        self.enable_user()
        self.user_login(next_page='?next=/settings')
        self.assertEqual(self.verify().location, '/settings')
        self.client.get('/logout')
        self.age_send()
        self.user_login(next_page='?next=//evil.example')
        self.assertIn('/dashboard', self.verify().location)

    def test_csrf_required_for_code_and_resend_and_setup(self):
        self.enable_user()
        self.user_login()
        app.config['WTF_CSRF_ENABLED'] = True
        self.assertEqual(self.verify().status_code, 400)
        self.assertEqual(self.client.post('/two-factor/verify', data={'action': 'resend'}).status_code, 400)
        page = self.client.get('/two-factor/verify').get_data(as_text=True)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        self.assertEqual(self.client.post('/two-factor/verify', data={'csrf_token': csrf, 'code': self.code()}).status_code, 302)
        self.assertEqual(self.client.post('/account/2fa/disable', data={'current_password': self.password}).status_code, 400)

    def test_mail_debug_is_fail_closed_to_avoid_logging_codes(self):
        self.enable_user()
        with patch.dict(app.config, {'MAIL_DEBUG': True}):
            self.user_login()
        self.send.assert_not_called()
        self.assertEqual(EmailLoginChallenge.query.count(), 0)

    def test_setting_change_challenge_cannot_be_completed_after_logout(self):
        self.authenticated_user()
        self.client.post('/account/2fa/setup', data={'current_password': self.password})
        with self.client.session_transaction() as state:
            pending = dict(state['email_2fa_pending'])
        self.client.get('/logout')
        with self.client.session_transaction() as state:
            state['email_2fa_pending'] = pending
        self.verify()
        self.assertFalse(self.user.two_factor_enabled)


class EmailTwoFactorMigrationTests(unittest.TestCase):
    def test_upgrade_builds_challenge_schema_and_unique_principal(self):
        engine = sa.create_engine('sqlite:///:memory:')
        try:
            with engine.begin() as connection:
                path = Path(app.root_path) / 'migrations' / 'versions' / 'add_email_two_factor.py'
                spec = importlib.util.spec_from_file_location('email_two_factor_migration', path)
                migration = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(migration)
                self.assertEqual(migration.down_revision, 'harden_security_20261110')
                with Operations.context(MigrationContext.configure(connection)):
                    migration.upgrade()
                inspector = sa.inspect(connection)
                self.assertTrue(any(c['column_names'] == ['principal'] for c in inspector.get_unique_constraints('email_login_challenge')))
                self.assertEqual(
                    {c['name'] for c in inspector.get_columns('email_login_challenge')},
                    set(EmailLoginChallenge.__table__.columns.keys()),
                )
        finally:
            engine.dispose()
