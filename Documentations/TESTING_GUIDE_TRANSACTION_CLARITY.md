# Transaction Clarity - Testing & Verification Guide

**Purpose**: Comprehensive testing of the Transaction Clarity feature  
**Created**: December 7, 2025

---

## Pre-Testing Setup

### 1. Environment Check

Verify all components are in place:

```powershell
# Check Python version
python --version  # Should be 3.8+

# Check Flask installation
python -c "import flask; print(f'Flask: {flask.__version__}')"

# Check reportlab installation
python -c "import reportlab; print('reportlab: OK')"

# Check transaction_clarity module
python -c "from transaction_clarity import calculate_estimated_delivery; print('transaction_clarity: OK')"
```

### 2. Database Migration

If not already done:

```powershell
flask db migrate -m "Add transaction clarity fields"
flask db upgrade
```

### 3. Start Application

```powershell
python app.py
```

Verify no startup errors appear.

---

## Test Cases

### Test Suite 1: Order Creation

#### Test 1.1 - Order Number Generation
```
OBJECTIVE: Verify order numbers are generated correctly
STEPS:
  1. Log in as test user
  2. Add item to cart
  3. Proceed to checkout
  4. Complete order
  5. Check database or order details page
EXPECTED:
  - Order number format: ORD-YYYYMMDD-NNNNN
  - Example: ORD-20251207-00001
  - Number should be unique per order
VERIFICATION:
  □ Order number present in database
  □ Format matches expected pattern
  □ No duplicate order numbers
```

#### Test 1.2 - Credit Balance Calculation
```
OBJECTIVE: Verify credit balances are calculated correctly
STEPS:
  1. Note current user credit balance
  2. Add item(s) to cart (note total value: e.g., 5000 credits)
  3. Complete order
  4. Check order details page
  5. Verify new user balance
EXPECTED:
  - credits_balance_before = original balance
  - credits_used = total item value
  - credits_balance_after = before - used
  - Example: 50,000 - 5,000 = 45,000
  - User balance updates correctly
VERIFICATION:
  □ Balance before captured correctly
  □ Credits used calculated correctly
  □ Balance after matches calculation
  □ User credit balance updated in profile
  □ Credit values match item values
```

#### Test 1.3 - Estimated Delivery Date
```
OBJECTIVE: Verify estimated delivery dates are calculated
STEPS:
  1. Complete order with "home delivery"
  2. Check order details
  3. Note estimated delivery date
  4. Repeat with "pickup" option
EXPECTED:
  - Home delivery: current_date + 3-7 days
  - Pickup: current_date + 1-2 days
  - Date format: Month DD, YYYY HH:MM AM/PM
  - Date should be in future
VERIFICATION:
  □ Delivery date calculated for home delivery
  □ Delivery date calculated for pickup
  □ Date is in correct future range
  □ Date format is readable
  □ Different dates for different methods
```

#### Test 1.4 - All Fields Populated
```
OBJECTIVE: Verify all transaction clarity fields are populated
STEPS:
  1. Create order
  2. Query database directly:
     SELECT order_number, total_credits, credits_used, 
            credits_balance_before, credits_balance_after,
            estimated_delivery_date FROM order WHERE id=?
  3. Check each field
EXPECTED:
  - No NULL values (except actual_delivery_date)
  - All fields contain data
  - Data types match schema
VERIFICATION:
  □ order_number: String value
  □ total_credits: Numeric value
  □ credits_used: Numeric value
  □ credits_balance_before: Numeric value
  □ credits_balance_after: Numeric value
  □ estimated_delivery_date: DateTime value
  □ receipt_downloaded: Boolean (False)
```

---

### Test Suite 2: Order Details Page

#### Test 2.1 - Page Load & Display
```
OBJECTIVE: Verify order details page loads and displays correctly
STEPS:
  1. Go to "My Orders"
  2. Click on recent order
  3. Verify page loads
EXPECTED:
  - Page loads without errors
  - All sections visible
  - No 404 or 500 errors
  - No broken images/icons
VERIFICATION:
  □ Page loads successfully
  □ URL: /order/<id>
  □ No console errors
  □ All styles load (colors, fonts, spacing)
```

#### Test 2.2 - Order Header Display
```
OBJECTIVE: Verify order header shows correct information
EXPECTED ELEMENTS:
  - Order number (e.g., "ORD-20251207-00001")
  - Order date (e.g., "December 7, 2025")
  - Status badge (color-coded: pending/processing/shipped/delivered)
VERIFICATION:
  □ Order number matches database
  □ Date matches order creation date
  □ Status badge visible and correct color
  □ All elements properly aligned
```

