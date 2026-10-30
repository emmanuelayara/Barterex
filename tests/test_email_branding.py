import unittest

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


if __name__ == '__main__':
    unittest.main()
