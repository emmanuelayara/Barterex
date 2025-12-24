# Rate Limiting - Quick Reference

**Status:** ✅ ACTIVE
**Endpoints Protected:** 3 critical endpoints

---

## What's Protected

| Endpoint | Limit | Why |
|----------|-------|-----|
| `/checkout` | 10/min | Prevents spam validation |
| `/api/estimate-price` | 5/min | Prevents AI processing abuse (strictest) |
| `/finalize_purchase` | 10/min | Prevents transaction spam |

---

## How It Works

```
User sends request
    ↓
Check: Has this IP exceeded 5-10 requests/minute?
    ├─ NO → Allow request ✅
    └─ YES → Return 429 error ❌
    
Normal users (1-2 requests/min): Always allowed ✅
Attackers (100+ requests/min): After 5-10 requests → 429 error ❌
```

---

## User Experience

### Normal User
```
✅ Estimate item: 1 request/minute = Allowed
✅ Checkout: 1 request/minute = Allowed
✅ Purchase: 1 request/minute = Allowed
✅ All 3 requests total = All allowed
```

### Spam/Attack
```
❌ 100 requests in 10 seconds
├─ First 5 requests: ✅ Allowed (on /api/estimate-price)
├─ Requests 6+: ❌ 429 Too Many Requests
└─ Wait 60 seconds, try again...
```

---

## Error Messages

### When Rate Limited (429)
```
HTTP Status: 429 Too Many Requests

User sees: "You've made too many requests. Please wait a minute and try again."
```

### Response Headers
```
X-RateLimit-Limit: 5        # Maximum per minute
X-RateLimit-Remaining: 0    # Remaining requests
X-RateLimit-Reset: 123456   # Unix timestamp when limit resets
```

---

## Code Examples

### Decorators Used
```python
# Strict: AI processing endpoint
@limiter.limit("5 per minute")
def estimate_item_price():
    ...

# Moderate: Transaction endpoints
@limiter.limit("10 per minute")
def checkout():
    ...

@limiter.limit("10 per minute")
def finalize_purchase():
    ...
```

### Catching Error in Frontend
```javascript
// JavaScript
fetch('/checkout', {method: 'POST'})
  .then(response => {
    if (response.status === 429) {
      alert('Please wait a minute before trying again');
      return;
    }
    return response.json();
  })
```

### Catching in Python
```python
import requests

try:
    resp = requests.post('/checkout')
    if resp.status_code == 429:
        print("Rate limited! Wait 60 seconds")
    else:
        print("Success!")
except Exception as e:
    print(f"Error: {e}")
```

---

## Configuration

### Current Setup (app.py)
```python
limiter = Limiter(
    app=app,
    key_func=get_remote_address,      # Rate limit by IP
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"            # In-memory (single instance)
)
```

### For Multi-Instance (use Redis)
```python
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="redis://localhost:6379"  # ← Redis
)
```

---

## Testing

### Verify Working
```bash
# First request
curl -X POST http://localhost:5000/checkout

# Check rate limit headers
curl -v -X POST http://localhost:5000/checkout
# Look for: X-RateLimit-Remaining: X
```

### Trigger Rate Limit
```bash
# Send 11 requests rapidly to /checkout
for i in {1..11}; do
  echo "Request $i:"
  curl -X POST http://localhost:5000/checkout
done

# First 10: Success
# 11th: 429 Too Many Requests
```

### Wait for Reset
```bash
# After 60 seconds, try again
sleep 60
curl -X POST http://localhost:5000/checkout
# Should succeed again
```

---

## Common Questions

**Q: Will legitimate users be affected?**
A: No. Normal users make 1-2 requests/minute. Limits are 5-10/minute.

**Q: What if user is on shared WiFi?**
A: They share the IP with others. If others spam, everyone on that IP gets throttled. Standard behavior for rate limiting.

**Q: Can we raise the limits?**
A: Yes. Edit routes/items.py and change the @limiter.limit() values. Lower = stricter, Higher = more lenient.

**Q: Does it work with multiple servers?**
A: No, not yet. Currently uses in-memory storage. For multiple instances, switch to Redis.

**Q: Can admins bypass rate limiting?**
A: Currently no. Could add @limiter.exempt to admin endpoints if needed.

---

## Limits Explained

### Why 5/min for /api/estimate-price?
- AI image analysis is CPU intensive
- Takes ~2 seconds per request
- Users estimate 1-2 items per minute max
- Stricter limit protects against abuse

### Why 10/min for /checkout and /finalize_purchase?
- Less resource intensive
- Users might click multiple times quickly (accidental double-click)
- 10/minute = 1 every 6 seconds (reasonable for human)
- Prevents spam but allows natural user behavior

### Global 200/day, 50/hour?
- Fallback for all other endpoints
- Prevents long-term abuse
- 50/hour = 1 every 72 seconds (reasonable baseline)
- 200/day = user can be active for hours

---

## Files Modified

- [routes/items.py](routes/items.py#L9) - Added limiter import
- [routes/items.py](routes/items.py#L299) - Added @limiter to /checkout
- [routes/items.py](routes/items.py#L342) - Added @limiter to /finalize_purchase  
- [routes/items.py](routes/items.py#L778) - Added @limiter to /api/estimate-price

---

## Status

✅ **ACTIVE** - All three endpoints protected
✅ **TESTED** - Rate limiting working
✅ **PRODUCTION READY** - Can be deployed immediately

---

**Security Status: API SPAM PROTECTED ✅**
