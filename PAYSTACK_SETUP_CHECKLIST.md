# Paystack Migration - Quick Start Checklist

## ✅ What's Been Done

Your codebase has been updated to use **Paystack** instead of **Monnify** for payments. Here's what changed:

### Files Created:
1. ✅ **paystack_payment_service.py** - New Paystack payment service class
2. ✅ **PAYSTACK_MIGRATION_GUIDE.md** - Comprehensive migration documentation
3. ✅ **migrations/versions/add_paystack_support.py** - Database migration

### Files Modified:
1. ✅ **models.py** - Added `paystack_reference` field to Payment model
2. ✅ **routes/payments.py** - Updated to use PaystackPaymentService
3. ✅ **.env** - Added Paystack configuration (needs credentials)

---

## 🚀 Next Steps to Complete Setup

### 1. Get Paystack API Keys
- [ ] Go to https://dashboard.paystack.com
- [ ] Sign up or log in
- [ ] Navigate to **Settings > API Keys & Webhooks**
- [ ] Copy **Test Public Key** (for development)
- [ ] Copy **Test Secret Key** (for development)

### 2. Update .env File
```env
# Update these in your .env file:
PAYSTACK_PUBLIC_KEY=pk_test_YOUR_KEY_HERE
PAYSTACK_SECRET_KEY=sk_test_YOUR_KEY_HERE
PAYMENT_TEST_MODE=true
```

### 3. Run Database Migration
```bash
# Option 1: Using Flask-Migrate (recommended)
cd c:\Users\ayara\Documents\Python\Barterex
flask db upgrade

# Option 2: Manual (if migrations not set up)
python
>>> from app import app, db
>>> with app.app_context():
...     db.create_all()
```

### 4. Configure Paystack Webhook
- [ ] Go to Paystack Dashboard > Settings > Webhooks
- [ ] Add webhook URL: `http://127.0.0.1:5000/payments/webhook` (development)
- [ ] Or: `https://yourdomain.com/payments/webhook` (production)
- [ ] Select events: `charge.success`

### 5. Test the Integration
```bash
# 1. Make sure Flask is running
python app.py

# 2. Install requests (if not already installed)
pip install requests

# 3. Test payment flow
# - Navigate to fund account page
# - Enter amount: 100
# - Click "Fund Account"
# - If TEST_MODE=true, payment auto-completes
```

### 6. Use Paystack Test Card (for production mode)
- Card Number: `4084084084084081`
- Expiry: Any future date
- CVV: Any 3 digits

---

## 📋 Key Configuration Reference

### Development Setup
```env
PAYSTACK_PUBLIC_KEY=pk_test_...
PAYSTACK_SECRET_KEY=sk_test_...
PAYSTACK_API_URL=https://api.paystack.co
PAYMENT_TEST_MODE=true
PAYMENT_CALLBACK_URL=http://127.0.0.1:5000/payments/webhook
```

### Production Setup
```env
PAYSTACK_PUBLIC_KEY=pk_live_...
PAYSTACK_SECRET_KEY=sk_live_...
PAYSTACK_API_URL=https://api.paystack.co
PAYMENT_TEST_MODE=false
PAYMENT_CALLBACK_URL=https://yourdomain.com/payments/webhook
```

---

## 🔍 Verifying the Setup

### Check Service is Loaded
```python
python
>>> from paystack_payment_service import PaystackPaymentService
>>> print(PaystackPaymentService.BASE_URL)
https://api.paystack.co
```

### Test Payment Initiation (in Python shell)
```python
from app import app, db
from paystack_payment_service import PaystackPaymentService
from models import User

with app.app_context():
    user = User.query.first()
    if user:
        result = PaystackPaymentService.initiate_payment(user.id, 100)
        print(result)
```

### Database Check
```python
from app import app, db
from models import Payment

with app.app_context():
    payment = Payment.query.first()
    if payment:
        print(f"Monnify ref: {payment.monnify_reference}")
        print(f"Paystack ref: {payment.paystack_reference}")
```

---

## ⚠️ Important Notes

### Backwards Compatibility
- ✅ Old Monnify payments still work (monnify_reference field preserved)
- ✅ Can migrate gradually without losing payment history
- ✅ Payment model supports both payment methods

### Test Mode
- When `PAYMENT_TEST_MODE=true`, all payments auto-complete
- Perfect for development and testing
- Don't use in production

### API Differences from Monnify
- Paystack uses **kobo** (1 Naira = 100 kobo) internally, but the service handles conversion
- Webhook header: `x-paystack-signature` (not `X-Monnify-Signature`)
- Amount is sent in kobo to API, but accepted as Naira in the service

---

## 🐛 Troubleshooting

### "ModuleNotFoundError: No module named 'paystack_payment_service'"
- Ensure `paystack_payment_service.py` exists in root directory
- Make sure Flask is started from the correct directory

### "PaystackPaymentService.SECRET_KEY is None"
- Check `.env` file has `PAYSTACK_SECRET_KEY=...`
- Make sure it's set before starting Flask
- Restart Flask after updating `.env`

### "PaymentError: Payment record not found"
- Ensure payment was created in database before verification
- Check reference matches what's stored in database

### "Invalid signature" on webhook
- Verify `PAYSTACK_SECRET_KEY` is correct
- Ensure webhook handler uses `request.get_data(as_text=True)`
- Check webhook is actually being sent by Paystack

---

## 📚 More Information

For detailed information, see: **PAYSTACK_MIGRATION_GUIDE.md**

Topics covered:
- Complete API specifications
- Code examples for each operation
- Common errors and solutions
- Frontend integration examples
- Webhook handling
- Test cards and payloads

---

## ✨ Summary of Changes

| Aspect | Old (Monnify) | New (Paystack) |
|--------|---------------|----------------|
| Service Class | `MonnifyPaymentService` | `PaystackPaymentService` |
| Reference Field | `monnify_reference` | `paystack_reference` |
| Import | `from payment_service import ...` | `from paystack_payment_service import ...` |
| Init Endpoint | `/api/v1/transactions/init` | `/transaction/initialize` |
| Webhooks Header | `X-Monnify-Signature` | `x-paystack-signature` |
| Amount Units | Naira | Kobo (auto-converted) |

---

## 🎯 You're All Set!

Once you complete the steps above, your Barterex payment system will be fully integrated with Paystack. Users can now:
- ✅ Fund their accounts
- ✅ Purchase credits
- ✅ Receive instant credit confirmation
- ✅ Track payment history

Good luck! 🚀