#### Test 2.3 - Status Explanation Box
```
OBJECTIVE: Verify status explanation displays correctly
EXPECTED ELEMENTS:
  - Icon emoji (📦 pending, ⚙️ processing, 🚚 shipped, ✅ delivered)
  - Status title (e.g., "Order Received")
  - Description (e.g., "Your order has been received and is being reviewed")
  - "What happens next" section
VERIFICATION:
  □ Icon displays correctly
  □ Title matches status
  □ Description is helpful and accurate
  □ Next steps explained clearly
```

#### Test 2.4 - Order Information Section
```
OBJECTIVE: Verify order info card displays correctly
EXPECTED ELEMENTS:
  - Order Date
  - Order Number
  - Number of Items
  - Current Status
VERIFICATION:
  □ All fields present
  □ Values match database
  □ Formatting is consistent
  □ Mobile responsive
```

#### Test 2.5 - Delivery Information Section
```
OBJECTIVE: Verify delivery info card displays correctly
EXPECTED ELEMENTS:
  - Delivery Method (home delivery / pickup)
  - Estimated Delivery/Pickup Date
  - Timeline (e.g., "1-2 business days")
  - Delivery Address OR Pickup Station
VERIFICATION:
  □ Method matches order
  □ Estimated date matches calculation
  □ Timeline matches DELIVERY_TIMELINES config
  □ Address/station is correct
```

#### Test 2.6 - Items Table
```
OBJECTIVE: Verify items display in detailed table
EXPECTED COLUMNS:
  - Item Name
  - Condition
  - Location
  - Value (in credits)
TABLE VERIFICATION:
  □ All ordered items present
  □ No duplicate items
  □ Values match item prices
  □ Conditions display correctly
  □ Formatting is readable
  □ Table has borders/spacing
```

#### Test 2.7 - Credit Summary Section
```
OBJECTIVE: Verify credit breakdown is clear and correct
EXPECTED DISPLAY:
  Balance Before: ₦50,000
  Total Items Value: ₦15,000
  Credits Used: ₦15,000
  Balance After: ₦35,000
  
  Explanation: "You had ₦50,000 credits. After this order (₦15,000), 
  your balance is now ₦35,000."
  
CALCULATIONS TO VERIFY:
  ✓ Balance Before = user.credits at order time
  ✓ Total Items Value = sum of all item prices
  ✓ Credits Used = Total Items Value
  ✓ Balance After = Balance Before - Credits Used
  ✓ Explanation is accurate
VERIFICATION:
  □ All values display correctly
  □ Format is currency (₦X,XXX)
  □ Calculations are accurate
  □ Explanation is clear
  □ Green background visible (emphasis)
```

---

### Test Suite 3: Receipt Download

#### Test 3.1 - PDF Generation
```
OBJECTIVE: Verify PDF receipt generates without errors
STEPS:
  1. Navigate to order details page
  2. Click "📥 Download Receipt" button
  3. PDF should download
EXPECTED:
  - No error messages
  - PDF file downloads
  - Filename: Receipt-{order_number}.pdf
  - File size > 5KB (should contain content)
VERIFICATION:
  □ Button visible and clickable
  □ PDF downloads successfully
  □ Filename is correct
  □ File can be opened
```

#### Test 3.2 - PDF Content
```
OBJECTIVE: Verify PDF contains all transaction details
STEPS:
  1. Open downloaded PDF
  2. Check each section
EXPECTED SECTIONS:
  - Order Information Header
    □ Order Number
    □ Order Date
    □ Customer Name/Email
  - Delivery Information
    □ Method (delivery/pickup)
    □ Estimated Date
    □ Address/Station
  - Itemized List
    □ Item names
    □ Quantities
    □ Prices
    □ Total
  - Credit Summary
    □ Balance before
    □ Items total
    □ Balance after
  - Footer
    □ Thank you message
    □ Generation timestamp
    □ Company info (if applicable)
VERIFICATION:
  □ All sections present
  □ Values are correct
  □ Formatting is professional
  □ PDF is readable/printable
```

#### Test 3.3 - Receipt Download Tracking
```
OBJECTIVE: Verify receipt_downloaded flag is updated
STEPS:
  1. Check database before download:
     SELECT receipt_downloaded FROM order WHERE id=?
     (Should be False)
  2. Download receipt
  3. Check database after download:
     SELECT receipt_downloaded FROM order WHERE id=?
     (Should be True)
VERIFICATION:
  □ Flag is False before first download
  □ Flag becomes True after download
  □ Flag persists between page refreshes
```

