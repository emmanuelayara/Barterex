"""
Reservation / settlement service for "Get with BXC" purchases.

A buyer picks a marketplace item and chooses which of their OWN activated
items (ReservationAsset) to surrender as collateral covering its price - a
single item or a combination (see get_eligible_backing_items/create_reservation).
The seller's item and every chosen backing asset must pass final physical
verification within the settlement window (RESERVATION_HOLD_HOURS). New
reservations transfer passing backing assets only after the seller's item
passes. If the seller's item fails, the buyer gets 24 hours to reconfirm before
any passing backing asset transfers to Barter Express.

Verified backing assets are acquired by Barter Express as soon as the owner
passes physical verification and recorded in clearing inventory. Reservation
success only determines whether the requested marketplace item also transfers.
"""
from datetime import datetime, timedelta

from app import db
from models import (
    ClearingInventoryItem,
    CreditTransaction,
    Item,
    Notification,
    Order,
    OrderItem,
    Reservation,
    ReservationAsset,
    ReservationCreditEntry,
    ReservationRevaluation,
    Trade,
    User,
)
from logger_config import setup_logger

logger = setup_logger(__name__)

RESERVATION_HOLD_HOURS = 72
TITLE_TRANSFER_CONSENT_HOURS = 24
REVALUATION_DECISION_HOURS = 24
LEGACY_BACKING_ASSET_CONSENT_VERSION = 'company_inventory_v1'
BACKING_ASSET_CONSENT_VERSION = 'company_inventory_v2'
RELIABILITY_PENALTY = 10
RELIABILITY_BONUS = 2
MAX_RELIABILITY = 100


def _reject_reservation(message):
    db.session.rollback()
    return None, message


def _reject_transition(message):
    db.session.rollback()
    return False, message


def get_eligible_backing_items(user):
    """The user's own activated items that are currently free to offer as collateral."""
    return Item.query.filter(
        Item.user_id == user.id,
        Item.status == 'approved',
        Item.is_available.is_(True),
        Item.provisional_credit_amount.is_not(None),
        Item.provisional_credit_settled.is_(False),
        Item.locked_for_reservation_id.is_(None),
        Item.reserved_by_id.is_(None),
    ).all()


def _adjust_reliability(user, delta):
    if not user:
        return
    current = user.reliability_score if user.reliability_score is not None else 100
    user.reliability_score = max(0, min(MAX_RELIABILITY, current + delta))


def _change_reservation_balance(user, reservation, balance_type, delta, entry_type, item=None):
    """Apply and audit one reservation-related balance movement."""
    field = 'provisional_credits' if balance_type == 'provisional' else 'credits'
    before = int(getattr(user, field) or 0)
    after = before + delta
    if after < 0:
        raise ValueError(
            f"Cannot {entry_type} reservation {reservation.id}: "
            f"{balance_type} BXC balance would become negative."
        )

    setattr(user, field, after)
    db.session.add(ReservationCreditEntry(
        reservation_id=reservation.id,
        user_id=user.id,
        item_id=item.id if item else None,
        balance_type=balance_type,
        entry_type=entry_type,
        amount=delta,
        balance_before=before,
        balance_after=after,
    ))
    return before, after


def _change_held_spendable(reservation, delta, entry_type, item=None):
    """Apply and audit spendable BXC held for this reservation."""
    before = int(reservation.spendable_credits_held or 0)
    after = before + delta
    if after < 0:
        raise ValueError(
            f"Cannot {entry_type} reservation {reservation.id}: "
            "held spendable BXC balance would become negative."
        )

    reservation.spendable_credits_held = after
    db.session.add(ReservationCreditEntry(
        reservation_id=reservation.id,
        user_id=reservation.user_id,
        item_id=item.id if item else None,
        balance_type='spendable_held',
        entry_type=entry_type,
        amount=delta,
        balance_before=before,
        balance_after=after,
    ))
    return before, after


def _create_revaluation(reservation, item, original_value, proposed_value, admin_id, asset=None):
    if proposed_value is None:
        return None
    try:
        normalized_value = int(proposed_value)
    except (TypeError, ValueError):
        raise ValueError("The revised BXC value must be a whole number.")
    if normalized_value <= 0:
        raise ValueError("The revised BXC value must be greater than zero.")
    original_value = int(original_value)
    if normalized_value == original_value:
        return None

    now = datetime.utcnow()
    deadline = now + timedelta(hours=REVALUATION_DECISION_HOURS)
    proposal = ReservationRevaluation(
        reservation_id=reservation.id,
        item_id=item.id,
        reservation_asset_id=asset.id if asset else None,
        original_value=original_value,
        proposed_value=normalized_value,
        proposed_by_admin_id=admin_id,
        status='pending',
        buyer_decision='pending',
        seller_decision='pending',
        proposed_at=now,
        decision_expires_at=deadline,
    )
    db.session.add(proposal)
    if reservation.expires_at < deadline:
        reservation.expires_at = deadline
        if reservation.item:
            reservation.item.reservation_expires_at = deadline

    item_description = f"'{item.name}'"
    for participant_id, role in (
        (reservation.user_id, 'buyer'),
        (item.user_id, 'seller'),
    ):
        db.session.add(Notification(
            user_id=participant_id,
            message=(
                f"A revised valuation of ᗸ{normalized_value:,} was proposed for "
                f"{item_description} in reservation {reservation.id}. Both parties must "
                f"respond by {deadline:%b %d, %Y %I:%M %p}."
            ),
        ))
    logger.info(
        f"Reservation {reservation.id} revaluation proposed for item {item.id}: "
        f"{original_value} -> {normalized_value}"
    )
    return proposal


def _exclude_backing_asset(reservation, asset, proposal=None, resolution_status='declined'):
    if asset.excluded_from_settlement:
        return
    item = asset.item
    if not item or item.owner_type != 'user' or item.user_id != reservation.user_id:
        raise ValueError(
            f"Reservation asset {asset.id} cannot be released because it is no longer buyer-owned."
        )
    held_amount = int(asset.reserved_provisional_amount or 0)
    if held_amount:
        if int(reservation.provisional_credits_used or 0) < held_amount:
            raise ValueError(
                f"Reservation {reservation.id} provisional backing total is inconsistent."
            )
        _change_reservation_balance(
            reservation.user,
            reservation,
            'provisional',
            held_amount,
            'release',
            item=item,
        )
        reservation.provisional_credits_used -= held_amount
    asset.excluded_from_settlement = True
    _unlock_backing_asset(asset, relist=True)
    if proposal:
        proposal.status = resolution_status
        proposal.resolved_at = datetime.utcnow()
    db.session.add(Notification(
        user_id=reservation.user_id,
        message=(
            f"'{item.name}' was not accepted at its revised value. It remains yours and "
            "contributes no BXC to this reservation; you can cover any resulting shortfall "
            "with another eligible item or spendable BXC."
        ),
    ))


def _has_pending_revaluations(reservation):
    return any(proposal.status == 'pending' for proposal in reservation.revaluations)


