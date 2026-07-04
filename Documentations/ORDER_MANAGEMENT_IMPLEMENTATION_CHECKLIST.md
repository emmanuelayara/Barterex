# Order Management - Implementation Checklist

**Project:** Fix Order Management System  
**Priority:** 🔴 CRITICAL  
**Estimated Time:** 5-6 hours total

---

## PHASE 1: CRITICAL FIX (30 minutes)

### [ ] Understanding the Problem
- [ ] Read ORDER_MANAGEMENT_SUMMARY.md (5 min)
- [ ] Verify problem: Run `Order.query.all()` in shell → should return `[]`
- [ ] Open routes/items.py and locate `finalize_purchase()` function
- [ ] Read through the finalize_purchase code (lines 407-570)

### [ ] Implement Order Creation (20 min)
- [ ] Open routes/items.py
- [ ] Find line ~560 (before `session.pop('pending_checkout_items')`)
- [ ] Add Order creation code from ORDER_MANAGEMENT_FIXES.md → **Fix #1**
- [ ] Import new dependencies: `from models import Order, OrderItem` (check if already imported)
- [ ] Import timedelta: `from datetime import timedelta`
- [ ] Save file

### [ ] Quick Testing (5 min)
- [ ] Start Flask app: `python app.py`
- [ ] Add item to cart
- [ ] Go through checkout
- [ ] Set delivery address
- [ ] Confirm purchase
- [ ] Check if order appears in database:
  ```python
  from models import Order
  Order.query.all()  # Should now have 1+ orders
  ```
- [ ] Verify order in `/my_orders` page (should show your order)

**Milestone:** ✅ Orders are now being created!

---

## PHASE 2: FIX RELATED ISSUES (1.5 hours)

### [ ] Fix Order Reference Bug (10 min)
- [ ] Open routes/admin.py
- [ ] Go to line ~1078 in `update_order_status()`
- [ ] Find: `for oi in order.items`
- [ ] Change to: `for oi in order.order_items`
- [ ] Save file

### [ ] Add OrderAuditLog Model (15 min)
- [ ] Open models.py
- [ ] Find class OrderItem (around line 435)
- [ ] After OrderItem class, add OrderAuditLog class from ORDER_MANAGEMENT_FIXES.md → **Fix #6**
- [ ] Import datetime if not already imported: `from datetime import datetime`
- [ ] Save file

### [ ] Add Database Indexes (10 min)
- [ ] Open models.py
- [ ] Find Order class
- [ ] Add `__table_args__` from ORDER_MANAGEMENT_FIXES.md → **Fix #7**
- [ ] Save file

### [ ] Implement Order Status Validation (20 min)
- [ ] Open models.py
- [ ] Find Order class, after relationships
- [ ] Add VALID_TRANSITIONS dict from ORDER_MANAGEMENT_FIXES.md → **Fix #3**
- [ ] Add methods: `can_transition_to()`, `get_valid_next_statuses()`, `__repr__()`
- [ ] Save file

### [ ] Replace Hard-Coded Status Logic (30 min)
- [ ] Open routes/admin.py
- [ ] Find `update_order_status()` function (line 1064)
- [ ] Delete entire function (lines ~1064-1145)
- [ ] Replace with new function from ORDER_MANAGEMENT_FIXES.md → **Fix #4**
- [ ] Check imports at top of file:
  - [ ] `from sqlalchemy.orm import joinedload` - should exist
  - [ ] `from sqlalchemy import String` - add if missing
- [ ] Save file

### [ ] Improve Admin manage_orders Route (20 min)
- [ ] Open routes/admin.py
- [ ] Find `manage_orders()` function (line 1049)
- [ ] Delete entire function (lines ~1049-1063)
- [ ] Replace with new function from ORDER_MANAGEMENT_FIXES.md → **Fix #5**
- [ ] Verify imports (joinedload, String)
- [ ] Save file

**Milestone:** ✅ Core functionality fixed and validated!

---

## PHASE 3: TESTING (2 hours)

### [ ] Database Migration Tests
- [ ] Test 1: Check OrderAuditLog table created
  ```python
  from models import OrderAuditLog
  OrderAuditLog.query.all()  # Should work
  ```
- [ ] Test 2: Check Order has new attributes
  ```python
  from models import Order
  o = Order.query.first()
  print(o.can_transition_to('Shipped'))  # Should return bool
  ```

### [ ] Order Creation Tests
- [ ] Test 1: Purchase single item
  - [ ] Add 1 item to cart
  - [ ] Checkout
  - [ ] Set delivery address
  - [ ] Confirm purchase
  - [ ] Verify: Order created, order_number set, user_id correct
  
