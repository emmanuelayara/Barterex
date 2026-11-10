import os
import unittest
from unittest.mock import patch

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from app import app, db
from models import Admin, ContactMessage, Item, Notification, User
from services.email_two_factor import fingerprint


class NotificationEmailRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            WTF_CSRF_ENABLED=False,
        )

    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()
        self.admin = Admin(
            username='alert-admin', email='alert-admin@example.com', is_super_admin=True, password='h'
        )
        self.user = User(username='member', email='member@example.com', password_hash='h')
        db.session.add_all([self.admin, self.user])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _admin_client(self):
        client = app.test_client()
        with client.session_transaction() as flask_session:
            flask_session['admin_id'] = self.admin.id
            flask_session['admin_mfa'] = fingerprint(self.admin)
        return client

    def _recipients(self, send_email):
        return [call.kwargs['recipients'][0] for call in send_email.call_args_list]

    def test_contact_form_confirms_to_sender_and_alerts_admins(self):
        with patch('routes.auth.send_email_async') as send_email:
            response = app.test_client().post('/contact-form', data={
                'name': 'Ada Obi',
                'email': 'ada@example.com',
                'message': 'I need help with my reservation.',
            })

        self.assertEqual(response.status_code, 302)
        self.assertCountEqual(
            self._recipients(send_email), ['ada@example.com', self.admin.email]
        )

    def test_message_status_change_emails_the_sender(self):
        message = ContactMessage(name='Ada', email='ada@example.com', message='Hello there, help', user_id=self.user.id)
        db.session.add(message)
        db.session.commit()

        with patch('routes.auth.send_email_async') as send_email:
            response = self._admin_client().post(
                f'/admin/messages/{message.id}/status', data={'status': 'resolved'}
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._recipients(send_email), ['ada@example.com'])
        self.assertTrue(Notification.query.filter_by(user_id=self.user.id).count())

    def test_deleting_an_item_notifies_its_owner_with_reason(self):
        item = Item(
            name='Old camera', category='Electronics', user_id=self.user.id, value=100,
            status='approved', is_approved=True, is_available=True,
        )
        db.session.add(item)
        db.session.commit()

        with patch('routes.auth.send_email_async') as send_email:
            response = self._admin_client().post(
                f'/admin/delete-item/{item.id}', data={'reason': 'Prohibited item'}
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._recipients(send_email), [self.user.email])
        note = Notification.query.filter_by(user_id=self.user.id).one()
        self.assertIn('Prohibited item', note.message)

    def test_rejecting_an_unban_appeal_notifies_the_user(self):
        self.user.is_banned = True
        self.user.appeal_message = 'Please unban me'
        self.user.unban_requested = True
        db.session.commit()

        with patch('routes.auth.send_email_async') as send_email:
            response = self._admin_client().post(f'/admin/reject_unban_appeal/{self.user.id}')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._recipients(send_email), [self.user.email])
        self.assertIn('not been approved', Notification.query.filter_by(user_id=self.user.id).one().message)

    def test_order_status_update_emails_the_buyer(self):
        from models import Order, OrderItem

        item = Item(
            name='Lamp', category='Home', user_id=None, value=50,
            status='approved', is_approved=True, is_available=False, owner_type='company',
        )
        db.session.add(item)
        db.session.flush()
        order = Order(
            user_id=self.user.id, order_number='ORD-TEST-1', total_credits=50, credits_used=50,
            delivery_method='home delivery', status='Pending',
        )
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderItem(order_id=order.id, item_id=item.id))
        db.session.commit()

        with patch('routes.auth.send_email_async') as send_email:
            response = self._admin_client().post(f'/admin/update_order_status/{order.id}')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._recipients(send_email), [self.user.email])
        self.assertIn('shipped', Notification.query.filter_by(user_id=self.user.id).first().message)

    def test_shared_layout_keeps_commit_and_rollback_email_behavior(self):
        from services.email_notifications import notify_user

        with patch('routes.auth.send_email_async') as send:
            notify_user(
                self.user, 'First paragraph.\n\nSecond paragraph.',
                subject='Readable update', details=['Deadline: Tomorrow'],
                cta_endpoint='user.my_reservations', cta_label='View reservations',
            )
            send.assert_not_called()
            db.session.commit()
            send.assert_called_once()
            html = send.call_args.kwargs['html_body']
            self.assertIn('First paragraph.', html)
            self.assertIn('Second paragraph.', html)
            self.assertIn('Deadline: Tomorrow', html)
            self.assertIn('View reservations', html)
            self.assertIn('barter-express-email-logo', html)
            send.reset_mock()
            notify_user(self.user, 'This change is rolled back.')
            db.session.rollback()
            send.assert_not_called()

    def test_credit_purchase_sends_shared_template_with_configured_links(self):
        from notifications import notify_credit_purchase
        with app.test_request_context(), patch('flask_mail.Mail') as mail:
            note = notify_credit_purchase(
                self.user.id, 500, 500, 0, 500, reference='TEST-CREDIT',
            )
        self.assertIsNotNone(note)
        mail.return_value.send.assert_called_once()
        message = mail.return_value.send.call_args.args[0]
        self.assertIn('Your BXC purchase is confirmed', message.html)
        self.assertIn('TEST-CREDIT', message.html)
        self.assertIn(app.config['APP_URL'].rstrip('/') + '/dashboard', message.html)
        self.assertEqual(message.html.count('barter-express-email-logo'), 1)

    def test_wishlist_email_preserves_item_and_preference_links(self):
        from services.wishlist_service import send_wishlist_email

        item = Item(
            name='Camera', category='Electronics', condition='Like New',
            user_id=self.user.id, value=500, image_url='https://example.com/camera.jpg',
        )
        db.session.add(item)
        db.session.commit()
        with app.test_request_context(), patch('services.wishlist_service.mail.send') as send:
            result = send_wishlist_email(
                self.user.email, self.user.username, item.name, item.id,
                item.category, item.condition, 'Wishlist match', item=item,
            )
        self.assertTrue(result)
        send.assert_called_once()
        message = send.call_args.args[0]
        self.assertIn('An item matches your wishlist', message.html)
        self.assertIn('src="https://example.com/camera.jpg"', message.html)
        for path in (f'/item/{item.id}', '/wishlist/manage', '/notification-settings'):
            self.assertIn(app.config['APP_URL'].rstrip('/') + path, message.html)
        self.assertEqual(message.html.count('barter-express-email-logo'), 1)


if __name__ == '__main__':
    unittest.main()
