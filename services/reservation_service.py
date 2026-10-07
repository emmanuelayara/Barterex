"""
Reservation / settlement service for "Get with BXC" purchases.

A buyer picks a marketplace item and chooses which of their OWN activated
items (ReservationAsset) to surrender as collateral covering its price - a
single item or a combination (see get_eligible_backing_items/create_reservation).
Both the seller's item and every chosen backing asset must then pass a final,
PARALLEL physical verification within a short settlement window
(RESERVATION_HOLD_HOURS) before anything actually changes hands - see
routes/admin.py's settlement verification queue (verify_seller_item /
verify_backing_asset below). This is all-or-nothing: if either side fails, the
whole purchase is cancelled and nothing is lost except a dent in the
responsible party's reliability_score.

NOTE: surrendered backing assets currently transfer directly to the seller
(simple swap-completion). The business model's full multi-hop "clearing layer"
(a surrendered item going to a different, unrelated buyer C) is not built yet.
"""
from datetime import datetime, timedelta

from app import db
from models import Reservation, ReservationAsset, Item, Trade, Notification
from logger_config import setup_logger

logger = setup_logger(__name__)

RESERVATION_HOLD_HOURS = 72
RELIABILITY_PENALTY = 10
RELIABILITY_BONUS = 2
MAX_RELIABILITY = 100


def get_eligible_backing_items(user):
    """The user's own activated items that are currently free to offer as collateral."""
    return Item.query.filter(
        Item.user_id == user.id,
        Item.status == 'approved',
        Item.locked_for_reservation_id.is_(None),
        Item.reserved_by_id.is_(None),
    ).all()


def _adjust_reliability(user, delta):
    if not user:
        return
    current = user.reliability_score if user.reliability_score is not None else 100
    user.reliability_score = max(0, min(MAX_RELIABILITY, current + delta))


def _unlock_backing_asset(asset, relist):
    item = asset.item
    if not item:
        return
    item.locked_for_reservation_id = None
    if relist and asset.verification_status != 'failed':
        item.is_available = True
    else:
        item.is_available = False
        item.status = 'failed_verification'


def _unlock_seller_item(item, relist):
    if not item:
        return
    item.reserved_by_id = None
    item.reserved_at = None
    item.reservation_expires_at = None
    if relist:
        item.is_available = True
    else:
        item.is_available = False
        item.status = 'failed_verification'


def create_reservation(user, item, backing_item_ids):
    """
    Buyer requests to acquire `item`, backing it with a combination of their
    own activated items. Returns (reservation_or_None, error_message_or_None).
    Nothing settles yet - both sides still need to pass final verification.
    """
    release_expired_reservations(item_id=item.id)

    if item.user_id == user.id:
        return None, "You can't acquire your own item."
    if not item.is_approved or not item.is_available:
        return None, "This item is no longer available."
    if not item.value:
        return None, "This item doesn't have a price set yet."
    if item.reserved_by_id:
        return None, "This item is already reserved by another buyer."

    backing_item_ids = list(dict.fromkeys(backing_item_ids or []))
    if not backing_item_ids:
        return None, "Please choose at least one of your activated items to back this purchase."

    backing_items = Item.query.filter(
        Item.id.in_(backing_item_ids),
        Item.user_id == user.id,
        Item.status == 'approved',
        Item.locked_for_reservation_id.is_(None),
        Item.reserved_by_id.is_(None),
    ).all()

    if len(backing_items) != len(backing_item_ids):
        return None, "One or more of the items you chose are no longer available to use as collateral."

    total_backing_value = sum(int(round(asset.value or 0)) for asset in backing_items)
    if total_backing_value < item.value:
        return None, (f"Your selected items are only worth ᗸ{total_backing_value:,}, but this item costs "
                       f"ᗸ{item.value:,.0f}. Please select more items.")

    expires_at = datetime.utcnow() + timedelta(hours=RESERVATION_HOLD_HOURS)
    reservation = Reservation(
        user_id=user.id,
        item_id=item.id,
        provisional_credits_used=total_backing_value,
        status='active',
        expires_at=expires_at,
    )
    db.session.add(reservation)
    db.session.flush()  # assigns reservation.id for the asset rows / item locks below

    for asset_item in backing_items:
        db.session.add(ReservationAsset(
            reservation_id=reservation.id,
            item_id=asset_item.id,
            amount=int(round(asset_item.value or 0)),
        ))
        asset_item.locked_for_reservation_id = reservation.id
        asset_item.is_available = False

    user.provisional_credits = (user.provisional_credits or 0) - total_backing_value
    item.reserved_by_id = user.id
    item.reserved_at = datetime.utcnow()
    item.reservation_expires_at = expires_at
    item.is_available = False

    db.session.commit()
    logger.info(f"Reservation created - Buyer: {user.username}, Item: {item.id}, "
                f"Backing items: {backing_item_ids}, Total: {total_backing_value}")
    return reservation, None


