"""30-day marketplace freshness reconfirmation for listed items."""
import secrets
from datetime import datetime, timedelta

from app import db
from models import Item
from logger_config import setup_logger
from services.email_notifications import notify_user

logger = setup_logger(__name__)

FRESHNESS_WINDOW_DAYS = 30
FRESHNESS_WARNING_DAYS = 3  # warn this many days before the listing is pulled
HIGH_VALUE_THRESHOLD = 50000  # BXC - items worth at least this need a visible code on reconfirmation


def generate_reconfirmation_code() -> str:
    return secrets.token_hex(3).upper()  # e.g. "A1B2C3"


def deactivate_stale_items():
    """
    Pulls listed items off the marketplace once their freshness window has
    lapsed. Safe to rerun from the maintenance scheduler or a request path.
    Returns the number of items deactivated.
    """
    cutoff = datetime.utcnow() - timedelta(days=FRESHNESS_WINDOW_DAYS)
    stale = Item.query.filter(
        Item.status == 'approved',
        Item.is_available == True,
        Item.owner_type == 'user',
        Item.user_id.isnot(None),
        db.or_(
            Item.last_reconfirmed_at < cutoff,
            db.and_(Item.last_reconfirmed_at.is_(None), Item.activated_at < cutoff),
        ),
    ).order_by(Item.id.asc()).with_for_update().all()

    for item in stale:
        item.is_available = False
        item.status = 'reconfirmation_required'
        if item.value and item.value >= HIGH_VALUE_THRESHOLD and not item.reconfirmation_code:
            item.reconfirmation_code = generate_reconfirmation_code()
        notify_user(
            item.user_id,
            (
                f"'{item.name}' was removed from the marketplace because its 30-day "
                "freshness check is due. Submit a recent photo from My Items to relist it."
            ),
            subject=f"'{item.name}' was removed from the marketplace",
            cta_endpoint='user.user_items',
            cta_label='Reconfirm My Item',
            notification_type='listing',
            category='alert',
        )

    if stale:
        db.session.commit()
        logger.info(f"Deactivated {len(stale)} stale item(s) pending reconfirmation")
    return len(stale)


def warn_items_nearing_freshness_deadline():
    """Warn owners a few days before a listing is pulled. Once per freshness cycle."""
    now = datetime.utcnow()
    window_start = now - timedelta(days=FRESHNESS_WINDOW_DAYS)
    warning_start = now - timedelta(days=FRESHNESS_WINDOW_DAYS - FRESHNESS_WARNING_DAYS)
    last_confirmed = db.func.coalesce(Item.last_reconfirmed_at, Item.activated_at)
    due_soon = Item.query.filter(
        Item.status == 'approved',
        Item.is_available == True,
        Item.owner_type == 'user',
        Item.user_id.isnot(None),
        last_confirmed > window_start,
        last_confirmed <= warning_start,
        db.or_(
            Item.freshness_warning_sent_at.is_(None),
            Item.freshness_warning_sent_at < last_confirmed,
        ),
    ).all()
    for item in due_soon:
        reference = item.last_reconfirmed_at or item.activated_at
        deadline = reference + timedelta(days=FRESHNESS_WINDOW_DAYS)
        item.freshness_warning_sent_at = now
        notify_user(
            item.user_id,
            (
                f"'{item.name}' will be removed from the marketplace on {deadline:%d %b %Y} unless you "
                "reconfirm it. Submit a recent photo from My Items to keep it listed."
            ),
            subject=f"Reconfirm '{item.name}' to keep it listed",
            cta_endpoint='user.user_items',
            cta_label='Reconfirm My Item',
            notification_type='listing',
            category='alert',
        )
    if due_soon:
        db.session.commit()
        logger.info(f"Warned {len(due_soon)} item owner(s) about the upcoming freshness deadline")
    return len(due_soon)
