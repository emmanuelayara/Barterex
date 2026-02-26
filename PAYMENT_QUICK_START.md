# 🚀 PAYMENT SYSTEM - QUICK START GUIDE

## Current Status
- ✅ **Test Mode**: ENABLED (PAYMENT_TEST_MODE=true)
- ✅ **Loading Spinner**: FIXED (10-second timeout)
- ✅ **Error Handling**: IMPROVED
- ✅ **Ready for**: Full end-to-end testing

## Quick Test (< 5 minutes)

### 1. Start the App
```bash
python app.py
```
- Should see: `Running on http://127.0.0.1:5000`

### 2. Log In
- Go to: http://localhost:5000/dashboard
- Use your test account credentials

### 3. Fund Account
- Click "Fund Account" button on dashboard
- Enter amount: `5000`
- Click "Fund Account"
- ✅ Loading spinner appears (doesn't hang)
- ✅ Redirects to success page
- ✅ Balance updated by 5000 credits

## Test Scenarios

### ✅ Valid Amounts
- `100` → 100 credits (minimum)
- `1000` → 1000 credits  
- `5000` → 5000 credits
- `500000` → 500000 credits (large)

### ❌ Invalid Amounts
- `50` → Error: "Minimum amount is ₦100"
- `2000000` → Error: "Maximum amount is ₦1,000,000"
- Empty → Error: "Minimum amount is ₦100"
- `abc` → Error: "Invalid amount format"

## What's New

### 1. Test Mode Payment Flow
```
User enters amount
    ↓
System creates TEST_XXXXX reference
    ↓
Frontend detects test mode
    ↓
Auto-redirects to verification
    ↓
Payment marked "completed"
    ↓
Credits added to account
    ↓
Success page displayed
```

### 2. Timeout Protection
- Form has 10-second timeout
- If server doesn't respond: shows error
- Spinner automatically hidden
- Can retry immediately

### 3. Better Error Messages
- Clear reason for failures
- Min/max amount validation
- Format validation
- Network error details

## File Changes

| File | Change | Impact |
|------|--------|--------|
| `payment_service.py` | Added TEST_MODE logic | Can test without API |
| `routes/payments.py` | Better validation | Clearer errors |
| `fund_account.html` | Timeout + test mode | No freeze, instant test |
| `.env` | PAYMENT_TEST_MODE=true | Test mode active |

## Check List: Testing Verification

- [ ] App starts without errors: `python app.py`
- [ ] Can navigate to fund page: `/payments/fund-account`
- [ ] Form appears and is interactive
- [ ] Can enter amount and see credits update
- [ ] Submit button works (loading appears)
- [ ] Loader doesn't freeze (completes in ~1-2 seconds)
- [ ] Gets redirected to success page
- [ ] Balance updated correctly
- [ ] Can test multiple times
- [ ] Error cases show helpful messages

## Troubleshooting Quick Fixes

**Issue: Spinner hung/App freezed**
- Fix: Refresh page (Ctrl+R)
- Action: Check server console for errors
- Should work now ✅

**Issue: "User not found" error**
- Fix: Make sure you're logged in
- Action: Go to login page first
- Then access /payments/fund-account

**Issue: Amount error message appears**
- Fix: Enter amount between 100 and 1000000
- Try: `5000` (should work)

**Issue: Network error / Request timeout**
- Fix: Flask server May have crashed
- Action: Restart: `python app.py`
- Try payment again

## Server Console Output

Watch for these when testing:

```
[TEST MODE] Payment created: TEST_A1B2C3D4 for 5000 naira (5000 credits)
Verifying TEST payment: TEST_A1B2C3D4
[TEST MODE] Payment verified: TEST_A1B2C3D4
```

## Database Check (Optional)

See all test payments:
```python
python
>>> from app import app, db
>>> from models import Payment
>>> app.app_context().push()
>>> payments = Payment.query.filter(Payment.moniepoint_reference.like('TEST_%')).all()
>>> for p in payments: print(f"{p.id}: {p.amount_naira} → {p.credits_purchased} credits")
```

## Next Phase

When ready to test with **real** Moniepoint:

1. Get sandbox credentials from: https://app.moniepoint.com
2. Update `.env`:
   ```env
   PAYMENT_TEST_MODE=false
   MONIEPOINT_API_KEY=your_key
   MONIEPOINT_PUBLIC_KEY=your_public_key
   PAYMENT_CALLBACK_URL=https://yourdomain.com/payments/webhook
   ```
3. Restart Flask
4. Test with sandbox payment gateway

## Support Reference

**Configuration Files:**
- Python: `app.py`, `payment_service.py`, `routes/payments.py`
- Environment: `.env`
- Frontend: `templates/payments/fund_account.html`

**Key Models:**
- `Payment` - Payment records
- `CreditTransaction` - Credit ledger
- `User` - User accounts (credits field)

**Key Routes:**
- `GET /payments/fund-account` - Form page
- `POST /payments/fund-account` - Process payment
- `GET /payments/verify-payment/<ref>` - Verify & complete
- `GET /payments/history` - Transaction history

---

**Status**: Ready ✅  
**Test Mode**: Active ✅  
**Freezing Issue**: Fixed ✅  

**Next**: Run tests and verify functionality!
