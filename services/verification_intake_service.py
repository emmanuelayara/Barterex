"""Physical verification intake and custody-chain recording."""

from datetime import datetime

from app import db
from models import Admin, CustodyEvent, VerificationIntake


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
    if serial_check == 'matched':
        expected_serial = (item.serial_number or '').strip()
        if not expected_serial or not observed_serial:
            raise IntakeValidationError(
                'Enter the observed serial number and the submitted serial number before marking it as matched.'
            )
        if expected_serial.casefold() != observed_serial.casefold():
            raise IntakeValidationError(
                'The observed serial number differs from the submitted number; record it as a mismatch.'
            )
    if outcome == 'passed' and not identity_confirmed:
        raise IntakeValidationError('An item must be positively identified before it can pass verification.')
    if outcome == 'passed' and serial_check == 'mismatch':
        raise IntakeValidationError('An item with a serial-number mismatch cannot pass verification.')

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
