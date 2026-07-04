# 🚀 Transaction Explanations - Quick Start Guide

## For Users

### How to View Your Transaction History

1. **Log into Barterex**
2. **Navigate to** "Credit History" (link in sidebar/menu)
3. **You'll see:**
   - 📊 Statistics summary at top
   - 💳 List of all transactions with details

### Understanding Your Transactions

Each transaction card shows:
- **Icon** - Visual indicator of transaction type
- **Description** - What happened
- **Date & Time** - When it occurred
- **Amount** - How many credits (color: red=spent, green=earned)
- **Balance Before** - Your balance before this transaction
- **Amount** - The exact amount involved
- **Balance After** - Your balance after this transaction
- **Explanation** - Clear text explaining what happened
- **View Order** - Link to order details (if applicable)

### Example: Understanding a Purchase

**You See:**
```
🛍️ Item Purchase
Paid ₦5,000 for item purchase
Date: 12 Dec 2025, 2:30 PM

Transaction Breakdown:
Your Balance Before: ₦50,000
Amount Deducted: -₦5,000
Your Balance After: ₦45,000

📝 What Happened:
You purchased item(s) worth ₦5,000. 
This amount was deducted from your credit balance.
```

**What It Means:**
- You had ₦50,000 credits
- You spent ₦5,000 on items
- Now you have ₦45,000 credits left

### Common Transaction Types

1. **🛍️ Purchase** - You bought items
2. **🎁 Referral Bonus** - Someone signed up using your code, or made a purchase through your referral
3. **⭐ Admin Credit** - Admin added credits to your account
4. **↩️ Refund** - You received credits back

---

## For Developers

### Quick Integration

#### Step 1: Import the Manager
```python
from transaction_manager import create_detailed_transaction
```

#### Step 2: Create Transaction After Action
```python
# After a purchase is completed
old_balance = user.credits
user.credits -= purchase_amount
new_balance = user.credits

create_detailed_transaction(
    user_id=user.id,
    amount=purchase_amount,
    transaction_type='purchase',
    description=f'Purchased {item_name}',
    reason='Item Purchase',
    balance_before=old_balance,
    balance_after=new_balance,
    related_order_id=order.id
)
```

#### Step 3: Transaction Automatically Shows in `/credit-history`

### Creating Different Transaction Types

#### Purchase Transaction
```python
create_detailed_transaction(
    user_id=user.id,
    amount=5000,
    transaction_type='purchase',
    description='Purchased 2 items: iPhone 12, Laptop',
    reason='Item Purchase',
    balance_before=50000,
    balance_after=45000,
    related_order_id=order_id
)
```

#### Referral Signup Bonus
```python
create_detailed_transaction(
    user_id=referrer.id,
    amount=100,
    transaction_type='referral_signup_bonus',
    description=f'New signup: {new_user.username}',
    reason='Referral Signup Bonus',
    balance_before=45000,
    balance_after=45100
)
```

#### Referral Purchase Bonus
```python
create_detailed_transaction(
    user_id=referrer.id,
    amount=500,
    transaction_type='referral_purchase_bonus',
    description=f'Referral purchase by {buyer.username}',
    reason='Referral Purchase Commission',
    balance_before=45100,
    balance_after=45600
)
```

#### Admin Credit
```python
create_detailed_transaction(
    user_id=user.id,
    amount=5000,
    transaction_type='admin_credit',
    description='Customer service compensation',
    reason='Admin Credit',
    balance_before=45000,
    balance_after=50000
)
```

#### Refund
```python
create_detailed_transaction(
    user_id=user.id,
    amount=5000,
    transaction_type='refund',
    description='Order cancellation refund',
    reason='Refund',
    balance_before=45000,
    balance_after=50000,
    related_order_id=order_id
)
```

### Available Helper Functions

#### Get Transaction Explanation
```python
from transaction_manager import get_transaction_explanation

transaction = CreditTransaction.query.get(45)
details = get_transaction_explanation(transaction)

# Details include:
# - type, amount, is_debit, is_credit
# - date, description, reason
# - balance_before, balance_after
# - explanation (human-readable text)
```