#### Test 3.4 - Multiple Downloads
```
OBJECTIVE: Verify PDF can be downloaded multiple times
STEPS:
  1. Download receipt
  2. Wait 5 seconds
  3. Download again
  4. Verify both files are identical
EXPECTED:
  - Both downloads successful
  - Files are identical
  - No error on second download
  - receipt_downloaded remains True
VERIFICATION:
  □ Multiple downloads work
  □ Files are identical
  □ No database conflicts
```

---

### Test Suite 4: Authorization & Security

#### Test 4.1 - Authorization Check
```
OBJECTIVE: Verify users can only view their own orders
STEPS:
  1. Log in as User A
  2. Create order (note order_id)
  3. Log in as User B
  4. Try to access User A's order: /order/{order_id}
EXPECTED:
  - 404 error or access denied message
  - User cannot view order
  - No error leakage (doesn't say "order doesn't exist")
VERIFICATION:
  □ Unauthorized users blocked
  □ Proper error response
  □ No sensitive data exposed
```

#### Test 4.2 - Receipt Download Authorization
```
OBJECTIVE: Verify only order owner can download receipt
STEPS:
  1. Log in as User A, create order
  2. Log in as User B
  3. Try to download receipt: /order/{order_a_id}/download-receipt
EXPECTED:
  - 404 or access denied
  - File not downloaded
  - Error message is generic
VERIFICATION:
  □ Unauthorized download blocked
  □ No file served to unauthorized user
  □ Error message doesn't leak data
```

#### Test 4.3 - Non-Existent Order
```
OBJECTIVE: Verify 404 for non-existent orders
STEPS:
  1. Try to access: /order/99999
  2. Check response
EXPECTED:
  - 404 error page
  - Graceful error handling
  - No database errors exposed
VERIFICATION:
  □ 404 returned
  □ Error message is user-friendly
  □ No stack trace shown
```

---

### Test Suite 5: Responsive Design

#### Test 5.1 - Mobile Display
```
OBJECTIVE: Verify order details page is mobile-friendly
STEPS:
  1. Open order details page
  2. Open browser dev tools (F12)
  3. Set viewport to mobile (375x667)
  4. Check layout
EXPECTED:
  - Content stacks vertically
  - No horizontal scrolling
  - Text is readable
  - Buttons are clickable
  - Images scale appropriately
VERIFICATION:
  □ Mobile layout responsive
  □ No overflow issues
  □ Text readable
  □ Buttons are hit-able (44x44px+)
```

#### Test 5.2 - Tablet Display
```
OBJECTIVE: Verify order details on tablet
STEPS:
  1. Set viewport to tablet (768x1024)
  2. Check layout
EXPECTED:
  - Two-column or optimized layout
  - Better use of space than mobile
  - All content accessible
VERIFICATION:
  □ Tablet layout looks good
  □ No awkward spacing
  □ Professional appearance
```

#### Test 5.3 - Desktop Display
```
OBJECTIVE: Verify order details on desktop
STEPS:
  1. Set viewport to desktop (1920x1080)
  2. Check layout
EXPECTED:
  - Three-column layout (order info, delivery, items)
  - Professional spacing
  - All content visible
VERIFICATION:
  □ Desktop layout optimized
  □ Good use of space
  □ Professional appearance
```

---

### Test Suite 6: Performance

#### Test 6.1 - Order Details Load Time
```
OBJECTIVE: Verify page loads quickly
STEPS:
  1. Open order details page
  2. Monitor load time (DevTools → Network)
EXPECTED:
  - Initial load: < 2 seconds
  - Fully interactive: < 3 seconds
  - No unoptimized images
VERIFICATION:
  □ Fast initial load
  □ Responsive after load
  □ No performance warnings
```

#### Test 6.2 - PDF Generation Time
```
OBJECTIVE: Verify PDF generates quickly
STEPS:
  1. Click download receipt
  2. Monitor response time (DevTools → Network)
EXPECTED:
  - PDF generation: < 5 seconds
  - File ready for download < 5 seconds
VERIFICATION:
  □ Quick PDF generation
  □ No timeout errors
  □ User gets immediate feedback
```

#### Test 6.3 - Database Query Performance
```
OBJECTIVE: Verify database queries are efficient
STEPS:
  1. Enable query logging
  2. Load order details page
  3. Check logs
EXPECTED:
  - Main query: 1-2 database queries
  - No N+1 queries
  - Response time < 100ms
VERIFICATION:
  □ Efficient queries
  □ No excess database hits
  □ Fast response time
```

---

### Test Suite 7: Edge Cases

