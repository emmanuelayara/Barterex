import re
from html import escape

from flask import current_app


EMAIL_LOGO_MARKER = '<!-- barter-express-email-logo -->'


def add_email_logo(html_body):
    """Add a remotely hosted company logo near the top of an email body."""
    if EMAIL_LOGO_MARKER in html_body:
        return html_body

    logo_url = escape(current_app.config['EMAIL_LOGO_URL'], quote=True)
    logo = f'''{EMAIL_LOGO_MARKER}
<table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0">
  <tr>
    <td align="center" style="padding: 16px 0 24px;">
      <img src="{logo_url}" alt="Barter Express" width="160" style="display: block; width: 160px; max-width: 100%; height: auto; border: 0;">
    </td>
  </tr>
</table>'''

    body_match = re.search(r'<body(?:\s[^>]*)?>', html_body, flags=re.IGNORECASE)
    if body_match:
        return html_body[:body_match.end()] + '\n' + logo + html_body[body_match.end():]
    return logo + '\n' + html_body
