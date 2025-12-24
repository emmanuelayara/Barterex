"""
Transaction Management Utilities
Handles detailed credit transaction tracking and explanations
"""
from datetime import datetime
from app import db
from models import CreditTransaction
from logger_config import setup_logger

logger = setup_logger(__name__)


def create_detailed_transaction(
    user_id,
    amount,
    transaction_type,
    description=None,
    reason=None,
    balance_before=None,
    balance_after=None,
    related_order_id=None,
    related_item_id=None
):
    """
    Create a detailed credit transaction with full explanation
    
    Args:
        user_id: User ID performing the transaction
        amount: Amount of credits involved
        transaction_type: Type of transaction (purchase, referral_bonus, admin_credit, etc.)
        description: Detailed description of the transaction
        reason: Human-readable reason/category
        balance_before: User's balance before the transaction
        balance_after: User's balance after the transaction
        related_order_id: Link to order if applicable
        related_item_id: Link to item if applicable
    
    Returns:
        CreditTransaction object or None if failed
    """
    try:
        transaction = CreditTransaction(
            user_id=user_id,
            amount=amount,
            transaction_type=transaction_type,
            description=description,
            reason=reason or transaction_type.replace('_', ' ').title(),
            balance_before=balance_before,
            balance_after=balance_after,
            related_order_id=related_order_id,
            related_item_id=related_item_id,
            timestamp=datetime.utcnow()
        )
        db.session.add(transaction)
        db.session.commit()
        logger.info(f"Transaction created - User: {user_id}, Type: {transaction_type}, Amount: {amount}")
        return transaction
    except Exception as e:
        logger.error(f"Error creating transaction: {str(e)}", exc_info=True)
        db.session.rollback()
        return None


def get_transaction_explanation(transaction):
    """
    Get a detailed human-readable explanation of a transaction
    
    Args:
        transaction: CreditTransaction object
    
    Returns:
        dict with detailed explanation
    """
    try:
        explanation = {
            'type': transaction.transaction_type,
            'amount': f"₦{transaction.amount:,.0f}",
            'is_debit': transaction.transaction_type in ['purchase', 'debit'],
            'is_credit': transaction.transaction_type not in ['purchase', 'debit'],
            'date': transaction.timestamp.strftime('%d %b %Y, %I:%M %p'),
            'description': transaction.get_human_readable_description(),
            'reason': transaction.reason or transaction.transaction_type.replace('_', ' ').title(),
        }
        
        # Add balance information if available
        if transaction.balance_before is not None:
            explanation['balance_before'] = f"₦{transaction.balance_before:,.0f}"
        
        if transaction.balance_after is not None:
            explanation['balance_after'] = f"₦{transaction.balance_after:,.0f}"
        
        # Generate detailed explanation text
        if transaction.transaction_type == 'purchase':
            explanation['explanation'] = (
                f"You purchased items worth ₦{transaction.amount:,.0f}. "
                f"This amount was deducted from your balance."
            )
        elif transaction.transaction_type == 'referral_signup_bonus':
            explanation['explanation'] = (
                f"You earned ₦{transaction.amount:,.0f} from a referral signup bonus. "
                f"Someone signed up using your referral code!"
            )
        elif transaction.transaction_type == 'referral_purchase_bonus':
            explanation['explanation'] = (
                f"You earned ₦{transaction.amount:,.0f} as a referral commission. "
                f"Someone you referred made a purchase!"
            )
        elif transaction.transaction_type == 'admin_credit':
            explanation['explanation'] = (
                f"An admin credited ₦{transaction.amount:,.0f} to your account. "
                f"{transaction.description or 'Thank you for using Barterex!'}"
            )
        elif transaction.transaction_type == 'refund':
            explanation['explanation'] = (
                f"You received a refund of ₦{transaction.amount:,.0f}. "
                f"This credit has been returned to your account."
            )
        else:
            explanation['explanation'] = transaction.description or f"Transaction: {transaction.transaction_type}"
        
        return explanation
    except Exception as e:
        logger.error(f"Error generating transaction explanation: {str(e)}", exc_info=True)
        return {}


def get_transaction_statistics(user_id):
    """
    Get statistics about a user's transactions
    
    Args:
        user_id: User ID to get statistics for
    
    Returns:
        dict with transaction statistics
    """
    try:
        all_transactions = CreditTransaction.query.filter_by(user_id=user_id).all()
        
        purchases = [t for t in all_transactions if t.transaction_type in ['purchase', 'debit']]
        credits = [t for t in all_transactions if t.transaction_type not in ['purchase', 'debit']]
        
        total_spent = sum(t.amount for t in purchases)
        total_earned = sum(t.amount for t in credits)
        
        return {
            'total_transactions': len(all_transactions),
            'total_purchases': len(purchases),
            'total_credits': len(credits),
            'total_spent': total_spent,
            'total_earned': total_earned,
            'net_balance_change': total_earned - total_spent,
        }
    except Exception as e:
        logger.error(f"Error getting transaction statistics: {str(e)}", exc_info=True)
        return {}