def get_reservation_shortfall(reservation):
    """Return uncovered purchase value, counting active planned backing assets and held BXC."""
    if reservation.status != 'active':
        return 0
    backing_value = sum(
        int(asset.amount or 0)
        for asset in reservation.backing_assets
        if not asset.excluded_from_settlement and asset.verification_status != 'failed'
    )
    covered = backing_value + int(reservation.spendable_funding_held or 0)
    return max(0, int(reservation.purchase_value or 0) - covered)


def add_reservation_backing_assets(reservation, user, item_ids, consent_confirmed):
    """Add and hold eligible user items to cover an active reservation shortfall."""
    release_expired_reservations(item_id=reservation.item_id)
    reservation = _lock_reservation_for_update(reservation.id)
    if not reservation:
        return False, "This reservation no longer exists."
    if reservation.user_id != user.id:
        return _reject_transition("You can only add items to your own reservation.")
    if reservation.status != 'active':
        return _reject_transition("This reservation is no longer active.")
    if _has_pending_revaluations(reservation):
        return _reject_transition("Resolve the pending revised valuations before adding backing items.")
    if get_reservation_shortfall(reservation) <= 0:
        return _reject_transition("This reservation does not currently need additional coverage.")
    if not consent_confirmed:
        return _reject_transition("Confirm that you consent to transfer title to the added backing items.")

    item_ids = list(dict.fromkeys(item_ids or []))
    if not item_ids:
        return _reject_transition("Choose at least one eligible item.")

    items = Item.query.filter(Item.id.in_(item_ids)).order_by(Item.id).with_for_update().all()
    if len(items) != len(item_ids):
        return _reject_transition("One or more selected items are no longer available.")
    existing_item_ids = {asset.item_id for asset in reservation.backing_assets}
    if any(
        item.id in existing_item_ids
        or item.user_id != user.id
        or item.owner_type != 'user'
        or item.status != 'approved'
        or not item.is_available
        or item.provisional_credit_amount is None
        or item.provisional_credit_settled
        or item.locked_for_reservation_id is not None
        or item.reserved_by_id is not None
        for item in items
    ):
        return _reject_transition("One or more selected items are no longer eligible backing items.")

    amounts = {item.id: int(round(item.value or 0)) for item in items}
    if any(amount <= 0 for amount in amounts.values()):
        return _reject_transition("Every selected item must have a positive BXC value.")
    total_amount = sum(amounts.values())
    if (reservation.user.provisional_credits or 0) < total_amount:
        return _reject_transition(
            "Your available provisional BXC is not enough to hold the selected items."
        )

    try:
        now = datetime.utcnow()
        reservation.backing_asset_consent_at = now
        reservation.backing_asset_consent_version = BACKING_ASSET_CONSENT_VERSION
        for item in items:
            amount = amounts[item.id]
            asset = ReservationAsset(
                reservation_id=reservation.id,
                item_id=item.id,
                amount=amount,
                reserved_provisional_amount=amount,
                consent_confirmed_at=now,
            )
            db.session.add(asset)
            db.session.flush()
            item.locked_for_reservation_id = reservation.id
            item.is_available = False
            reservation.provisional_credits_used += amount
            _change_reservation_balance(
                reservation.user,
                reservation,
                'provisional',
                -amount,
                'hold',
                item=item,
            )
        if get_reservation_shortfall(reservation) == 0:
            reservation.revaluation_shortfall_expires_at = None
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return True, None


def cover_reservation_shortfall(reservation, user, amount):
    """Move the buyer's available spendable BXC into the reservation hold."""
    release_expired_reservations(item_id=reservation.item_id)
    reservation = _lock_reservation_for_update(reservation.id)
    if not reservation:
        return False, "This reservation no longer exists."
    if reservation.user_id != user.id:
        return _reject_transition("You can only fund your own reservation.")
    if reservation.status != 'active':
        return _reject_transition("This reservation is no longer active.")
    if _has_pending_revaluations(reservation):
        return _reject_transition("Resolve the pending revised valuations before funding the shortfall.")
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return _reject_transition("Enter a whole-number BXC amount.")
    shortfall = get_reservation_shortfall(reservation)
    if amount <= 0 or amount > shortfall:
        return _reject_transition(
            f"Enter an amount from 1 to ᗸ{shortfall:,}, the current reservation shortfall."
        )
    buyer = reservation.user
    if int(buyer.credits or 0) < amount:
        return _reject_transition(
            "Your available spendable BXC is insufficient. Fund your account or add eligible backing items."
        )

    try:
        _change_reservation_balance(
            buyer, reservation, 'spendable', -amount, 'hold', item=reservation.item
        )
        _change_held_spendable(reservation, amount, 'hold', item=reservation.item)
        reservation.spendable_funding_held = (
            int(reservation.spendable_funding_held or 0) + amount
        )
        _resolve_reservation(reservation)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return True, None


def respond_to_reservation_revaluation(revaluation_id, user, accepted):
    proposal_hint = db.session.get(ReservationRevaluation, revaluation_id)
    if not proposal_hint:
        return False, "This revaluation proposal no longer exists."
    release_expired_reservations(
        item_id=proposal_hint.reservation.item_id if proposal_hint.reservation else None
    )
    reservation = _lock_reservation_for_update(proposal_hint.reservation_id)
    if not reservation:
        return _reject_transition("This reservation no longer exists.")
    proposal = ReservationRevaluation.query.filter_by(
        id=revaluation_id,
        reservation_id=reservation.id,
    ).with_for_update().first()
    if not proposal or proposal.status != 'pending':
        return _reject_transition("This revaluation proposal is no longer awaiting a decision.")
    if reservation.status != 'active':
        return _reject_transition("This reservation is no longer active.")
    if proposal.decision_expires_at <= datetime.utcnow():
        return _reject_transition("The revaluation response window has expired.")

    is_buyer = user.id == reservation.user_id
    is_seller = reservation.item and user.id == reservation.item.user_id
    if not is_buyer and not is_seller:
        return _reject_transition("You are not a party to this reservation.")
    decision_field = 'buyer_decision' if is_buyer else 'seller_decision'
    timestamp_field = 'buyer_decision_at' if is_buyer else 'seller_decision_at'
    if getattr(proposal, decision_field) != 'pending':
        return _reject_transition("You have already responded to this revaluation.")

    try:
        setattr(proposal, decision_field, 'accepted' if accepted else 'declined')
        setattr(proposal, timestamp_field, datetime.utcnow())
        if not accepted:
            _finish_revaluation_decision(reservation, proposal, accepted=False)
        elif proposal.buyer_decision == 'accepted' and proposal.seller_decision == 'accepted':
            _finish_revaluation_decision(reservation, proposal, accepted=True)
        else:
            other_id = (
                reservation.item.user_id if is_buyer and reservation.item
                else reservation.user_id
            )
            db.session.add(Notification(
                user_id=other_id,
                message=(
                    f"The other party accepted the revised valuation for '{proposal.item.name}'. "
                    f"Please respond by {proposal.decision_expires_at:%b %d, %Y %I:%M %p}."
                ),
            ))
        settled = _resolve_reservation(reservation)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    if settled:
        _award_reservation_points(reservation)
    return True, None


