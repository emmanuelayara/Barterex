import os
import unittest
from unittest.mock import patch

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from app import app, db
from models import Admin, ContactMessage, Item, Notification, User


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


if __name__ == '__main__':
    unittest.main()
