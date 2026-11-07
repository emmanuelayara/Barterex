"""Physical verification intake and custody-chain recording."""

from datetime import datetime, timedelta

from app import db
from models import Admin, CustodyEvent, Order, VerificationIntake


SERIAL_CHECKS = {'matched', 'mismatch', 'not_applicable'}
INTAKE_OUTCOMES = {'passed', 'failed'}


class IntakeValidationError(ValueError):
    """A user-correctable intake or custody form error."""


def create_verification_intake(
    item,
    admin_id,
    details,
    workflow_type,
    outcome,
    reservation=None,
    reservation_asset=None,
):
    """Create an inspection snapshot and its initial receipt custody event."""
    if outcome not in INTAKE_OUTCOMES:
        raise IntakeValidationError('Choose a valid physical verification outcome.')

    admin = db.session.get(Admin, admin_id)
    if not admin:
        raise IntakeValidationError('Your admin session is no longer valid. Please sign in again.')

    location = (details.get('received_location') or '').strip()
    condition = (details.get('observed_condition') or '').strip()
    serial_check = (details.get('serial_check') or '').strip()
    observed_serial = (details.get('observed_serial_number') or '').strip() or None
    identity_confirmed = details.get('identity_confirmed') == 'yes'
    accessories = (details.get('accessories_received') or '').strip() or None
    notes = (details.get('intake_notes') or '').strip() or None

    if not location or len(location) > 200:
        raise IntakeValidationError('Enter the location where the item was received (maximum 200 characters).')
    if condition not in item.VALID_CONDITIONS:
        raise IntakeValidationError('Select the item condition observed during inspection.')
    if serial_check not in SERIAL_CHECKS:
        raise IntakeValidationError('Record whether the serial number matched or does not apply.')
    if len(observed_serial or '') > 100:
        raise IntakeValidationError('The observed serial number must be 100 characters or fewer.')
    expected_serial = (item.serial_number or '').strip()
    if serial_check == 'matched':
        if not observed_serial:
            raise IntakeValidationError(
                'Enter the physically observed serial number before recording or matching it.'
            )
        if expected_serial and expected_serial.casefold() != observed_serial.casefold():
            raise IntakeValidationError(
                'The observed serial number differs from the submitted number; record it as a mismatch.'
            )
    if outcome == 'passed' and not identity_confirmed:
        raise IntakeValidationError('An item must be positively identified before it can pass verification.')
    if outcome == 'passed' and serial_check == 'mismatch':
        raise IntakeValidationError('An item with a serial-number mismatch cannot pass verification.')

    if outcome == 'passed' and serial_check == 'matched' and not expected_serial:
        item.serial_number = observed_serial

    now = datetime.utcnow()
    intake = VerificationIntake(
        item_id=item.id,
        reservation_id=reservation.id if reservation else None,
        reservation_asset_id=reservation_asset.id if reservation_asset else None,
        workflow_type=workflow_type,
        outcome=outcome,
        received_at=now,
        received_location=location,
        received_by_admin_id=admin.id,
        observed_condition=condition,
        observed_serial_number=observed_serial,
        serial_check=serial_check,
        identity_confirmed=identity_confirmed,
        accessories_received=accessories,
        inspection_notes=notes,
        inspected_at=now,
        inspected_by_admin_id=admin.id,
    )
    db.session.add(intake)
    db.session.flush()
    db.session.add(CustodyEvent(
        item_id=item.id,
        intake=intake,
        event_type='received',
        from_location=None,
        to_location=location,
        custodian_name=admin.username,
        recorded_by_admin_id=admin.id,
        recorded_at=now,
        notes='Item received for physical verification.',
    ))
    return intake


