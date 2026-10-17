import os
import unittest

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from app import app, db
from models import Admin, AuditLog, ContactMessage, Item, PickupStation, User


class AdminPagesRenderTests(unittest.TestCase):
    """Every admin page must render for a super admin, both empty and with sample data."""

    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')

    def setUp(self):
        self.ctx = app.app_context()
        self.ctx.push()
        db.drop_all()
        db.create_all()
        self.admin = Admin(username='boss', email='boss@example.com', password='x', is_super_admin=True)
        self.user = User(username='someone', email='someone@example.com', password_hash='x')
        db.session.add_all([self.admin, self.user])
        db.session.flush()
        self.item = Item(name='Phone', category='Electronics', condition='Like New', user_id=self.user.id,
                         status='pending', ai_estimated_value=100)
        self.station = PickupStation(name='Main', state='Lagos', city='Ikeja', address='1 Road')
        self.message = ContactMessage(name='Ann', email='ann@example.com', message='Hello there')
        db.session.add_all([self.item, self.station, self.message])
        db.session.flush()
        db.session.add(AuditLog(admin_id=self.admin.id, action_type='approve_item', target_type='item',
                                target_id=self.item.id, description='Approved'))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _client(self):
        client = app.test_client()
        with client.session_transaction() as s:
            s['admin_id'] = self.admin.id
            s['admin_username'] = self.admin.username
        return client

    def _paths(self):
        return [
            '/admin/dashboard',
            '/admin/dashboard?status=all',
            '/admin/users',
            '/admin/pending_appeals',
            f'/admin/view_user/{self.user.id}',
            f'/admin/user/{self.user.id}/edit',
            '/admin/approvals',
            '/admin/pre-verification',
            '/admin/video-review',
            '/admin/reconfirmation-review',
            '/admin/settlement-queue',
            '/admin/clearing-inventory',
            '/admin/verification-intake',
            '/admin/pickup-stations',
            '/admin/pickup-stations/add',
            f'/admin/pickup_stations/edit/{self.station.id}',
            '/admin/manage_orders',
            '/admin/audit-log',
            '/admin/maintenance',
            '/admin/system_settings',
            '/admin/messages',
            '/admin/admins',
            '/admin/register',
            f'/admin/admins/{self.admin.id}/edit',
        ]

    def test_pages_render(self):
        client = self._client()
        for path in self._paths():
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200, path)
                body = response.get_data(as_text=True)
                self.assertIn('class="admin-navbar"', body, path)
                self.assertNotIn('unexpected error occurred', body, path)

    def test_login_page_renders(self):
        response = app.test_client().get('/admin/login')
        self.assertEqual(response.status_code, 200)

    def test_forbidden_page_renders(self):
        limited = Admin(username='limited', email='limited@example.com', password='x')
        limited.permission_list = ['messages.manage']
        db.session.add(limited)
        db.session.commit()
        client = app.test_client()
        with client.session_transaction() as s:
            s['admin_id'] = limited.id
        response = client.get('/admin/users')
        self.assertEqual(response.status_code, 403)
        self.assertIn('Access denied', response.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
