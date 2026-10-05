"""
Reservation service: lets a user spend PROVISIONAL credits (granted at upload
time for an accepted AI valuation - see valuator_client.py / routes/items.py
upload_item) to put a temporary hold on a marketplace item, while they bring
their own uploaded item in for physical verification. Once that verification
converts their provisional credits into real ones (see routes/admin.py
approve_item), the reservation can be completed into an actual purchase -
see complete_reservation() below.
"""
from datetime import datetime, timedelta

from app import db
from models import Reservation
from logger_config import setup_logger

logger = setup_logger(__name__)

RESERVATION_HOLD_HOURS = 72


def _release_hold(reservation, new_status):
    """Refunds the provisional credits and clears the item's reservation fields."""
    user = reservation.user
    if user:
        user.provisional_credits = (user.provisional_credits or 0) + reservation.provisional_credits_used
    item = reservation.item
    if item and item.reserved_by_id == reservation.user_id:
        item.reserved_by_id = None
        item.reserved_at = None
        item.reservation_expires_at = None
        item.is_available = True
    reservation.status = new_status
    if new_status == 'cancelled':
        reservation.cancelled_at = datetime.utcnow()


def release_expired_reservations(item_id=None):
    """
    Finds reservations whose hold has expired, refunds the provisional credits,
    and re-lists the item. Cheap/indexed - safe to call before showing
    marketplace/item pages or reservation lists so stale holds never linger.
    Returns the number of reservations released.
    """
    query = Reservation.query.filter(
        Reservation.status == 'active',
        Reservation.expires_at < datetime.utcnow(),
    )
    if item_id is not None:
        query = query.filter(Reservation.item_id == item_id)

    expired = query.all()
    for reservation in expired:
        _release_hold(reservation, new_status='expired')

    if expired:
        db.session.commit()
        logger.info(f"Released {len(expired)} expired reservation(s)")
    return len(expired)


def get_active_reservation(item):
    """The current active (non-expired) reservation on an item, or None."""
    release_expired_reservations(item_id=item.id)
    return Reservation.query.filter_by(item_id=item.id, status='active').first()


def create_reservation(user, item):
    """
    Attempts to reserve `item` for `user` using provisional credits.
    Returns (reservation_or_None, error_message_or_None).
    """
    release_expired_reservations(item_id=item.id)

    if item.user_id == user.id:
        return None, "You can't reserve your own item."
    if not item.is_approved or not item.is_available:
        return None, "This item is no longer available."
    if not item.value:
        return None, "This item doesn't have a price set yet."
    if item.reserved_by_id:
        return None, "This item is already reserved by another buyer."
    if (user.provisional_credits or 0) < item.value:
        return None, "You don't have enough provisional credits to reserve this item."

    expires_at = datetime.utcnow() + timedelta(hours=RESERVATION_HOLD_HOURS)
    reservation = Reservation(
        user_id=user.id,
        item_id=item.id,
        provisional_credits_used=int(round(item.value)),
        status='active',
        expires_at=expires_at,
    )
    user.provisional_credits = (user.provisional_credits or 0) - reservation.provisional_credits_used
    item.reserved_by_id = user.id
    item.reserved_at = datetime.utcnow()
    item.reservation_expires_at = expires_at
    item.is_available = False

    db.session.add(reservation)
    db.session.commit()
    logger.info(f"Item reserved - User: {user.username}, Item: {item.id}, Credits held: {reservation.provisional_credits_used}")
    return reservation, None


def cancel_reservation(reservation, user):
    """User-initiated cancellation of their own active reservation."""
    if reservation.user_id != user.id:
        return False, "You can only cancel your own reservations."
    if reservation.status != 'active':
        return False, "This reservation is no longer active."

    _release_hold(reservation, new_status='cancelled')
    db.session.commit()
    logger.info(f"Reservation cancelled - User: {user.username}, Item: {reservation.item_id}")
    return True, None


def complete_reservation(reservation, user):
    """
    Finalizes an active reservation into a real purchase. Only possible once
    the buyer has enough REAL credits to cover the hold - which happens when
    an admin physically verifies one of their uploaded items and converts its
    provisional credits into real ones (see routes/admin.py approve_item).
    The provisional hold itself was already removed from the spendable pool
    at reservation time, so only real credits move here.
    Returns (ok: bool, error_message_or_None).
    """
    from models import Trade, Notification
    from trading_points import award_points_for_purchase, create_level_up_notification

    if reservation.user_id != user.id:
        return False, "You can only complete your own reservations."
    if reservation.status != 'active':
        return False, "This reservation is no longer active."
    if reservation.expires_at < datetime.utcnow():
        return False, "This reservation has expired."

    item = reservation.item
    if not item:
        return False, "This item no longer exists."

    amount = reservation.provisional_credits_used
    if (user.credits or 0) < amount:
        return False, ("You don't have enough real credits yet. This unlocks once an admin "
                        "verifies your uploaded item in person and approves it.")

    seller_id = item.user_id

    user.credits -= amount
    item.user_id = user.id
    item.is_available = False
    item.reserved_by_id = None
    item.reserved_at = None
    item.reservation_expires_at = None

    trade = Trade(
        sender_id=user.id,
        receiver_id=seller_id,
        item_id=item.id,
        item_received_id=item.id,
        status='completed'
    )
    db.session.add(trade)

    reservation.status = 'completed'
    reservation.completed_at = datetime.utcnow()

    db.session.add(Notification(
        user_id=seller_id,
        message=f"💰 Your item '{item.name}' was purchased via a reservation for ᗸ{amount:,} BXC."
    ))

    db.session.commit()

    # Best-effort extras: never let these break an already-committed purchase.
    try:
        level_up_info = award_points_for_purchase(user, f"reservation-{reservation.id}")
        if level_up_info:
            create_level_up_notification(user, level_up_info)
            db.session.commit()
    except Exception as e:
        logger.warning(f"Could not award trading points for reservation {reservation.id}: {e}")

    logger.info(f"Reservation completed - User: {user.username}, Item: {item.id}, Credits spent: {amount}")
    return True, None