def _finish_revaluation_decision(reservation, proposal, accepted):
    proposal.resolved_at = datetime.utcnow()
    if not accepted:
        proposal.status = 'declined'
        if proposal.reservation_asset_id:
            asset = next(
                (
                    candidate for candidate in reservation.backing_assets
                    if candidate.id == proposal.reservation_asset_id
                ),
                None,
            )
            if not asset:
                raise ValueError(f"Revaluation {proposal.id} has no reservation backing item.")
            _exclude_backing_asset(reservation, asset, proposal)
        else:
            reservation.seller_item_revaluation_failed = True
        return

    if proposal.reservation_asset_id:
        asset = next(
            (
                candidate for candidate in reservation.backing_assets
                if candidate.id == proposal.reservation_asset_id
            ),
            None,
        )
        if not asset or not asset.item or asset.excluded_from_settlement:
            raise ValueError(f"Revaluation {proposal.id} has no eligible reservation backing item.")
        if ClearingInventoryItem.query.filter_by(reservation_asset_id=asset.id).first():
            raise ValueError(
                f"Revaluation {proposal.id} cannot change a backing item already acquired by Barter Express."
            )
        asset.amount = proposal.proposed_value
        asset.item.value = proposal.proposed_value
    else:
        item = reservation.item
        seller = item.user if item else None
        if not item or not seller or item.id != proposal.item_id:
            raise ValueError(f"Revaluation {proposal.id} has no seller-owned item.")
        current_grant = int(round(item.provisional_credit_amount or 0))
        grant_delta = proposal.proposed_value - current_grant
        if grant_delta < 0 and int(seller.provisional_credits or 0) < abs(grant_delta):
            proposal.status = 'declined'
            reservation.seller_item_revaluation_failed = True
            db.session.add(Notification(
                user_id=reservation.user_id,
                message=(
                    "The seller cannot support the revised provisional-credit adjustment. "
                    "The reservation will be cancelled and you will be asked again before any "
                    "passed backing item transfers."
                ),
            ))
            return
        if grant_delta:
            _change_reservation_balance(
                seller,
                reservation,
                'provisional',
                grant_delta,
                'revaluation',
                item=item,
            )
        item.value = proposal.proposed_value
        item.provisional_credit_amount = proposal.proposed_value
        reservation.purchase_value = proposal.proposed_value

    proposal.status = 'applied'
    db.session.add(Notification(
        user_id=reservation.user_id,
        message=(
            f"The revised valuation of ᗸ{proposal.proposed_value:,} for "
            f"'{proposal.item.name}' was accepted by both parties."
        ),
    ))
    if reservation.item and reservation.item.user_id != reservation.user_id:
        db.session.add(Notification(
            user_id=reservation.item.user_id,
            message=(
                f"The revised valuation of ᗸ{proposal.proposed_value:,} for "
                f"'{proposal.item.name}' was accepted by both parties."
            ),
        ))


def _acquire_backing_asset(reservation, asset, hold_for_purchase=True):
    """Move a consented, verified backing asset into company-owned inventory."""
    item = asset.item
    buyer = reservation.user
    if asset.excluded_from_settlement:
        raise ValueError(f"Reservation asset {asset.id} was excluded from settlement.")
    if not item or not buyer or item.user_id != buyer.id or item.owner_type != 'user':
        raise ValueError(f"Reservation asset {asset.id} no longer belongs to its consenting owner.")
    if (
        not asset.consent_confirmed_at
        or not reservation.backing_asset_consent_at
        or reservation.backing_asset_consent_version not in (
            LEGACY_BACKING_ASSET_CONSENT_VERSION,
            BACKING_ASSET_CONSENT_VERSION,
        )
    ):
        raise ValueError(f"Reservation asset {asset.id} has no recorded surrender consent.")
    if ClearingInventoryItem.query.filter_by(item_id=item.id).first():
        raise ValueError(f"Item {item.id} is already recorded in clearing inventory.")

    amount = int(asset.amount)
    purchase_value = int(reservation.purchase_value or 0)
    held_for_purchase = min(
        amount,
        max(0, purchase_value - int(reservation.spendable_credits_held or 0)),
    ) if hold_for_purchase else 0
    available_credit = amount - held_for_purchase
    source_user_id = item.user_id

    item.user_id = None
    item.owner_type = 'barterex'
    item.status = 'clearing_inventory'
    item.is_approved = False
    item.is_available = False
    item.locked_for_reservation_id = None
    item.provisional_credit_settled = True
    db.session.add(ClearingInventoryItem(
        item_id=item.id,
        reservation_id=reservation.id,
        reservation_asset_id=asset.id,
        source_user_id=source_user_id,
        acquisition_value=amount,
        status='held_for_resale',
    ))

    if available_credit:
        before, after = _change_reservation_balance(
            buyer, reservation, 'spendable', available_credit, 'settlement', item=item
        )
        db.session.add(CreditTransaction(
            user_id=buyer.id,
            amount=available_credit,
            transaction_type='reservation_backing_settlement',
            description=f'Spendable BXC for verified item surrendered in reservation {reservation.id}',
            reason='reservation_backing_settlement',
            balance_before=before,
            balance_after=after,
            related_item_id=item.id,
        ))
    if held_for_purchase:
        _change_held_spendable(reservation, held_for_purchase, 'hold', item=item)

    db.session.add(Notification(
        user_id=buyer.id,
        message=(
            f"'{item.name}' passed physical verification and is now Barter Express property. "
            f"ᗸ{available_credit:,} was added to your available spendable BXC; "
            f"ᗸ{held_for_purchase:,} is held for your reservation."
        ),
    ))


def _lock_reservation_for_update(reservation_id):
    """Lock users, reservation and its items in a consistent order."""
    hint = db.session.get(Reservation, reservation_id)
    if not hint:
        return None

    seller_item_hint = db.session.get(Item, hint.item_id)
    user_ids = {hint.user_id}
    if seller_item_hint:
        user_ids.add(seller_item_hint.user_id)
    locked_users = User.query.filter(User.id.in_(user_ids)).order_by(
        User.id
    ).with_for_update().populate_existing().all()
    users_by_id = {user.id: user for user in locked_users}

    reservation = Reservation.query.filter_by(id=reservation_id).with_for_update().populate_existing().first()
    if not reservation:
        return None

    db.session.expire(reservation, ['backing_assets', 'item', 'user'])
    assets = ReservationAsset.query.filter_by(
        reservation_id=reservation.id
    ).order_by(ReservationAsset.id).all()
    item_ids = {reservation.item_id}
    item_ids.update(asset.item_id for asset in assets)
    locked_items = Item.query.filter(Item.id.in_(item_ids)).order_by(
        Item.id
    ).with_for_update().populate_existing().all()
    items_by_id = {item.id: item for item in locked_items}

    reservation.user = users_by_id.get(reservation.user_id)
    reservation.item = items_by_id.get(reservation.item_id)
    for asset in assets:
        asset.item = items_by_id.get(asset.item_id)
    reservation.backing_assets = assets
    return reservation


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


