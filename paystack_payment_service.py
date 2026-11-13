"""
Paystack Payment Service
Handles all payment processing, verification, and credit allocation using Paystack
"""

import os
import requests
import json
import hashlib
import hmac
from datetime import datetime, timedelta
from dotenv import load_dotenv
from models import Payment, Reservation, User, CreditTransaction
from app import db
from services.email_notifications import notify_user, notify_admins
from flask import current_app

load_dotenv()

class PaystackPaymentService:
    """
    Service class for handling Paystack payment operations
    """
    
    BASE_URL = os.getenv('PAYSTACK_API_URL', 'https://api.paystack.co')
    SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY')
    PUBLIC_KEY = os.getenv('PAYSTACK_PUBLIC_KEY')
    CALLBACK_URL = os.getenv('PAYMENT_CALLBACK_URL')
    
    # Enable test mode for development (no real API calls)
    _payment_test_mode_env = os.getenv('PAYMENT_TEST_MODE', 'false')
    TEST_MODE = _payment_test_mode_env.lower() == 'true'
    
    # Conversion rate: 1 Naira = 1 Credit
    CONVERSION_RATE = 1.0
    
    # Minimum and maximum amounts (in Naira)
    MIN_AMOUNT = 100  # Minimum ₦100
    MAX_AMOUNT = 1000000  # Maximum ₦1,000,000

    @staticmethod
    def initiate_delivery_fee_payment(reservation, user):
        """Retired endpoint: never create or reuse a logistics checkout."""
        return {'success': False, 'error': 'Only verification-centre collection is available. Delivery-fee payments are disabled.'}

    @staticmethod
    def initiate_service_fee_payment(reservation, user):
        return PaystackPaymentService._initiate_reservation_fee(reservation, user, 'reservation_service_fee')

    @staticmethod
    def _initiate_reservation_fee(reservation, user, purpose):
        if purpose != 'reservation_service_fee':
            return {'success': False, 'error': 'Delivery-fee payments are disabled. Use verification-centre collection.'}
        if reservation.user_id != user.id:
            return {'success': False, 'error': 'You can only pay fees for your own reservation.'}
        from services.reservation_service import _lock_reservation_for_update

        reservation = _lock_reservation_for_update(reservation.id)
        if not reservation or reservation.user_id != user.id:
            return {'success': False, 'error': 'This reservation is no longer available for payment.'}
        from services.reservation_service import _service_fee_ready, FINAL_TERMS_VERSION
        if (
            reservation.delivery_method != 'pickup'
            or not _service_fee_ready(reservation)
            or reservation.service_fee_status != 'awaiting_payment'
            or not reservation.final_terms_accepted_at
            or reservation.final_terms_version != FINAL_TERMS_VERSION
            or not reservation.service_fee_deadline
            or reservation.service_fee_deadline <= datetime.utcnow()
        ):
            return {'success': False, 'error': 'Verification-centre collection, verification and final acceptance are required within the payment deadline.'}
        if reservation.status != 'active' or reservation.expires_at <= datetime.utcnow():
            return {'success': False, 'error': 'This reservation is closed or expired; a new reservation-fee payment cannot be started.'}

        amount_naira = float(reservation.service_fee_naira or 0)
        if not PaystackPaymentService.MIN_AMOUNT <= amount_naira <= PaystackPaymentService.MAX_AMOUNT:
            return {'success': False, 'error': 'The reservation fee is outside Paystack payment limits.'}

        existing = Payment.query.filter_by(
            reservation_id=reservation.id,
            purpose=purpose,
        ).filter(Payment.status.in_(('pending', 'test_pending'))).order_by(
            Payment.created_at.desc()
        ).first()
        if existing:
            if round(existing.amount_naira * 100) != round(amount_naira * 100):
                return {'success': False, 'error': 'The pending payment amount differs from the reservation fee. Contact support.'}
            payment_link = None
            if existing.status == 'test_pending':
                payment_link = f'/payments/verify-payment/{existing.paystack_reference}?test=true'
            else:
                payment_link = (
                    (existing.payment_metadata or {}).get('paystack_response', {}).get('authorization_url')
                )
            if payment_link:
                return {
                    'success': True,
                    'payment_link': payment_link,
                    'reference': existing.paystack_reference,
                    'payment_id': existing.id,
                }
            return {'success': False, 'error': 'The pending Paystack payment link is unavailable.'}

        payment = Payment(
            user_id=user.id,
            amount_naira=amount_naira,
            credits_purchased=0,
            status='pending',
            purpose=purpose,
            reservation_id=reservation.id,
            customer_email=user.email,
            customer_phone=user.phone_number,
            expires_at=reservation.service_fee_deadline,
        )
        metadata = {
            'purpose': purpose,
            'reservation_id': reservation.id,
        }
        metadata.update(order_id=reservation.order.id, final_terms_version=reservation.final_terms_version)

        if PaystackPaymentService.TEST_MODE:
            import uuid
            reference = f'TEST_{uuid.uuid4().hex[:12].upper()}'
            payment.paystack_reference = reference
            payment.status = 'test_pending'
            payment.payment_metadata = {'mode': 'test', **metadata}
            db.session.add(payment)
            db.session.flush()
            PaystackPaymentService._notify_service_fee_link(
                reservation, f'/payments/verify-payment/{reference}?test=true'
            )
            db.session.commit()
            return {
                'success': True,
                'payment_link': f'/payments/verify-payment/{reference}?test=true',
                'reference': reference,
                'payment_id': payment.id,
                'test_mode': True,
            }

        import uuid
        reference = f'barterxpress-service-{reservation.id}-{uuid.uuid4().hex[:12]}'
        payment.paystack_reference = reference
        db.session.add(payment)
        db.session.commit()
        payload = {
            'email': user.email,
            'amount': int(round(amount_naira * 100)),
            'currency': 'NGN',
            'reference': reference,
            'callback_url': PaystackPaymentService.CALLBACK_URL,
            'metadata': metadata,
            'channels': ['card', 'bank_transfer'],
        }
        try:
            response = requests.post(
                f'{PaystackPaymentService.BASE_URL}/transaction/initialize',
                json=payload,
                headers=PaystackPaymentService.get_auth_header(),
                timeout=30,
            )
        except requests.RequestException as error:
            payment.error_message = f'Paystack initialization outcome is unknown: {error}'
            db.session.commit()
            return {
                'success': False,
                'error': 'Paystack could not confirm payment initialization. Contact support before retrying.',
            }

        try:
            data = response.json() if response.text else {}
        except ValueError as error:
            payment.error_message = f'Paystack returned an invalid initialization response: {error}'
            db.session.commit()
            return {
                'success': False,
                'error': 'Paystack returned an invalid response. Contact support before retrying.',
            }
        if response.status_code != 200 or not data.get('status'):
            payment.status = 'failed'
            payment.error_message = data.get(
                'message',
                f'Payment initialization failed (HTTP {response.status_code})',
            )
            db.session.commit()
            return {
                'success': False,
                'error': payment.error_message,
            }

        response_data = data.get('data', {})
        authorization_url = response_data.get('authorization_url')
        if not authorization_url:
            payment.error_message = 'Paystack did not return an authorization URL.'
            db.session.commit()
            return {
                'success': False,
                'error': 'Paystack did not return a payment link. Contact support before retrying.',
            }
        payment.paystack_reference = response_data.get('reference', reference)
        payment.payment_metadata = {
            **metadata,
            'paystack_response': response_data,
        }
        db.session.add(payment)
        PaystackPaymentService._notify_service_fee_link(reservation, authorization_url)
        db.session.commit()
        return {
            'success': True,
            'payment_link': authorization_url,
            'reference': payment.paystack_reference,
            'payment_id': payment.id,
        }

    @staticmethod
    def _notify_service_fee_link(reservation, payment_link):
        from flask import url_for, has_request_context
        from services.reservation_service import service_fee_email_details
        if payment_link.startswith('/'):
            if has_request_context():
                payment_link = url_for('payments.verify_payment',
                                       reference=payment_link.split('/')[-1].split('?')[0],
                                       test='true', _external=True)
            else:
                payment_link = current_app.config['APP_URL'].rstrip('/') + payment_link
        notify_user(
            reservation.user,
            f"Pay the NGN {reservation.service_fee_naira:,.2f} service fee for order "
            f"{reservation.order.order_number}. Collection is at your verification centre. "
            f"Payment deadline: {reservation.service_fee_deadline:%d %b %Y, %H:%M UTC}.",
            subject='Your order service-fee payment link',
            details=service_fee_email_details(reservation),
            cta_endpoint=None, cta_label='Pay service fee', cta_url=payment_link,
        )

    @staticmethod
    def _complete_service_fee_payment(payment, payment_method):
        from services.reservation_service import (
            _lock_reservation_for_update, _resolve_reservation, FINAL_TERMS_VERSION,
        )
        reservation = _lock_reservation_for_update(payment.reservation_id)
        if (
            not reservation or reservation.user_id != payment.user_id
            or not reservation.final_terms_accepted_at
            or reservation.final_terms_version != FINAL_TERMS_VERSION
            or round(float(reservation.service_fee_naira or 0) * 100) != round(payment.amount_naira * 100)
        ):
            raise ValueError('Service-fee payment does not match the accepted reservation terms.')
        payment.status = 'completed'
        payment.paid_at = datetime.utcnow()
        payment.payment_method = payment_method
        reservation.service_fee_status = 'paid'
        # A late provider confirmation must never resurrect or release a closed reservation.
        if (
            reservation.delivery_method != 'pickup'
            or reservation.status != 'active'
            or reservation.expires_at <= datetime.utcnow()
        ):
            payment.error_message = 'Service fee received for a closed, expired or retired reservation; support reconciliation required.'
            current_app.logger.warning('Unfulfillable service-fee payment %s for reservation %s', payment.id, reservation.id)
            notify_user(reservation.user, 'Your service-fee payment was received for a closed, expired '
                        'or retired reservation. No item was released. Contact support for payment resolution.',
                        subject='Service-fee payment needs support review')
            notify_admins('orders.manage', 'Service-fee payment needs reconciliation',
                          f'Payment {payment.id} for reservation {reservation.id} requires reconciliation.')
            return False
        settled = _resolve_reservation(reservation)
        if not settled:
            raise ValueError('Paid service-fee reservation no longer satisfies settlement requirements.')
        return True

    @staticmethod
    def _complete_delivery_fee_payment(payment, payment_method):
        from services.reservation_service import _lock_reservation_for_update

        reservation = _lock_reservation_for_update(payment.reservation_id)
        if not reservation or reservation.user_id != payment.user_id:
            raise ValueError('The reservation linked to this delivery payment no longer exists.')
        if (
            round(float(reservation.delivery_quote_naira or 0) * 100)
            != round(float(payment.amount_naira) * 100)
        ):
            raise ValueError('The accepted delivery quote does not match this payment.')
        if reservation.delivery_fee_status == 'paid':
            payment.status = 'completed'
            payment.paid_at = payment.paid_at or datetime.utcnow()
            payment.payment_method = payment_method
            return False
        if reservation.delivery_fee_status != 'awaiting_payment':
            raise ValueError('This reservation is not waiting for delivery-fee payment.')
        payment.status = 'completed'
        payment.paid_at = datetime.utcnow()
        payment.payment_method = payment_method
        reservation.delivery_fee_status = 'paid'
        if reservation.status == 'active':
            from services.reservation_service import _cancel_reservation
            if reservation.expires_at <= datetime.utcnow():
                _cancel_reservation(reservation, new_status='expired', relist_seller_item=True, relist_assets=True)
        payment.error_message = 'Payment for a retired logistics booking; support reconciliation required.'
        notify_admins(
            'settlement.manage',
            'Payment received for a retired booking',
            f"Reservation {reservation.id} is {reservation.status}; payment {payment.id} "
            "requires reconciliation. No item was released or booking reopened.",
            cta_endpoint='admin.settlement_queue',
            cta_label='Open Settlement Queue',
        )
        notify_user(
            reservation.user_id,
            f"A payment was received for retired reservation {reservation.id}. "
            "No item was released or booking reopened. Contact support for payment reconciliation.",
            subject="Retired booking payment needs review",
            cta_endpoint='user.my_reservations',
            cta_label='View My Reservations',
            notification_type='reservation',
        )
        return False
    
    @staticmethod
    def get_auth_header():
        """
        Generate Auth header with Bearer token for Paystack API requests
        
        Returns:
            dict: Authorization header with secret key
        """
        return {
            'Authorization': f'Bearer {PaystackPaymentService.SECRET_KEY}',
            'Content-Type': 'application/json',
        }
    
    @staticmethod
    def initiate_payment(user_id, amount_naira):
        """
        Initiate a payment request with Paystack
        
        Args:
            user_id: ID of the user
            amount_naira: Amount in Nigerian Naira
            
        Returns:
            dict: Paystack response with payment link or error
        """
        try:
            user = User.query.get(user_id)
            if not user:
                return {'success': False, 'error': 'User not found'}
            
            # Validate amount
            amount_naira = float(amount_naira)
            if amount_naira < PaystackPaymentService.MIN_AMOUNT:
                return {'success': False, 'error': f'Minimum amount is ₦{PaystackPaymentService.MIN_AMOUNT}'}
            if amount_naira > PaystackPaymentService.MAX_AMOUNT:
                return {'success': False, 'error': f'Maximum amount is ₦{PaystackPaymentService.MAX_AMOUNT}'}
            
            # Calculate credits (1 naira = 1 credit)
            credits = int(amount_naira * PaystackPaymentService.CONVERSION_RATE)
            
            # Create payment record
            payment = Payment(
                user_id=user_id,
                amount_naira=amount_naira,
                credits_purchased=credits,
                status='pending',
                customer_email=user.email,
                customer_phone=user.phone_number,
                expires_at=datetime.utcnow() + timedelta(hours=24)
            )
            
            # TEST MODE: Return mock payment link for development
            if PaystackPaymentService.TEST_MODE:
                import uuid
                mock_reference = f'TEST_{uuid.uuid4().hex[:12].upper()}'
                payment.paystack_reference = mock_reference
                payment.status = 'test_pending'
                payment.payment_metadata = {'mode': 'test', 'test_note': 'This is a test payment'}
                
                db.session.add(payment)
                db.session.commit()
                
                # Return a test payment link that redirects to success page
                mock_link = f'/payments/verify-payment/{mock_reference}?test=true'
                
                print(f'[TEST MODE] Paystack Payment created: {mock_reference} for {amount_naira} naira ({credits} credits)')
                
                return {
                    'success': True,
                    'payment_link': mock_link,
                    'reference': mock_reference,
                    'payment_id': payment.id,
                    'test_mode': True
                }
            
            # PRODUCTION MODE: Make real API call to Paystack
            # Paystack expects amount in kobo (1 Naira = 100 kobo)
            amount_kobo = int(amount_naira * 100)
            
            import uuid
            reference = f'barterxpress-{user_id}-{int(datetime.utcnow().timestamp())}'
            
            payload = {
                'email': user.email,
                'amount': amount_kobo,  # Amount in kobo
                'currency': 'NGN',
                'reference': reference,
                'callback_url': PaystackPaymentService.CALLBACK_URL,
                'metadata': {
                    'user_id': user_id,
                    'username': user.username,
                    'credits': credits,
                    'source': 'barterex_credit_purchase'
                }
            }
            
            headers = PaystackPaymentService.get_auth_header()
            
            # Initialize transaction with Paystack
            api_url = f'{PaystackPaymentService.BASE_URL}/transaction/initialize'
            print(f'[PAYSTACK API] Calling: {api_url}')
            print(f'[PAYSTACK API] Payload: {json.dumps(payload, indent=2)}')
            
            response = requests.post(
                api_url,
                json=payload,
                headers=headers,
                timeout=30
            )
            
            print(f'[PAYSTACK API] Response Status: {response.status_code}')
            print(f'[PAYSTACK API] Response Body: {response.text}')
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('status'):  # Paystack returns 'status': True for success
                    response_data = data.get('data', {})
                    
                    # Store Paystack reference
                    payment.paystack_reference = response_data.get('reference')
                    payment.payment_metadata = {'paystack_response': response_data}
                    
                    db.session.add(payment)
                    db.session.commit()
                    
                    return {
                        'success': True,
                        'payment_link': response_data.get('authorization_url'),
                        'reference': payment.paystack_reference,
                        'payment_id': payment.id,
                        'access_code': response_data.get('access_code')
                    }
                else:
                    return {
                        'success': False,
                        'error': data.get('message', 'Payment initialization failed')
                    }
            else:
                error_data = response.json() if response.text else {}
                print(f'[ERROR] Paystack API returned {response.status_code}')
                print(f'[ERROR] Response: {response.text}')
                return {
                    'success': False,
                    'error': error_data.get('message', f'Payment initialization failed (HTTP {response.status_code})'),
                    'status_code': response.status_code,
                    'full_response': error_data
                }
                
        except requests.RequestException as e:
            print(f'[ERROR] Requests exception in payment: {str(e)}')
            return {'success': False, 'error': f'Request failed: {str(e)}'}
        except Exception as e:
            print(f'[ERROR] Payment service error: {str(e)}')
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': f'Server error: {str(e)}'}
    
    @staticmethod
    def verify_payment(reference):
        """
        Verify a payment with Paystack
        
        Args:
            reference: Paystack transaction reference
            
        Returns:
            dict: Payment verification result
        """
        try:
            # Check both paystack_reference and monnify_reference for backwards compatibility
            payment = Payment.query.filter_by(
                paystack_reference=reference
            ).first()
            
            if not payment:
                payment = Payment.query.filter_by(
                    monnify_reference=reference
                ).first()
            
            if not payment:
                return {'success': False, 'error': 'Payment record not found'}

            if payment.status == 'completed':
                return {
                    'success': True,
                    'message': 'Payment already verified',
                    'credits_added': 0,
                    'new_balance': User.query.get(payment.user_id).credits,
                }
            
            # TEST MODE: Auto-complete test payments
            if PaystackPaymentService.TEST_MODE and reference.startswith('TEST_'):
                if payment.status == 'test_pending':
                    if not PaystackPaymentService._claim_payment(payment):
                        return {'success': False, 'error': 'Payment is already being processed. Check its status.'}
                    if payment.purpose in ('reservation_delivery_fee', 'reservation_service_fee'):
                        complete = (PaystackPaymentService._complete_service_fee_payment
                                    if payment.purpose == 'reservation_service_fee'
                                    else PaystackPaymentService._complete_delivery_fee_payment)
                        settled = complete(payment, 'test_card')
                        payment.payment_metadata = {
                            **(payment.payment_metadata or {}),
                            'verified': True,
                        }
                        db.session.commit()
                        if settled:
                            from services.reservation_service import _award_reservation_points
                            _award_reservation_points(db.session.get(Reservation, payment.reservation_id))
                        user = User.query.get(payment.user_id)
                        return {
                            'success': True,
                            'message': 'Reservation fee payment verified',
                            'credits_added': 0,
                            'new_balance': user.credits,
                        }
                    payment.status = 'completed'
                    payment.paid_at = datetime.utcnow()
                    payment.payment_method = 'test_card'
                    payment.payment_metadata = {'mode': 'test', 'verified': True}
                    
                    # Credit user's account
                    user = User.query.get(payment.user_id)
                    old_balance = user.credits
                    user.credits += payment.credits_purchased
                    
                    # Create transaction record
                    transaction = CreditTransaction(
                        user_id=payment.user_id,
                        amount=payment.credits_purchased,
                        transaction_type='credit_purchase',
                        reason='test_payment',
                        description=f'[TEST] Purchased {payment.credits_purchased} credits for ₦{payment.amount_naira:,.0f}',
                        balance_before=old_balance,
                        balance_after=user.credits,
                        payment_id=payment.id,
                    )
                    
                    db.session.add(transaction)
                    db.session.commit()
                    
                    print(f'[TEST MODE] Payment verified: {reference}')
                    
                    # Send in-app and email notifications
                    try:
                        from notifications import notify_credit_purchase
                        notify_credit_purchase(
                            user_id=payment.user_id,
                            amount_naira=payment.amount_naira,
                            credits_purchased=payment.credits_purchased,
                            previous_balance=old_balance,
                            new_balance=user.credits,
                            reference=reference
                        )
                    except Exception as notif_err:
                        print(f'[WARNING] Failed to send payment notification: {str(notif_err)}')
                    
                    return {
                        'success': True,
                        'message': 'Test payment verified and credits added',
                        'credits_added': payment.credits_purchased,
                        'new_balance': user.credits
                    }
                else:
                    return {
                        'success': False,
                        'error': f'Test payment has already been processed (status: {payment.status})'
                    }
            
            # PRODUCTION MODE: Verify with Paystack API
            headers = PaystackPaymentService.get_auth_header()
            
            # Check payment status with Paystack
            response = requests.get(
                f'{PaystackPaymentService.BASE_URL}/transaction/verify/{reference}',
                headers=headers,
                timeout=30
            )
            
            print(f'[PAYSTACK VERIFY] Response Status: {response.status_code}')
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('status'):  # Paystack returns 'status': True for success
                    response_data = data.get('data', {})
                    pay_status = response_data.get('status')  # 'success', 'pending', etc.
                    
                    # Check if payment was successful
                    if pay_status == 'success':
                        expected_amount = int(round(float(payment.amount_naira) * 100))
                        if (
                            response_data.get('currency') != 'NGN'
                            or int(response_data.get('amount') or 0) != expected_amount
                            or response_data.get('reference') != reference
                        ):
                            current_app.logger.error('Payment verification mismatch for payment %s', payment.id)
                            return {'success': False, 'error': 'Verified transaction reference, amount or currency does not match the payment.'}
                        if not PaystackPaymentService._claim_payment(payment):
                            db.session.rollback()
                            existing = db.session.get(Payment, payment.id)
                            if existing.status == 'completed':
                                return {'success': True, 'message': 'Payment already verified', 'credits_added': 0,
                                        'new_balance': db.session.get(User, existing.user_id).credits}
                            return {'success': False, 'error': 'Payment is already being processed. Check its status.'}
                        if payment.purpose in ('reservation_delivery_fee', 'reservation_service_fee'):
                            complete = (PaystackPaymentService._complete_service_fee_payment
                                        if payment.purpose == 'reservation_service_fee'
                                        else PaystackPaymentService._complete_delivery_fee_payment)
                            settled = complete(
                                payment,
                                response_data.get('channel', 'card'),
                            )
                            db.session.commit()
                            if settled:
                                from services.reservation_service import _award_reservation_points
                                _award_reservation_points(db.session.get(Reservation, payment.reservation_id))
                            user = User.query.get(payment.user_id)
                            return {
                                'success': True,
                                'message': 'Delivery fee payment verified',
                                'credits_added': 0,
                                'new_balance': user.credits,
                            }

                        payment.status = 'completed'
                        payment.paid_at = datetime.utcnow()
                        payment.payment_method = response_data.get('channel', 'card')  # card, bank_transfer, etc.
                        
                        # Credit user's account
                        user = User.query.get(payment.user_id)
                        old_balance = user.credits
                        user.credits += payment.credits_purchased
                        
                        # Create transaction record
                        transaction = CreditTransaction(
                            user_id=payment.user_id,
                            amount=payment.credits_purchased,
                            transaction_type='credit_purchase',
                            reason='paystack_payment',
                            description=f'Purchased {payment.credits_purchased} credits for ₦{payment.amount_naira:,.0f}',
                            balance_before=old_balance,
                            balance_after=user.credits,
                            payment_id=payment.id,
                        )
                        
                        db.session.add(transaction)
                        db.session.commit()
                        
                        # Send in-app and email notifications
                        try:
                            from notifications import notify_credit_purchase
                            notify_credit_purchase(
                                user_id=payment.user_id,
                                amount_naira=payment.amount_naira,
                                credits_purchased=payment.credits_purchased,
                                previous_balance=old_balance,
                                new_balance=user.credits,
                                reference=reference
                            )
                        except Exception as notif_err:
                            print(f'[WARNING] Failed to send payment notification: {str(notif_err)}')
                        
                        return {
                            'success': True,
                            'message': 'Payment verified and credits added',
                            'credits_added': payment.credits_purchased,
                            'new_balance': user.credits
                        }
                    else:
                        db.session.rollback()
                        
                        return {
                            'success': False,
                            'error': f'Payment was not successful. Status: {pay_status}',
                            'status': pay_status
                        }
                else:
                    return {
                        'success': False,
                        'error': data.get('message', 'Failed to verify payment')
                    }
            else:
                return {
                    'success': False,
                    'error': 'Failed to verify payment',
                    'status_code': response.status_code
                }
                
        except requests.RequestException as e:
            db.session.rollback()
            current_app.logger.exception('Payment verification request failed')
            return {'success': False, 'error': f'Verification request failed: {str(e)}'}
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception('Payment verification failed')
            return {'success': False, 'error': 'Payment verification failed. Please retry or contact support.'}

    @staticmethod
    def _claim_payment(payment):
        """Only one transaction may claim and credit a pending payment."""
        claimed = Payment.query.filter(
            Payment.id == payment.id,
            Payment.status.in_(['pending', 'test_pending', 'failed']),
        ).update({'status': 'processing'}, synchronize_session=False)
        if not claimed:
            return False
        db.session.expire(payment)
        # Serialize balance changes across different payments for this user, too.
        User.query.filter_by(id=payment.user_id).with_for_update().populate_existing().one()
        return True
    
    @staticmethod
    def verify_webhook_signature(signature, payload_string):
        """
        Verify webhook signature from Paystack
        Paystack uses HMAC-SHA512 for signature verification
        
        Args:
            signature: Signature header from webhook (x-paystack-signature)
            payload_string: Raw payload string
            
        Returns:
            bool: True if signature is valid, False otherwise
        """
        try:
            # Paystack uses the secret key as the HMAC secret
            secret_bytes = PaystackPaymentService.SECRET_KEY.encode('utf-8')
            expected_signature = hmac.new(
                secret_bytes,
                payload_string.encode('utf-8'),
                hashlib.sha512
            ).hexdigest()
            
            return hmac.compare_digest(signature, expected_signature)
        except Exception as e:
            print(f'Signature verification error: {str(e)}')
            return False
    
    @staticmethod
    def get_payment_status(payment_id):
        """
        Get the status of a payment
        
        Args:
            payment_id: Payment ID in database
            
        Returns:
            dict: Payment details
        """
        payment = Payment.query.get(payment_id)
        if not payment:
            return {'error': 'Payment not found'}
        
        return {
            'id': payment.id,
            'amount': payment.amount_naira,
            'credits': payment.credits_purchased,
            'purpose': payment.purpose,
            'status': payment.status,
            'created_at': payment.created_at.isoformat(),
            'paid_at': payment.paid_at.isoformat() if payment.paid_at else None,
            'reference': payment.paystack_reference
        }
    
    @staticmethod
    def get_user_payment_history(user_id, limit=10):
        """
        Get payment history for a user
        
        Args:
            user_id: User ID
            limit: Number of records to return
            
        Returns:
            list: Payment records
        """
        payments = Payment.query.filter_by(
            user_id=user_id,
            purpose='credit_purchase',
        ).order_by(
            Payment.created_at.desc()
        ).limit(limit).all()
        
        return [
            {
                'id': p.id,
                'amount': p.amount_naira,
                'credits': p.credits_purchased,
                'status': p.status,
                'created_at': p.created_at.isoformat(),
                'reference': p.paystack_reference or p.monnify_reference
            }
            for p in payments
        ]
    
    @staticmethod
    def calculate_credits(amount_naira):
        """
        Calculate credits based on amount
        1 Naira = 1 Credit
        """
        return int(float(amount_naira) * PaystackPaymentService.CONVERSION_RATE)
