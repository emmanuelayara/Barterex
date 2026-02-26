# Payment System - Test Mode Guide

## Overview
The payment system now supports **TEST MODE** for development and testing without requiring real Moniepoint API credentials.

## Current Status
✅ **TEST MODE ENABLED** - `PAYMENT_TEST_MODE=true` in `.env`

## How Test Mode Works

### 1. **Test Payment Initialization**
When you submit the fund account form:
- Input: Any amount between ₦100 and ₦1,000,000
- System creates a payment record with a test reference (e.g., `TEST_A1B2C3D4E5F6`)
- Returns a mock payment link that redirects to verification

### 2. **Automatic Verification**
After initiating a test payment:
- The form automatically redirects to the verification page with `?test=true` parameter
- The system detects this is a test payment (reference starts with `TEST_`)
- Automatically completes the payment
- Adds credits to user's account
- Displays success with new credit balance

### 3. **Test Payment Records**
All test payments are stored in the database with:
- Status: `completed` (in test mode) or `test_pending` (initial state)
- Payment metadata: `{'mode': 'test', 'verified': True}`
- Reason: `test_payment` (as transaction reason)
- Description prefix: `[TEST]` to clearly identify test transactions

## Testing the Payment Flow

### Step 1: Start the Application
```bash
python app.py
```

### Step 2: Access Fund Account Page
1. Log in to your account
2. Click "Fund Account" button on dashboard
3. Or navigate to: `/payments/fund-account`

### Step 3: Enter Test Amount
1. Enter any amount between ₦100 and ₦1,000,000
2. Observe credits display update in real-time (1 Naira = 1 Credit)
3. Click "Fund Account" button

### Step 4: Watch Test Flow
1. ✓ Loading spinner appears
2. ✓ After ~1-2 seconds, success message shows
3. ✓ Automatically redirected to success page
4. ✓ Credits added to account

### Example Test Scenarios
```
Test Case 1: Minimum Amount
Amount: ₦100
Credits: 100
Expected: Success, balance increases by 100

Test Case 2: Mid-Range Amount  
Amount: ₦5,000
Credits: 5,000
Expected: Success, balance increases by 5,000

Test Case 3: Large Amount
Amount: ₦500,000
Credits: 500,000
Expected: Success, balance increases by 500,000

Test Case 4: Below Minimum
Amount: ₦50
Expected: Error - "Minimum amount is ₦100"

Test Case 5: Above Maximum
Amount: ₦2,000,000
Expected: Error - "Maximum amount is ₦1,000,000"
```

## Switching to Production Mode

### When Ready to Use Real Credentials:

1. **Obtain Moniepoint Credentials**
   - Sign up at: https://app.moniepoint.com
   - Get API Key and Public Key
   - Set up callback URL

2. **Update .env File**
   ```env
   PAYMENT_TEST_MODE=false
   MONIEPOINT_API_KEY=your_actual_key_here
   MONIEPOINT_PUBLIC_KEY=your_actual_key_here
   PAYMENT_CALLBACK_URL=https://yourdomain.com/payments/webhook
   ```

3. **Restart Application**
   ```bash
   python app.py
   ```

## Debugging Test Mode

### Check Test Mode Status
- Open browser console (F12)
- Submit a test payment
- Console will show: `[TEST MODE] Payment created: TEST_XXXXXX for 5000 naira (5000 credits)`

### View Payment Records
1. Access payment history: `/payments/history`
2. Look for entries with:
   - Status: `completed`
   - Description starting with `[TEST]`
   - Recent timestamps

### Database Inspection
```python
# In Python shell
from models import Payment, CreditTransaction
from app import app, db

with app.app_context():
    # View test payments
    test_payments = Payment.query.filter(Payment.moniepoint_reference.like('TEST_%')).all()
    for p in test_payments:
        print(f"{p.id}: {p.moniepoint_reference} - ₦{p.amount_naira} ({p.status})")
```

## Known Limitations of Test Mode

⚠️ **Test Mode Only Features:**
- Payments are always auto-completed
- No real Moniepoint interaction
- All references start with `TEST_` prefix
- Webhooks are not tested
- Payment method is fixed as `test_card`

✅ **What Works the Same:**
- Database records created and stored
- Credit calculations (1 Naira = 1 Credit)
- User balance updates
- Transaction history tracking
- Error handling and validation
- UI/UX flow

## Frontend Test Mode Detection

The payment form now detects test mode responses and:
1. Recognizes test reference pattern: `TEST_XXXXXX`
2. Shows "Test Payment Initiated" message
3. Automatically redirects to verification after 1.5 seconds
4. No manual Moniepoint payment required

## Troubleshooting

### Issue: Payment Form Hangs
- **Cause**: Backend not responding
- **Fix**: Check server logs, restart Flask app
- **Test**: Form has 10-second timeout - should show error if no response

### Issue: Credits Not Added
- **Cause**: Verification failing silently
- **Fix**: 
  1. Check browser console for errors
  2. Check server logs for error messages
  3. Verify user is logged in

### Issue: Test Mode Not Active
- **Cause**: `PAYMENT_TEST_MODE` not set to `true`
- **Fix**: 
  1. Edit `.env` file
  2. Set: `PAYMENT_TEST_MODE=true`
  3. Restart Flask app

## Next Steps

1. ✅ Test entire payment flow in test mode
2. ✅ Verify UI doesn't freeze (timeout fix applied)
3. ✅ Check credit calculations work correctly
4. ✅ Validate payment history is tracking transactions
5. ⏳ Obtain real Moniepoint credentials for production
6. ⏳ Switch to production mode and test with real sandbox
7. ⏳ Set up webhook receiver for real payment callbacks
8. ⏳ Deploy to production

## Support

For issues or questions:
- Check server console for error messages: `[TEST MODE]` or `[ERROR]` prefixes
- Review `.env` configuration
- Restart Flask application after any changes
- Clear browser cache if experiencing UI issues
