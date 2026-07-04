# Moniepoint Payment Integration Guide for Barterex

## Overview
This guide walks you through setting up Moniepoint payment processing for users to buy credits with cash on the Barterex platform.

## What's Been Implemented

### 1. Database Model (`models.py`)
- **Payment Model**: Tracks all payment transactions
  - Stores Moniepoint reference, amount, credits, status
  - Links to user and transaction history
  - Tracks payment method and metadata

### 2. Payment Service (`payment_service.py`)
- **MoniePointPaymentService**: Core payment operations
  - `initiate_payment()`: Start a payment with Moniepoint
  - `verify_payment()`: Check payment status and credit user
  - `verify_webhook_signature()`: Secure webhook verification
  - Payment history and package management

### 3. Payment Routes (`routes/payments.py`)
- `/payments/fund-account` - Main funding page
- `/payments/verify-payment/<reference>` - Payment verification
- `/payments/status/<id>` - API endpoint for status
- `/payments/history` - User payment history
- `/payments/webhook` - Moniepoint callback endpoint
- `/payments/api/packages` - Get credit packages
- `/payments/cancel` - Handle cancelled payments

### 4. Frontend Templates
- `fund_account.html` - Beautiful credit purchase page with packages
- `payment_success.html` - Success confirmation
- `payment_failed.html` - Failure handling
- `payment_cancelled.html` - Cancellation page
- `payment_error.html` - Error page
- `payment_history.html` - Transaction history

### 5. Dashboard Integration
- "Fund Account" button on credit balance card
- Quick access to payment page from dashboard

---

## Setup Instructions

### Step 1: Get Moniepoint API Credentials