def record_custody_handoff(intake, admin_id, location, custodian_name, notes=None):
    """Append a movement/handoff record without modifying prior custody events."""
    intake = VerificationIntake.query.filter_by(id=intake.id).with_for_update().populate_existing().one()
    db.session.expire(intake, ['custody_events'])
    if intake.custody_closed:
        raise IntakeValidationError('This custody record is closed. A new physical intake is required before recording another handoff.')
    if VerificationIntake.query.filter(
        VerificationIntake.item_id == intake.item_id,
        db.or_(
            VerificationIntake.received_at > intake.received_at,
            db.and_(VerificationIntake.received_at == intake.received_at, VerificationIntake.id > intake.id),
        ),
    ).first():
        raise IntakeValidationError('This is a historical inspection. Record movements against the latest physical intake.')
    admin = db.session.get(Admin, admin_id)
    if not admin:
        raise IntakeValidationError('Your admin session is no longer valid. Please sign in again.')
    location = (location or '').strip()
    custodian_name = (custodian_name or '').strip()
    notes = (notes or '').strip() or None
    if not location or len(location) > 200:
        raise IntakeValidationError('Enter the new item location (maximum 200 characters).')
    if not custodian_name or len(custodian_name) > 120:
        raise IntakeValidationError('Enter the receiving custodian name (maximum 120 characters).')

    latest_event = CustodyEvent.query.filter_by(intake_id=intake.id).order_by(
        CustodyEvent.recorded_at.desc(), CustodyEvent.id.desc()
    ).first()
    if not latest_event:
        raise IntakeValidationError('This intake has no initial receipt record.')

    if (
        latest_event.to_location == location
        and latest_event.custodian_name.casefold() == custodian_name.casefold()
    ):
        raise IntakeValidationError('Record a changed location or receiving custodian.')
    event_type = (
        'handed_off'
        if latest_event.custodian_name.casefold() != custodian_name.casefold()
        else 'moved'
    )
    event = CustodyEvent(
        item_id=intake.item_id,
        intake_id=intake.id,
        event_type=event_type,
        from_location=latest_event.to_location,
        to_location=location,
        custodian_name=custodian_name,
        recorded_by_admin_id=admin.id,
        recorded_at=datetime.utcnow(),
        notes=notes,
    )
    db.session.add(event)
    return event


def record_order_delivery_custody(order, admin_id, historical=False):
    """Close the receipt cycle for purchased items without releasing buyer backing items."""
    admin = db.session.get(Admin, admin_id)
    if not admin:
        raise IntakeValidationError('Your admin session is no longer valid. Please sign in again.')
    if order.status != 'Delivered' or order.cancelled:
        raise IntakeValidationError('Only a delivered, non-cancelled order can release items to its buyer.')
    if not order.user:
        raise IntakeValidationError('The delivered order has no buyer record.')

    now = datetime.utcnow()
    cutoff = order.date_ordered
    if not cutoff:
        raise IntakeValidationError('The order date is missing; custody cannot be matched safely.')
    # SQLite's order default stores whole seconds, while inspection timestamps include microseconds.
    whole_second_order = cutoff.microsecond == 0
    if whole_second_order:
        cutoff += timedelta(seconds=1)
    recorded = 0
    missing = []
    for item_id in sorted({entry.item_id for entry in order.items}):
        intake = VerificationIntake.query.filter(
            VerificationIntake.item_id == item_id,
            VerificationIntake.received_at < cutoff if whole_second_order else VerificationIntake.received_at <= cutoff,
        ).order_by(
            VerificationIntake.received_at.desc(), VerificationIntake.id.desc(),
        ).with_for_update().populate_existing().first()
        if not intake:
            missing.append(item_id)
            continue
        if intake.outcome != 'passed':
            raise IntakeValidationError(f'Item {item_id} has no passed inspection for this order.')
        db.session.expire(intake, ['custody_events'])
        if any(event.event_type == 'released_to_buyer' for event in intake.custody_events):
            continue
        if intake.custody_closed:
            raise IntakeValidationError(f'Item {item_id} was already returned to its owner; review custody before confirming delivery.')
        if not intake.custody_events:
            raise IntakeValidationError(f'Item {item_id} has no receipt custody record.')
        latest = intake.custody_events[-1]
        db.session.add(CustodyEvent(
            item_id=item_id, intake=intake, event_type='released_to_buyer',
            from_location=latest.to_location, to_location='Released to buyer',
            custodian_name=order.user.username, recorded_by_admin_id=admin.id,
            recorded_at=now,
            notes=(
                f"Reconciled previously delivered order {order.order_number}. "
                "This is the reconciliation time, not a reconstructed delivery time."
                if historical else
                f"Final handoff recorded when order {order.order_number} was marked Delivered."
            ),
        ))
        recorded += 1
    if not historical:
        order.actual_delivery_date = order.actual_delivery_date or now
    return recorded, missing


def reconcile_delivered_order_custody(admin_id):
    """Repair existing delivered orders, retaining original inspection and movement history."""
    orders = Order.query.filter_by(status='Delivered', cancelled=False).order_by(
        Order.date_ordered, Order.id,
    ).with_for_update().all()
    recorded = 0
    missing = []
    for order in orders:
        count, missing_items = record_order_delivery_custody(order, admin_id, historical=True)
        recorded += count
        missing.extend((order.id, item_id) for item_id in missing_items)
    return recorded, missing
