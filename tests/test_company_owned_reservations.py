import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from app import app, db
from models import (
    ClearingInventoryItem,
    CreditTransaction,
    Item,
    Order,
    Reservation,
    ReservationAsset,
    Trade,
    User,
)
from services.reservation_service import (
    cancel_reservation,
    create_reservation,
    release_expired_reservations,
    verify_backing_asset,
)


class CompanyOwnedReservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            WTF_CSRF_ENABLED=False,
        )

    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()
        self.notification_patches = [
            patch('services.reservation_service._notice'),
            patch('services.reservation_service.notify_admins'),
        ]
        for notification_patch in self.notification_patches:
            notification_patch.start()

    def tearDown(self):
        for notification_patch in self.notification_patches:
            notification_patch.stop()
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _create_company_item(self, buyer_credits=0, buyer_provisional=0):
        buyer = User(
            username='company-buyer',
            email='company-buyer@example.com',
            password_hash='test-hash',
            credits=buyer_credits,
            provisional_credits=buyer_provisional,
        )
        former_owner = User(
            username='former-owner',
            email='former-owner@example.com',
            password_hash='test-hash',
            credits=0,
            provisional_credits=0,
        )
        db.session.add_all([buyer, former_owner])
        db.session.flush()

        company_item = Item(
            name='Company-owned item',
            category='Electronics',
            user_id=None,
            owner_type='barterex',
            value=250,
            status='approved',
            is_approved=True,
            is_available=True,
            provisional_credit_settled=True,
        )
        inventory_record = ClearingInventoryItem(
            item=company_item,
            source_user_id=former_owner.id,
            acquisition_value=250,
            status='held_for_resale',
        )
        db.session.add_all([company_item, inventory_record])
        db.session.commit()
        return buyer, former_owner, company_item, inventory_record

    def _create_backing_item(self, buyer, value=250):
        backing_item = Item(
            name='Buyer backing item',
            category='Electronics',
            user_id=buyer.id,
            value=value,
            status='approved',
            is_approved=True,
            is_available=True,
            provisional_credit_amount=value,
            provisional_credit_settled=False,
        )
        db.session.add(backing_item)
        db.session.commit()
        return backing_item

    def test_spendable_purchase_completes_without_payment_to_former_owner(self):
        buyer, former_owner, item, inventory_record = self._create_company_item(
            buyer_credits=500
        )

        with patch('trading_points.award_points_for_purchase', return_value=None):
            reservation, error = create_reservation(
                buyer, item, [], funding_mode='spendable'
            )

        self.assertIsNone(error)
        db.session.refresh(buyer)
        db.session.refresh(former_owner)
        db.session.refresh(item)
        db.session.refresh(inventory_record)
        self.assertEqual(reservation.status, 'completed')
        self.assertEqual(buyer.credits, 250)
        self.assertEqual(former_owner.credits, 0)
        self.assertEqual(former_owner.provisional_credits, 0)
        self.assertEqual(
            CreditTransaction.query.filter_by(user_id=former_owner.id).count(), 0
        )
        self.assertEqual(CreditTransaction.query.filter_by(
            user_id=buyer.id, reason='reservation_purchase'
        ).count(), 1)
        self.assertEqual(item.user_id, buyer.id)
        self.assertEqual(item.owner_type, 'user')
        self.assertFalse(item.is_available)
        self.assertEqual(inventory_record.status, 'sold')
        self.assertEqual(inventory_record.source_user_id, former_owner.id)
        self.assertIsNone(inventory_record.reservation_asset_id)
        self.assertEqual(Order.query.filter_by(reservation_id=reservation.id).count(), 1)
        self.assertEqual(Trade.query.filter_by(item_id=item.id).count(), 0)

    def test_item_backed_purchase_settles_after_backing_verification(self):
        buyer, former_owner, item, inventory_record = self._create_company_item(
            buyer_credits=80,
            buyer_provisional=250,
        )
        backing_item = self._create_backing_item(buyer)
        reservation, error = create_reservation(
            buyer,
            item,
            [backing_item.id],
            funding_mode='item_backed',
            consent_confirmed=True,
        )
        self.assertIsNone(error)
        self.assertEqual(reservation.status, 'active')
        self.assertEqual(reservation.seller_item_verification_status, 'passed')

        with patch('trading_points.award_points_for_purchase', return_value=None):
            ok, error = verify_backing_asset(
                ReservationAsset.query.filter_by(reservation_id=reservation.id).one(),
                passed=True,
            )

        self.assertTrue(ok, error)
        db.session.refresh(buyer)
        db.session.refresh(former_owner)
        db.session.refresh(item)
        db.session.refresh(inventory_record)
        self.assertEqual(reservation.status, 'completed')
        self.assertEqual(buyer.credits, 80)
        self.assertEqual(buyer.provisional_credits, 0)
        self.assertEqual(former_owner.credits, 0)
        self.assertEqual(
            CreditTransaction.query.filter_by(user_id=former_owner.id).count(), 0
        )
        self.assertEqual(CreditTransaction.query.filter_by(
            user_id=buyer.id, reason='reservation_purchase'
        ).count(), 1)
        self.assertEqual(item.user_id, buyer.id)
        self.assertEqual(inventory_record.status, 'sold')
        self.assertEqual(inventory_record.source_user_id, former_owner.id)
        self.assertEqual(Trade.query.filter_by(item_id=item.id).count(), 0)
        self.assertEqual(Order.query.filter_by(reservation_id=reservation.id).count(), 1)

    def test_cancellation_releases_funding_and_relists_company_item(self):
        buyer, former_owner, item, inventory_record = self._create_company_item(
            buyer_credits=50,
            buyer_provisional=250,
        )
        backing_item = self._create_backing_item(buyer)
        reservation, error = create_reservation(
            buyer,
            item,
            [backing_item.id],
            funding_mode='item_backed',
            consent_confirmed=True,
        )
        self.assertIsNone(error)

        ok, error = cancel_reservation(reservation, buyer)

        self.assertTrue(ok, error)
        db.session.refresh(buyer)
        db.session.refresh(item)
        db.session.refresh(backing_item)
        db.session.refresh(inventory_record)
        self.assertEqual(reservation.status, 'cancelled')
        self.assertEqual(buyer.provisional_credits, 250)
        self.assertEqual(item.owner_type, 'barterex')
        self.assertIsNone(item.user_id)
        self.assertTrue(item.is_available)
        self.assertEqual(inventory_record.status, 'held_for_resale')
        self.assertIsNone(inventory_record.reservation_id)
        self.assertIsNone(inventory_record.reservation_asset_id)
        self.assertTrue(backing_item.is_available)
        self.assertIsNone(backing_item.locked_for_reservation_id)
        self.assertEqual(former_owner.id, inventory_record.source_user_id)

    def test_expiry_releases_funding_and_relists_company_item(self):
        buyer, former_owner, item, inventory_record = self._create_company_item(
            buyer_credits=50,
            buyer_provisional=250,
        )
        backing_item = self._create_backing_item(buyer)
        reservation, error = create_reservation(
            buyer,
            item,
            [backing_item.id],
            funding_mode='item_backed',
            consent_confirmed=True,
        )
        self.assertIsNone(error)
        reservation.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()

        self.assertEqual(release_expired_reservations(item_id=item.id), 1)

        db.session.refresh(buyer)
        db.session.refresh(item)
        db.session.refresh(backing_item)
        db.session.refresh(inventory_record)
        self.assertEqual(reservation.status, 'expired')
        self.assertEqual(buyer.provisional_credits, 250)
        self.assertEqual(item.owner_type, 'barterex')
        self.assertTrue(item.is_available)
        self.assertEqual(inventory_record.status, 'held_for_resale')
        self.assertTrue(backing_item.is_available)
        self.assertEqual(former_owner.id, inventory_record.source_user_id)

    def test_failed_backing_verification_releases_company_item_for_resale(self):
        buyer, former_owner, item, inventory_record = self._create_company_item(
            buyer_credits=50,
            buyer_provisional=250,
        )
        backing_item = self._create_backing_item(buyer)
        reservation, error = create_reservation(
            buyer,
            item,
            [backing_item.id],
            funding_mode='item_backed',
            consent_confirmed=True,
        )
        self.assertIsNone(error)
        asset = ReservationAsset.query.filter_by(reservation_id=reservation.id).one()

        ok, error = verify_backing_asset(asset, passed=False)

        self.assertTrue(ok, error)
        db.session.refresh(buyer)
        db.session.refresh(item)
        db.session.refresh(inventory_record)
        self.assertEqual(reservation.status, 'cancelled')
        self.assertEqual(buyer.provisional_credits, 250)
        self.assertEqual(item.owner_type, 'barterex')
        self.assertTrue(item.is_available)
        self.assertEqual(inventory_record.status, 'held_for_resale')
        self.assertEqual(former_owner.id, inventory_record.source_user_id)


if __name__ == '__main__':
    unittest.main()
