"""Scheduled maintenance tasks for reservation deadlines and listing freshness."""

from services.freshness_service import deactivate_stale_items, warn_items_nearing_freshness_deadline
from services.reservation_service import release_expired_reservations, send_reservation_deadline_reminders


def run_maintenance_sweep():
    """Run idempotent deadline and freshness sweeps; errors propagate to the scheduler."""
    expired_reservations = release_expired_reservations()
    reservation_reminders = send_reservation_deadline_reminders()
    stale_items = deactivate_stale_items()
    freshness_warnings = warn_items_nearing_freshness_deadline()
    return {
        "expired_reservations": expired_reservations,
        "reservation_reminders": reservation_reminders,
        "stale_items": stale_items,
        "freshness_warnings": freshness_warnings,
    }
