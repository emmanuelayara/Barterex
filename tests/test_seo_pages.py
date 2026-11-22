import json
import os
import re
import unittest

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from app import app, db, limiter


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


if __name__ == '__main__':
    unittest.main()