def _update_backing_return_status(reservation, statuses=None):
    if (
        reservation.delivery_method != 'home delivery'
        or not reservation.backing_assets
    ):
        reservation.backing_return_status = 'not_required'
        return
    return_required = any(
        asset.verification_status in (statuses or {'passed', 'failed'})
        and not ClearingInventoryItem.query.filter_by(
            reservation_asset_id=asset.id
        ).first()
        for asset in reservation.backing_assets
    )
    reservation.backing_return_status = 'return_required' if return_required else 'not_required'


def create_reservation(
    user,
    item,
    backing_item_ids,
    consent_confirmed=False,
    funding_mode='item_backed',
    delivery_method='pickup',
    delivery_address=None,
    pickup_station_id=None,
):
    """
    Buyer reserves `item` with spendable BXC or their activated backing items.
    Returns (reservation_or_None, error_message_or_None). Purchase settlement
    waits for the required physical verification.
    """
    release_expired_reservations(item_id=item.id)
    user = User.query.filter_by(id=user.id).with_for_update().populate_existing().first()
    if not user:
        return _reject_reservation("This item or account is no longer available.")

    if funding_mode not in ('item_backed', 'spendable'):
        return _reject_reservation("Choose a valid BXC funding method.")
    if delivery_method not in ('pickup', 'home delivery'):
        return _reject_reservation("Choose a valid delivery method.")
    if delivery_method == 'home delivery':
        delivery_address = (delivery_address or '').strip()
        if not delivery_address:
            return _reject_reservation("Enter the home delivery address.")
        if len(delivery_address) > 200:
            return _reject_reservation("The home delivery address must be 200 characters or fewer.")
        pickup_station_id = None
    else:
        delivery_address = None

    backing_item_ids = list(dict.fromkeys(backing_item_ids or []))
    locked_items = Item.query.filter(
        Item.id.in_([item.id, *backing_item_ids])
    ).order_by(Item.id).with_for_update().populate_existing().all()
    items_by_id = {locked_item.id: locked_item for locked_item in locked_items}
    item = items_by_id.get(item.id)
    if not item:
        return _reject_reservation("This item or account is no longer available.")

    if funding_mode == 'item_backed' and not consent_confirmed:
        return _reject_reservation(
            "Confirm the title-transfer terms for your backing items."
        )
    if item.owner_type != 'user' or item.user_id is None:
        return _reject_reservation("This item is not owned by an eligible user.")
    if item.user_id == user.id:
        return _reject_reservation("You can't acquire your own item.")
    if not item.is_approved or not item.is_available:
        return _reject_reservation("This item is no longer available.")
    if not item.value:
        return _reject_reservation("This item doesn't have a price set yet.")
    if item.reserved_by_id:
        return _reject_reservation("This item is already reserved by another buyer.")

    backing_items = []
    total_backing_value = 0
    purchase_amount = int(round(item.value))
    if funding_mode == 'item_backed':
        if not backing_item_ids:
            return _reject_reservation("Please choose at least one of your activated items to back this purchase.")

        backing_items = [items_by_id[item_id] for item_id in backing_item_ids if item_id in items_by_id]
        backing_items = [
            backing_item for backing_item in backing_items
            if backing_item.user_id == user.id
            and backing_item.owner_type == 'user'
            and backing_item.status == 'approved'
            and backing_item.is_available
            and backing_item.provisional_credit_amount is not None
            and not backing_item.provisional_credit_settled
            and backing_item.locked_for_reservation_id is None
            and backing_item.reserved_by_id is None
        ]

        if len(backing_items) != len(backing_item_ids):
            return _reject_reservation(
                "One or more of the items you chose are no longer available to use as collateral."
            )

        total_backing_value = sum(int(round(asset.value or 0)) for asset in backing_items)
        if total_backing_value < item.value:
            return _reject_reservation(
                f"Your selected items are only worth ᗸ{total_backing_value:,}, but this item costs "
                f"ᗸ{item.value:,.0f}. Please select more items."
            )
        if total_backing_value > (user.provisional_credits or 0):
            return _reject_reservation(
                "Your available provisional BXC is not enough to reserve these items. "
                "Please activate more items or choose less valuable backing items."
            )
    else:
        if backing_item_ids:
            return _reject_reservation("Spendable BXC reservations cannot include backing items.")
        if (user.credits or 0) < purchase_amount:
            return _reject_reservation("Your available spendable BXC is not enough for this purchase.")

    expires_at = datetime.utcnow() + timedelta(hours=RESERVATION_HOLD_HOURS)
    try:
        reservation = Reservation(
            user_id=user.id,
            item_id=item.id,
            provisional_credits_used=total_backing_value,
            purchase_value=purchase_amount,
            spendable_credits_held=0,
            spendable_funding_held=(
                purchase_amount if funding_mode == 'spendable' else 0
            ),
            clearing_mode='company_inventory',
            funding_mode=funding_mode,
            delivery_method=delivery_method,
            delivery_address=delivery_address,
            pickup_station_id=pickup_station_id,
            delivery_fee_status='quote_pending' if delivery_method == 'home delivery' else 'not_required',
            backing_asset_consent_at=(
                datetime.utcnow() if funding_mode == 'item_backed' else None
            ),
            backing_asset_consent_version=(
                BACKING_ASSET_CONSENT_VERSION if funding_mode == 'item_backed' else None
            ),
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
                reserved_provisional_amount=int(round(asset_item.value or 0)),
                consent_confirmed_at=reservation.backing_asset_consent_at,
            ))
            asset_item.locked_for_reservation_id = reservation.id
            asset_item.is_available = False
            _change_reservation_balance(
                user,
                reservation,
                'provisional',
                -int(round(asset_item.value or 0)),
                'hold',
                item=asset_item,
            )
        if funding_mode == 'spendable':
            _change_reservation_balance(
                user, reservation, 'spendable', -purchase_amount, 'hold', item=item
            )
            _change_held_spendable(
                reservation, purchase_amount, 'hold', item=item
            )
        item.reserved_by_id = user.id
        item.reserved_at = datetime.utcnow()
        item.reservation_expires_at = expires_at
        item.is_available = False
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    logger.info(f"Reservation created - Buyer: {user.username}, Item: {item.id}, "
                f"Backing items: {backing_item_ids}, Total: {total_backing_value}")
    return reservation, None


def cancel_reservation(reservation, user):
    """Buyer-initiated cancellation, only while nothing has been submitted for verification yet."""
    release_expired_reservations(item_id=reservation.item_id)
    reservation = _lock_reservation_for_update(reservation.id)
    if not reservation:
        return False, "This reservation no longer exists."
    if reservation.user_id != user.id:
        return _reject_transition("You can only cancel your own reservations.")
    if reservation.status != 'active':
        return _reject_transition("This reservation is no longer active.")
    if (reservation.seller_item_verification_status != 'not_submitted'
            or any(a.verification_status != 'not_submitted' for a in reservation.backing_assets)):
        return _reject_transition(
            "Verification has already started on this purchase - contact support to cancel it."
        )

    try:
        _cancel_reservation(reservation, new_status='cancelled', relist_seller_item=True, relist_assets=True)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    logger.info(f"Reservation cancelled - User: {user.username}, Item: {reservation.item_id}")
    return True, None