#### Test 7.1 - Multiple Items Order
```
OBJECTIVE: Verify order with 10+ items displays correctly
STEPS:
  1. Add 10 items to cart
  2. Complete order
  3. View details
EXPECTED:
  - All items display
  - Table scrolls if needed (mobile)
  - Totals calculated correctly
VERIFICATION:
  □ All items visible
  □ Layout handles multiple items
  □ Calculations accurate
```

#### Test 7.2 - Long Address
```
OBJECTIVE: Verify long delivery address formats correctly
STEPS:
  1. Order with very long address (100+ chars)
  2. View order details
EXPECTED:
  - Address wraps properly
  - No text overflow
  - Readable format
VERIFICATION:
  □ Address wraps correctly
  □ No layout breaking
  □ Readable on all devices
```

#### Test 7.3 - Special Characters in Names
```
OBJECTIVE: Verify special characters display correctly
STEPS:
  1. Order item with special characters (™, ®, etc.)
  2. View details and PDF
EXPECTED:
  - Characters display correctly
  - No encoding issues
  - Professional appearance
VERIFICATION:
  □ Special chars render correctly
  □ PDF shows characters properly
  □ No broken encoding
```

---

## Testing Checklist

### Pre-Testing
- [ ] Database migrated successfully
- [ ] reportlab installed
- [ ] App starts without errors
- [ ] transaction_clarity.py is accessible
- [ ] All new routes are accessible

### Order Creation
- [ ] Order numbers generated correctly
- [ ] Credit balances calculated accurately
- [ ] Estimated delivery dates computed
- [ ] All transaction fields populated
- [ ] User credit balance updated

### Order Details Page
- [ ] Page loads successfully
- [ ] Order header displays correctly
- [ ] Status explanation shows
- [ ] Order info card populated
- [ ] Delivery info card populated
- [ ] Items table displays all items
- [ ] Credit summary shows correct breakdown

### Receipt Download
- [ ] PDF generates without errors
- [ ] PDF downloads successfully
- [ ] PDF has correct filename
- [ ] PDF content is complete
- [ ] PDF is readable/printable
- [ ] receipt_downloaded flag updates

### Authorization
- [ ] Users can only view own orders
- [ ] Users can only download own receipts
- [ ] 404 for non-existent orders
- [ ] No data leakage in errors

### Design & UX
- [ ] Mobile layout responsive
- [ ] Tablet layout optimized
- [ ] Desktop layout professional
- [ ] All text readable
- [ ] All buttons clickable
- [ ] No overflow issues

### Performance
- [ ] Order details loads < 2 sec
- [ ] PDF generates < 5 sec
- [ ] No excessive database queries
- [ ] No performance warnings

### Edge Cases
- [ ] Multiple items handled
- [ ] Long addresses format correctly
- [ ] Special characters display
- [ ] Empty fields handled gracefully

---

## Success Criteria

All tests pass if:

✅ Order numbers generate uniquely  
✅ Credit calculations are accurate  
✅ Delivery dates are calculated correctly  
✅ Order details page displays all info  
✅ PDF receipts generate and download  
✅ Authorization checks prevent unauthorized access  
✅ Page is responsive and professional  
✅ Performance is acceptable  
✅ No errors in logs  
✅ User experience is smooth  

---

## Troubleshooting

### Issue: "Order not found" when accessing details
**Solution**: Verify order ID in URL matches database

### Issue: PDF download fails
**Solution**: Check reportlab is installed: `pip install reportlab`

### Issue: Credit calculations incorrect
**Solution**: Verify order creation in routes/items.py populated fields correctly

### Issue: Page loads slowly
**Solution**: Check database queries aren't duplicated, consider adding indexes

### Issue: Authorization error on own order
**Solution**: Verify current_user.id matches order.user_id in database

---

## Test Report Template

```
Test Date: [DATE]
Tester: [NAME]
Environment: [DEV/TEST/PROD]
Python Version: [VERSION]
Browser: [BROWSER/VERSION]

RESULTS:
- Test Suite 1 (Order Creation): [PASS/FAIL]
- Test Suite 2 (Order Details): [PASS/FAIL]
- Test Suite 3 (Receipt): [PASS/FAIL]
- Test Suite 4 (Authorization): [PASS/FAIL]
- Test Suite 5 (Responsive): [PASS/FAIL]
- Test Suite 6 (Performance): [PASS/FAIL]
- Test Suite 7 (Edge Cases): [PASS/FAIL]

ISSUES FOUND:
[List any issues]

NOTES:
[Any additional observations]

SIGN-OFF: [PASS/FAIL - Ready for production]
```
