"""
Moniepoint Payment Service
Handles all payment processing, verification, and credit allocation
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

class MoniePointPaymentService:
    """
    Service class for handling Moniepoint payment operations
    """
    
    BASE_URL = os.getenv('MONIEPOINT_API_URL', 'https://api.moniepoint.com')
    API_KEY = os.getenv('MONIEPOINT_API_KEY')
    PUBLIC_KEY = os.getenv('MONIEPOINT_PUBLIC_KEY')
    CALLBACK_URL = os.getenv('PAYMENT_CALLBACK_URL')
    
    # Enable test mode for development (no real API calls)
    TEST_MODE = os.getenv('PAYMENT_TEST_MODE', 'false').lower() == 'true'
    
    # Conversion rate: 1 Naira = 1 Credit
    CONVERSION_RATE = 1.0
    
    # Minimum and maximum amounts
    MIN_AMOUNT = 100  # Minimum ₦100
    MAX_AMOUNT = 1000000  # Maximum ₦1,000,000
    
    @staticmethod
    def initiate_payment(user_id, amount_naira):
        """
        Initiate a payment request with Moniepoint
        
        Args:
            user_id: ID of the user
            amount_naira: Amount in Nigerian Naira
            
        Returns:
            dict: Moniepoint response with payment link or error
        """
        try:
            user = User.query.get(user_id)
            if not user:
                return {'success': False, 'error': 'User not found'}
            
            # Validate amount
            amount_naira = float(amount_naira)
            if amount_naira < MoniePointPaymentService.MIN_AMOUNT:
                return {'success': False, 'error': f'Minimum amount is ₦{MoniePointPaymentService.MIN_AMOUNT}'}
            if amount_naira > MoniePointPaymentService.MAX_AMOUNT:
                return {'success': False, 'error': f'Maximum amount is ₦{MoniePointPaymentService.MAX_AMOUNT}'}
            
            # Calculate credits (1 naira = 1 credit)
            credits = int(amount_naira * MoniePointPaymentService.CONVERSION_RATE)
            
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
            if MoniePointPaymentService.TEST_MODE:
                import uuid
                mock_reference = f'TEST_{uuid.uuid4().hex[:12].upper()}'
                payment.moniepoint_reference = mock_reference
                payment.status = 'test_pending'
                payment.payment_metadata = {'mode': 'test', 'test_note': 'This is a test payment'}
                
                db.session.add(payment)
                db.session.commit()
                
                # Return a test payment link that redirects to success page
                mock_link = f'/payments/verify-payment/{mock_reference}?test=true'
                
                print(f'[TEST MODE] Payment created: {mock_reference} for {amount_naira} naira ({credits} credits)')
                
                return {
                    'success': True,
                    'payment_link': mock_link,
                    'reference': mock_reference,
                    'payment_id': payment.id,
                    'test_mode': True
                }
            
            # PRODUCTION MODE: Make real API call to Moniepoint
            # Prepare Moniepoint request
            payload = {
                'amount': int(amount_naira * 100),  # Convert to kobo (Moniepoint uses smallest unit)
                'currency': 'NGN',
                'customer': {
                    'email': user.email,
                    'name': user.username,
                    'phone': user.phone_number or '',
                },
                'description': f'Purchase {credits} credits on Barterex',
                'metadata': {
                    'user_id': user_id,
                    'credits': credits,
                    'payment_type': 'credit_purchase',
                },
                'callback_url': MoniePointPaymentService.CALLBACK_URL
            }
            
            headers = {
                'Authorization': f'Bearer {MoniePointPaymentService.API_KEY}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            # Initialize payment with Moniepoint
            response = requests.post(
                f'{MoniePointPaymentService.BASE_URL}/api/transactions/init',
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                
                # Store Moniepoint reference
                payment.moniepoint_reference = data.get('transaction_reference') or data.get('reference')
                payment.payment_metadata = {'moniepoint_response': data}
                
                db.session.add(payment)
                db.session.commit()
                
                return {
                    'success': True,
                    'payment_link': data.get('authorization_url') or data.get('payment_link'),
                    'reference': payment.moniepoint_reference,
                    'payment_id': payment.id
                }
            else:
                error_data = response.json() if response.text else {}
                return {
                    'success': False,
                    'error': error_data.get('message', 'Payment initialization failed'),
                    'status_code': response.status_code
                }
                
        except requests.RequestException as e:
            return {'success': False, 'error': f'Request failed: {str(e)}'}
        except Exception as e:
            print(f'Payment service error: {str(e)}')
            return {'success': False, 'error': f'Server error: {str(e)}'}
        except Exception as e:
            return {'success': False, 'error': f'An error occurred: {str(e)}'}
    
    @staticmethod
    def verify_payment(reference):
        """
        Verify a payment with Moniepoint
        
        Args:
            reference: Moniepoint transaction reference
            
        Returns:
            dict: Payment verification result
        """
        try:
            # Update payment in database
            payment = Payment.query.filter_by(
                moniepoint_reference=reference
            ).first()
            
            if not payment:
                return {'success': False, 'error': 'Payment record not found'}
            
            # TEST MODE: Auto-complete test payments
            if MoniePointPaymentService.TEST_MODE and reference.startswith('TEST_'):
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
            
            # PRODUCTION MODE: Verify with Moniepoint API
            headers = {
                'Authorization': f'Bearer {MoniePointPaymentService.API_KEY}',
                'Accept': 'application/json'
            }
            
            # Check payment status with Moniepoint
            response = requests.get(
                f'{MoniePointPaymentService.BASE_URL}/api/transactions/{reference}',
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if payment was successful
                if data.get('status') == 'success' or data.get('status') == 'completed':
                    payment.status = 'completed'
                    payment.paid_at = datetime.utcnow()
                    payment.payment_method = data.get('payment_method', 'card')
                    
                    # Credit user's account
                    user = User.query.get(payment.user_id)
                    old_balance = user.credits
                    user.credits += payment.credits_purchased
                    
                    # Create transaction record
                    transaction = CreditTransaction(
                        user_id=payment.user_id,
                        amount=payment.credits_purchased,
                        transaction_type='credit_purchase',
                        reason='moniepoint_payment',
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
                    payment.error_message = data.get('message', 'Payment failed')
                    db.session.commit()
                    
                    return {
                        'success': False,
                        'error': data.get('message', 'Payment was not successful'),
                        'status': data.get('status')
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
        Verify webhook signature from Moniepoint
        
        Args:
            signature: Signature header from webhook
            payload_string: Raw payload string
            
        Returns:
            bool: True if signature is valid, False otherwise
        """
        try:
            secret_bytes = MoniePointPaymentService.API_KEY.encode('utf-8')
            expected_signature = hmac.new(
                secret_bytes,
                payload_string.encode('utf-8'),
                hashlib.sha256
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
            'reference': payment.moniepoint_reference
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
                'reference': p.moniepoint_reference
            }
            for p in payments
        ]
    
    @staticmethod
    def calculate_credits(amount_naira):
        """
        Calculate credits based on amount
        1 Naira = 1 Credit
        """
        return int(float(amount_naira) * MoniePointPaymentService.CONVERSION_RATE)
