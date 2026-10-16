"""Marketplace activation and its provisional-credit ledger entry."""
from datetime import datetime

from app import db
from models import Item, ReservationCreditEntry, User


def activate_item(item_id, video_url):
    """Stage activation atomically; the caller owns the transaction commit."""
    item = Item.query.filter_by(id=item_id).with_for_update().populate_existing().one()
    amount = item.activation_credit_amount()
    if item.provisional_credit_granted_at is not None or ReservationCreditEntry.query.filter_by(
        item_id=item.id, entry_type='activation',
    ).first() is not None:
        raise ValueError('This item has already received provisional activation credits.')
    if not video_url:
        raise ValueError('An approved published video is required for activation.')
    owner = User.query.filter_by(id=item.user_id).with_for_update().populate_existing().first()
    if owner is None:
        raise ValueError(f'Item {item.id} owner no longer exists.')

    before = int(owner.provisional_credits or 0)
    owner.provisional_credits = before + amount
    item.value = amount
    item.video_url = video_url
    item.status = 'approved'
    item.is_approved = True
    item.is_available = True
    item.activated_at = datetime.utcnow()
    item.last_reconfirmed_at = item.activated_at
    item.provisional_credit_amount = amount
    item.provisional_credit_granted_at = item.activated_at
    item.provisional_credit_settled = False
    db.session.add(ReservationCreditEntry(
        user_id=owner.id,
        item_id=item.id,
        balance_type='provisional',
        entry_type='activation',
        amount=amount,
        balance_before=before,
        balance_after=owner.provisional_credits,
    ))
    return amount
