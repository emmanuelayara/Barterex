# Monnify to Paystack Migration Guide

## Overview
This guide documents the complete migration from Monnify payment gateway to Paystack for the Barterex application.

## What Has Changed

### New Files Created
- **`paystack_payment_service.py`** - New payment service class for Paystack integration
  - Handles payment initiation, verification, and webhook processing
  - Replaces Monnify-specific payment logic
  - Includes test mode for development

### Files Modified

#### 1. **models.py** - Payment Model
**Changes:**
- `monnify_reference` field changed from `NOT NULL` to `nullable=True`
- New field added: `paystack_reference` (unique, nullable=True)
- Model now supports both Monnify (legacy) and Paystack references
- Updated docstring to reflect multi-gateway support

**Before:**
```python
monnify_reference = db.Column(db.String(255), unique=True, nullable=False, index=True)
```

**After:**
```python
monnify_reference = db.Column(db.String(255), unique=True, nullable=True, index=True)  # Legacy
paystack_reference = db.Column(db.String(255), unique=True, nullable=True, index=True)  # Paystack
```

#### 2. **routes/payments.py** - Payment Routes
**Changes:**
- Import changed from `MonnifyPaymentService` to `PaystackPaymentService`
- All payment initiation calls now use Paystack API
- Webhook endpoint updated to use Paystack signature (`x-paystack-signature`)
- Webhook event handling for Paystack format
- All Monnify references replaced with Paystack equivalents

**Key Route Changes:**
- `/fund-account` - Initiates Paystack transactions
- `/verify-payment/<reference>` - Verifies with Paystack API
- `/webhook` - Handles Paystack callbacks
- `/status/<payment_id>` - Uses Paystack service
- `/history` - Uses Paystack service
- `/api/packages` - Returns Paystack config

#### 3. **.env** - Environment Configuration
**Changes:**
- Removed Monnify credentials
- Added Paystack credentials (commented as templates)
- Updated `PAYMENT_CALLBACK_URL` to point to same webhook endpoint
- Both configurations documented for reference

## Setup Instructions