def cancel_reservation(reservation, user):
    """Buyer-initiated cancellation, only while nothing has been submitted for verification yet."""
    if reservation.user_id != user.id:
        return False, "You can only cancel your own reservations."
    if reservation.status != 'active':
        return False, "This reservation is no longer active."
    if (reservation.seller_item_verification_status != 'not_submitted'
            or any(a.verification_status != 'not_submitted' for a in reservation.backing_assets)):
        return False, "Verification has already started on this purchase - contact support to cancel it."

    _cancel_reservation(reservation, new_status='cancelled', relist_seller_item=True, relist_assets=True)
    db.session.commit()
    logger.info(f"Reservation cancelled - User: {user.username}, Item: {reservation.item_id}")
    return True, None


def _cancel_reservation(reservation, new_status, relist_seller_item, relist_assets):
    """Shared cleanup for the cancel/expire/failed-verification paths."""
    user = reservation.user
    if user:
        user.provisional_credits = (user.provisional_credits or 0) + reservation.provisional_credits_used

    _unlock_seller_item(reservation.item, relist=relist_seller_item)
    for asset in reservation.backing_assets:
        _unlock_backing_asset(asset, relist=relist_assets)

    reservation.status = new_status
    if new_status == 'cancelled':
        reservation.cancelled_at = datetime.utcnow()


def release_expired_reservations(item_id=None):
    """
    Settlement-window timeout: one or both sides never showed up. All-or-nothing
    cancel, with a reliability hit for whichever side(s) didn't submit in time.
    Cheap/indexed - safe to call on every relevant page load.
    """
    query = Reservation.query.filter(
        Reservation.status == 'active',
        Reservation.expires_at < datetime.utcnow(),
    )
    if item_id is not None:
        query = query.filter(Reservation.item_id == item_id)

    expired = query.all()
    for reservation in expired:
        if reservation.seller_item_verification_status == 'not_submitted':
            _adjust_reliability(reservation.item.user if reservation.item else None, -RELIABILITY_PENALTY)
        for asset in reservation.backing_assets:
            if asset.verification_status == 'not_submitted':
                _adjust_reliability(reservation.user, -RELIABILITY_PENALTY)
        _cancel_reservation(reservation, new_status='expired', relist_seller_item=True, relist_assets=True)

    if expired:
        db.session.commit()
        logger.info(f"Expired {len(expired)} reservation(s) past their settlement window")
    return len(expired)


def get_active_reservation(item):
    """The current active (non-expired) reservation on an item, or None."""
    release_expired_reservations(item_id=item.id)
    return Reservation.query.filter_by(item_id=item.id, status='active').first()


def verify_seller_item(reservation, passed, notes=None):
    """Admin action: records the final (re-)verification outcome for the seller's item."""
    if reservation.status != 'active':
        return False, "This reservation is no longer active."

    reservation.seller_item_verification_status = 'passed' if passed else 'failed'
    reservation.seller_item_verified_at = datetime.utcnow()
    reservation.seller_item_verification_notes = notes
    if not passed:
        _adjust_reliability(reservation.item.user if reservation.item else None, -RELIABILITY_PENALTY)

    db.session.commit()
    _resolve_reservation(reservation)
    return True, None


def verify_backing_asset(asset, passed, notes=None):
    """Admin action: records the final verification outcome for one backing asset."""
    reservation = asset.reservation
    if reservation.status != 'active':
        return False, "This reservation is no longer active."

    asset.verification_status = 'passed' if passed else 'failed'
    asset.verified_at = datetime.utcnow()
    asset.verification_notes = notes
    if not passed:
        _adjust_reliability(reservation.user, -RELIABILITY_PENALTY)

    db.session.commit()
    _resolve_reservation(reservation)
    return True, None


