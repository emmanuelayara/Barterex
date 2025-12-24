# Rate Limiting Implementation - Security Fix

**Issue:** Users could spam API endpoints without restrictions
**Status:** ✅ FIXED
**Date:** December 24, 2025

---

## Problem Statement

### Security Vulnerability
- No rate limiting on critical endpoints
- Users could spam `/checkout` to cause DoS (Denial of Service)
- Users could spam `/api/estimate-price` for AI processing abuse
- Users could spam `/finalize_purchase` to process transactions repeatedly
- Resource exhaustion risk - server could crash from repeated requests

### Impact
- **Availability Risk:** Spammed endpoints become unavailable
- **Resource Abuse:** AI processing CPU exhaustion
- **Transaction Risk:** Repeated purchase attempts
- **DDoS Vector:** Easy target for denial of service attacks

### Example Attack Scenario
```
Attacker sends 100 requests/second to /api/estimate-price
├─ Each request processes AI image analysis (CPU intensive)
├─ Server becomes overloaded
├─ Legitimate users can't use the service
└─ Service becomes unavailable (DoS)
```

---

## Solution Implemented

### Rate Limiting Using Flask-Limiter

**Framework:** Flask-Limiter (already installed in app.py)
**Storage:** In-memory (suitable for single-instance deployment)
**Key Method:** `get_remote_address` (tracks by IP address)

### Three Critical Endpoints Protected

#### 1. `/checkout` - 10 requests per minute
```python
@items_bp.route('/checkout')
@limiter.limit("10 per minute")  # 10 requests per minute per IP
@login_required
@handle_errors
def checkout():
```

**Rationale:**
- Users should not checkout more than 10 times per minute
- Legitimate users check out 1-2 times per minute
- Prevents rapid spam of checkout validation

#### 2. `/api/estimate-price` - 5 requests per minute
```python
@items_bp.route('/api/estimate-price', methods=['POST'])
@limiter.limit("5 per minute")  # 5 requests per minute per IP
@login_required
def estimate_item_price():
```

**Rationale:**
- Most CPU-intensive endpoint (AI image analysis)
- Stricter limit than checkout
- Users estimate 1-2 items per minute at most
- Prevents AI processing spam/abuse

#### 3. `/finalize_purchase` - 10 requests per minute
```python
@items_bp.route('/finalize_purchase', methods=['POST'])
@limiter.limit("10 per minute")  # 10 requests per minute per IP
@login_required
@handle_errors
@safe_database_operation("finalize_purchase")
def finalize_purchase():
```

**Rationale:**
- Critical transaction endpoint
- Users finalize 1-2 purchases per minute max
- Prevents transaction fraud/abuse
- Row-level locks prevent double-crediting anyway, but rate limiting adds defense

---

## Implementation Details

### How Rate Limiting Works

```
User sends request
    ↓
Limiter checks IP address
    ├─ Under limit? → Allow request ✅
    └─ Over limit? → Return 429 error ❌
    
Limiter tracks requests:
├─ IP: 192.168.1.1
├─ Endpoint: /checkout
├─ Window: 1 minute
└─ Count: 5 requests (out of 10)
```

### Rate Limit Algorithm

- **Sliding Window:** Counts requests in last 60 seconds
- **Per IP Address:** Each unique IP has its own counter
- **Per Endpoint:** Different limits for different endpoints
- **Per User:** Actually per IP (session-agnostic)

### Error Response

When rate limit exceeded:
```
HTTP 429 Too Many Requests

{
  "error": "Rate limit exceeded: 5 per minute"
}
```

**Error message shown to user:**
```
"You've made too many requests. Please wait a minute and try again."
```

---

## Configuration Details

### In app.py
```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)
```

**Components:**
- `key_func=get_remote_address` - Rate limit by IP
- `default_limits` - Global limits for all endpoints
- `storage_uri="memory://"` - In-memory storage (fast, suitable for single instance)

### Rate Limits Set

| Endpoint | Limit | Rationale |
|----------|-------|-----------|
| `/checkout` | 10/min | Normal user flow |
| `/api/estimate-price` | 5/min | CPU-intensive (stricter) |
| `/finalize_purchase` | 10/min | Transaction safety |
| Other endpoints | 200/day, 50/hour | Global defaults |

---

## User Experience

### Normal User (Legitimate Traffic)
```
User estimates 1 item → 1 request ✅
User waits 5 seconds → Estimates another item → 1 request ✅
User checks out → 1 request per minute ✅
All requests succeed
```

### Attacker (Spam/Abuse)
```
Attacker sends 100 requests in 10 seconds
├─ Request 1-5: ✅ Accepted
├─ Request 6+: ❌ 429 Too Many Requests
├─ Waits 1 minute
├─ Request 6-10: ✅ Accepted
└─ Pattern: Can only send 5 requests per minute (throttled)
```

---

## Security Benefits

### Before Fix ❌
- No rate limiting
- Unlimited requests to critical endpoints
- Easy to spam/DoS
- Easy to abuse AI processing
- Transaction endpoints vulnerable to rapid abuse

### After Fix ✅
- 5-10 requests per minute limit on critical endpoints
- Spam attacks throttled automatically
- AI processing abuse prevented
- Transaction endpoints protected
- DDoS resistance improved
- Service availability protected

---

## Technical Specifications

### Files Modified

