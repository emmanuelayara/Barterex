# Checkout Bug Fix Report - Critical Severity

## Issue Summary
**Status**: CRITICAL - Users losing credits  
**Root Causes**: 3 distinct transaction safety issues in `process_checkout()` function

## Bugs Identified

### Bug #1: Race Condition - Item Ownership Changed Before Commit
**Severity**: CRITICAL  
**Location**: Lines 364-366 in `routes/items.py`

```python
# WRONG - Item ownership changed immediately, but not committed yet!
current_user.credits -= item.value
item.user_id = current_user.id      # ← Changed but not committed
item.is_available = False
```

**Problem**: 
- If an error occurs between line 365 and commit (line 378), the item's `user_id` is set to buyer but NOT committed
- However, credits ARE deducted from the buyer
- Database rollback reverts the item ownership, but credits remain deducted
- Result: **User loses credits but doesn't get the item**

**Scenario**:
1. User has 5000 credits
2. Buys item worth 3000 credits
3. User credits deducted to 2000 in memory
4. Item.user_id set to buyer in memory
5. Network error occurs before commit
6. Rollback occurs, item.user_id reverted to seller
7. Credits stay deducted at 2000 (LOST!)

### Bug #2: Missing Transaction Savepoint for Partial Failures
**Severity**: HIGH  
**Location**: Lines 357-378 in `routes/items.py`

```python
for ci in available:
    item = ci.item
    # ... process item ...
    current_user.credits -= item.value  # Deducted in loop
    item.user_id = current_user.id
    db.session.delete(ci)
    # NO SAVEPOINT - if item N fails, items 1-N-1 are lost!
```

**Problem**:
- Multiple items processed in single transaction
- If item 5 fails validation, items 1-4 are already deducted from credits
- Rollback cancels ALL items, but user expectations are misaligned
- No way to recover partial checkout

### Bug #3: Credits Deducted Outside Try Block Protection
**Severity**: CRITICAL  
**Location**: Lines 363-378 in `routes/items.py`

```python
try:
    # ... validation ...
    for ci in available:
        item = ci.item
        current_user.credits -= item.value  # ← Inside try block but...
        # ... if any exception after this line ...
        # ... credits already changed in memory ...
        # ... rollback resets DB but not the damage ...
```

**Problem**:
- Credits modified in memory within loop
- Exception occurs → `db.session.rollback()`
- Rollback doesn't affect already-loaded objects in memory
- Objects still show deducted credits even though DB was rolled back
- User might see "Purchase failed" but credits show wrong value until page refresh

## Fixes Implemented

### Fix #1: Use Database Savepoints
Implement savepoints for each item to allow partial rollback:

```python
for ci in available:
    item = ci.item
    savepoint = db.session.begin_nested()  # Create savepoint
    try:
        # Validate item before any deductions
        if not item.is_available:
            continue
        
        # All deductions happen AFTER validation
        current_user.credits -= item.value
        item.user_id = current_user.id
        item.is_available = False
        
        # Create trade, award points
        trade = Trade(...)
        db.session.add(trade)
        
        # If we reach here, commit this savepoint
        savepoint.commit()
        purchased_items.append(item)
        
    except Exception as e:
        savepoint.rollback()  # Only this item's changes rolled back
        logger.warning(f"Item {item.id} checkout failed: {str(e)}")
        continue  # Continue with next item
```

### Fix #2: Strict Order of Operations
1. **Validate first** - Check all items are available, prices, etc.
2. **Deduct credits only after all validations pass**
3. **Link items only after credits deducted**
4. **Commit all changes together**

```python
# Phase 1: Validate everything
for ci in available:
    if not ci.item.is_available:
        raise CheckoutError(f"Item {ci.item.id} no longer available")

# Phase 2: Calculate total
total_cost = sum(ci.item.value for ci in available)
if current_user.credits < total_cost:
    raise InsufficientCreditsError(total_cost, current_user.credits)

# Phase 3: Process (all or nothing)
current_user.credits -= total_cost  # Single deduction

for ci in available:
    item = ci.item
    item.user_id = current_user.id
    item.is_available = False
    # ... create trade ...

db.session.commit()  # All or nothing
```

### Fix #3: Add Transaction ID Tracking
Generate unique transaction ID to allow audit trail:

```python
import uuid

transaction_id = str(uuid.uuid4())
current_user.last_transaction_id = transaction_id
current_user.last_transaction_timestamp = datetime.utcnow()

logger.info(f"[TXN:{transaction_id}] Checkout started - User: {current_user.id}")
```

## Implementation Changes

### Modified: `routes/items.py` - `process_checkout()` function
- Refactored to 3-phase approach (validate → calculate → process)
- Added transaction ID tracking
- Added savepoint error handling
- Improved logging for audit trail
- Single atomic credit deduction

### Database Audit Trail (Future Enhancement)
Create `CheckoutTransaction` model to track:
- Transaction ID
- User ID
- Items purchased
- Credits deducted
- Status (completed, failed, partial)
- Timestamp
- Error details if failed

## Testing Checklist
- [ ] Single item purchase succeeds
- [ ] Multi-item purchase succeeds
- [ ] Purchase with insufficient credits fails gracefully
- [ ] Database connection loss during checkout rolls back everything
- [ ] Credits correctly deducted on success
- [ ] Items correctly linked to buyer on success
- [ ] Failed item doesn't affect other items in same purchase
- [ ] Page refresh shows correct state after transaction

## Deployment Instructions
1. Backup database
2. Deploy updated `routes/items.py`
3. No database migration needed
4. Monitor logs for `[TXN:...]` entries
5. Test on staging with multi-item purchases

## Critical Note
This is a production-blocking bug. Do not deploy without fix.
Users have already lost credits in production!