- [ ] Test 2: Purchase multiple items
  - [ ] Add 3 items to cart
  - [ ] Checkout
  - [ ] Set pickup location
  - [ ] Confirm purchase
  - [ ] Verify: Order created with 3 OrderItems

- [ ] Test 3: Order data accuracy
  - [ ] Purchase item worth ₦100
  - [ ] User had ₦200 before
  - [ ] Verify Order.credits_used = 100
  - [ ] Verify Order.credits_balance_before = 200
  - [ ] Verify Order.credits_balance_after = 100
  - [ ] Verify Order.delivery_method correct

- [ ] Test 4: Order number uniqueness
  - [ ] Make 2 purchases same day
  - [ ] Verify order numbers are different
  - [ ] Verify both in database

### [ ] Status Update Tests
- [ ] Test 1: Valid transition
  - [ ] Order status: Pending
  - [ ] Admin changes to: Shipped
  - [ ] Verify: Status changed, notification created, audit log created
  
- [ ] Test 2: Invalid transition
  - [ ] Order status: Pending
  - [ ] Admin tries: Delivered
  - [ ] Verify: Error message shown, status unchanged
  
- [ ] Test 3: Delivery timestamp
  - [ ] Order status: In Transit
  - [ ] Admin changes to: Delivered
  - [ ] Verify: actual_delivery_date set to now
  
- [ ] Test 4: Audit logging
  - [ ] Make 3 status updates
  - [ ] Check OrderAuditLog table
  - [ ] Verify: 3 entries, correct admin_id, correct timestamps

- [ ] Test 5: User notification
  - [ ] Order status: Shipped
  - [ ] Admin changes to: In Transit
  - [ ] Verify: Notification created for user
  - [ ] Verify: Notification contains order number

### [ ] Admin Route Tests
- [ ] Test 1: Load manage_orders page
  - [ ] Visit /manage_orders
  - [ ] Verify: Page loads (no 500 error)
  - [ ] Verify: Orders display in table
  
- [ ] Test 2: Status filter
  - [ ] Make orders with different statuses
  - [ ] Filter by "Pending"
  - [ ] Verify: Only Pending orders shown
  
- [ ] Test 3: Search functionality
  - [ ] Search by order number
  - [ ] Search by user
  - [ ] Verify: Correct orders returned
  
- [ ] Test 4: Pagination
  - [ ] Create 25+ orders
  - [ ] Visit page 1 → shows 20 orders
  - [ ] Visit page 2 → shows remaining orders
  - [ ] Verify: Pagination controls work

- [ ] Test 5: Sorting
  - [ ] Change sort to "date-asc"
  - [ ] Verify: Orders sorted correctly
  
- [ ] Test 6: Performance
  - [ ] Load manage_orders with 100+ orders
  - [ ] Should load in < 1 second
  - [ ] Check console: No N+1 queries

### [ ] User View Tests
- [ ] Test 1: User order history
  - [ ] Purchase 3 items
  - [ ] Visit /my_orders
  - [ ] Verify: All 3 orders displayed
  
- [ ] Test 2: View order details
  - [ ] Click order from list
  - [ ] Verify: All details display correctly
  - [ ] Verify: Cannot view other user's orders
  
- [ ] Test 3: Download receipt
  - [ ] Click "Download Receipt"
  - [ ] Verify: PDF downloads
  - [ ] Verify: receipt_downloaded flag set

- [ ] Test 4: Order status tracking
  - [ ] Admin changes order status
  - [ ] Refresh user order page
  - [ ] Verify: Status updated for user

### [ ] Authorization Tests
- [ ] Test 1: User cannot see other user's order
  - [ ] User A purchases item
  - [ ] User B tries to access User A's order (via URL)
  - [ ] Verify: 403 Forbidden error
  
- [ ] Test 2: Non-admin cannot update orders
  - [ ] Regular user tries to POST to update_order_status
  - [ ] Verify: Rejected (403 or redirect)

### [ ] Edge Cases
- [ ] Test 1: Order with pickup location
  - [ ] Purchase with pickup method
  - [ ] Verify: pickup_station_id set, delivery_address null
  
- [ ] Test 2: Order with home delivery
  - [ ] Purchase with home delivery
  - [ ] Verify: delivery_address set, pickup_station_id null
  
- [ ] Test 3: Cancelled order
  - [ ] Create order
  - [ ] Change status to Cancelled
  - [ ] Verify: No points awarded
  
