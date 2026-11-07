import os
import unittest
from datetime import datetime, timedelta

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from app import app, db
from models import Admin, AuditLog, ContactMessage, Item, ItemVideo, Order, PickupStation, Reservation, User


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

    def test_station_pages_use_verification_station_labels(self):
        client = self._client()
        for path in ('/admin/pickup-stations', f'/admin/pickup_stations/edit/{self.station.id}'):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                body = response.get_data(as_text=True)
                self.assertIn('Verification Station', body)
                self.assertNotIn('pickup station', body.lower())

    def test_live_templates_use_new_station_terminology(self):
        from pathlib import Path
        import re

        templates = Path(app.root_path) / 'templates'
        for path in templates.rglob('*.html'):
            with self.subTest(template=path.name):
                self.assertIsNone(re.search(r'pickup\s+stations?', path.read_text(encoding='utf-8'), re.I))

    def test_top_navigation_only_has_dashboard_and_logout(self):
        from html.parser import HTMLParser
        from flask import url_for

        class NavigationLinks(HTMLParser):
            def __init__(self):
                super().__init__()
                self.in_nav = False
                self.links = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'nav' and attrs.get('class') == 'admin-navbar':
                    self.in_nav = True
                if self.in_nav and tag == 'a' and attrs.get('class') == 'nav-link':
                    self.links.append(attrs.get('href'))

            def handle_endtag(self, tag):
                if tag == 'nav':
                    self.in_nav = False

        client = self._client()
        with app.test_request_context():
            expected = [url_for('admin.admin_dashboard'), url_for('admin.admin_logout')]
            shortcut_urls = [
                url_for('admin.stolen_reports'),
                url_for('admin.clearing_inventory'),
                url_for('admin.verification_intake_log'),
            ]
        for path in ('/admin/dashboard', '/admin/clearing-inventory'):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                parser = NavigationLinks()
                parser.feed(response.get_data(as_text=True))
                self.assertEqual(parser.links, expected)
                if path == '/admin/dashboard':
                    for shortcut in shortcut_urls:
                        self.assertIn(f'href="{shortcut}"', response.get_data(as_text=True))

    def test_preverification_route_is_removed(self):
        response = self._client().get('/admin/pre-verification')
        self.assertEqual(response.status_code, 404)

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

    def test_pending_counts_cover_actionable_queues_and_clear_when_resolved(self):
        from routes.admin import inject_admin_context

        reconfirmation = Item(
            name='Reconfirmation', category='Electronics', user_id=self.user.id,
            status='reconfirmation_review',
        )
        db.session.add(reconfirmation)
        for status in ItemVideo.VALID_STATUSES:
            db.session.add(ItemVideo(
                item_id=self.item.id, uploaded_by_id=self.user.id, status=status,
            ))
        for index, (status, cancelled) in enumerate((
            ('Pending', False), ('Processing', False), ('Shipped', False),
            ('Ready for Pickup', False), ('Delivered', False),
            ('Cancelled', False), ('Pending', True),
        )):
            db.session.add(Order(
                user_id=self.user.id, delivery_method='pickup',
                order_number=f'TEST-{index}', status=status, cancelled=cancelled,
            ))
        for status in ('pending', 'in_progress', 'resolved', 'spam'):
            db.session.add(ContactMessage(
                name='Read message', email='read@example.com', message='Help',
                status=status, is_read=True,
            ))
        self.user.is_banned = True
        self.user.appeal_message = 'Please review'
        self.user.unban_request_date = datetime.utcnow()
        for status, delivery, fee, backing_return in (
            ('active', 'pickup', 'not_required', 'not_required'),
            ('completed', 'home delivery', 'quote_pending', 'not_required'),
            ('cancelled', 'home delivery', 'paid', 'return_required'),
            ('completed', 'pickup', 'not_required', 'not_required'),
        ):
            db.session.add(Reservation(
                user_id=self.user.id, item_id=self.item.id,
                provisional_credits_used=100, status=status, delivery_method=delivery,
                delivery_fee_status=fee, backing_return_status=backing_return,
                expires_at=datetime.utcnow() + timedelta(days=1),
            ))
        db.session.commit()
        expected = {
            'items': 1, 'videos': 2, 'reconfirmations': 1,
            'settlements': 3, 'orders': 4, 'appeals': 1, 'messages': 3, 'stolen_reports': 0,
            'manual_reviews': 0,
        }
        with app.test_request_context('/admin/dashboard'):
            from flask import session
            session['admin_id'] = self.admin.id
            context = inject_admin_context()
            self.assertEqual(context['admin_pending_counts'], expected)
            self.assertEqual(context['admin_pending_total'], sum(expected.values()))

        response = self._client().get('/admin/dashboard')
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        for queue, count in expected.items():
            if not count:
                continue
            self.assertIn(
                f'data-pending-queue="{queue}" aria-label="{count} pending">{count}</span>',
                body,
            )

        Item.query.update({'status': 'approved'})
        ItemVideo.query.update({'status': 'approved'})
        Order.query.update({'status': 'Delivered'})
        Reservation.query.update({
            'status': 'completed', 'delivery_fee_status': 'paid',
            'backing_return_status': 'returned', 'seller_item_verification_status': 'passed',
        })
        ContactMessage.query.update({'status': 'resolved'})
        self.user.appeal_message = None
        db.session.commit()
        response = self._client().get('/admin/dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('data-pending-queue=', response.get_data(as_text=True))

    def test_pending_counts_are_permission_scoped_and_read_does_not_resolve(self):
        from routes.admin import inject_admin_context
        from flask import session

        limited = Admin(username='support', email='support@example.com', password='x')
        limited.permission_list = ['messages.manage']
        self.message.is_read = True
        db.session.add(limited)
        db.session.commit()
        with app.test_request_context('/admin/dashboard'):
            session['admin_id'] = limited.id
            context = inject_admin_context()
            self.assertEqual(context['admin_pending_counts'], {'messages': 1})
            self.assertEqual(context['admin_pending_total'], 1)
        client = app.test_client()
        with client.session_transaction() as s:
            s['admin_id'] = limited.id
        body = client.get('/admin/dashboard').get_data(as_text=True)
        self.assertIn('data-pending-queue="messages"', body)
        self.assertNotIn('data-pending-queue="items"', body)
        self.assertNotIn('data-pending-queue="videos"', body)
        self.assertNotIn('data-pending-queue="orders"', body)
        with app.test_request_context('/admin/login'):
            self.assertEqual(inject_admin_context()['admin_pending_counts'], {})


if __name__ == '__main__':
    unittest.main()
