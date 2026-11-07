"""Marketplace activation and its custody-appropriate credit ledger entry."""
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
        raise ValueError('This item has already received activation credits.')
    if not video_url:
        raise ValueError('An approved published video is required for activation.')
    owner = User.query.filter_by(id=item.activation_submitter_id()).with_for_update().populate_existing().first()
    if owner is None:
        raise ValueError(f'Item {item.id} owner no longer exists.')

    company_acquisition = item.manual_review_requested and item.manual_custody_choice == 'company'
    if company_acquisition:
        inventory = item.clearing_inventory
        if inventory is None or inventory.status != 'awaiting_activation' or item.owner_type != 'barterex' or item.user_id is not None:
            raise ValueError('The manual acquisition is missing its pending company inventory record.')
    balance_field = 'credits' if company_acquisition else 'provisional_credits'
    before = int(getattr(owner, balance_field) or 0)
    setattr(owner, balance_field, before + amount)
    item.value = amount
    item.video_url = video_url
    item.status = 'approved'
    item.is_approved = True
    item.is_available = True
    item.activated_at = datetime.utcnow()
    item.last_reconfirmed_at = item.activated_at
    item.provisional_credit_amount = amount
    item.provisional_credit_granted_at = item.activated_at
    item.provisional_credit_settled = company_acquisition
    if company_acquisition:
        inventory.status = 'held_for_resale'
    db.session.add(ReservationCreditEntry(
        user_id=owner.id,
        item_id=item.id,
        balance_type='spendable' if company_acquisition else 'provisional',
        entry_type='activation',
        amount=amount,
        balance_before=before,
        balance_after=getattr(owner, balance_field),
    ))
    return amount
