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
from services.email_notifications import notify_user

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
        """Create a Paystack charge for a quoted reservation delivery fee, not account credits."""
        if reservation.user_id != user.id:
            return {'success': False, 'error': 'You can only pay delivery fees for your own reservation.'}
        if reservation.delivery_method != 'home delivery':
            return {'success': False, 'error': 'This reservation does not require a home-service fee.'}
        if reservation.delivery_fee_status not in ('awaiting_payment', 'paid'):
            return {'success': False, 'error': 'There is no accepted delivery quote to pay.'}
        if reservation.delivery_fee_status == 'paid':
            return {'success': False, 'error': 'The delivery fee has already been paid.'}

        amount_naira = float(reservation.delivery_quote_naira or 0)
        if not PaystackPaymentService.MIN_AMOUNT <= amount_naira <= PaystackPaymentService.MAX_AMOUNT:
            return {'success': False, 'error': 'The delivery quote is outside Paystack payment limits.'}

        existing = Payment.query.filter_by(
            reservation_id=reservation.id,
            purpose='reservation_delivery_fee',
        ).filter(Payment.status.in_(('pending', 'test_pending'))).order_by(
            Payment.created_at.desc()
        ).first()
        if existing:
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
            purpose='reservation_delivery_fee',
            reservation_id=reservation.id,
            customer_email=user.email,
            customer_phone=user.phone_number,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        metadata = {
            'purpose': 'reservation_delivery_fee',
            'reservation_id': reservation.id,
        }

        if PaystackPaymentService.TEST_MODE:
            import uuid
            reference = f'TEST_{uuid.uuid4().hex[:12].upper()}'
            payment.paystack_reference = reference
            payment.status = 'test_pending'
            payment.payment_metadata = {'mode': 'test', **metadata}
            db.session.add(payment)
            db.session.commit()
            return {
                'success': True,
                'payment_link': f'/payments/verify-payment/{reference}?test=true',
                'reference': reference,
                'payment_id': payment.id,
                'test_mode': True,
            }

        import uuid
        reference = f'barterex_delivery_{reservation.id}_{uuid.uuid4().hex[:12]}'
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
        db.session.commit()
        return {
            'success': True,
            'payment_link': authorization_url,
            'reference': payment.paystack_reference,
            'payment_id': payment.id,
        }

    @staticmethod
    def _complete_delivery_fee_payment(payment, payment_method):
        reservation = Reservation.query.filter_by(
            id=payment.reservation_id,
            user_id=payment.user_id,
        ).with_for_update().first()
        if not reservation:
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
            return
        if reservation.delivery_fee_status != 'awaiting_payment':
            raise ValueError('This reservation is not waiting for delivery-fee payment.')
        payment.status = 'completed'
        payment.paid_at = datetime.utcnow()
        payment.payment_method = payment_method
        reservation.delivery_fee_status = 'paid'
        notify_user(
            reservation.user_id,
            f"Your non-refundable home-service fee for reservation {reservation.id} is paid. "
            "Dispatch may proceed after verification succeeds.",
            subject="Home-service fee received",
            cta_endpoint='user.my_reservations',
            cta_label='View My Reservations',
            notification_type='reservation',
        )
    
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
            reference = f'barterex_{user_id}_{int(datetime.utcnow().timestamp())}'
            
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

            if payment.purpose == 'reservation_delivery_fee' and payment.status == 'completed':
                return {
                    'success': True,
                    'message': 'Delivery fee payment already verified',
                    'credits_added': 0,
                    'new_balance': User.query.get(payment.user_id).credits,
                }
            
            # TEST MODE: Auto-complete test payments
            if PaystackPaymentService.TEST_MODE and reference.startswith('TEST_'):
                if payment.status == 'test_pending':
                    if payment.purpose == 'reservation_delivery_fee':
                        PaystackPaymentService._complete_delivery_fee_payment(payment, 'test_card')
                        payment.payment_metadata = {
                            **(payment.payment_metadata or {}),
                            'verified': True,
                        }
                        db.session.commit()
                        user = User.query.get(payment.user_id)
                        return {
                            'success': True,
                            'message': 'Delivery fee payment verified',
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
                        balance_after=user.credits
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
            print(f'[PAYSTACK VERIFY] Response Body: {response.text}')
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('status'):  # Paystack returns 'status': True for success
                    response_data = data.get('data', {})
                    pay_status = response_data.get('status')  # 'success', 'pending', etc.
                    
                    # Check if payment was successful
                    if pay_status == 'success':
                        if payment.purpose == 'reservation_delivery_fee':
                            expected_amount = int(round(float(payment.amount_naira) * 100))
                            if (
                                response_data.get('currency') != 'NGN'
                                or int(response_data.get('amount') or 0) != expected_amount
                            ):
                                payment.status = 'failed'
                                payment.error_message = 'Verified transaction amount or currency does not match the delivery quote.'
                                db.session.commit()
                                return {
                                    'success': False,
                                    'error': payment.error_message,
                                }
                            PaystackPaymentService._complete_delivery_fee_payment(
                                payment,
                                response_data.get('channel', 'card'),
                            )
                            db.session.commit()
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
                            balance_after=user.credits
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
                        payment.status = 'failed'
                        payment.error_message = f'Payment status: {pay_status}'
                        db.session.commit()
                        
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
            return {'success': False, 'error': f'Verification request failed: {str(e)}'}
        except Exception as e:
            return {'success': False, 'error': f'Verification error: {str(e)}'}
    
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