def _resolve_reservation(reservation):
    """
    All-or-nothing check, run after every verification event. Settles the
    purchase once everything has passed, or cancels it the moment anything
    makes success impossible.
    """
    if reservation.status != 'active':
        return

    assets = reservation.backing_assets
    passed_total = sum(a.amount for a in assets if a.verification_status == 'passed')
    any_failed = any(a.verification_status == 'failed' for a in assets)
    all_assets_done = all(a.verification_status in ('passed', 'failed') for a in assets)
    seller_status = reservation.seller_item_verification_status
    item_value = (reservation.item.value if reservation.item else 0) or 0

    if seller_status == 'failed':
        _cancel_reservation(reservation, new_status='cancelled', relist_seller_item=False, relist_assets=True)
        db.session.add(Notification(
            user_id=reservation.user_id,
            message="⚠️ The item you tried to acquire failed final verification. Your collateral items "
                    "have been released back to you and your provisional credits are untouched."
        ))
        db.session.commit()
        logger.info(f"Reservation {reservation.id} cancelled - seller item failed verification")
        return

    if any_failed and passed_total < item_value:
        _cancel_reservation(reservation, new_status='cancelled', relist_seller_item=True, relist_assets=True)
        db.session.add(Notification(
            user_id=reservation.item.user_id if reservation.item else None,
            message="⚠️ The buyer's collateral for your item failed verification. Your item is back on the marketplace."
        ))
        db.session.commit()
        logger.info(f"Reservation {reservation.id} cancelled - backing asset(s) failed verification")
        return

    if seller_status == 'passed' and all_assets_done and not any_failed:
        _settle_reservation(reservation)


def _settle_reservation(reservation):
    """Both sides passed: transfer ownership, convert the seller's provisional credit, award points."""
    from trading_points import award_points_for_purchase, create_level_up_notification

    buyer = reservation.user
    seller_item = reservation.item
    seller = seller_item.user if seller_item else None
    if not buyer or not seller_item or not seller:
        return

    # Transfer the purchased item to the buyer.
    seller_item.user_id = buyer.id
    seller_item.is_available = False
    seller_item.reserved_by_id = None
    seller_item.reserved_at = None
    seller_item.reservation_expires_at = None

    db.session.add(Trade(sender_id=buyer.id, receiver_id=seller.id, item_id=seller_item.id,
                          item_received_id=seller_item.id, status='completed'))

    # Closes the earlier "Activate for Trade" gap: the seller's own provisional credit for
    # this item becomes real now that it has actually left their possession via a verified exchange.
    if seller_item.provisional_credit_amount and not seller_item.provisional_credit_settled:
        amount = int(round(seller_item.provisional_credit_amount))
        seller.provisional_credits = max(0, (seller.provisional_credits or 0) - amount)
        seller.credits = (seller.credits or 0) + amount
        seller_item.provisional_credit_settled = True

    # Transfer each surrendered backing asset to the seller (direct swap-completion; the
    # full multi-hop "clearing layer" to an unrelated third buyer isn't built yet).
    for asset in reservation.backing_assets:
        asset_item = asset.item
        if not asset_item:
            continue
        asset_item.locked_for_reservation_id = None
        asset_item.user_id = seller.id
        asset_item.is_available = False
        db.session.add(Trade(sender_id=buyer.id, receiver_id=seller.id, item_id=asset_item.id,
                              item_received_id=asset_item.id, status='completed'))

    _adjust_reliability(buyer, RELIABILITY_BONUS)
    _adjust_reliability(seller, RELIABILITY_BONUS)

    reservation.status = 'completed'
    reservation.completed_at = datetime.utcnow()

    db.session.add(Notification(user_id=buyer.id, message=f"🎉 Purchase complete! '{seller_item.name}' is now yours."))
    db.session.add(Notification(user_id=seller.id,
                                 message=f"🎉 '{seller_item.name}' has been exchanged! Thanks for trading on Barter Express."))

    db.session.commit()

    try:
        level_up_info = award_points_for_purchase(buyer, f"reservation-{reservation.id}")
        if level_up_info:
            create_level_up_notification(buyer, level_up_info)
            db.session.commit()
    except Exception as e:
        logger.warning(f"Could not award trading points for reservation {reservation.id}: {e}")

    logger.info(f"Reservation {reservation.id} settled - Buyer: {buyer.username}, Item: {seller_item.id}")
