"""
30-day marketplace freshness reconfirmation for listed items.

Lazily swept (no cron needed) - see deactivate_stale_items(), called from the
marketplace listing and "My Items" page. A stale item is pulled off the
marketplace (is_available=False) and marked status='reconfirmation_required'
until its owner uploads a fresh photo (see routes/items.py reconfirm_item).
High-value items also need a stored code visible in that photo, which only an
admin can confirm by eye (see routes/admin.py reconfirmation_review_queue) -
low-value items relist instantly, self-service.
"""
import secrets
from datetime import datetime, timedelta

from app import db
from models import Item
from logger_config import setup_logger

logger = setup_logger(__name__)

FRESHNESS_WINDOW_DAYS = 30
HIGH_VALUE_THRESHOLD = 50000  # BXC - items worth at least this need a visible code on reconfirmation


def generate_reconfirmation_code() -> str:
    return secrets.token_hex(3).upper()  # e.g. "A1B2C3"


def deactivate_stale_items():
    """
    Pulls listed items off the marketplace once their freshness window has
    lapsed. Cheap/indexed - safe to call on every marketplace/My Items load.
    Returns the number of items deactivated.
    """
    cutoff = datetime.utcnow() - timedelta(days=FRESHNESS_WINDOW_DAYS)
    stale = Item.query.filter(
        Item.status == 'approved',
        Item.is_available == True,
        db.or_(
            Item.last_reconfirmed_at < cutoff,
            db.and_(Item.last_reconfirmed_at.is_(None), Item.activated_at < cutoff),
        ),
    ).all()

    for item in stale:
        item.is_available = False
        item.status = 'reconfirmation_required'
        if item.value and item.value >= HIGH_VALUE_THRESHOLD and not item.reconfirmation_code:
            item.reconfirmation_code = generate_reconfirmation_code()

    if stale:
        db.session.commit()
        logger.info(f"Deactivated {len(stale)} stale item(s) pending reconfirmation")
    return len(stale)
