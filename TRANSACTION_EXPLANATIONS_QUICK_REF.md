# 💳 Transaction Explanations - Quick Reference

## User-Facing Features

### Credit History Page (`/credit-history`)
Displays all user transactions with detailed breakdowns.

**What Users See:**
- 📊 **Statistics Dashboard**
  - Total Transactions: Count
  - Current Balance: ₦X,XXX
  - Total Earned: +₦X,XXX
  - Total Spent: -₦X,XXX

- 💳 **Transaction Cards** (for each transaction)
  - Icon (🛍️ 🎁 ⭐ ↩️)
  - Transaction type and description
  - Date/time
  - Amount (red for debit, green for credit)
  - Balance breakdown:
    - Balance Before
    - Amount Added/Deducted
    - Balance After
  - Plain English explanation
  - Link to related order (if applicable)

**Example UI:**
```
💰 Credit Transaction History

📊 Statistics:
├─ Total Transactions: 45
├─ Current Balance: ₦45,000
├─ Total Earned: ₦125,000
└─ Total Spent: -₦80,000

💳 Transactions:

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

## Developer Integration

### Using the Transaction Manager

#### 1. Create a Detailed Transaction
```python
from transaction_manager import create_detailed_transaction

create_detailed_transaction(
    user_id=user.id,
    amount=5000,
    transaction_type='purchase',
    description='Purchased iPhone 12',
    reason='Item Purchase',
    balance_before=50000,
    balance_after=45000,
    related_order_id=order.id
)
```

#### 2. Get Transaction Explanation
```python
from transaction_manager import get_transaction_explanation

transaction = CreditTransaction.query.get(45)
details = get_transaction_explanation(transaction)

# Use in template
# {{ details.description }}
# {{ details.explanation }}
# {{ details.balance_before }}
# {{ details.balance_after }}
```

#### 3. Get User Statistics
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

### Transaction Types

| Type | Icon | Description |
|------|------|-------------|
| `purchase` | 🛍️ | User purchased items |
| `referral_signup_bonus` | 🎁 | Someone signed up with referral code |
| `referral_purchase_bonus` | 🎁 | Referral made a purchase |
| `admin_credit` | ⭐ | Admin manually credited account |
| `refund` | ↩️ | Refund of previous transaction |
| `debit` | 💳 | Generic debit |
| `credit` | 💰 | Generic credit |

### Database Fields

```python
class CreditTransaction(db.Model):
    # Core fields
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    amount = db.Column(db.Integer, nullable=False)
    transaction_type = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # New explanation fields
    description = db.Column(db.String(255), nullable=True)
    reason = db.Column(db.String(100), nullable=True)
    balance_before = db.Column(db.Float, nullable=True)
    balance_after = db.Column(db.Float, nullable=True)
    
    # Links to related data
    related_order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    related_item_id = db.Column(db.Integer, db.ForeignKey('item.id'))
```

## Common Use Cases

### Scenario 1: Record a Purchase
```python
# User purchases items
order = Order(user_id=user.id, total_credits=5000)
db.session.add(order)
db.session.flush()  # Get order.id

# Record transaction
old_balance = user.credits
user.credits -= 5000
new_balance = user.credits

create_detailed_transaction(
    user_id=user.id,
    amount=5000,
    transaction_type='purchase',
    description='Purchased 3 items: iPhone 12, Laptop, Headphones',
    reason='Item Purchase',
    balance_before=old_balance,
    balance_after=new_balance,
    related_order_id=order.id
)
db.session.commit()
```

### Scenario 2: Award Referral Bonus
```python
# Referral signup detected
old_balance = referrer.credits
referrer.credits += 100
new_balance = referrer.credits

create_detailed_transaction(
    user_id=referrer.id,
    amount=100,
    transaction_type='referral_signup_bonus',
    description=f'New signup: {new_user.username}',
    reason='Referral Signup Bonus',
    balance_before=old_balance,
    balance_after=new_balance
)
db.session.commit()
```

### Scenario 3: Admin Credit
```python
# Admin manually credits account
old_balance = user.credits
user.credits += 5000
new_balance = user.credits

create_detailed_transaction(
    user_id=user.id,
    amount=5000,
    transaction_type='admin_credit',
    description='Admin credit for customer support compensation',
    reason='Customer Service',
    balance_before=old_balance,
    balance_after=new_balance
)
db.session.commit()
```

## Template Usage

### Display Transaction in Template
```html
{% for transaction in history %}
  <div class="transaction-card">
    <h3>{{ transaction.get_human_readable_description() }}</h3>
    <p>{{ transaction.description }}</p>
    <div class="balance-info">
      Before: ₦{{ "{:,.0f}".format(transaction.balance_before) }}
      After: ₦{{ "{:,.0f}".format(transaction.balance_after) }}
    </div>
  </div>
{% endfor %}
```

### Query Transactions
```python
# Get all transactions for a user
transactions = CreditTransaction.query.filter_by(user_id=user.id).order_by(CreditTransaction.timestamp.desc()).all()

# Get transactions of a specific type
purchases = CreditTransaction.query.filter_by(user_id=user.id, transaction_type='purchase').all()

# Get transactions with balance tracking
tracked = CreditTransaction.query.filter_by(user_id=user.id).filter(CreditTransaction.balance_before.isnot(None)).all()

# Get transactions in date range
from datetime import datetime, timedelta
last_30_days = datetime.utcnow() - timedelta(days=30)
recent = CreditTransaction.query.filter_by(user_id=user.id).filter(CreditTransaction.timestamp >= last_30_days).all()
```

## Best Practices

1. **Always Record Balance** - Capture `balance_before` and `balance_after` for transparency
2. **Use Descriptive Reasons** - Make the reason field human-readable
3. **Link to Related Data** - Use `related_order_id` and `related_item_id` for context
4. **Update Balance Atomically** - Update user balance and create transaction in same operation
5. **Log Failures** - Use logger if transaction creation fails

## Troubleshooting

**Q: Why doesn't my transaction show balance?**
A: Make sure you're passing `balance_before` and `balance_after` when creating the transaction.

**Q: How do I update an existing transaction?**
A: Directly edit the transaction object and commit:
```python
t = CreditTransaction.query.get(45)
t.description = "Updated description"
t.balance_before = 50000
t.balance_after = 45000
db.session.commit()
```

**Q: How do I search transactions?**
A: Use Flask-SQLAlchemy queries:
```python
# By type
CreditTransaction.query.filter_by(user_id=user.id, transaction_type='purchase').all()

# By date range
CreditTransaction.query.filter_by(user_id=user.id).filter(
    CreditTransaction.timestamp.between(start_date, end_date)
).all()

# By amount range
CreditTransaction.query.filter_by(user_id=user.id).filter(
    CreditTransaction.amount > 1000
).all()
```

## Files Included

- `models.py` - Enhanced CreditTransaction model
- `transaction_manager.py` - Utility functions
- `templates/transaction_history.html` - UI template
- `routes/user.py` - Route handling
- `migrate_transactions.py` - Database migration
- `TRANSACTION_EXPLANATIONS_IMPLEMENTATION.md` - Full documentation
