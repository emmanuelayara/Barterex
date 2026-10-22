import os
import unittest

os.environ["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

from app import app, db
from models import Item, Reservation, User


class ReservationProfileGateTests(unittest.TestCase):
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

        self.buyer = User(
            username="incomplete-buyer",
            email="buyer@example.com",
            password_hash="test-hash",
        )
        self.seller = User(
            username="seller",
            email="seller@example.com",
            password_hash="test-hash",
        )
        db.session.add_all([self.buyer, self.seller])
        db.session.flush()
        self.item = Item(
            name="Available item",
            category="Electronics",
            user_id=self.seller.id,
            owner_type="user",
            status="approved",
            is_approved=True,
            is_available=True,
            value=100,
        )
        db.session.add(self.item)
        db.session.commit()

        self.client = app.test_client()
        with self.client.session_transaction() as flask_session:
            flask_session["_user_id"] = str(self.buyer.id)
            flask_session["_fresh"] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_incomplete_profile_cannot_open_or_submit_reservation(self):
        chooser_response = self.client.get(
            f"/item/{self.item.id}/choose-backing-assets"
        )
        reserve_response = self.client.post(f"/item/{self.item.id}/reserve")

        expected_settings_url = "/settings?edit=profile#profile"
        self.assertEqual(chooser_response.status_code, 302)
        self.assertTrue(chooser_response.location.endswith(expected_settings_url))
        self.assertEqual(reserve_response.status_code, 302)
        self.assertTrue(reserve_response.location.endswith(expected_settings_url))
        self.assertEqual(Reservation.query.count(), 0)

    def test_item_page_prompts_incomplete_user_to_complete_profile(self):
        response = self.client.get(f"/item/{self.item.id}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Complete your profile to reserve", response.data)
        self.assertNotIn(b"Get with BXC", response.data)