def _cancel_reservation(reservation, new_status, relist_seller_item, relist_assets):
    """Shared cleanup for the cancel/expire/failed-verification paths."""
    user = reservation.user
    for proposal in reservation.revaluations:
        if proposal.status == 'pending':
            proposal.status = 'cancelled'
            proposal.resolved_at = datetime.utcnow()
    if user:
        if reservation.clearing_mode == 'company_inventory':
            for asset in reservation.backing_assets:
                acquired = ClearingInventoryItem.query.filter_by(
                    reservation_asset_id=asset.id
                ).first()
                if not acquired and not asset.excluded_from_settlement:
                    _change_reservation_balance(
                        user,
                        reservation,
                        'provisional',
                        asset.reserved_provisional_amount,
                        'release',
                        item=asset.item,
                    )
            held = int(reservation.spendable_credits_held or 0)
            if held:
                _change_held_spendable(reservation, -held, 'release')
                before, after = _change_reservation_balance(
                    user, reservation, 'spendable', held, 'release'
                )
                db.session.add(CreditTransaction(
                    user_id=user.id,
                    amount=held,
                    transaction_type='reservation_release',
                    description=f'Released held BXC from failed reservation {reservation.id}',
                    reason='reservation_release',
                    balance_before=before,
                    balance_after=after,
                ))
        else:
            _change_reservation_balance(
                user, reservation, 'provisional', reservation.provisional_credits_used, 'release'
            )

    _unlock_seller_item(reservation.item, relist=relist_seller_item)
    for asset in reservation.backing_assets:
        acquired = (
            reservation.clearing_mode == 'company_inventory'
            and ClearingInventoryItem.query.filter_by(
                reservation_asset_id=asset.id
            ).first()
        )
        if not acquired:
            _unlock_backing_asset(asset, relist=relist_assets)

    _update_backing_return_status(reservation)
    reservation.status = new_status
    if new_status == 'cancelled':
        reservation.cancelled_at = datetime.utcnow()


def release_expired_reservations(item_id=None):
    """
    Settlement-window timeout: one or both sides never showed up. All-or-nothing
    cancel, with a reliability hit for whichever side(s) didn't submit in time.
    Cheap/indexed - safe to call on every relevant page load.
    """
    released_count = 0
    pending_revaluations = ReservationRevaluation.query.filter(
        ReservationRevaluation.status == 'pending',
        ReservationRevaluation.decision_expires_at < datetime.utcnow(),
    )
    if item_id is not None:
        pending_revaluations = pending_revaluations.join(Reservation).filter(
            Reservation.item_id == item_id
        )
    expired_revaluation_ids = [
        revaluation_id
        for (revaluation_id,) in pending_revaluations.with_entities(
            ReservationRevaluation.id
        ).all()
    ]
    for revaluation_id in expired_revaluation_ids:
        proposal_hint = db.session.get(ReservationRevaluation, revaluation_id)
        if not proposal_hint:
            continue
        reservation = _lock_reservation_for_update(proposal_hint.reservation_id)
        proposal = ReservationRevaluation.query.filter_by(
            id=revaluation_id,
            status='pending',
        ).with_for_update().first()
        if (
            not reservation
            or reservation.status != 'active'
            or not proposal
            or proposal.decision_expires_at >= datetime.utcnow()
        ):
            continue
        try:
            if proposal.reservation_asset_id:
                asset = next(
                    (
                        candidate for candidate in reservation.backing_assets
                        if candidate.id == proposal.reservation_asset_id
                    ),
                    None,
                )
                if not asset:
                    raise ValueError(
                        f"Revaluation {proposal.id} has no reservation backing item."
                    )
                _exclude_backing_asset(
                    reservation,
                    asset,
                    proposal,
                    resolution_status='expired',
                )
            else:
                proposal.status = 'expired'
                proposal.resolved_at = datetime.utcnow()
                reservation.seller_item_revaluation_failed = True
            _resolve_reservation(reservation)
            db.session.commit()
            released_count += 1
        except Exception:
            db.session.rollback()
            raise

    query = Reservation.query.filter(
        Reservation.status == 'active',
        db.or_(
            Reservation.expires_at < datetime.utcnow(),
            db.and_(
                Reservation.revaluation_shortfall_expires_at.is_not(None),
                Reservation.revaluation_shortfall_expires_at < datetime.utcnow(),
            ),
        ),
    )
    if item_id is not None:
        query = query.filter(Reservation.item_id == item_id)

    expired_ids = [reservation_id for (reservation_id,) in query.with_entities(Reservation.id).all()]
    for reservation_id in expired_ids:
        reservation = _lock_reservation_for_update(reservation_id)
        if (
            not reservation
            or reservation.status != 'active'
            or (
                reservation.expires_at >= datetime.utcnow()
                and (
                    not reservation.revaluation_shortfall_expires_at
                    or reservation.revaluation_shortfall_expires_at >= datetime.utcnow()
                )
            )
        ):
            continue
        if reservation.seller_item_verification_status == 'not_submitted':
            _adjust_reliability(reservation.item.user if reservation.item else None, -RELIABILITY_PENALTY)
        for asset in reservation.backing_assets:
            if asset.verification_status == 'not_submitted':
                _adjust_reliability(reservation.user, -RELIABILITY_PENALTY)
        try:
            _cancel_reservation(reservation, new_status='expired', relist_seller_item=True, relist_assets=True)
            db.session.commit()
            released_count += 1
        except Exception:
            db.session.rollback()
            raise

    title_consent_query = Reservation.query.filter(
        Reservation.status == 'awaiting_consent',
        Reservation.title_transfer_decision_expires_at < datetime.utcnow(),
    )
    if item_id is not None:
        title_consent_query = title_consent_query.filter(Reservation.item_id == item_id)
    awaiting_ids = [
        reservation_id
        for (reservation_id,) in title_consent_query.with_entities(Reservation.id).all()
    ]
    for reservation_id in awaiting_ids:
        reservation = _lock_reservation_for_update(reservation_id)
        if (
            not reservation
            or reservation.status != 'awaiting_consent'
            or not reservation.title_transfer_decision_expires_at
            or reservation.title_transfer_decision_expires_at >= datetime.utcnow()
        ):
            continue
        try:
            _finish_failed_seller_title_decision(reservation, accepted=False, decision='expired')
            db.session.commit()
            released_count += 1
        except Exception:
            db.session.rollback()
            raise

    if released_count:
        logger.info(f"Expired {released_count} reservation(s) past their settlement window")
    return released_count


