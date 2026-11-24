"""Public, crawlable pages and crawler files (robots.txt, sitemap.xml).

Only pages that contain no account, valuation or verification data belong here.
"""
from xml.sax.saxutils import escape

from flask import Blueprint, Response, current_app, render_template, url_for

from app import limiter
from models import Item

# Crawlers fetch these files often; keep them outside the per-IP request limits.
_exempt_from_limits = limiter.exempt if limiter is not None else (lambda view: view)

seo_bp = Blueprint('seo', __name__)

# Public pages offered to search engines: (endpoint, changefreq, priority)
SITEMAP_PAGES = (
    ('marketplace.home', 'weekly', '1.0'),
    ('seo.check_item_value', 'monthly', '0.9'),
    ('seo.phone_valuation', 'monthly', '0.8'),
    ('seo.laptop_valuation', 'monthly', '0.8'),
    ('seo.swap_in_nigeria', 'monthly', '0.8'),
    ('marketplace.marketplace', 'daily', '0.8'),
    ('marketplace.how_it_works', 'monthly', '0.7'),
    ('marketplace.faq', 'monthly', '0.6'),
    ('marketplace.safety', 'monthly', '0.5'),
    ('marketplace.about', 'monthly', '0.5'),
    ('marketplace.contact', 'yearly', '0.4'),
    ('marketplace.terms', 'yearly', '0.3'),
    ('marketplace.privacy', 'yearly', '0.3'),
)

# Everything that is personal, transactional or administrative.
PRIVATE_PATHS = (
    '/admin/', '/account/', '/api/', '/payments/', '/two-factor/', '/debug/',
    '/dashboard', '/settings', '/profile-settings', '/credit-history',
    '/my-', '/my_', '/order', '/reservation/', '/cart', '/checkout', '/finalize_purchase',
    '/upload', '/edit/', '/user-items', '/items/', '/manual-verification-stations',
    '/notification', '/favorites', '/add_to_', '/remove_from_', '/wishlist/', '/clear_cart',
    '/item/*/reserve', '/item/*/choose-backing-assets', '/item/*/cancel-reservation',
    '/item/*/report-stolen',
    '/login', '/logout', '/register', '/forgot_password', '/reset_password/', '/verify-email/',
    '/confirm-email-change/', '/resend-verification', '/banned', '/request_unban',
    '/contact-form', '/contact-success/', '/value/',
)


def is_private_path(path):
    """True for URLs that must never be indexed (wildcard-only rules are skipped)."""
    return any(path.startswith(prefix) for prefix in PRIVATE_PATHS if '*' not in prefix)


def _site_url():
    return current_app.config['APP_URL']


@seo_bp.route('/check-item-value')
def check_item_value():
    return render_template('check_item_value.html')


@seo_bp.route('/phone-valuation-nigeria')
def phone_valuation():
    return render_template('phone_valuation.html')


@seo_bp.route('/laptop-valuation-nigeria')
def laptop_valuation():
    return render_template('laptop_valuation.html')


@seo_bp.route('/swap-items-nigeria')
def swap_in_nigeria():
    return render_template('swap_in_nigeria.html')


@seo_bp.route('/robots.txt')
@_exempt_from_limits
def robots_txt():
    lines = ['User-agent: *']
    lines += [f'Disallow: {path}' for path in PRIVATE_PATHS]
    lines += ['', f'Sitemap: {_site_url()}/sitemap.xml', '']
    return Response('\n'.join(lines), mimetype='text/plain')


@seo_bp.route('/sitemap.xml')
@_exempt_from_limits
def sitemap_xml():
    entries = ''.join(
        '<url>'
        f'<loc>{escape(_site_url() + url_for(endpoint))}</loc>'
        f'<changefreq>{changefreq}</changefreq>'
        f'<priority>{priority}</priority>'
        '</url>'
        for endpoint, changefreq, priority in SITEMAP_PAGES
    )
    entries += ''.join(
        '<url>'
        f'<loc>{escape(_site_url() + url_for("marketplace.view_item", item_id=item_id))}</loc>'
        '<changefreq>daily</changefreq>'
        '</url>'
        for (item_id,) in Item.query.with_entities(Item.id).filter(Item.is_public_listing).order_by(Item.id).all()
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f'{entries}</urlset>'
    )
    return Response(xml, mimetype='application/xml')
