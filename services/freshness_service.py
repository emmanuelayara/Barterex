"""30-day marketplace freshness reconfirmation for listed items."""
import secrets
from datetime import datetime, timedelta

from app import db
from models import Item, Notification
from logger_config import setup_logger

logger = setup_logger(__name__)

FRESHNESS_WINDOW_DAYS = 30
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
        db.session.add(Notification(
            user_id=item.user_id,
            message=(
                f"'{item.name}' was removed from the marketplace because its 30-day "
                "freshness check is due. Submit a recent photo from My Items to relist it."
            ),
            notification_type='listing',
            category='alert',
            action_url='/user-items',
            priority='normal',
        ))

    if stale:
        db.session.commit()
        logger.info(f"Deactivated {len(stale)} stale item(s) pending reconfirmation")
    return len(stale)
