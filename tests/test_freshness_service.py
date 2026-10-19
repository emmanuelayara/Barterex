import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

from app import app, db
from models import Item, Notification, User
from services.freshness_service import (
    FRESHNESS_WINDOW_DAYS,
    HIGH_VALUE_THRESHOLD,
    deactivate_stale_items,
    warn_items_nearing_freshness_deadline,
)
from services.maintenance_service import run_maintenance_sweep


class FreshnessServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            WTF_CSRF_ENABLED=False,
        )

    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()
        self.user = User(
            username="freshness-user",
            email="freshness@example.com",
            password_hash="test-hash",
        )
        db.session.add(self.user)
        db.session.flush()
        cutoff = datetime.utcnow() - timedelta(days=FRESHNESS_WINDOW_DAYS, seconds=5)
        self.stale_high_value = Item(
            name="Stale high-value listing",
            category="Electronics",
            user_id=self.user.id,
            status="approved",
            is_approved=True,
            is_available=True,
            value=HIGH_VALUE_THRESHOLD,
            activated_at=cutoff,
        )
        self.stale_low_value = Item(
            name="Stale low-value listing",
            category="Books",
            user_id=self.user.id,
            status="approved",
            is_approved=True,
            is_available=True,
            value=100,
            activated_at=cutoff,
        )
        self.fresh_listing = Item(
            name="Recently reconfirmed listing",
            category="Books",
            user_id=self.user.id,
            status="approved",
            is_approved=True,
            is_available=True,
            value=100,
            activated_at=cutoff,
            last_reconfirmed_at=datetime.utcnow(),
        )
        self.unavailable_item = Item(
            name="Unlisted item",
            category="Books",
            user_id=self.user.id,
            status="approved",
            is_approved=True,
            is_available=False,
            value=100,
            activated_at=cutoff,
        )
        self.company_item = Item(
            name="Company inventory item",
            category="Books",
            user_id=None,
            owner_type="company",
            status="approved",
            is_approved=True,
            is_available=True,
            value=100,
            activated_at=cutoff,
        )
        db.session.add_all([
            self.stale_high_value,
            self.stale_low_value,
            self.fresh_listing,
            self.unavailable_item,
            self.company_item,
        ])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_deactivates_stale_listings_and_requires_high_value_reconfirmation_code(self):
        count = deactivate_stale_items()

        self.assertEqual(count, 2)
        self.assertFalse(self.stale_high_value.is_available)
        self.assertEqual(self.stale_high_value.status, "reconfirmation_required")
        self.assertIsNotNone(self.stale_high_value.reconfirmation_code)
        self.assertFalse(self.stale_low_value.is_available)
        self.assertEqual(self.stale_low_value.status, "reconfirmation_required")
        self.assertIsNone(self.stale_low_value.reconfirmation_code)
        self.assertTrue(self.fresh_listing.is_available)
        self.assertEqual(self.fresh_listing.status, "approved")
        self.assertFalse(self.unavailable_item.is_available)
        self.assertTrue(self.company_item.is_available)
        self.assertEqual(Notification.query.count(), 2)

    def test_warns_owner_once_before_listing_is_pulled(self):
        self.fresh_listing.last_reconfirmed_at = datetime.utcnow() - timedelta(days=FRESHNESS_WINDOW_DAYS - 2)
        db.session.commit()

        with patch("routes.auth.send_email_async") as send_email:
            self.assertEqual(warn_items_nearing_freshness_deadline(), 1)
            self.assertEqual(warn_items_nearing_freshness_deadline(), 0)

        send_email.assert_called_once()
        self.assertEqual(send_email.call_args.kwargs["recipients"], [self.user.email])
        self.assertEqual(Notification.query.count(), 1)
        self.assertTrue(self.fresh_listing.is_available)

        # A warning from a previous cycle (before the latest reconfirmation) doesn't block a new one.
        self.fresh_listing.freshness_warning_sent_at = datetime.utcnow() - timedelta(days=60)
        db.session.commit()
        with patch("routes.auth.send_email_async"):
            self.assertEqual(warn_items_nearing_freshness_deadline(), 1)

    def test_sweep_is_idempotent_and_returns_job_counts(self):
        with patch(
            "services.maintenance_service.release_expired_reservations",
            return_value=3,
        ) as expire_reservations, patch(
            "services.maintenance_service.send_reservation_deadline_reminders",
            return_value=1,
        ), patch(
            "services.maintenance_service.warn_items_nearing_freshness_deadline",
            return_value=0,
        ):
            result = run_maintenance_sweep()

        self.assertEqual(
            result,
            {
                "expired_reservations": 3,
                "reservation_reminders": 1,
                "stale_items": 2,
                "freshness_warnings": 0,
            },
        )
        expire_reservations.assert_called_once_with()
        self.assertEqual(deactivate_stale_items(), 0)
        self.assertEqual(Notification.query.count(), 2)

    def test_maintenance_cli_reports_sweep_counts(self):
        with patch(
            "services.maintenance_service.release_expired_reservations",
            return_value=2,
        ), patch(
            "services.maintenance_service.deactivate_stale_items",
            return_value=4,
        ), patch(
            "services.maintenance_service.send_reservation_deadline_reminders",
            return_value=5,
        ), patch(
            "services.maintenance_service.warn_items_nearing_freshness_deadline",
            return_value=6,
        ):
            result = app.test_cli_runner().invoke(args=["maintenance-sweep"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("2 reservation deadline(s) resolved", result.output)
        self.assertIn("5 reservation reminder(s) sent", result.output)
        self.assertIn("4 stale listing(s) deactivated", result.output)
        self.assertIn("6 freshness warning(s) sent", result.output)


if __name__ == "__main__":
    unittest.main()
