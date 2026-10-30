import os
import unittest
from datetime import datetime, timedelta

os.environ["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

from flask import url_for

from app import app, db
from models import Item, Order, Reservation, User


class SettingsNavigationTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.context = app.app_context()
        self.context.push()
        db.create_all()
        user = User(
            username="settings-user",
            email="settings@example.com",
            password_hash="test-hash",
        )
        db.session.add(user)
        db.session.commit()
        self.user_id = user.id
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["_user_id"] = str(user.id)
            session["_fresh"] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_logout_is_in_settings_sidebar_before_delete_not_top_navbar(self):
        response = self.client.get("/settings")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        with app.test_request_context():
            logout_link = f'href="{url_for("auth.logout")}"'
        navbar = html.split('<header id="navbar"', 1)[1].split("</header>", 1)[0]
        sidebar = html.split('<aside class="st-sidebar"', 1)[1].split("</aside>", 1)[0]
        self.assertNotIn(logout_link, navbar)
        self.assertEqual(html.count(logout_link), 1)
        logout_position = sidebar.index(logout_link)
        delete_position = sidebar.index('data-tab="delete"')
        self.assertLess(logout_position, delete_position)
        self.assertRegex(
            sidebar[logout_position:],
            r'Logout</a>\s*<button[^>]+data-tab="delete"',
        )

    def test_valuations_link_is_beside_reservations_and_active_on_valuations(self):
        with app.test_request_context():
            valuations_url = url_for("user.my_valuations")
            reservations_url = url_for("user.my_reservations")
        for path, active in (("/settings", False), (valuations_url, True)):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                navbar = response.get_data(as_text=True).split(
                    '<header id="navbar"', 1
                )[1].split("</header>", 1)[0]
                self.assertRegex(
                    navbar,
                    rf'href="{reservations_url}"[^<]*>[\s\S]*?</a>\s*</li>\s*'
                    rf'<li>\s*<a href="{valuations_url}"',
                )
                active_class = " is-active" if active else ""
                self.assertIn(
                    f'href="{valuations_url}" class="bx-nav__link{active_class}"',
                    navbar,
                )

    def test_reservations_badge_counts_only_current_users_pending_items(self):
        other = User(username="other", email="other@example.com", password_hash="test")
        db.session.add(other)
        db.session.flush()
        item = Item(name="Test item", user_id=other.id, category="Electronics")
        db.session.add(item)
        db.session.flush()
        now = datetime.utcnow()
        future, past = now + timedelta(hours=12), now - timedelta(hours=12)
        cases = [
            (self.user_id, "active", future, None, None),
            (self.user_id, "awaiting_consent", past, None, future),
            (self.user_id, "active", past, None, None),
            (self.user_id, "active", future, past, None),
            (self.user_id, "awaiting_consent", future, None, past),
            (self.user_id, "completed", future, None, None),
            (self.user_id, "cancelled", future, None, None),
            (self.user_id, "expired", future, None, None),
            (other.id, "active", future, None, None),
        ]
        for user_id, status, expires, shortfall, consent in cases:
            db.session.add(Reservation(
                user_id=user_id, item_id=item.id, provisional_credits_used=100,
                status=status, expires_at=expires,
                revaluation_shortfall_expires_at=shortfall,
                title_transfer_decision_expires_at=consent,
            ))
        db.session.commit()
        response = self.client.get("/settings")
        self.assertEqual(response.status_code, 200)
        navbar = response.get_data(as_text=True).split(
            '<header id="navbar"', 1
        )[1].split("</header>", 1)[0]
        self.assertIn('class="bx-nav__badge" aria-hidden="true">2</span>', navbar)
        self.assertIn('aria-label="Reservations, 2 pending"', navbar)

        Reservation.query.filter_by(user_id=self.user_id).update({"status": "completed"})
        db.session.commit()
        response = self.client.get("/settings")
        self.assertNotIn(b'class="bx-nav__badge"', response.data)

    def test_guest_has_no_reservations_badge(self):
        with self.client.session_transaction() as session:
            session.clear()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'class="bx-nav__badge"', response.data)

    def test_orders_and_valuations_badges_count_only_users_pending_records(self):
        other = User(username="other", email="other@example.com", password_hash="test")
        db.session.add(other)
        db.session.flush()
        for owner in (self.user_id, other.id):
            for status in ("valuation_only", "pending_activation", "approved", "rejected"):
                db.session.add(Item(
                    name="Test item", user_id=owner, category="Electronics", status=status,
                ))
            for index, (status, cancelled) in enumerate((
                ("Pending", False), ("Processing", False), ("Shipped", False),
                ("Ready for Pickup", False), ("Delivered", False),
                ("Cancelled", False), ("Pending", True),
            )):
                db.session.add(Order(
                    user_id=owner, order_number=f"TEST-{owner}-{index}",
                    delivery_method="pickup", status=status, cancelled=cancelled,
                ))
        db.session.commit()
        response = self.client.get("/settings")
        self.assertEqual(response.status_code, 200)
        navbar = response.get_data(as_text=True).split(
            '<header id="navbar"', 1
        )[1].split("</header>", 1)[0]
        self.assertIn('aria-label="Orders, 4 pending"', navbar)
        self.assertIn('aria-label="Valuations, 2 pending"', navbar)
        self.assertIn('class="bx-nav__badge" aria-hidden="true">4</span>', navbar)
        self.assertIn('class="bx-nav__badge" aria-hidden="true">2</span>', navbar)

        Order.query.filter_by(user_id=self.user_id).update({"status": "Delivered"})
        Item.query.filter_by(user_id=self.user_id).update({"status": "approved"})
        db.session.commit()
        response = self.client.get("/settings")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'class="bx-nav__badge"', response.data)


if __name__ == "__main__":
    unittest.main()