def respond_to_failed_seller_title_transfer(reservation, user, accepted):
    """Record the buyer's renewed title-transfer decision after seller-item failure."""
    release_expired_reservations(item_id=reservation.item_id)
    reservation = _lock_reservation_for_update(reservation.id)
    if not reservation:
        return False, "This reservation no longer exists."
    if reservation.user_id != user.id:
        return _reject_transition("You can only respond to your own reservation.")
    if reservation.status != 'awaiting_consent':
        return _reject_transition("This reservation is not waiting for a title-transfer decision.")
    if (
        not reservation.title_transfer_decision_expires_at
        or reservation.title_transfer_decision_expires_at <= datetime.utcnow()
    ):
        return _reject_transition("The title-transfer response window has expired.")

    try:
        _finish_failed_seller_title_decision(
            reservation,
            accepted=accepted,
            decision='accepted' if accepted else 'declined',
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return True, None


def _finish_failed_seller_title_decision(reservation, accepted, decision):
    """Transfer verified items on consent, otherwise return their held BXC and ownership."""
    buyer = reservation.user
    if not buyer:
        raise ValueError(f"Reservation {reservation.id} has no buyer.")

    passed_assets = [
        asset for asset in reservation.backing_assets
        if asset.verification_status == 'passed' and not asset.excluded_from_settlement
    ]
    if not passed_assets:
        raise ValueError(f"Reservation {reservation.id} has no verified backing items to decide.")

    for asset in passed_assets:
        item = asset.item
        if not item:
            raise ValueError(f"Reservation asset {asset.id} has no item.")
        if accepted:
            if not ClearingInventoryItem.query.filter_by(reservation_asset_id=asset.id).first():
                _acquire_backing_asset(reservation, asset, hold_for_purchase=False)
        else:
            if item.owner_type == 'user' and item.user_id == buyer.id:
                if asset.excluded_from_settlement:
                    continue
                _change_reservation_balance(
                    buyer,
                    reservation,
                    'provisional',
                    asset.reserved_provisional_amount,
                    'release',
                    item=item,
                )
                _unlock_backing_asset(asset, relist=True)
            elif item.owner_type != 'barterex':
                raise ValueError(
                    f"Reservation asset {asset.id} no longer belongs to the buyer or Barter Express."
                )

    held_spendable = int(reservation.spendable_credits_held or 0)
    if held_spendable:
        _change_held_spendable(reservation, -held_spendable, 'release')
        before, after = _change_reservation_balance(
            buyer,
            reservation,
            'spendable',
            held_spendable,
            'release',
        )
        db.session.add(CreditTransaction(
            user_id=buyer.id,
            amount=held_spendable,
            transaction_type='reservation_release',
            description=f'Released held BXC from cancelled reservation {reservation.id}',
            reason='reservation_release',
            balance_before=before,
            balance_after=after,
        ))

    reservation.title_transfer_decision = decision
    reservation.title_transfer_decision_at = datetime.utcnow()
    reservation.status = 'cancelled'
    reservation.cancelled_at = datetime.utcnow()
    _update_backing_return_status(reservation)
    db.session.add(Notification(
        user_id=buyer.id,
        message=(
            "Your verified backing item(s) were transferred to Barter Express and their full "
            "verified BXC value is now spendable."
            if accepted else
            "Your verified backing item(s) remain yours and were released. Their original "
            "provisional BXC has been restored."
        ),
    ))
    logger.info(
        f"Reservation {reservation.id} failed-seller title decision: {decision}"
    )


def get_active_reservation(item):
    """The current active (non-expired) reservation on an item, or None."""
    release_expired_reservations(item_id=item.id)
    return Reservation.query.filter_by(item_id=item.id, status='active').first()


def verify_seller_item(
    reservation,
    passed,
    notes=None,
    intake_details=None,
    admin_id=None,
    revised_value=None,
):
    """Admin action: records the final (re-)verification outcome for the seller's item."""
    release_expired_reservations(item_id=reservation.item_id)
    reservation = _lock_reservation_for_update(reservation.id)
    if not reservation:
        return _reject_transition("This reservation no longer exists.")
    if reservation.status != 'active':
        return _reject_transition("This reservation is no longer active.")
    if reservation.seller_item_verification_status != 'not_submitted':
        return _reject_transition("The seller's item has already been verified.")

    try:
        if intake_details is not None:
            from services.verification_intake_service import create_verification_intake

            create_verification_intake(
                reservation.item,
                admin_id,
                intake_details,
                workflow_type='reservation_seller_item',
                outcome='passed' if passed else 'failed',
                reservation=reservation,
            )
        reservation.seller_item_verification_status = 'passed' if passed else 'failed'
        reservation.seller_item_verified_at = datetime.utcnow()
        reservation.seller_item_verification_notes = notes
        if not passed:
            _adjust_reliability(reservation.item.user if reservation.item else None, -RELIABILITY_PENALTY)
        elif reservation.item:
            _create_revaluation(
                reservation,
                reservation.item,
                reservation.purchase_value or round(reservation.item.value or 0),
                revised_value,
                admin_id,
            )

        settled = _resolve_reservation(reservation)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    if settled:
        _award_reservation_points(reservation)
    return True, None


def verify_backing_asset(
    asset,
    passed,
    notes=None,
    intake_details=None,
    admin_id=None,
    revised_value=None,
):
    """Admin action: records the final verification outcome for one backing asset."""
    asset_hint = db.session.get(ReservationAsset, asset.id)
    if not asset_hint:
        return False, "This backing item no longer exists."
    release_expired_reservations(item_id=asset_hint.reservation.item_id)
    reservation = _lock_reservation_for_update(asset_hint.reservation_id)
    if not reservation:
        return _reject_transition("This reservation no longer exists.")
    asset = next((candidate for candidate in reservation.backing_assets if candidate.id == asset_hint.id), None)
    if not asset:
        return _reject_transition("This backing item no longer exists.")
    if reservation.status != 'active':
        return _reject_transition("This reservation is no longer active.")
    if (
        reservation.delivery_method == 'home delivery'
        and reservation.delivery_fee_status != 'paid'
    ):
        return _reject_transition(
            "The buyer must pay the quoted non-refundable home-service fee before backing-item pickup and verification."
        )
    if asset.verification_status != 'not_submitted':
        return _reject_transition("This backing item has already been verified.")

    try:
        if intake_details is not None:
            from services.verification_intake_service import create_verification_intake

            create_verification_intake(
                asset.item,
                admin_id,
                intake_details,
                workflow_type='reservation_backing_item',
                outcome='passed' if passed else 'failed',
                reservation=reservation,
                reservation_asset=asset,
            )
        asset.verification_status = 'passed' if passed else 'failed'
        asset.verified_at = datetime.utcnow()
        asset.verification_notes = notes
        proposal = None
        if not passed:
            _adjust_reliability(reservation.user, -RELIABILITY_PENALTY)
        else:
            proposal = _create_revaluation(
                reservation,
                asset.item,
                asset.amount,
                revised_value,
                admin_id,
                asset=asset,
            )
        if passed and proposal is None and not _has_pending_revaluations(reservation) and (
            reservation.clearing_mode == 'company_inventory'
            and (
                reservation.backing_asset_consent_version
                == LEGACY_BACKING_ASSET_CONSENT_VERSION
                or reservation.seller_item_verification_status == 'passed'
            )
        ):
            _acquire_backing_asset(reservation, asset)

        settled = _resolve_reservation(reservation)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    if settled:
        _award_reservation_points(reservation)
    return True, None


def _resolve_reservation(reservation):
    """
    All-or-nothing check, run after every verification event. Settles the
    purchase once everything has passed, or cancels it the moment anything
    makes success impossible.
    """
    if reservation.status != 'active':
        return False

    assets = reservation.backing_assets
    any_failed = any(a.verification_status == 'failed' for a in assets)
    all_assets_done = all(a.verification_status in ('passed', 'failed') for a in assets)
    seller_status = reservation.seller_item_verification_status

    if seller_status == 'failed' or reservation.seller_item_revaluation_failed:
        for proposal in reservation.revaluations:
            if proposal.status == 'pending' and proposal.reservation_asset_id:
                asset = next(
                    (
                        candidate for candidate in assets
                        if candidate.id == proposal.reservation_asset_id
                    ),
                    None,
                )
                if asset:
                    _exclude_backing_asset(reservation, asset, proposal)
        passed_assets = [
            asset for asset in assets
            if asset.verification_status == 'passed' and not asset.excluded_from_settlement
        ]
        if (
            reservation.clearing_mode == 'company_inventory'
            and reservation.backing_asset_consent_version == BACKING_ASSET_CONSENT_VERSION
            and passed_assets
        ):
            physical_failure = seller_status == 'failed'
            _unlock_seller_item(reservation.item, relist=not physical_failure)
            for asset in assets:
                if asset.verification_status == 'passed' or asset.excluded_from_settlement:
                    continue
                _change_reservation_balance(
                    reservation.user,
                    reservation,
                    'provisional',
                    asset.reserved_provisional_amount,
                    'release',
                    item=asset.item,
                )
                reservation.provisional_credits_used -= int(
                    asset.reserved_provisional_amount or 0
                )
                asset.excluded_from_settlement = True
                _unlock_backing_asset(asset, relist=True)
            reservation.status = 'awaiting_consent'
            _update_backing_return_status(reservation, statuses={'failed'})
            reservation.title_transfer_decision_expires_at = (
                datetime.utcnow() + timedelta(hours=TITLE_TRANSFER_CONSENT_HOURS)
            )
            db.session.add(Notification(
                user_id=reservation.user_id,
                message=(
                    (
                        "The requested item failed physical verification. Your verified backing "
                        "item(s) still belong to you. Confirm within 24 hours whether to transfer "
                        "them to Barter Express; if you decline or do not respond, the items stay "
                        "yours and their original provisional BXC is restored."
                    )
                    if physical_failure else
                    "The requested item's revised value was not accepted or could not be applied. "
                    "Confirm within 24 hours whether to transfer any verified backing item(s) to "
                    "Barter Express; if you decline or do not respond, they stay yours and their "
                    "original provisional BXC is restored."
                ),
            ))
            logger.info(
                f"Reservation {reservation.id} awaiting renewed title consent after seller-side failure"
            )
            return False

        _cancel_reservation(
            reservation,
            new_status='cancelled',
            relist_seller_item=(seller_status != 'failed'),
            relist_assets=True,
        )
        if reservation.clearing_mode == 'company_inventory':
            if reservation.backing_asset_consent_version == LEGACY_BACKING_ASSET_CONSENT_VERSION:
                passed_names = [
                    f"'{asset.item.name}'" for asset in assets
                    if asset.verification_status == 'passed' and asset.item
                ]
                detail = (
                    f" Passed backing item(s) {', '.join(passed_names)} were transferred to Barter Express "
                    "and their verified BXC value was credited; other backing BXC was released."
                    if passed_names else
                    " Your backing items remain yours and their provisional BXC was restored."
                )
            else:
                detail = " Your backing items remain yours and their provisional BXC was restored."
        else:
            detail = " Your collateral items have been released back to you and your provisional credits are untouched."
        db.session.add(Notification(
            user_id=reservation.user_id,
            message=f"⚠️ The item you tried to acquire failed final verification.{detail}"
        ))
        logger.info(f"Reservation {reservation.id} cancelled - seller-side verification/revaluation failed")
        return False

    if _has_pending_revaluations(reservation):
        return False

    shortfall = get_reservation_shortfall(reservation)
    if shortfall:
        if reservation.revaluation_shortfall_expires_at is None:
            shortfall_deadline = datetime.utcnow() + timedelta(
                hours=REVALUATION_DECISION_HOURS
            )
            reservation.revaluation_shortfall_expires_at = shortfall_deadline
            if reservation.expires_at < shortfall_deadline:
                reservation.expires_at = shortfall_deadline
                if reservation.item:
                    reservation.item.reservation_expires_at = shortfall_deadline
    else:
        reservation.revaluation_shortfall_expires_at = None

    if seller_status == 'passed' and reservation.clearing_mode == 'company_inventory':
        for asset in assets:
            if (
                asset.verification_status == 'passed'
                and not asset.excluded_from_settlement
                and not ClearingInventoryItem.query.filter_by(reservation_asset_id=asset.id).first()
            ):
                _acquire_backing_asset(reservation, asset)

    if any_failed:
        _cancel_reservation(reservation, new_status='cancelled', relist_seller_item=True, relist_assets=True)
        db.session.add(Notification(
            user_id=reservation.item.user_id if reservation.item else None,
            message="⚠️ The buyer's collateral for your item failed verification. Your item is back on the marketplace."
        ))
        if reservation.clearing_mode == 'company_inventory':
            db.session.add(Notification(
                user_id=reservation.user_id,
                message=(
                    "A backing item failed verification. Any backing item that had already passed remains "
                    "Barter Express property and its BXC value remains yours; other backing items and held "
                    "purchase BXC were released."
                ),
            ))
        logger.info(f"Reservation {reservation.id} cancelled - backing asset(s) failed verification")
        return False

    if seller_status == 'passed' and all_assets_done and not any_failed:
        return _settle_reservation(reservation)
    return False


def _settle_reservation(reservation):
    """Both sides passed: transfer ownership and apply all BXC changes atomically."""
    buyer = reservation.user
    seller_item = reservation.item
    seller = seller_item.user if seller_item else None
    if not buyer or not seller_item or not seller or buyer.id == seller.id:
        raise ValueError(f"Reservation {reservation.id} has invalid buyer or seller data.")
    participating_assets = [
        asset for asset in reservation.backing_assets
        if not asset.excluded_from_settlement
    ]
    if any(
        asset.item is None or asset.verification_status != 'passed'
        for asset in participating_assets
    ):
        raise ValueError(f"Reservation {reservation.id} has a missing or unverified backing item.")
    backing_total = sum(asset.amount for asset in participating_assets)
    reserved_total = sum(
        asset.reserved_provisional_amount for asset in participating_assets
    )
    if reserved_total != reservation.provisional_credits_used:
        raise ValueError(f"Reservation {reservation.id} backing ledger does not match its reserved BXC.")
    company_inventory_mode = reservation.clearing_mode == 'company_inventory'
    if company_inventory_mode and any(
        asset.item.owner_type != 'barterex'
        or asset.item.user_id is not None
        or not ClearingInventoryItem.query.filter_by(reservation_asset_id=asset.id).first()
        for asset in participating_assets
    ):
        raise ValueError(f"Reservation {reservation.id} has backing assets missing from clearing inventory.")

    purchase_amount = int(
        reservation.purchase_value
        if reservation.purchase_value is not None
        else round(seller_item.value or 0)
    )
    if purchase_amount <= 0:
        raise ValueError(f"Reservation {reservation.id} has no valid agreed item value.")
    if backing_total + int(reservation.spendable_funding_held or 0) < purchase_amount:
        return False
    held_before = int(reservation.spendable_credits_held or 0)
    if company_inventory_mode and held_before < purchase_amount:
        return False

    seller_provisional_amount = 0
    if seller_item.provisional_credit_amount and not seller_item.provisional_credit_settled:
        seller_provisional_amount = int(round(seller_item.provisional_credit_amount))
        if (seller.provisional_credits or 0) < seller_provisional_amount:
            raise ValueError(
                f"Reservation {reservation.id} cannot settle: seller's provisional BXC "
                "balance is lower than the item's unsettled provisional value."
            )

    # Transfer the purchased item to the buyer.
    seller_item.user_id = buyer.id
    seller_item.owner_type = 'user'
    seller_item.is_available = False
    seller_item.reserved_by_id = None
    seller_item.reserved_at = None
    seller_item.reservation_expires_at = None

    db.session.add(Trade(sender_id=buyer.id, receiver_id=seller.id, item_id=seller_item.id,
                          item_received_id=seller_item.id, status='completed'))

    # Closes the earlier "Activate for Trade" gap: the seller's own provisional credit for
    # this item becomes real now that it has actually left their possession via a verified exchange.
    if seller_provisional_amount:
        _change_reservation_balance(
            seller,
            reservation,
            'provisional',
            -seller_provisional_amount,
            'settlement',
            item=seller_item,
        )
        seller_balance_before, seller_balance_after = _change_reservation_balance(
            seller,
            reservation,
            'spendable',
            seller_provisional_amount,
            'settlement',
            item=seller_item,
        )
        db.session.add(CreditTransaction(
            user_id=seller.id,
            amount=seller_provisional_amount,
            transaction_type='reservation_settlement',
            description=f'BXC settled for item exchanged in reservation {reservation.id}',
            reason='reservation_settlement',
            balance_before=seller_balance_before,
            balance_after=seller_balance_after,
            related_item_id=seller_item.id,
        ))
        seller_item.provisional_credit_settled = True

    # Return the unused portion of the buyer's reserved provisional BXC as
    # spendable credits. The selected assets have already been debited from the
    # buyer's provisional balance when the reservation was created.
    change_amount = 0
    if company_inventory_mode:
        _change_held_spendable(
            reservation, -purchase_amount, 'purchase', item=seller_item
        )
        excess_held = held_before - purchase_amount
        if excess_held:
            _change_held_spendable(
                reservation, -excess_held, 'release', item=seller_item
            )
            balance_before, balance_after = _change_reservation_balance(
                buyer,
                reservation,
                'spendable',
                excess_held,
                'change',
                item=seller_item,
            )
            db.session.add(CreditTransaction(
                user_id=buyer.id,
                amount=excess_held,
                transaction_type='refund',
                description=f'Change from reservation {reservation.id} for {seller_item.name}',
                reason='reservation_change',
                balance_before=balance_before,
                balance_after=balance_after,
                related_item_id=seller_item.id,
            ))
        db.session.add(CreditTransaction(
            user_id=buyer.id,
            amount=purchase_amount,
            transaction_type='purchase',
            description=f'BXC spent on {seller_item.name} in reservation {reservation.id}',
            reason='reservation_purchase',
            balance_before=(buyer.credits or 0) + purchase_amount,
            balance_after=buyer.credits or 0,
            related_item_id=seller_item.id,
        ))
    else:
        change_amount = max(0, reservation.provisional_credits_used - purchase_amount)
    if change_amount:
        balance_before, balance_after = _change_reservation_balance(
            buyer,
            reservation,
            'spendable',
            change_amount,
            'change',
            item=seller_item,
        )
        db.session.add(CreditTransaction(
            user_id=buyer.id,
            amount=change_amount,
            transaction_type='refund',
            description=f'Change from reservation {reservation.id} for {seller_item.name}',
            reason='reservation_change',
            balance_before=balance_before,
            balance_after=balance_after,
            related_item_id=seller_item.id,
        ))

    if not company_inventory_mode:
        for asset in participating_assets:
            asset_item = asset.item
            if not asset_item:
                continue
            asset_item.locked_for_reservation_id = None
            asset_item.user_id = seller.id
            asset_item.owner_type = 'user'
            asset_item.is_available = False
            if asset_item.provisional_credit_amount and not asset_item.provisional_credit_settled:
                asset_item.provisional_credit_settled = True
            db.session.add(Trade(sender_id=buyer.id, receiver_id=seller.id, item_id=asset_item.id,
                                  item_received_id=asset_item.id, status='completed'))

    _adjust_reliability(buyer, RELIABILITY_BONUS)
    _adjust_reliability(seller, RELIABILITY_BONUS)

    order_number = f"RSV-{datetime.utcnow():%Y%m%d}-{reservation.id:06d}"
    order = Order(
        user_id=buyer.id,
        delivery_method=reservation.delivery_method,
        delivery_address=reservation.delivery_address,
        pickup_station_id=reservation.pickup_station_id,
        status='Pending',
        order_number=order_number,
        total_credits=purchase_amount,
        credits_used=purchase_amount,
        credits_balance_before=(buyer.credits or 0) + purchase_amount,
        credits_balance_after=buyer.credits or 0,
        reservation_id=reservation.id,
        logistics_fee_naira=reservation.delivery_quote_naira,
    )
    db.session.add(order)
    db.session.flush()
    db.session.add(OrderItem(order_id=order.id, item_id=seller_item.id))

    reservation.status = 'completed'
    reservation.completed_at = datetime.utcnow()
    reservation.backing_return_status = 'not_required'

    buyer_message = f"🎉 Purchase complete! '{seller_item.name}' is now yours."
    if company_inventory_mode:
        buyer_message += f" ᗸ{purchase_amount:,} was spent from your held BXC balance."
    elif change_amount:
        buyer_message += f" ᗸ{change_amount:,} in change was added to your spendable balance."
    db.session.add(Notification(user_id=buyer.id, message=buyer_message))
    db.session.add(Notification(
        user_id=buyer.id,
        message=(
            f"Your purchase is verified and order {order_number} is ready for fulfillment."
            if reservation.delivery_method == 'pickup'
            else f"Your purchase is verified. Accept and pay the home-service quote before dispatching order {order_number}."
        ),
    ))
    db.session.add(Notification(user_id=seller.id,
                                 message=f"🎉 '{seller_item.name}' has been exchanged! Thanks for trading on Barter Express."))

    logger.info(f"Reservation {reservation.id} settled - Buyer: {buyer.username}, Item: {seller_item.id}")
    return True


def _award_reservation_points(reservation):
    from trading_points import award_points_for_purchase, create_level_up_notification

    try:
        level_up_info = award_points_for_purchase(reservation.user, f"reservation-{reservation.id}")
        if level_up_info:
            create_level_up_notification(reservation.user, level_up_info)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning(f"Could not award trading points for reservation {reservation.id}: {e}")
