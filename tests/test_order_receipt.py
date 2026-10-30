import os
import re
import unittest
from datetime import datetime
from unittest.mock import patch

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from app import app, db
from models import Item, Order, OrderItem, PickupStation, Reservation, ReservationAsset, User
from reportlab.platypus import SimpleDocTemplate
from transaction_clarity import generate_pdf_receipt


class OrderReceiptTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.context = app.app_context()
        self.context.push()
        db.create_all()
        self.user = User(username='receipt-buyer', email='buyer@example.com', password_hash='x')
        self.other = User(username='other-buyer', email='other@example.com', password_hash='x')
        db.session.add_all([self.user, self.other])
        db.session.flush()
        self.item = Item(
            name='Camera & lens <Special Edition> with a complete accessory kit',
            item_number='BX-FULL-REFERENCE-123456789',
            condition='Like New', category='Electronics', value=900,
            user_id=self.user.id,
        )
        self.order = Order(
            user_id=self.user.id, order_number='ORD-RECEIPT-001',
            delivery_method='pickup', status='Pending',
            date_ordered=datetime(2026, 10, 23, 12, 30),
            total_credits=250, credits_used=250,
            credits_balance_before=1000, credits_balance_after=750,
        )
        db.session.add_all([self.item, self.order])
        db.session.flush()
        db.session.add(OrderItem(order_id=self.order.id, item_id=self.item.id))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def readable_pdf(self):
        def uncompressed_doc(*args, **kwargs):
            return SimpleDocTemplate(*args, pageCompression=0, **kwargs)

        with patch('transaction_clarity.SimpleDocTemplate', side_effect=uncompressed_doc):
            buffer = generate_pdf_receipt(self.order, self.user)
        self.assertIsNotNone(buffer)
        return buffer.getvalue()

    def assert_pdf_text(self, pdf, content):
        fragments = re.findall(rb'\(((?:\\.|[^\\)])*)\)\s*Tj', pdf)
        text = b''.join(re.sub(rb'\\([\\()])', rb'\1', part) for part in fragments)
        self.assertIn(re.sub(rb'\s+', b'', content), re.sub(rb'\s+', b'', text))

    def test_branded_receipt_preserves_references_and_order_time_amounts(self):
        pdf = self.readable_pdf()
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertIn(b'/Subtype /Image', pdf)
        for content in (
            b'BARTER EXPRESS', b'RECEIPT', b'ORD-RECEIPT-001', b'buyer@example.com',
            b'BX-FULL-REFERENCE-123456789', b'Special Edition', b'250.00 BXC',
            b'1,000.00 BXC', b'750.00 BXC', b'Page 1',
        ):
            self.assert_pdf_text(pdf, content)
        self.assertNotIn(b'900.00 BXC', pdf)

    def test_reservation_receipt_includes_backing_items_and_separate_fee(self):
        reservation = Reservation(
            user_id=self.user.id, item_id=self.item.id,
            provisional_credits_used=300, purchase_value=250,
            funding_mode='item_backed', status='completed',
            expires_at=datetime(2026, 10, 26), completed_at=datetime(2026, 10, 23),
            delivery_fee_status='paid',
        )
        backing = Item(
            name='Backing laptop', item_number='BACKING-1', category='Electronics',
            condition='Used', value=300, user_id=self.user.id,
        )
        db.session.add_all([reservation, backing])
        db.session.flush()
        db.session.add(ReservationAsset(
            reservation_id=reservation.id, item_id=backing.id,
            amount=300, verification_status='passed',
        ))
        self.order.reservation = reservation
        self.order.delivery_method = 'home delivery'
        self.order.delivery_address = '12 Long Street, Lagos & environs'
        self.order.logistics_fee_naira = 1500
        db.session.commit()

        pdf = self.readable_pdf()
        for content in (
            b'RESERVATION & FUNDING', b'Backing laptop', b'300.00 BXC',
            b'1,500.00 NGN', b'Paid', b'non-refundable',
        ):
            self.assert_pdf_text(pdf, content)

    def test_pickup_and_cancellation_details_are_retained(self):
        self.order.pickup_station = PickupStation(
            name='Central Station', address='10 Market Street', city='Ikeja', state='Lagos',
        )
        self.order.cancelled = True
        self.order.status = 'Cancelled'
        self.order.cancelled_at = datetime(2026, 10, 24)
        self.order.cancellation_reason = 'Customer requested cancellation'
        self.order.credits_balance_before = None
        db.session.commit()

        pdf = self.readable_pdf()
        self.assertIn(b'Central Station', pdf)
        self.assertIn(b'CANCELLATION RECORD', pdf)
        self.assertIn(b'Customer requested cancellation', pdf)
        self.assertIn(b'Not recorded', pdf)

    def test_many_items_paginate_with_repeated_table_headers(self):
        for index in range(45):
            item = Item(
                name=f'Accessory set {index} with a long description that must wrap safely',
                item_number=f'LONG-ITEM-REFERENCE-{index:04d}',
                category='Electronics', condition='Like New', value=10, user_id=self.user.id,
            )
            db.session.add(item)
            db.session.flush()
            db.session.add(OrderItem(order_id=self.order.id, item_id=item.id))
        db.session.commit()

        pdf = self.readable_pdf()
        self.assertIn(b'Page 2', pdf)
        self.assert_pdf_text(pdf, b'LONG-ITEM-REFERENCE-0044')
        self.assertGreater(pdf.count(b'Item reference'), 1)

    def login(self, user):
        client = app.test_client()
        with client.session_transaction() as session:
            session['_user_id'] = str(user.id)
            session['_fresh'] = True
        return client

    def test_download_returns_pdf_attachment_and_records_download(self):
        response = self.login(self.user).get(f'/order/{self.order.id}/download-receipt')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/pdf')
        self.assertIn('Receipt-ORD-RECEIPT-001.pdf', response.headers['Content-Disposition'])
        self.assertTrue(response.data.startswith(b'%PDF-'))
        self.assertTrue(db.session.get(Order, self.order.id).receipt_downloaded)
        response.close()

    def test_other_user_cannot_download_receipt(self):
        with patch('routes.user.generate_pdf_receipt') as generate:
            response = self.login(self.other).get(f'/order/{self.order.id}/download-receipt')
        self.assertEqual(response.status_code, 302)
        generate.assert_not_called()
        self.assertFalse(db.session.get(Order, self.order.id).receipt_downloaded)


if __name__ == '__main__':
    unittest.main()