- [ ] Test 4: Zero-credit order (shouldn't happen but...)
  - [ ] Manually create order with 0 credits
  - [ ] Verify: No errors, order saves

**Milestone:** ✅ All tests passing!

---

## PHASE 4: DOCUMENTATION & CLEANUP (30 min)

### [ ] Code Comments
- [ ] Add comment above Order creation explaining the change
- [ ] Add comment to VALID_TRANSITIONS explaining state machine
- [ ] Update docstring for update_order_status

### [ ] Database Backup
- [ ] Backup database before production deploy
- [ ] Test restoration

### [ ] Commit to Git
- [ ] Stage changes: `git add .`
- [ ] Commit with message: `Fix: Implement Order record creation in finalize_purchase`
- [ ] Create pull request
- [ ] Get code review
- [ ] Merge to main branch

### [ ] Create Deployment Notes
- [ ] Document what changed
- [ ] Document testing done
- [ ] List any breaking changes (none expected)
- [ ] Rollback plan (if needed)

**Milestone:** ✅ Code reviewed and ready for production!

---

## PHASE 5: DEPLOYMENT (30 min)

### [ ] Pre-Deployment
- [ ] Confirm all tests passing locally
- [ ] Code review approved by teammate
- [ ] Database backups completed

### [ ] Deployment
- [ ] Deploy to staging environment
- [ ] Run full test suite on staging
- [ ] Verify no errors in logs
- [ ] Manual smoke test on staging

### [ ] Production Deployment
- [ ] Deploy to production
- [ ] Monitor logs for errors
- [ ] Check Order table has records
- [ ] Verify admin /manage_orders page works
- [ ] Verify user /my_orders page works

### [ ] Post-Deployment
- [ ] Send team notification
- [ ] Update documentation
- [ ] Monitor for errors (24 hours)
- [ ] Celebrate! 🎉

**Milestone:** ✅ Live in production!

---

## OPTIONAL IMPROVEMENTS (Future)

After core fixes are working, consider:

### [ ] Enhancements (1-2 hours)
- [ ] Add order cancellation UI for users
- [ ] Add return request feature
- [ ] Add delivery tracking integration
- [ ] Add estimated delivery countdown
- [ ] Add order status history view
- [ ] Add bulk status update for admin

### [ ] Performance (30 min)
- [ ] Run EXPLAIN on queries
- [ ] Verify indexes are used
- [ ] Add caching for order summaries
- [ ] Monitor slow queries

### [ ] Monitoring (30 min)
- [ ] Set up alerts for empty Order tables
- [ ] Monitor order creation latency
- [ ] Track failed orders
- [ ] Set up dashboard for order metrics

---

## TROUBLESHOOTING GUIDE

### Problem: "No module named Order"
**Solution:** Check if `from models import Order` is at top of routes/items.py

### Problem: "OrderAuditLog not created"
**Solution:** Run `python` shell, then:
```python
from app import db
from models import OrderAuditLog
db.create_all()  # Creates the table
```

### Problem: Orders still not showing
**Solution:** 
1. Verify fix was saved: `grep "Order(" routes/items.py`
2. Verify models imported: Check line 1 of routes/items.py
3. Restart Flask: `python app.py`
4. Purchase new item to test

### Problem: "Invalid transition from Pending to Shipped" error
**Solution:** Check VALID_TRANSITIONS dict in models.py has correct states

### Problem: Page loads slowly with many orders
**Solution:** Verify joinedload is being used in manage_orders route

### Problem: Audit logs not created
**Solution:** Verify OrderAuditLog model was added to models.py

---

## SUCCESS CRITERIA

Project is complete when:

✅ Order records are created when purchase finalized  
✅ User can see order history in /my_orders  
✅ Admin can see all orders in /manage_orders  
✅ Admin can update order status with validation  
✅ Status changes logged in audit table  
✅ User notifications sent on status change  
✅ All tests passing  
✅ No errors in production logs  
✅ Performance acceptable (< 1 sec page load)  
✅ Code reviewed and approved  

---

## QUICK REFERENCE

| Task | File | Line | Time |
|------|------|------|------|
| Add Order creation | routes/items.py | ~560 | 20 min |
| Fix order.items ref | routes/admin.py | ~1078 | 5 min |
| Add audit model | models.py | ~465 | 10 min |
| Add validation | models.py | Order class | 10 min |
| Fix status logic | routes/admin.py | ~1064 | 20 min |
| Fix admin route | routes/admin.py | ~1049 | 15 min |
| Database indexes | models.py | Order class | 5 min |
| TOTAL IMPLEMENTATION | — | — | ~85 min |

---

## CONTACTS & ESCALATION

For issues:
1. Check TROUBLESHOOTING section above
2. Check ORDER_MANAGEMENT_CODE_REVIEW.md for details
3. Check ORDER_MANAGEMENT_FIXES.md for exact code
4. Review ORDER_MANAGEMENT_VISUAL_FLOW.md for understanding

---

**Last Updated:** December 2024  
**Status:** Ready for Implementation  
**Confidence Level:** 99% (core bug is clear, fix is straightforward)

