import re
import unittest

from app import app, db
from models import ActivityLog, SecuritySettings, User


class TrustedDeviceTests(unittest.TestCase):
    def setUp(self):
        self.previous_csrf = app.config['WTF_CSRF_ENABLED']
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.context = app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.user = User(username='device-user', email='devices@example.com', password_hash='test')
        self.other = User(username='other-user', email='other-devices@example.com', password_hash='test')
        db.session.add_all([self.user, self.other])
        db.session.commit()
        self.user_id = self.user.id
        self.other_id = self.other.id
        self.client = app.test_client()
        with self.client.session_transaction() as state:
            state['_user_id'] = self.user.get_id()
            state['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        app.config['WTF_CSRF_ENABLED'] = self.previous_csrf
        self.context.pop()

    def devices(self):
        db.session.expire_all()
        return SecuritySettings.query.filter_by(user_id=self.user_id).one().trusted_devices

    def add(self, name):
        return self.client.post('/account/trusted-devices/add', data={'name': name, 'fingerprint': name})

    def test_multiple_additions_and_removals_persist_after_reload(self):
        self.add('Laptop')
        self.add('Phone')
        self.add('Tablet')
        self.assertEqual([device['name'] for device in self.devices()], ['Laptop', 'Phone', 'Tablet'])
        response = self.client.post('/account/trusted-devices/remove/1')
        self.assertEqual(response.status_code, 302)
        self.assertEqual([device['name'] for device in self.devices()], ['Laptop', 'Tablet'])
        for path in ('/account/trusted-devices', '/account/security'):
            page = self.client.get(path).get_data(as_text=True)
            device_names = re.findall(r'<h6 class="mb-0">(.*?)</h6>', page)
            self.assertNotIn('Phone', device_names)
            self.assertIn('Tablet', device_names)
        self.client.post('/account/trusted-devices/remove/0')
        self.assertEqual([device['name'] for device in self.devices()], ['Tablet'])
        self.client.post('/account/trusted-devices/remove/0')
        self.assertEqual(self.devices(), [])
        self.assertEqual(ActivityLog.query.filter_by(user_id=self.user_id, activity_type='device_untrusted').count(), 3)

    def test_invalid_index_reports_error_without_changing_devices(self):
        self.add('Laptop')
        response = self.client.post('/account/trusted-devices/remove/10', follow_redirects=True)
        self.assertIn('This trusted device was not found', response.get_data(as_text=True))
        self.assertEqual([device['name'] for device in self.devices()], ['Laptop'])
        self.assertEqual(ActivityLog.query.filter_by(user_id=self.user_id, activity_type='device_untrusted').count(), 0)

    def test_removal_is_scoped_to_logged_in_user(self):
        self.add('Laptop')
        db.session.add(SecuritySettings(user_id=self.other_id, trusted_devices=[{'name': 'Other laptop'}]))
        db.session.commit()
        self.client.post('/account/trusted-devices/remove/0')
        self.assertEqual(self.devices(), [])
        self.assertEqual(SecuritySettings.query.filter_by(user_id=self.other_id).one().trusted_devices,
                         [{'name': 'Other laptop'}])
        self.assertEqual(app.test_client().post('/account/trusted-devices/remove/0').status_code, 302)

    def test_both_pages_include_csrf_tokens_for_device_forms(self):
        self.add('Laptop')
        app.config['WTF_CSRF_ENABLED'] = True
        self.assertEqual(self.client.post('/account/trusted-devices/remove/0').status_code, 400)
        for path in ('/account/trusted-devices', '/account/security'):
            with self.subTest(path=path):
                page = self.client.get(path).get_data(as_text=True)
                for action in ('/account/trusted-devices/add', '/account/trusted-devices/remove/0'):
                    form = re.search(r'<form[^>]*action="' + action + r'"[^>]*>(.*?)</form>',
                                     page, re.DOTALL).group(1)
                    self.assertIn('name="csrf_token"', form)
        token = re.search(r'name="csrf_token" value="([^"]+)"', form).group(1)
        response = self.client.post('/account/trusted-devices/remove/0', data={'csrf_token': token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.devices(), [])