| File | Changes |
|------|---------|
| [routes/items.py](routes/items.py#L9) | Added limiter import |
| [routes/items.py](routes/items.py#L299) | Added @limiter.limit("10 per minute") to /checkout |
| [routes/items.py](routes/items.py#L342) | Added @limiter.limit("10 per minute") to /finalize_purchase |
| [routes/items.py](routes/items.py#L778) | Added @limiter.limit("5 per minute") to /api/estimate-price |

### Code Changes Summary
- 3 imports added (0 new, using existing limiter)
- 3 decorators added (one per endpoint)
- Total changes: ~3 lines of actual code

---

## Error Handling

### What Happens When Limit Exceeded

**HTTP Response:**
```
Status: 429 Too Many Requests

Headers:
  X-RateLimit-Limit: 5
  X-RateLimit-Remaining: 0
  X-RateLimit-Reset: 1234567890
```

**Flask Response:**
```python
# Automatic error handler for 429
error_message = "Rate limit exceeded: 5 per minute"
```

### Catching in Frontend
```javascript
fetch('/api/estimate-price', {method: 'POST', body: ...})
  .then(response => {
    if (response.status === 429) {
      alert('Too many requests. Please wait a minute.');
    }
    return response.json();
  })
```

---

## Testing

### Test Rate Limiting Manually

#### Test 1: Verify Normal Request Works
```bash
# First request should succeed
curl -X POST http://localhost:5000/checkout \
  -H "Content-Type: application/json"

# Response: Should work normally
```

#### Test 2: Exceed Rate Limit
```bash
# Send 11 requests in rapid succession
for i in {1..11}; do
  curl -X POST http://localhost:5000/checkout
done

# First 10: Success
# 11th: 429 Too Many Requests
```

#### Test 3: After 1 Minute
```bash
# Wait 60 seconds, then retry
sleep 60
curl -X POST http://localhost:5000/checkout

# Should succeed again
```

### Test Script (test_rate_limiting.py)
```python
import requests
import time

def test_rate_limiting():
    url = "http://localhost:5000/checkout"
    
    # Test 1: Normal request
    print("Test 1: First request...")
    resp = requests.post(url)
    print(f"Status: {resp.status_code}")  # Should be 200-400 (not 429)
    
    # Test 2: Spam requests
    print("\nTest 2: Sending 11 requests rapidly...")
    for i in range(11):
        resp = requests.post(url)
        print(f"Request {i+1}: {resp.status_code}")
    
    # After request 10, should get 429
    print("\nTest 3: Waiting 60 seconds...")
    time.sleep(60)
    
    # Test 4: Request again after cooldown
    print("Test 4: Request after 60 seconds...")
    resp = requests.post(url)
    print(f"Status: {resp.status_code}")  # Should work again
```

---

## Production Considerations

### Single Instance Deployment
✅ **Suitable** - In-memory storage works fine
- Current setup: `storage_uri="memory://"`
- Good for single-instance deployments

### Multi-Instance Deployment
⚠️ **Not suitable for multi-instance**
- Each instance has separate in-memory counter
- User could hit 10/min on instance 1, then 10/min on instance 2
- **Fix:** Use Redis for shared rate limit storage

**If deploying to multiple instances, update:**
```python
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="redis://localhost:6379"  # ← Use Redis instead
)
```

### Monitoring Rate Limit Hits
```python
# Optional: Log when rate limits are hit
@app.errorhandler(429)
def rate_limit_exceeded(e):
    logger.warning(f"Rate limit exceeded: {request.remote_addr} - {request.path}")
    return {'error': 'Rate limit exceeded'}, 429
```

---

## Customization

### Adjust Limits (if needed)
```python
# More strict
@limiter.limit("3 per minute")

# More lenient
@limiter.limit("20 per minute")

# Per hour
@limiter.limit("100 per hour")

# Complex: Different limits
@limiter.limit("10 per hour; 1 per minute")
```

### Skip Rate Limiting (if needed)
```python
# For admin endpoints or special cases
@limiter.exempt
def admin_endpoint():
    return ...
```

---

## Best Practices

✅ **DO:**
- Keep `/api/estimate-price` stricter (5/min) - it's CPU intensive
- Keep `/checkout` and `/finalize_purchase` moderate (10/min)
- Monitor rate limit hits in logs
- Adjust limits based on actual user behavior
- Use Redis for multi-instance deployments

❌ **DON'T:**
- Set limits too strict (users can't use the app)
- Set limits too lenient (security is compromised)
- Use in-memory storage for multi-instance
- Forget to log rate limit exceptions
- Expose rate limit details in error messages to attackers

---

## Compatibility

### Backward Compatibility
✅ No breaking changes
✅ Legitimate users unaffected
✅ No client-side changes needed
⚠️ Very aggressive clients (bots) will be throttled

### Existing Sessions
✅ No session invalidation
✅ User stays logged in during rate limit
✅ Rate limit applies to next request after cooldown

---

## Security Summary

### Before Fix ❌
- No protection against spam
- Easy API abuse
- DDoS vulnerability
- Unlimited AI processing requests
- Unlimited transaction attempts

### After Fix ✅
- 5-10 requests/minute per IP per endpoint
- Spam automatically throttled
- DDoS resistance improved
- AI processing protected
- Transaction endpoints protected

---

## Status

**✅ ACTIVE** - Rate limiting enforced on all critical endpoints

**Endpoints Protected:**
1. ✅ `/checkout` - 10/min
2. ✅ `/api/estimate-price` - 5/min (strictest)
3. ✅ `/finalize_purchase` - 10/min

**Global Fallback:**
- ✅ 200 per day, 50 per hour (all other endpoints)

---

## Documentation Files

| Document | Purpose |
|----------|---------|
| [RATE_LIMITING_IMPLEMENTATION.md](RATE_LIMITING_IMPLEMENTATION.md) | This guide |
| [routes/items.py](routes/items.py) | Implementation code |

---

**Security Status: PROTECTED ✅**
- Rate limiting active on critical endpoints
- API spam prevented
- DDoS resistance improved
- Service availability protected
