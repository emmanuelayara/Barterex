"""Scheduled maintenance tasks for reservation deadlines and listing freshness."""

from services.freshness_service import deactivate_stale_items
from services.reservation_service import release_expired_reservations


def run_maintenance_sweep():
    """Run idempotent deadline and freshness sweeps; errors propagate to the scheduler."""
    expired_reservations = release_expired_reservations()
    stale_items = deactivate_stale_items()
    return {
        "expired_reservations": expired_reservations,
        "stale_items": stale_items,
    }
