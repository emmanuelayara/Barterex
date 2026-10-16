import os
import unittest

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from app import app, db
from models import Admin
from permissions import ALL_PERMISSIONS, ENDPOINT_PERMISSIONS, SUPER_ADMIN_ONLY, PUBLIC_ENDPOINTS, AUTHENTICATED_ENDPOINTS


class AdminPermissionTests(unittest.TestCase):
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
        self.super_admin = self._make_admin('boss', is_super_admin=True)
        self.messenger = self._make_admin('messenger', permissions=['messages.manage'])
        self.nobody = self._make_admin('nobody', permissions=[])

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _make_admin(self, name, is_super_admin=False, permissions=None):
        admin = Admin(username=name, email=f'{name}@example.com', password='test-hash',
                      is_super_admin=is_super_admin)
        admin.permission_list = permissions or []
        db.session.add(admin)
        db.session.commit()
        return admin

    def _client_for(self, admin):
        client = app.test_client()
        with client.session_transaction() as s:
            s['admin_id'] = admin.id
            s['admin_username'] = admin.username
        return client

    def test_every_admin_endpoint_is_mapped(self):
        endpoints = {r.endpoint for r in app.url_map.iter_rules() if r.endpoint.startswith('admin.')}
        mapped = set(ENDPOINT_PERMISSIONS) | PUBLIC_ENDPOINTS | AUTHENTICATED_ENDPOINTS
        self.assertEqual(endpoints - mapped, set())
        self.assertEqual(set(ENDPOINT_PERMISSIONS) - endpoints, set())

    def test_mapped_permissions_exist_in_catalog(self):
        for endpoint, perm in ENDPOINT_PERMISSIONS.items():
            self.assertTrue(perm == SUPER_ADMIN_ONLY or perm in ALL_PERMISSIONS, endpoint)

    def test_anonymous_is_redirected_to_login(self):
        response = app.test_client().get('/admin/users')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login', response.headers['Location'])

    def test_sub_admin_can_only_reach_granted_areas(self):
        client = self._client_for(self.messenger)
        self.assertEqual(client.get('/admin/messages').status_code, 200)
        self.assertEqual(client.get('/admin/users').status_code, 403)
        self.assertEqual(client.get('/admin/audit-log').status_code, 403)
        self.assertEqual(client.post('/admin/delete_user/1').status_code, 403)

    def test_sub_admin_cannot_manage_admins(self):
        client = self._client_for(self.messenger)
        for path in ('/admin/register', '/admin/admins', f'/admin/admins/{self.nobody.id}/edit'):
            self.assertEqual(client.get(path).status_code, 403, path)
        self.assertEqual(client.post(f'/admin/admins/{self.nobody.id}/toggle-active').status_code, 403)

    def test_dashboard_is_available_to_every_admin_and_hides_other_areas(self):
        response = self._client_for(self.messenger).get('/admin/dashboard')
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('Messages', body)
        self.assertNotIn('Manage Users', body)
        self.assertNotIn('Audit Log', body)
        self.assertNotIn('Create Admin', body)

        empty = self._client_for(self.nobody).get('/admin/dashboard')
        self.assertEqual(empty.status_code, 200)
        self.assertIn('No actions have been assigned', empty.get_data(as_text=True))

    def test_super_admin_has_full_access(self):
        client = self._client_for(self.super_admin)
        self.assertEqual(client.get('/admin/users').status_code, 200)
        self.assertEqual(client.get('/admin/admins').status_code, 200)
        self.assertEqual(client.get('/admin/register').status_code, 200)

    def test_revoking_permission_takes_effect_immediately(self):
        client = self._client_for(self.messenger)
        self.assertEqual(client.get('/admin/messages').status_code, 200)
        self.messenger.permission_list = []
        db.session.commit()
        self.assertEqual(client.get('/admin/messages').status_code, 403)

    def test_deactivated_admin_is_logged_out(self):
        client = self._client_for(self.messenger)
        self.messenger.is_active = False
        db.session.commit()
        response = client.get('/admin/messages')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login', response.headers['Location'])
        with client.session_transaction() as s:
            self.assertNotIn('admin_id', s)

    def test_create_admin_saves_only_selected_valid_permissions(self):
        client = self._client_for(self.super_admin)
        response = client.post('/admin/register', data={
            'username': 'newadmin',
            'email': 'newadmin@example.com',
            'password': 'Str0ng!Pass',
            'confirm_password': 'Str0ng!Pass',
            'permissions': ['users.view', 'audit.view', 'not.a.permission'],
        })
        self.assertEqual(response.status_code, 302)
        created = Admin.query.filter_by(username='newadmin').one()
        self.assertFalse(created.is_super_admin)
        self.assertEqual(created.permission_list, ['users.view', 'audit.view'])

    def test_create_admin_requires_a_permission_or_super_admin(self):
        client = self._client_for(self.super_admin)
        response = client.post('/admin/register', data={
            'username': 'newadmin',
            'email': 'newadmin@example.com',
            'password': 'Str0ng!Pass',
            'confirm_password': 'Str0ng!Pass',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(Admin.query.filter_by(username='newadmin').first())

    def test_edit_admin_updates_permissions(self):
        client = self._client_for(self.super_admin)
        response = client.post(f'/admin/admins/{self.messenger.id}/edit',
                               data={'permissions': ['orders.manage']})
        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.messenger)
        self.assertEqual(self.messenger.permission_list, ['orders.manage'])

    def test_last_super_admin_cannot_be_demoted_or_deactivated(self):
        client = self._client_for(self.super_admin)
        client.post(f'/admin/admins/{self.super_admin.id}/edit', data={'permissions': ['users.view']})
        client.post(f'/admin/admins/{self.super_admin.id}/toggle-active')
        db.session.refresh(self.super_admin)
        self.assertTrue(self.super_admin.is_super_admin)
        self.assertTrue(self.super_admin.is_active)

    def test_super_admin_can_deactivate_another_admin(self):
        client = self._client_for(self.super_admin)
        client.post(f'/admin/admins/{self.messenger.id}/toggle-active')
        db.session.refresh(self.messenger)
        self.assertFalse(self.messenger.is_active)

    def test_delete_admin_scrubs_account_but_keeps_row_for_history(self):
        from models import AuditLog
        db.session.add(AuditLog(admin_id=self.messenger.id, action_type='x', target_type='y'))
        db.session.commit()
        client = self._client_for(self.super_admin)

        response = client.post(f'/admin/admins/{self.messenger.id}/delete')

        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.messenger)
        self.assertIsNotNone(self.messenger.deleted_at)
        self.assertFalse(self.messenger.is_active)
        self.assertFalse(self.messenger.is_super_admin)
        self.assertEqual(self.messenger.permission_list, [])
        self.assertNotEqual(self.messenger.email, 'messenger@example.com')
        self.assertEqual(AuditLog.query.filter_by(admin_id=self.messenger.id, action_type='x').count(), 1)
        self.assertEqual(AuditLog.query.filter_by(action_type='delete_admin').count(), 1)
        listing = client.get('/admin/admins').get_data(as_text=True)
        self.assertNotIn('messenger@example.com', listing)
        self.assertEqual(client.get(f'/admin/admins/{self.messenger.id}/edit').status_code, 404)

    def test_deleted_admin_cannot_log_in_and_email_is_reusable(self):
        client = self._client_for(self.super_admin)
        client.post(f'/admin/admins/{self.messenger.id}/delete')
        reuse = client.post('/admin/register', data={
            'username': 'messenger',
            'email': 'messenger@example.com',
            'password': 'Str0ng!Pass',
            'confirm_password': 'Str0ng!Pass',
            'permissions': ['users.view'],
        })
        self.assertEqual(reuse.status_code, 302)

    def test_deleted_admin_session_is_rejected(self):
        victim_client = self._client_for(self.messenger)
        self._client_for(self.super_admin).post(f'/admin/admins/{self.messenger.id}/delete')
        response = victim_client.get('/admin/messages')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login', response.headers['Location'])

    def test_cannot_delete_self_or_last_super_admin(self):
        client = self._client_for(self.super_admin)
        client.post(f'/admin/admins/{self.super_admin.id}/delete')
        db.session.refresh(self.super_admin)
        self.assertIsNone(self.super_admin.deleted_at)

        other_super = self._make_admin('boss2', is_super_admin=True)
        self.super_admin.is_active = False
        db.session.commit()
        client2 = self._client_for(other_super)
        client2.post(f'/admin/admins/{other_super.id}/delete')
        db.session.refresh(other_super)
        self.assertIsNone(other_super.deleted_at)

    def test_sub_admin_cannot_delete_admins(self):
        client = self._client_for(self.messenger)
        self.assertEqual(client.post(f'/admin/admins/{self.nobody.id}/delete').status_code, 403)
        db.session.refresh(self.nobody)
        self.assertIsNone(self.nobody.deleted_at)


if __name__ == '__main__':
    unittest.main()
