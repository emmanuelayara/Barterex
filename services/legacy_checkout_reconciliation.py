import json
import math
from datetime import datetime

from app import db
from models import (
    CreditTransaction,
    LegacyCheckoutReconciliation,
    Order,
    Trade,
)


def _plan_order_reversal(order):
    if order.reservation_id is not None:
        return None, "Reservation-backed orders are not legacy cart checkouts."
    if order.cancelled or (order.status or "").lower() == "cancelled":
        return None, "Order is already cancelled; prior reversal state is unknown."
    if not order.items:
        return None, "Order has no linked items."

    credits_used = order.credits_used
    if credits_used is None or not math.isfinite(float(credits_used)):
        return None, "Order has no finite recorded BXC debit."
    rounded_credits = round(float(credits_used))
    if rounded_credits <= 0 or not math.isclose(float(credits_used), rounded_credits):
        return None, "Recorded BXC debit is not a positive whole number."

    if CreditTransaction.query.filter(
        CreditTransaction.related_order_id == order.id,
        CreditTransaction.transaction_type.in_(("refund", "reversal")),
    ).first():
        return None, "An existing refund or reversal is linked to the order."

    planned_items = []
    seen_item_ids = set()
    for order_item in order.items:
        item = order_item.item
        if not item or item.id in seen_item_ids:
            return None, "Order contains a missing or duplicate item."
        seen_item_ids.add(item.id)
        if item.locked_for_reservation_id is not None:
            return None, f"Item {item.id} is currently held by a reservation."

        matching_trades = Trade.query.filter_by(
            sender_id=order.user_id,
            item_id=item.id,
            item_received_id=item.id,
            item_given_id=None,
            status="completed",
        ).all()
        if len(matching_trades) != 1:
            return None, f"Item {item.id} does not have exactly one matching completed purchase trade."
        trade = matching_trades[0]
        if trade.receiver_id == order.user_id or not trade.receiver:
            return None, f"Item {item.id} has no distinct, valid original seller."
        planned_items.append((item, trade))

    return {
        "credits": int(rounded_credits),
        "items": planned_items,
    }, None


def reconcile_legacy_direct_checkouts(apply_changes=False):
    """Preview or reverse non-reservation orders that match the old checkout signature."""
    report = []
    orders = Order.query.filter(
        Order.reservation_id.is_(None)
    ).order_by(Order.id.asc()).all()

    for order in orders:
        audit = LegacyCheckoutReconciliation.query.filter_by(order_id=order.id).first()
        if audit and audit.status == "reversed":
            continue

        plan, reason = _plan_order_reversal(order)
        result = "reversed" if plan else "needs_review"
        details = (
            json.dumps({
                "item_ids": [item.id for item, _trade in plan["items"]],
                "seller_ids": [trade.receiver_id for _item, trade in plan["items"]],
            }, sort_keys=True)
            if plan
            else reason
        )
        report.append({
            "order_id": order.id,
            "status": result,
            "credits_refunded": plan["credits"] if plan else 0,
            "details": details,
        })

        if not apply_changes:
            continue

        if plan:
            buyer = order.user
            if not buyer or buyer.credits is None:
                result = "needs_review"
                details = "Order buyer is missing or has no recorded BXC balance."
                report[-1].update(status=result, credits_refunded=0, details=details)
            else:
                balance_before = buyer.credits
                buyer.credits += plan["credits"]
                db.session.add(CreditTransaction(
                    user_id=buyer.id,
                    amount=plan["credits"],
                    transaction_type="refund",
                    reason="legacy_direct_checkout_reversal",
                    description=f"Refund for reversed legacy order {order.order_number}.",
                    balance_before=balance_before,
                    balance_after=buyer.credits,
                    related_order_id=order.id,
                ))
                for item, trade in plan["items"]:
                    item.user_id = trade.receiver_id
                    item.owner_type = "user"
                    item.is_available = False
                    trade.status = "cancelled"

                order.cancelled = True
                order.cancelled_at = datetime.utcnow()
                order.cancellation_reason = (
                    "Legacy direct checkout reversed for non-custodial reservation migration."
                )
                order.status = "Cancelled"
                details = json.dumps({
                    "item_ids": [item.id for item, _trade in plan["items"]],
                    "seller_ids": [trade.receiver_id for _item, trade in plan["items"]],
                }, sort_keys=True)

        if audit:
            audit.status = result
            audit.credits_refunded = plan["credits"] if result == "reversed" and plan else 0
            audit.details = details
        else:
            db.session.add(LegacyCheckoutReconciliation(
                order_id=order.id,
                buyer_id=order.user_id if order.user else None,
                status=result,
                credits_refunded=plan["credits"] if result == "reversed" and plan else 0,
                details=details,
            ))

    if apply_changes:
        db.session.commit()
    return report
