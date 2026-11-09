import os
import unittest

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from flask import render_template

from app import app, db, limiter
from models import Admin, User


class MobileLayoutTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.context = app.app_context()
        self.context.push()
        self.previous_limiter = limiter.enabled
        limiter.enabled = False
        db.create_all()
        user = User(username='mobile-user', email='mobile-test@example.com', password_hash='test')
        admin = Admin(username='mobile-admin', email='mobile-admin@example.com', password='test', is_super_admin=True)
        db.session.add_all([user, admin])
        db.session.commit()
        self.user_id, self.admin_id = user.id, admin.id

    def tearDown(self):
        limiter.enabled = self.previous_limiter
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def assert_mobile_shell(self, html, admin=False):
        self.assertIn('width=device-width, initial-scale=1.0', html)
        self.assertIn('class="mobile-ui', html)
        self.assertEqual(html.count('href="/static/css/mobile.css"'), 1)
        self.assertLess(html.index('href="/static/css/mobile.css"'), html.index('</body>'))
        if admin:
            self.assertIn('mobile-admin', html)
        else:
            self.assertGreater(html.index('href="/static/css/mobile.css"'), html.index('<!-- PAGE CONTENT -->'))
        self.assertNotIn('maximum-scale=1', html)
        self.assertNotIn('user-scalable=no', html)

    def test_public_pages_use_shared_mobile_layer(self):
        client = app.test_client()
        for path in ('/home', '/marketplace', '/about', '/how-it-works', '/safety',
                     '/faq', '/terms', '/privacy', '/contact', '/login', '/register', '/forgot_password'):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assert_mobile_shell(response.get_data(as_text=True))

    def test_user_pages_use_shared_mobile_layer(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session['_user_id'] = str(self.user_id)
            session['_fresh'] = True
        for path in ('/upload', '/settings', '/user-items', '/my_valuations',
                     '/my_reservations', '/my-trades', '/my_orders', '/notifications',
                     '/notification-settings', '/payments/fund-account', '/payments/history', '/wishlist/manage'):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assert_mobile_shell(response.get_data(as_text=True))

    def test_admin_pages_use_shared_mobile_layer(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session['admin_id'] = self.admin_id
        for path in ('/admin/dashboard', '/admin/users', '/admin/approvals', '/admin/settlement-queue',
                     '/admin/verification-intake', '/admin/clearing-inventory', '/admin/system_settings'):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assert_mobile_shell(response.get_data(as_text=True), admin=True)

    def test_standalone_pages_use_mobile_layer(self):
        with app.test_request_context():
            for name in ('banned.html', 'maintenance_page.html', 'marketplace_disabled.html'):
                with self.subTest(name=name):
                    html = render_template(name, username='mobile-user', message='Please try again later.')
                    self.assertIn('mobile-ui mobile-standalone', html)
                    self.assertEqual(html.count('href="/static/css/mobile.css"'), 1)
                    self.assertIn('width=device-width', html)
