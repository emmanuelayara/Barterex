import unittest
from datetime import datetime
from types import SimpleNamespace
from html.parser import HTMLParser
from flask import render_template

from app import app
from services.email_branding import EMAIL_LOGO_MARKER, add_email_logo


class EmailBrandingTests(unittest.TestCase):
    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
        self.original_logo_url = app.config.get('EMAIL_LOGO_URL')
        app.config['EMAIL_LOGO_URL'] = 'https://example.com/static/logo.png'

    def tearDown(self):
        app.config['EMAIL_LOGO_URL'] = self.original_logo_url
        self.app_context.pop()

    def test_logo_is_inserted_inside_html_body(self):
        html = '<!doctype html><html><body class="email"><main>Message</main></body></html>'

        branded = add_email_logo(html)

        self.assertIn(EMAIL_LOGO_MARKER, branded)
        self.assertIn('<body class="email">\n' + EMAIL_LOGO_MARKER, branded)
        self.assertIn('src="https://example.com/static/logo.png"', branded)
        self.assertIn('alt="Barter Express"', branded)
        self.assertLess(branded.index(EMAIL_LOGO_MARKER), branded.index('<main>'))

    def test_logo_is_added_to_html_fragments_and_not_duplicated(self):
        html = '<p>Message</p>'

        branded = add_email_logo(html)

        self.assertTrue(branded.startswith(EMAIL_LOGO_MARKER))
        self.assertEqual(add_email_logo(branded), branded)

    def test_all_email_templates_have_readable_shared_layout(self):
        class EmailContent(HTMLParser):
            def __init__(self):
                super().__init__()
                self.links = []
                self.paragraphs = []
                self.images = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'a':
                    self.links.append(attrs)
                elif tag == 'p':
                    self.paragraphs.append(attrs)
                elif tag == 'img':
                    self.images.append(attrs)

        url = 'https://example.com/action?reference=TEST&source=email'
        context = dict(
            username='Reader <script>alert(1)</script>', user_name='Reader',
            heading='Reservation update', message='First paragraph.\n\nSecond paragraph.',
            details=['Item: Camera', 'Deadline: Tomorrow'], cta_url=url, cta_label='View reservation',
            verification_link=url, verification_token='test-token', reset_url=url,
            ban_date=datetime(2026, 11, 7), reason='Inspection feedback <script>alert(1)</script>',
            unban_url=url, item_name='Camera', item_number='EA-TEST', item_value=500,
            approval_url=url, reference='TEST-REFERENCE', amount=5000, credits_purchased=5000,
            previous_balance=100, new_balance=5100, transaction_date='7 November 2026',
            marketplace_url=url, dashboard_url=url, credits_awarded=100,
            level=2, tier='Starter', total_points=500,
            order_id=3, order_date='7 November 2026', delivery_method='home delivery',
            delivery_address='12 Test Street\nLagos', pickup_station=None,
            items=[SimpleNamespace(name='Camera', description='A clear description.')],
            status='processing', status_text='Processing', updated_date='7 November 2026',
            status_message='Being prepared.', action_url=url, item_condition='Like New',
            item_price='500 BXC', item_category='Electronics', item_description='Test description.',
            recommendation_reason='Matches your interests.', wishlist_name='Camera',
            item_image='https://example.com/item.jpg', item_location='Lagos',
            view_item_url=url, wishlist_url=url, unsubscribe_url=url,
        )
        templates = [
            'notification', 'welcome_email', 'verify_email', 'reset_password_email',
            'account_banned', 'account_unbanned', 'item_approved', 'item_rejected',
            'credit_purchase', 'level_up_notification', 'order_confirmation',
            'order_status_update', 'recommendation', 'wishlist_notification',
        ]
        with app.test_request_context():
            for template in templates:
                with self.subTest(template=template):
                    html = render_template(f'emails/{template}.html', **context)
                    self.assertEqual(html.count(EMAIL_LOGO_MARKER), 1)
                    self.assertEqual(add_email_logo(html), html)
                    self.assertIn('role="presentation"', html)
                    self.assertIn('Contact Barter Express support', html)
                    self.assertIn('copy this link into your browser', html)
                    self.assertNotIn('<script>', html)
                    self.assertNotIn('localhost', html)
                    self.assertNotIn('contact the seller', html.lower())
                    parser = EmailContent()
                    parser.feed(html)
                    self.assertEqual(
                        len([img for img in parser.images if img.get('alt') == 'Barter Express']), 1
                    )
                    self.assertTrue(any('font-size:16px' in p.get('style', '') for p in parser.paragraphs))
                    self.assertTrue(any('padding:14px 24px' in a.get('style', '') for a in parser.links))

    def test_notification_preserves_paragraphs_and_all_details_without_html_injection(self):
        message = 'First paragraph.\n\nSecond paragraph.\nA new line.\n\n' + 'Long message ' * 100
        with app.test_request_context():
            html = render_template(
                'emails/notification.html', heading='Clear update', message=message,
                details=['Feedback: <img src=x onerror=alert(1)>'], username='Reader',
                cta_url=None,
            )
        self.assertIn('Second paragraph.<br>A new line.', html)
        self.assertIn('Long message ' * 100, html)
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', html)
        self.assertNotIn('<img src=x', html)
        self.assertNotIn('copy this link', html)


if __name__ == '__main__':
    unittest.main()