### Step 1: Create Paystack Account
1. Go to [Paystack Dashboard](https://dashboard.paystack.com)
2. Create/login to your account
3. Go to **Settings > API Keys & Webhooks**
4. Copy your keys:
   - **Live Public Key** (starts with `pk_live_`)
   - **Live Secret Key** (starts with `sk_live_`)
   - Or **Test Keys** for development

### Step 2: Update .env File
Edit your `.env` file with Paystack credentials:

**Development (Test Mode):**
```env
PAYSTACK_PUBLIC_KEY=pk_test_YOUR_PUBLIC_KEY
PAYSTACK_SECRET_KEY=sk_test_YOUR_SECRET_KEY
PAYSTACK_API_URL=https://api.paystack.co
PAYMENT_TEST_MODE=true
PAYMENT_CALLBACK_URL=http://127.0.0.1:5000/payments/webhook
```

**Production:**
```env
PAYSTACK_PUBLIC_KEY=pk_live_YOUR_PUBLIC_KEY
PAYSTACK_SECRET_KEY=sk_live_YOUR_SECRET_KEY
PAYSTACK_API_URL=https://api.paystack.co
PAYMENT_TEST_MODE=false
PAYMENT_CALLBACK_URL=https://yourdomain.com/payments/webhook
```

### Step 3: Database Migration

Run a database migration to update the Payment model:

```bash
# Using Flask-Migrate
flask db migrate -m "Add Paystack support to Payment model"
flask db upgrade
```

If using Flask-Migrate is not set up, apply changes directly:

```bash
python
>>> from app import app, db
>>> with app.app_context():
...     db.create_all()
```

### Step 4: Set Up Paystack Webhook

1. Go to [Paystack Dashboard](https://dashboard.paystack.com)
2. Navigate to **Settings > Webhooks**
3. Add webhook URL:
   ```
   https://yourdomain.com/payments/webhook
   ```
4. Select events to listen to:
   - `charge.success` (required)
   - `charge.failed` (optional but recommended)

### Step 5: Update Frontend (if applicable)

If you have frontend code that initializes payments:

**Before (Monnify):**
```javascript
const result = MonnifyPaymentService.initiate_payment(userId, amount);
```

**After (Paystack):**
```javascript
const result = PaystackPaymentService.initiate_payment(userId, amount);
// Paystack returns authorization_url instead of checkoutUrl
window.location.href = result.authorization_url;
```

### Step 6: Test the Integration

#### Test Mode (using PAYMENT_TEST_MODE=true)
```bash
# Fund account with test amount
POST /payments/fund-account
{
    "amount": 100
}

# Response will include test reference starting with "TEST_"
# All test payments auto-complete without real API calls
```

#### Production Mode
```bash
# Set PAYMENT_TEST_MODE=false
# Fund account with real amount
POST /payments/fund-account
{
    "amount": 500
}

# User will be redirected to Paystack payment form
# After payment, webhook will verify and credit account
```

## Key Differences: Paystack vs Monnify

| Feature | Monnify | Paystack |
|---------|---------|----------|
| **Auth Method** | Basic Auth + Bearer Token | Bearer Token only |
| **Amount Unit** | Naira | Kobo (100 kobo = 1 Naira) |
| **Init Endpoint** | `/api/v1/transactions/init` | `/transaction/initialize` |
| **Verify Endpoint** | `/api/v1/transactions/query` | `/transaction/verify/{ref}` |
| **Webhook Header** | `X-Monnify-Signature` | `x-paystack-signature` |
| **Success Status** | `PAID`, `SUCCESSFUL` | `success` |
| **Test Prefix** | Bank Transfer, USSD | Test cards provided |

## Code Examples

### Initialize Payment
```python
from paystack_payment_service import PaystackPaymentService

# Initiate payment (500 Naira)
result = PaystackPaymentService.initiate_payment(user_id=123, amount_naira=500)

if result['success']:
    # Redirect user to payment page
    payment_link = result['payment_link']  # Paystack authorization URL
    reference = result['reference']  # Store for verification
else:
    print(result['error'])
```

### Verify Payment
```python
result = PaystackPaymentService.verify_payment(reference='barterex_123_1234567890')

if result['success']:
    print(f"Credits added: {result['credits_added']}")
    print(f"New balance: {result['new_balance']}")
else:
    print(f"Error: {result['error']}")
```

### Webhook Verification
```python
# In webhook handler
signature = request.headers.get('x-paystack-signature')
payload = request.get_data(as_text=True)

if PaystackPaymentService.verify_webhook_signature(signature, payload):
    # Process payment
    data = request.get_json()
    reference = data['data']['reference']
    result = PaystackPaymentService.verify_payment(reference)
```

## Testing Paystack Integration

### Test Card Numbers
Paystack provides test cards for development:

```
Card Number: 4084084084084081
Expiry: Any future date (e.g., 12/25)
CVV: Any 3 digits
OTP: Leave blank (auto-verified)
```

### Test Webhook
You can manually test webhooks using Paystack's test feature in the dashboard.

## API Response Examples

### Initialize Payment Response
```json
{
    "success": true,
    "payment_link": "https://checkout.paystack.com/...",
    "reference": "barterex_123_1234567890",
    "payment_id": 1,
    "access_code": "..."
}
```

### Verify Payment Response
```json
{
    "success": true,
    "message": "Payment verified and credits added",
    "credits_added": 500,
    "new_balance": 1500
}
```

### Webhook Payload
```json
{
    "event": "charge.success",
    "data": {
        "id": 123456789,
        "reference": "barterex_123_1234567890",
        "amount": 50000,
        "customer": {
            "id": 456,
            "email": "user@example.com"
        },
        "status": "success",
        "channel": "card",
        "currency": "NGN",
        "authorization": {...}
    }
}
```

## Troubleshooting

### Issue: "Invalid signature"
**Cause:** Secret key is incorrect or webhook payload wasn't received as raw text
**Solution:** 
- Verify `PAYSTACK_SECRET_KEY` in `.env`
- Ensure webhook handler uses `request.get_data(as_text=True)`

### Issue: "Payment not found"
**Cause:** Payment reference doesn't exist in database
**Solution:**
- Ensure payment was created before verification
- Check reference format matches database

### Issue: "Unauthorized" on verify-payment route
**Cause:** User trying to verify payment they don't own
**Solution:**
- This is a security feature
- Each user can only verify their own payments

### Issue: Test mode not working
**Cause:** `PAYMENT_TEST_MODE` not set to `true`
**Solution:**
```env
PAYMENT_TEST_MODE=true
```
- Restart the Flask app after changing .env

## Migration Checklist

- [ ] Created Paystack account
- [ ] Obtained Paystack API keys (test and live)
- [ ] Updated `.env` with Paystack credentials
- [ ] Ran database migration for Payment model
- [ ] Configured Paystack webhook in dashboard
- [ ] Tested payment flow in test mode
- [ ] Updated any frontend code that calls payment service
- [ ] Verified webhook receives messages
- [ ] Tested with real payment in production
- [ ] Disabled test mode (`PAYMENT_TEST_MODE=false`)
- [ ] Archived Monnify payment service

## Rollback Instructions

If you need to revert to Monnify:

1. Keep old `payment_service.py` as backup
2. Restore import in `routes/payments.py`:
   ```python
   from payment_service import MonnifyPaymentService
   ```
3. Update all service calls back to Monnify
4. Restore `.env` with Monnify credentials
5. Run `flask db downgrade` to revert model changes

## Support & Debugging

### Enable Debug Logging
All payment operations log to console with `[PAYSTACK API]`, `[PAYSTACK VERIFY]` prefixes.

### Common Headers in Requests
```
Authorization: Bearer sk_test_YOUR_SECRET_KEY
Content-Type: application/json
```

### Webhook Debug
Print received webhooks:
```python
@payment_bp.route('/webhook', methods=['POST'])
def webhook():
    print(f'[WEBHOOK] Received: {request.get_data(as_text=True)}')
    # ... rest of webhook handler
```

## References

- [Paystack Documentation](https://paystack.com/docs/api/)
- [Paystack Integration Guide](https://paystack.com/docs/integration/web/)
- [Webhook Documentation](https://paystack.com/docs/webhooks/)
- [Test Cards](https://paystack.com/docs/payments/test-cards/)
