"""
Payment Routes - Handles all payment-related endpoints
Includes Monnify integration for credit purchases
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from payment_service import MonnifyPaymentService
from models import Payment, db
import json

payment_bp = Blueprint('payments', __name__, url_prefix='/payments')

@payment_bp.route('/fund-account', methods=['GET', 'POST'])
@login_required
def fund_account():
    """
    Main page for users to purchase credits with flexible amounts
    Users can enter any amount and get that exact amount in credits
    """
    if request.method == 'GET':
        min_amount = MonnifyPaymentService.MIN_AMOUNT
        max_amount = MonnifyPaymentService.MAX_AMOUNT
        return render_template(
            'payments/fund_account.html',
            min_amount=min_amount,
            max_amount=max_amount
        )
    
    # POST request - process payment initialization
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
            
        amount = data.get('amount')
        
        if amount is None:
            return jsonify({'success': False, 'error': 'Amount is required'}), 400
        
        try:
            amount = float(amount)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid amount format'}), 400
        
        # Validate amount
        if amount < MonnifyPaymentService.MIN_AMOUNT:
            return jsonify({'success': False, 'error': f'Minimum amount is ₦{MonnifyPaymentService.MIN_AMOUNT}'}), 400
        if amount > MonnifyPaymentService.MAX_AMOUNT:
            return jsonify({'success': False, 'error': f'Maximum amount is ₦{MonnifyPaymentService.MAX_AMOUNT}'}), 400
        
        # Initiate payment with Monnify
        result = MonnifyPaymentService.initiate_payment(
            current_user.id,
            amount
        )
        
        if result['success']:
            return jsonify({
                'success': True,
                'payment_link': result['payment_link'],
                'reference': result['reference'],
                'payment_id': result['payment_id']
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Payment initialization failed')
            }), 400
            
    except Exception as e:
        print(f'Payment initiation error: {str(e)}')
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
        }), 500


@payment_bp.route('/verify-payment/<reference>', methods=['GET'])
@login_required
def verify_payment(reference):
    """
    Verify payment status with Monnify / Test Mode
    Called after user completes payment or in test mode
    """
    try:
        # Handle test mode - user can pass ?test=true to force verification
        is_test = request.args.get('test', 'false').lower() == 'true'
        
        if is_test and reference.startswith('TEST_'):
            print(f'Verifying TEST payment: {reference}')
        
        result = MonnifyPaymentService.verify_payment(reference)
        
        if result['success']:
            return render_template(
                'payments/payment_success.html',
                credits_added=result['credits_added'],
                new_balance=result['new_balance'],
                reference=reference
            )
        else:
            return render_template(
                'payments/payment_failed.html',
                error=result['error'],
                reference=reference
            )
            
    except Exception as e:
        print(f'Verify payment error: {str(e)}')
        return render_template(
            'payments/payment_error.html',
            error=str(e)
        ), 500


@payment_bp.route('/status/<int:payment_id>', methods=['GET'])
@login_required
def payment_status(payment_id):
    """
    Get payment status via API
    """
    payment = Payment.query.get(payment_id)
    
    if not payment:
        return jsonify({'error': 'Payment not found'}), 404
    
    # Verify user owns this payment
    if payment.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    status = MonnifyPaymentService.get_payment_status(payment_id)
    return jsonify(status)


@payment_bp.route('/history', methods=['GET'])
@login_required
def payment_history():
    """
    Get user's payment history
    """
    history = MonnifyPaymentService.get_user_payment_history(current_user.id)
    return render_template('payments/payment_history.html', payments=history)


@payment_bp.route('/webhook', methods=['POST'])
def webhook():
    """
    Webhook endpoint for Monnify callbacks
    Handles payment verification when user completes payment
    """
    try:
        # Verify webhook signature
        signature = request.headers.get('X-Monnify-Signature')
        payload = request.get_data(as_text=True)
        
        if not MonnifyPaymentService.verify_webhook_signature(signature, payload):
            return jsonify({'error': 'Invalid signature'}), 401
        
        data = request.get_json()
        event = data.get('event')
        
        # Handle successful payment
        if event == 'charge.success':
            reference = data.get('data', {}).get('reference')
            if reference:
                result = MonnifyPaymentService.verify_payment(reference)
                return jsonify({'success': True, 'result': result})
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f'Webhook error: {str(e)}')
        return jsonify({'error': str(e)}), 500


@payment_bp.route('/api/packages', methods=['GET'])
def get_packages():
    """
    Get payment configuration for frontend
    Returns min/max amounts instead of fixed packages
    """
    config = {
        'conversion_rate': MonnifyPaymentService.CONVERSION_RATE,
        'min_amount': MonnifyPaymentService.MIN_AMOUNT,
        'max_amount': MonnifyPaymentService.MAX_AMOUNT,
        'message': 'Enter any amount - 1 Naira = 1 Credit'
    }
    return jsonify(config)


@payment_bp.route('/cancel', methods=['GET'])
@login_required
def cancel_payment():
    """
    Handle cancelled payment
    """
    reference = request.args.get('reference')
    return render_template('payments/payment_cancelled.html', reference=reference)