1. Visit [Moniepoint Business Dashboard](https://dashboard.moniepoint.com)
2. Create a business account or login
3. Go to **Settings > API Keys**
4. Generate:
   - **API Key** (Secret key)
   - **Public Key** (for frontend, optional for current setup)
5. Copy these credentials

### Step 2: Update Environment Variables

Edit `.env` file and add:
```env
MONIEPOINT_API_KEY=your_actual_api_key_here
MONIEPOINT_API_URL=https://api.moniepoint.com
MONIEPOINT_PUBLIC_KEY=your_public_key_here
PAYMENT_CALLBACK_URL=https://yourdomain.com/api/payments/webhook
```

**For Development:**
```env
MONIEPOINT_API_URL=https://sandbox.moniepoint.com
```

**For Production:**
```env
MONIEPOINT_API_URL=https://api.moniepoint.com
PAYMENT_CALLBACK_URL=https://barterex.com.ng/payments/webhook
```

### Step 3: Run Database Migration

Create the Payment table:
```bash
# Using Flask-Migrate
flask db migrate -m "Add Payment model for Moniepoint"
flask db upgrade

# OR manually with SQLite
python -c "
from app import app, db
with app.app_context():
    db.create_all()
"
```

### Step 4: Install Required Package

```bash
pip install requests
```

### Step 5: Update app.py (Already Done)

The payment blueprint is already registered. Verify in `app.py`:
```python
from routes.payments import payment_bp
...
app.register_blueprint(payment_bp)
```

### Step 6: Configure Moniepoint Webhook

1. Go to **Moniepoint Dashboard > Webhooks**
2. Add webhook URL:
   ```
   https://yourdomain.com/payments/webhook
   ```
3. Select events:
   - `charge.success`
   - `charge.failed`

---

## How It Works

### User Flow

1. **User clicks "Fund Account"** on dashboard credit balance card
2. **Sees credit packages** with pricing (₦500, ₦2000, ₦3500, ₦15000)
3. **Clicks "Buy Now"** for desired package
4. **Redirected to Moniepoint** payment page
5. **Completes payment** (card, bank transfer, USSD)
6. **Returns to your app** with transaction reference
7. **Payment verified** and credits added automatically
8. **Success page** confirms credits

### Behind the Scenes

```
User clicks Buy
    ↓
initiate_payment() creates Payment record
    ↓
Sends request to Moniepoint API
    ↓
Receives payment link
    ↓
User redirected to Moniepoint
    ↓
User completes payment
    ↓
Webhook callback received
    ↓
verify_payment() checks with Moniepoint
    ↓
Credits added to user account
    ↓
Transaction logged
    ↓
Success confirmation sent
```

---

## Credit Packages Configuration

Edit credit conversion rate in `payment_service.py`:

```python
# Conversion rate: 1 Naira = 1 Credit
CONVERSION_RATE = 1.0

# Minimum and maximum amounts
MIN_AMOUNT = 100  # Minimum ₦100
MAX_AMOUNT = 1000000  # Maximum ₦1,000,000
```

**How it works:**
- User enters any amount (₦100 - ₦1,000,000)
- They receive that exact amount in credits
- ₦5000 payment = 5000 credits
- ₦100 payment = 100 credits

---

## API Endpoints Reference

### For Frontend

#### Get Available Packages
```
GET /payments/api/packages
Response: [
  {credits: 100, amount: 500, popular: false},
  ...
]
```

#### Check Payment Status
```
GET /payments/status/<payment_id>
Response: {
  id: 1,
  amount: 500,
  credits: 100,
  status: "completed",
  created_at: "2024-01-15T10:30:00",
  reference: "MP_ABC123..."
}
```

#### Get Payment History
```
GET /payments/history
Returns: payment_history.html with all transactions
```

### For Moniepoint (Webhook)

```
POST /payments/webhook
Headers:
  X-Moniepoint-Signature: <verified_signature>
Body:
  {
    event: "charge.success",
    data: {
      reference: "MP_ABC123...",
      amount: 50000,
      status: "success"
    }
  }
```

---

## Database Schema

### Payment Table
```sql
CREATE TABLE payment (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    moniepoint_reference VARCHAR(255) UNIQUE NOT NULL,
    amount_naira FLOAT NOT NULL,
    credits_purchased INTEGER NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    payment_method VARCHAR(100),
    created_at DATETIME DEFAULT NOW(),
    paid_at DATETIME,
    expires_at DATETIME,
    currency VARCHAR(3) DEFAULT 'NGN',
    customer_email VARCHAR(120),
    customer_phone VARCHAR(15),
    metadata JSON,
    error_message TEXT,
    FOREIGN KEY (user_id) REFERENCES user(id)
);
```

---

## Testing

### Test with Sandbox

1. Change `MONIEPOINT_API_URL` to `https://sandbox.moniepoint.com`
2. Use test card: `4111 1111 1111 1111` (Expiry: any future date, CVV: any 3 digits)
3. Go to `/payments/fund-account`
4. Select package and complete flow

### Test Webhook Locally

Use ngrok to expose local server:
```bash
ngrok http 5000
# Then update PAYMENT_CALLBACK_URL in .env
PAYMENT_CALLBACK_URL=https://your-ngrok-url.ngrok.io/payments/webhook
```

---

## Error Handling

### Common Issues

1. **"Invalid Signature"**
   - Verify `MONIEPOINT_API_KEY` is correct
   - Check webhook is being called from Moniepoint

2. **"Payment link not working"**
   - Ensure `MONIEPOINT_API_KEY` is valid
   - Check internet connection
   - Verify API URL is correct for env (sandbox vs production)

3. **"Credits not added"**
   - Check webhook is receiving callbacks
   - Verify signature verification passes
   - Check database has Payment model

4. **"User not found"**
   - Ensure user is logged in before initiating payment
   - Check user ID is being passed correctly

---

## Security Best Practices

✅ **Implemented:**
- HMAC signature verification for webhooks
- CSRF protection on payment form
- HTTPS only (production)
- Secure API key storage in .env
- No sensitive data in logs

✅ **Additional Recommendations:**
- Store API keys in environment variables (never commit to git)
- Use HTTPS in production
- Implement rate limiting on payment endpoints
- Monitor payment failures for fraud detection
- Regularly audit payment logs
- Keep Moniepoint SDK updated

---

## Troubleshooting

### Payment initiated but verification fails
```python
# Check in routes/payments.py
# Ensure webhook endpoint is receiving calls
# Verify signature validation
```

### Credits not appearing after payment
1. Check `payment.status` in database
2. Verify webhook was called
3. Check `verify_payment()` logic
4. Review error logs

### Testing locally without ngrok
1. Moniepoint won't call localhost
2. Use ngrok to expose your local server
3. Or deploy to staging server first

---

## Next Steps

1. **Go Live:**
   - Update to production API keys
   - Change `MONIEPOINT_API_URL` to live URL
   - Update callback URL to production domain

2. **Monitor:**
   - Track failed payments
   - Monitor webhook calls
   - Review transaction logs

3. **Extend:**
   - Add email receipts
   - Implement payment analytics
   - Add admin payment management dashboard
   - Create payment refund system

4. **Support:**
   - Create FAQ about payment issues
   - Set up contact form for payment help
   - Add payment troubleshooting guide

---

## Support & Resources

- **Moniepoint API Docs**: https://documentation.moniepoint.com
- **Sandbox Testing**: https://sandbox.moniepoint.com
- **GitHub Issues**: Report bugs in your repo
- **Status Page**: Check Moniepoint uptime

---

## File Structure Created

```
routes/
  └── payments.py          # Payment routes

templates/payments/
  ├── fund_account.html    # Main funding page
  ├── payment_success.html # Success page
  ├── payment_failed.html  # Failure page
  ├── payment_cancelled.html # Cancellation page
  ├── payment_error.html   # Error page
  └── payment_history.html # History page

payment_service.py          # Payment service logic

models.py                   # Updated with Payment model
app.py                      # Updated with payment_bp
.env                        # Updated with Moniepoint credentials
```

---

**Implementation Complete! Your Barterex users can now buy credits with cash via Moniepoint! 🎉**
