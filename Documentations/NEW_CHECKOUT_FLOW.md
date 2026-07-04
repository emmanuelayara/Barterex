# NEW CHECKOUT FLOW - DELIVERY SETUP BEFORE PURCHASE

## Flow Change Summary

**OLD FLOW** (❌ REMOVED):
```
1. Cart → Add Items
2. Checkout → ✓ PURCHASES immediately  
3. Order Setup → Setup delivery AFTER purchase
```

**NEW FLOW** (✅ IMPLEMENTED):
```
1. Cart → Add Items
2. Checkout → Validate items (NO purchase yet)
3. Order Setup → Setup delivery details
4. Order Review → Review order
5. Confirm Purchase → ✓ PURCHASES with lock
```

## Key Changes

### 1. `/checkout` Route - Now Only Validates
```python
# Before: Rendered checkout.html with purchase form
# After: Validates items and redirects to delivery setup

# NEW FLOW:
- Validate items are available ✓
- Check user has enough credits ✓
- Store pending items in session: session['pending_checkout_items']
- Redirect to /order_item (delivery setup)
- NO purchase happens yet ✓
```

### 2. `/order_item` Route - Delivery Setup BEFORE Purchase
```python
# Before: Created order record + finalized purchase
# After: ONLY sets up delivery, doesn't purchase

# NEW FLOW:
- Show delivery form (method, address, pickup station)
- Store delivery details in session: session['pending_delivery']
- Render order_review.html with "Confirm Purchase" button
- User reviews order with all details
- NO purchase happens yet ✓
```

### 3. `/finalize_purchase` Route - NEW (Purchase Happens Here)
```python
# NEW ROUTE:
- Gets pending items from session['pending_checkout_items']
- Gets delivery details from session['pending_delivery']
- Acquires database locks on items (prevents race condition)
- Re-validates items are still available
- Deducts credits (atomic operation)
- Links items to user
- Creates trade records
- Awards trading points
- Clears cart
- PURCHASE FINALIZED ✓
```

## Benefits

✅ **Better User Experience**
- Users review delivery details BEFORE committing purchase
- Can edit delivery method without losing cart items
- Clear confirmation step before money is deducted

✅ **Better Data Integrity**
- Items are still available when purchase finalizes
- Race conditions prevented with database locks
- All-or-nothing semantics (all items or none)

✅ **Better Safety**
- User can see final price before purchase
- Delivery details confirmed before deduction
- Can cancel without losing cart items (just back out)

✅ **Better Audit Trail**
- Transaction ID generated at purchase time (not checkout)
- Delivery details captured with purchase
- Clear separation between checkout and purchase

## User Journey Example

### Step 1: Add Items to Cart
```
User: Browses marketplace
User: Adds 2 items to cart (5000 + 3000 credits)
Status: Items in cart, not purchased
```

### Step 2: Checkout (Validation)
```
User: Clicks "Checkout" button
System: 
  ✓ Validates both items available
  ✓ Checks user has 8000+ credits
  ✓ Stores items: session['pending_checkout_items'] = [42, 55]
System: Redirects to delivery setup page
Status: Items validated, NOT purchased, waiting for delivery setup
```

### Step 3: Setup Delivery
```
User: Selects delivery method (home delivery)
User: Enters delivery address
User: Clicks "Next" or "Continue"
System:
  ✓ Stores delivery details in session
  ✓ Validates address format
System: Renders order review page
Status: Delivery set up, NOT purchased, waiting for confirmation
```

### Step 4: Review Order
```
User: Sees order summary:
  - Items: [Item 42: 5000cr, Item 55: 3000cr]
  - Total: 8000 credits
  - Delivery: Home delivery to [Address]
  - Final Balance After: 2000 credits
User: Clicks "Confirm Purchase" button
```

### Step 5: Finalize Purchase
```
System:
  ✓ Acquires database locks on items 42 & 55
  ✓ Re-validates both items still available
  ✓ Deducts 8000 credits atomically
  ✓ Links items to user
  ✓ Creates trade records
  ✓ Awards trading points
  ✓ Creates order record with delivery details
  ✓ Clears items from cart
  ✓ Generates transaction ID (TXN:a1b2c3d4)
System: Redirects to dashboard
Status: PURCHASE COMPLETE ✓
```

## API Routes

### Checkout Routes

```
GET  /checkout
  Purpose: Shows checkout page
  Action: Validates items, stores in session, redirects to /order_item
  
GET  /order_item
  Purpose: Shows delivery setup form
  Action: Renders form with default address
  
POST /order_item
  Purpose: Submit delivery details
  Action: Stores delivery info, renders order review page
  
POST /finalize_purchase
  Purpose: Confirm and finalize purchase
  Action: Deducts credits, links items, clears cart
```

## Session Storage

### Before Purchase Finalization
```python
session['pending_checkout_items'] = [42, 55]
session['pending_delivery'] = {
    'method': 'home delivery',
    'delivery_address': '123 Main St, Lagos',
    'pickup_station_id': None
}
```

### After Purchase Finalization
```python
# Session cleared:
session.pop('pending_checkout_items', None)
session.pop('pending_delivery', None)

# Order created in database with all details
```

## Error Handling

### If User Navigates Away
- Items stay in cart
- Pending checkout/delivery cleared
- User can restart checkout anytime
- No credits deducted

### If Item Becomes Unavailable
- During checkout: Caught before delivery setup
- During delivery setup: Caught in order_review
- During finalize_purchase: Caught with database lock

### If User Doesn't Have Enough Credits
- During checkout: Flash error, redirect to cart
- NOT during finalize_purchase (already validated)

## Database Transactions

```python
# Database Lock Acquired:
locked_items = Item.query.filter(Item.id.in_([42, 55])).with_for_update()

# This ensures:
- No other user can purchase items 42 & 55 simultaneously
- Items can't change between validation and purchase
- All-or-nothing semantics (all items purchased or none)
```

## Testing Checklist

- [ ] Add items to cart
- [ ] Click checkout (should redirect to /order_item)
- [ ] Setup delivery (home delivery)
- [ ] Review order shows all details
- [ ] Click "Confirm Purchase" button
- [ ] Credits deducted correctly
- [ ] Items in user's inventory
- [ ] Order record created with delivery details
- [ ] Notification sent
- [ ] Email sent
- [ ] Cart cleared

## Migration Notes

- ✅ No database schema changes needed
- ✅ Backward compatible (old pending_order_items sessions ignored)
- ✅ No data loss (items stay in cart if checkout abandoned)
- ✅ All existing security improvements preserved
- ✅ Database locks still prevent race conditions

## Benefits Summary

| Aspect | Before | After |
|--------|--------|-------|
| **User Review** | No | Yes ✅ |
| **Delivery Confirmation** | After purchase | Before purchase ✅ |
| **Cancel Option** | Difficult | Easy ✅ |
| **Safety** | Medium | High ✅ |
| **User Experience** | Good | Excellent ✅ |

---

**Status**: ✅ IMPLEMENTED AND READY FOR TESTING
