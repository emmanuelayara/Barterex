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
from models import Payment, User, CreditTransaction
from app import db

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
            
            # TEST MODE: Auto-complete test payments
            if PaystackPaymentService.TEST_MODE and reference.startswith('TEST_'):
                if payment.status == 'test_pending':
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
            user_id=user_id
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
