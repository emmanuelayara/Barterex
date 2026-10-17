import os
import unittest

os.environ["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

from app import app, db
from models import (
    Cart,
    CartItem,
    CreditTransaction,
    Item,
    LegacyCheckoutReconciliation,
    Order,
    OrderItem,
    Trade,
    User,
)
from services.legacy_checkout_reconciliation import reconcile_legacy_direct_checkouts


class LegacyCheckoutReconciliationTests(unittest.TestCase):
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
            username="legacy-buyer",
            email="legacy-buyer@example.com",
            password_hash="test-hash",
            credits=40,
        )
        self.seller = User(
            username="legacy-seller",
            email="legacy-seller@example.com",
            password_hash="test-hash",
        )
        db.session.add_all([self.buyer, self.seller])
        db.session.flush()
        self.item = Item(
            name="Legacy purchase",
            category="Electronics",
            user_id=self.buyer.id,
            owner_type="user",
            status="approved",
            is_approved=True,
            is_available=False,
            value=100,
        )
        db.session.add(self.item)
        db.session.flush()
        self.order = Order(
            user_id=self.buyer.id,
            delivery_method="pickup",
            status="Delivered",
            order_number="ORD-LEGACY-00001",
            total_credits=100,
            credits_used=100,
            credits_balance_before=140,
            credits_balance_after=40,
        )
        db.session.add(self.order)
        db.session.flush()
        db.session.add_all([
            OrderItem(order_id=self.order.id, item_id=self.item.id),
            Trade(
                sender_id=self.buyer.id,
                receiver_id=self.seller.id,
                item_id=self.item.id,
                item_received_id=self.item.id,
                status="completed",
            ),
        ])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_preview_is_read_only_and_apply_reverses_once(self):
        preview = reconcile_legacy_direct_checkouts()

        self.assertEqual(len(preview), 1)
        self.assertEqual(preview[0]["status"], "reversed")
        self.assertEqual(self.buyer.credits, 40)
        self.assertEqual(self.item.user_id, self.buyer.id)
        self.assertFalse(self.order.cancelled)
        self.assertEqual(LegacyCheckoutReconciliation.query.count(), 0)

        applied = reconcile_legacy_direct_checkouts(apply_changes=True)

        self.assertEqual(applied[0]["status"], "reversed")
        self.assertEqual(self.buyer.credits, 140)
        self.assertEqual(self.item.user_id, self.seller.id)
        self.assertFalse(self.item.is_available)
        self.assertTrue(self.order.cancelled)
        self.assertEqual(Trade.query.one().status, "cancelled")
        self.assertEqual(CreditTransaction.query.one().reason, "legacy_direct_checkout_reversal")

        repeated = reconcile_legacy_direct_checkouts(apply_changes=True)
        self.assertEqual(repeated, [])
        self.assertEqual(self.buyer.credits, 140)
        self.assertEqual(CreditTransaction.query.count(), 1)

    def test_ambiguous_order_is_reported_without_mutating_records(self):
        Trade.query.delete()
        db.session.commit()

        result = reconcile_legacy_direct_checkouts(apply_changes=True)

        self.assertEqual(result[0]["status"], "needs_review")
        self.assertEqual(self.buyer.credits, 40)
        self.assertEqual(self.item.user_id, self.buyer.id)
        self.assertFalse(self.order.cancelled)
        self.assertEqual(LegacyCheckoutReconciliation.query.one().status, "needs_review")
        self.assertEqual(CreditTransaction.query.count(), 0)

    def test_cart_checkout_endpoints_cannot_purchase_directly(self):
        checkout_item = Item(
            name="Checkout must be blocked",
            category="Electronics",
            user_id=self.seller.id,
            owner_type="user",
            status="approved",
            is_approved=True,
            is_available=True,
            value=25,
        )
        db.session.add(checkout_item)
        db.session.flush()
        cart = Cart(user_id=self.buyer.id)
        db.session.add(cart)
        db.session.flush()
        db.session.add(CartItem(cart_id=cart.id, item_id=checkout_item.id))
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as flask_session:
            flask_session["_user_id"] = str(self.buyer.id)
            flask_session["_fresh"] = True
            flask_session["pending_checkout_items"] = [checkout_item.id]
            flask_session["pending_delivery"] = {"method": "pickup"}

        checkout_response = client.get("/checkout")
        finalize_response = client.post("/finalize_purchase")
        add_to_cart_response = client.post(f"/add_to_cart/{checkout_item.id}")
        cart_response = client.get("/cart")

        self.assertEqual(checkout_response.status_code, 302)
        self.assertEqual(finalize_response.status_code, 302)
        self.assertEqual(add_to_cart_response.status_code, 302)
        self.assertEqual(cart_response.status_code, 302)
        self.assertTrue(cart_response.location.endswith("/favorites"))
        self.assertTrue(checkout_response.location.endswith("/favorites"))
        for path in ("/clear_cart", f"/remove_from_cart/{checkout_item.id}"):
            response = client.post(path)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.location.endswith("/favorites"))
        self.assertEqual(self.buyer.credits, 40)
        self.assertEqual(checkout_item.user_id, self.seller.id)
        self.assertTrue(checkout_item.is_available)
        self.assertEqual(CartItem.query.filter_by(item_id=checkout_item.id).count(), 1)

    def test_favorites_replace_cart_in_user_experience(self):
        client = app.test_client()
        with client.session_transaction() as flask_session:
            flask_session["_user_id"] = str(self.buyer.id)
            flask_session["_fresh"] = True

        response = client.get("/favorites")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertNotIn('data-tooltip="Favorites"', page)
        self.assertNotIn('data-tooltip="Revaluations"', page)
        self.assertNotIn('href="/cart"', page)
        self.assertNotIn('Shopping Cart', page)
        self.assertNotIn('add-to-cart', page)
        self.assertNotIn('added to your cart', page)

        response = client.get("/settings")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        sidebar = page.split('<div class="settings-tabs">', 1)[1].split(
            '<!-- Footer Links for Mobile -->', 1,
        )[0]
        self.assertIn('href="/favorites"', sidebar)
        self.assertIn('href="/my-revaluations"', sidebar)

        from models import Notification
        count = Notification.query.count()
        response = client.post("/api/notifications/cart/item-added", json={"item_id": self.item.id})
        self.assertEqual(response.status_code, 410)
        self.assertIn('error', response.get_json())
        self.assertEqual(Notification.query.count(), count)

    def test_favorites_still_save_reserve_and_remove_items(self):
        from flask import url_for
        from models import Favorite

        self.item.user_id = self.seller.id
        self.item.is_available = True
        db.session.commit()
        client = app.test_client()
        with client.session_transaction() as flask_session:
            flask_session["_user_id"] = str(self.buyer.id)
            flask_session["_fresh"] = True

        response = client.post(f"/api/favorites/toggle/{self.item.id}")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.get_json()["is_favorited"])
        self.assertEqual(Favorite.query.filter_by(user_id=self.buyer.id).count(), 1)
        response = client.get("/favorites")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        with app.test_request_context():
            reserve_url = url_for("marketplace.choose_backing_assets", item_id=self.item.id)
        self.assertIn(reserve_url, page)
        self.assertIn("Get with BXC", page)
        self.assertNotIn("added to your cart", page)
        self.assertNotIn("add-to-cart", page)
        response = client.post(f"/remove_from_favorites/{self.item.id}")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Favorite.query.filter_by(user_id=self.buyer.id).count(), 0)

        response = client.get("/notification-settings")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertNotIn("Cart Items", page)
        self.assertNotIn("data-pref=\"push_cart_items\"", page)
        self.assertIn("Order Updates", page)


if __name__ == "__main__":
    unittest.main()
