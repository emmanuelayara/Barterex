# AI Valuator integration

Barterex talks to the separate **barterxpress-valuator** service over HTTP (`valuator_client.py`).

## What happens
1. Seller uploads an item -> item is saved as usual -> a background thread asks the valuator for a price (35-45 s).
2. The result fills the `ai_*` columns on `Item`; the admin approvals page shows "AI suggests ᗸX", confidence, comparables and risk, and pre-fills the value box (not for HIGH risk).
3. Admin approves/rejects -> Barterex reports the verdict to the valuator (`/api/verify`).
4. Credits are ONLY ever given by the admin approval (`User.credits`). The valuator never pays credits.

If the valuator is off, slow, or wrong, uploads and approvals work exactly as before.

## Settings (.env)
```
VALUATOR_API_URL=http://127.0.0.1:5001     # empty = feature off
VALUATOR_API_KEY=<same value as in the valuator's .env>
VALUATOR_API_TIMEOUT=120
VALUATOR_ENABLED=true
VALUATOR_MAX_PARALLEL=2
```

## Database
Either `flask db upgrade` (migration `add_valuator_columns`) or, for a dev database, `python add_valuator_columns.py`. Both are safe to repeat.

## Tests
`python -m pytest tests/test_valuator_client.py -q`