#### Get User Statistics
```python
from transaction_manager import get_transaction_statistics

stats = get_transaction_statistics(user.id)

# Returns:
# {
#   'total_transactions': 45,
#   'total_purchases': 20,
#   'total_credits': 25,
#   'total_spent': 80000,
#   'total_earned': 125000,
#   'net_balance_change': 45000
# }
```

### Database Queries

#### Get All Transactions for User
```python
transactions = CreditTransaction.query.filter_by(
    user_id=user.id
).order_by(CreditTransaction.timestamp.desc()).all()
```

#### Get Transactions of Specific Type
```python
purchases = CreditTransaction.query.filter_by(
    user_id=user.id,
    transaction_type='purchase'
).all()
```

#### Get Recent Transactions (Last 30 Days)
```python
from datetime import datetime, timedelta

last_30_days = datetime.utcnow() - timedelta(days=30)
recent = CreditTransaction.query.filter_by(
    user_id=user.id
).filter(CreditTransaction.timestamp >= last_30_days).all()
```

#### Get High-Value Transactions
```python
high_value = CreditTransaction.query.filter_by(
    user_id=user.id
).filter(CreditTransaction.amount > 10000).all()
```

### Best Practices

1. **Always Capture Balance**
   - Always provide `balance_before` and `balance_after`
   - This allows users to verify accuracy

2. **Use Descriptive Text**
   - `description`: Be specific about what happened
   - `reason`: Use clear, human-readable categories

3. **Link Related Data**
   - Use `related_order_id` for purchases
   - Use `related_item_id` if applicable
   - This helps users trace transactions

4. **Atomic Operations**
   - Update balance and create transaction in same operation
   - Prevents orphaned records

5. **Log Failures**
   - If transaction creation fails, log the error
   - Don't silently ignore failures

### Common Pitfalls to Avoid

❌ **Don't:** Create transaction without balance info
```python
# Bad
create_detailed_transaction(
    user_id=user.id,
    amount=5000,
    transaction_type='purchase'
)
```

✅ **Do:** Provide complete information
```python
# Good
create_detailed_transaction(
    user_id=user.id,
    amount=5000,
    transaction_type='purchase',
    description='Purchased items',
    reason='Item Purchase',
    balance_before=50000,
    balance_after=45000,
    related_order_id=order.id
)
```

❌ **Don't:** Forget to capture balance
```python
# Bad - balance changes between capture and transaction
old_balance = user.credits
# ... other code ...
user.credits -= amount
create_detailed_transaction(...)  # Wrong old_balance!
```

✅ **Do:** Capture immediately before change
```python
# Good
old_balance = user.credits
user.credits -= amount
new_balance = user.credits
create_detailed_transaction(
    balance_before=old_balance,
    balance_after=new_balance,
    ...
)
```

### Troubleshooting

**Q: Transaction not showing in history?**
A: Check that:
- `balance_before` is set
- `balance_after` is set
- `user_id` is correct
- Transaction was committed to database

**Q: Balance numbers look wrong?**
A: Verify:
- `balance_before` = user.credits BEFORE the change
- `balance_after` = user.credits AFTER the change
- Math: before - amount = after (for purchases)

**Q: Need to edit a transaction?**
A: Update directly:
```python
t = CreditTransaction.query.get(45)
t.description = "Updated description"
t.balance_before = 50000
t.balance_after = 45000
db.session.commit()
```

---

## Files Reference

| File | Purpose |
|------|---------|
| `models.py` | CreditTransaction model definition |
| `transaction_manager.py` | Helper functions |
| `templates/transaction_history.html` | User-facing UI |
| `routes/user.py` | Route handler |
| `TRANSACTION_EXPLANATIONS_IMPLEMENTATION.md` | Full technical docs |
| `TRANSACTION_EXPLANATIONS_QUICK_REF.md` | Developer quick ref |
| `TRANSACTION_EXPLANATIONS_DELIVERY.md` | Implementation summary |

---

## Support

- 📖 Full docs: `TRANSACTION_EXPLANATIONS_IMPLEMENTATION.md`
- ⚡ Quick ref: `TRANSACTION_EXPLANATIONS_QUICK_REF.md`
- 📝 Code examples: This guide
- 💬 Questions: Check inline code comments

---

**Happy coding!** 🚀
