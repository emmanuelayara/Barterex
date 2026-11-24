import json
import os
import re
import unittest
from xml.etree import ElementTree

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from app import app, db, limiter
from models import Item


class SeoPagesTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.context = app.app_context()
        self.context.push()
        self.previous_limiter = limiter.enabled
        limiter.enabled = False
        db.create_all()
        self.client = app.test_client()

    def tearDown(self):
        limiter.enabled = self.previous_limiter
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_value_page_is_public_and_indexable(self):
        response = self.client.get('/check-item-value')
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('<meta name="robots" content="index, follow">', html)
        self.assertIn(f'<link rel="canonical" href="{app.config["APP_URL"]}/check-item-value">', html)
        self.assertRegex(html, r'<title>How Much Is My Used Phone Worth\?[^<]*Barter Express</title>')
        self.assertRegex(html, r'<meta name="description" content="[^"]{60,160}">')

        data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
        faq = next(node for node in data['@graph'] if node['@type'] == 'FAQPage')
        self.assertTrue(faq['mainEntity'])
        self.assertEqual(faq['mainEntity'][0]['name'], 'How much is my used phone worth?')

    def test_titles_do_not_repeat_the_brand(self):
        for path in ('/faq', '/about', '/how-it-works', '/home'):
            with self.subTest(path=path):
                title = re.search(r'<title>(.*?)</title>', self.client.get(path).get_data(as_text=True)).group(1)
                self.assertEqual(title.count('Barter Express'), 1, title)

    def test_non_public_pages_are_noindex_by_default(self):
        for path in ('/login', '/register'):
            with self.subTest(path=path):
                html = self.client.get(path).get_data(as_text=True)
                self.assertIn('<meta name="robots" content="noindex, nofollow">', html)
                self.assertNotIn('rel="canonical"', html)

    def test_private_areas_send_noindex_header(self):
        for path in ('/dashboard', '/my_valuations', '/admin/login', '/account/security', '/payments/history'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.headers.get('X-Robots-Tag'), 'noindex, nofollow')
        self.assertIsNone(self.client.get('/faq').headers.get('X-Robots-Tag'))

    def test_robots_and_sitemap(self):
        robots = self.client.get('/robots.txt')
        self.assertEqual(robots.mimetype, 'text/plain')
        text = robots.get_data(as_text=True)
        for private in ('/admin/', '/account/', '/my_', '/my-', '/upload', '/payments/', '/value/'):
            self.assertIn(f'Disallow: {private}', text)
        self.assertNotIn('Disallow: /check-item-value', text)
        self.assertIn(f'Sitemap: {app.config["APP_URL"]}/sitemap.xml', text)

        sitemap = self.client.get('/sitemap.xml')
        self.assertEqual(sitemap.mimetype, 'application/xml')
        locations = re.findall(r'<loc>(.*?)</loc>', sitemap.get_data(as_text=True))
        self.assertIn(f'{app.config["APP_URL"]}/check-item-value', locations)
        path_of = lambda url: url[len(app.config['APP_URL']):]
        for location in locations:
            self.assertFalse(
                any(path_of(location).startswith(p) for p in ('/admin', '/account', '/my', '/dashboard', '/upload', '/login')),
                location,
            )

    def test_public_listing_metadata_and_sitemap_exclude_private_items(self):
        public = Item(name='iPhone 12 & case', description='A blue phone with 128GB storage.',
                      category='Phones & Gadgets', condition='Like New', value=1000,
                      status='approved', is_approved=True, is_available=True)
        no_description = Item(name='Laptop X', category='Consumer Electronics', value=2000,
                              status='approved', is_approved=True, is_available=True)
        private = Item(name='Private valuation', category='Phones & Gadgets', value=3000,
                       status='valuation_only', is_approved=False, is_available=False)
        inconsistent = Item(name='Private inconsistent valuation', category='Phones & Gadgets', value=3000,
                            status='valuation_only', is_approved=True, is_available=True)
        unavailable = Item(name='Unavailable phone', category='Phones & Gadgets', value=1000,
                           status='approved', is_approved=True, is_available=False)
        no_value = Item(name='Unpriced phone', category='Phones & Gadgets',
                        status='approved', is_approved=True, is_available=True)
        db.session.add_all([public, no_description, private, inconsistent, unavailable, no_value])
        db.session.commit()

        locations = {node.text for node in ElementTree.fromstring(self.client.get('/sitemap.xml').data)
                     .iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')}
        for item in (public, no_description):
            self.assertIn(f'{app.config["APP_URL"]}/item/{item.id}', locations)
        for item in (private, inconsistent, unavailable, no_value):
            self.assertNotIn(f'{app.config["APP_URL"]}/item/{item.id}', locations)

        html = self.client.get(f'/item/{public.id}?source=test').get_data(as_text=True)
        self.assertIn('<title>Barter Express - iPhone 12 &amp; case for Barter in Nigeria</title>', html)
        self.assertIn('<meta name="description" content="A blue phone with 128GB storage.">', html)
        self.assertIn('<meta name="robots" content="index, follow">', html)
        self.assertIn(f'<link rel="canonical" href="{app.config["APP_URL"]}/item/{public.id}">', html)
        self.assertEqual(html.count('property="og:title"'), 1)
        fallback = self.client.get(f'/item/{no_description.id}').get_data(as_text=True)
        self.assertIn('Explore Laptop X on Barter Express', fallback)
        for item in (private, inconsistent):
            response = self.client.get(f'/item/{item.id}')
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.headers.get('X-Robots-Tag'), 'noindex, nofollow')
            self.assertNotIn(item.name, response.get_data(as_text=True))
        html = self.client.get(f'/item/{unavailable.id}').get_data(as_text=True)
        self.assertIn('<meta name="robots" content="noindex, nofollow">', html)
        self.assertNotIn('rel="canonical"', html)
        html = self.client.get(f'/item/{no_value.id}').get_data(as_text=True)
        self.assertIn('<meta name="robots" content="noindex, nofollow">', html)
        public.is_available = False
        db.session.commit()
        self.assertNotIn(f'{app.config["APP_URL"]}/item/{public.id}',
                         self.client.get('/sitemap.xml').get_data(as_text=True))
        self.assertIn('<meta name="robots" content="noindex, nofollow">',
                      self.client.get(f'/item/{public.id}').get_data(as_text=True))

    def test_nigeria_guides_and_homepage_are_discoverable(self):
        home = self.client.get('/home').get_data(as_text=True)
        self.assertIn('<title>Barter Express | Trade by Barter in Nigeria</title>', home)
        self.assertIn('Check your item’s value', home)
        self.assertRegex(home, r'href="/value/start" class="hm-btn primary"')
        self.assertNotIn("What's my item worth?", home)
        sitemap = self.client.get('/sitemap.xml').get_data(as_text=True)
        for path, phrase in (
            ('/phone-valuation-nigeria', 'used phone'),
            ('/laptop-valuation-nigeria', 'used laptop'),
            ('/swap-items-nigeria', 'swap items in nigeria'),
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                html = response.get_data(as_text=True)
                self.assertEqual(response.status_code, 200)
                self.assertIn('<meta name="robots" content="index, follow">', html)
                self.assertIn(f'<link rel="canonical" href="{app.config["APP_URL"]}{path}">', html)
                self.assertIn(phrase, html.lower())
                self.assertIn(f'href="{path}"', home)
                self.assertIn(f'{app.config["APP_URL"]}{path}', sitemap)
                self.assertIn('href="/value/start', html)


if __name__ == '__main__':
    unittest.main()
