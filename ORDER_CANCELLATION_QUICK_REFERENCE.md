# Order Cancellation Feature - Quick Reference

## ✅ What Users Can Do

### Cancel an Order
- **Eligibility**: Order must be in "Pending" or "Processing" status
- **Cannot cancel if**: Order is already Shipped, Out for Delivery, Delivered, or Cancelled
- **Result**: Credits are immediately refunded to account

### Where to Cancel
1. **Order Details Page** - Click "Cancel Order" button (red)
2. **Orders List** - Click "Cancel" button on order card

### Cancellation Process
1. Click cancel button
2. Confirmation modal appears
3. (Optional) Enter reason for cancellation
4. Click "Yes, Cancel Order"
5. ✓ Order cancelled, credits refunded

---

## ✅ What Happens After Cancellation

### User Gets:
- ✓ Refund of all credits used
- ✓ In-app notification with order summary
- ✓ Professional confirmation email
- ✓ Transaction record in account history

### System Does:
- ✓ Updates order status to "Cancelled"
- ✓ Records cancellation time
- ✓ Stores cancellation reason (if provided)
- ✓ Creates credit refund transaction
- ✓ Updates user's available credits
- ✓ Logs action for audit trail

---

## ✅ Key Features

| Feature | Details |
|---------|---------|
| **Status Check** | Only shows cancel option for pending/processing orders |
| **Authorization** | Only order owner can cancel their order |
| **Instant Refund** | Credits refunded immediately upon cancellation |
| **Email Confirmation** | HTML email with order details and refund amount |
| **Optional Reason** | User can provide feedback on why they cancelled |
| **Audit Trail** | All cancellations logged with timestamp |

---

## ✅ User Messaging

### Success Message
```
"Order cancelled successfully. ₦50,000 has been refunded to your account."
```

### Error Messages
```
"You don't have access to cancel this order"
"Order cannot be cancelled. Current status: Shipped"
"An error occurred while cancelling the order."
```

---

## ✅ Technical Implementation

### Model Changes
```python
class Order(db.Model):
    cancelled = db.Column(db.Boolean, default=False)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancellation_reason = db.Column(db.Text, nullable=True)
```

### New Route
```
POST /order/<order_id>/cancel
```

### Email Format
- Professional HTML template
- Shows order number, items, refund amount
- Displays cancellation date
- Includes refund confirmation

### JavaScript
- Modal for confirmation dialog
- Click outside to close
- Optional reason input
- Form submission to cancellation route

---

## ✅ Files Changed

1. **models.py** - Added 3 fields to Order class
2. **routes/user.py** - Added cancel_order route (67 lines)
3. **templates/order_details.html** - Added button, modal, modal CSS
4. **templates/user_orders.html** - Added action buttons, list modal, fixed order.items

---

## ✅ Validation Rules

| Check | Result if Failed |
|-------|------------------|
| User owns order | Reject with "You don't have access..." |
| Order status is pending/processing | Reject with "Order cannot be cancelled..." |
| User is logged in | Flask login_required redirects to login |
| Order exists | 404 error page |
| Database save succeeds | Generic error message, logged |

---

## ✅ Testing Scenarios

### Happy Path
1. Create pending order ✓
2. Go to order details ✓
3. Click "Cancel Order" button ✓
4. Modal appears ✓
5. Click "Yes, Cancel Order" ✓
6. Order cancelled ✓
7. Credits refunded ✓
8. Email received ✓

### Edge Cases
- Shipped order → Cancel button not shown
- User tries to cancel another user's order → Access denied
- Cancel button from orders list → Works identically
- Enter cancellation reason → Stored and shown in email ✓
- No reason provided → Still cancels normally ✓

---

## ✅ Database Tables Affected

| Table | What Changes |
|-------|--------------|
| `order` | `status`, `cancelled`, `cancelled_at`, `cancellation_reason` updated |
| `user` | `available_credits` increased by refund amount |
| `credit_transaction` | New refund record created |
| `notification` | New cancellation notification created |

---

## ✅ User Experience

### Order Details Page
```
┌─────────────────────────────────────┐
│ Order ORD-20251207-00042            │
│ Status: ⏳ Pending                  │
├─────────────────────────────────────┤
│ Items, Delivery, Credits...         │
├─────────────────────────────────────┤
│ [📥 Download Receipt]               │
│ [✕ Cancel Order]                    │
│ [← Back to Orders]                  │
└─────────────────────────────────────┘
```

### Cancel Modal
```
┌─────────────────────────────────────┐
│ ⚠️ Cancel Order?                    │
├─────────────────────────────────────┤
│ Are you sure? Credits will be       │
│ refunded to your account.           │
│                                     │
│ Reason (Optional):                  │
│ [________________]                  │
│                                     │
│ [Keep Order] [Yes, Cancel]          │
└─────────────────────────────────────┘
```

### Orders List
```
┌──────────────────────────────────┐
│ Order #42 - Jan 3, 2025          │
│ Status: ⏳ Pending               │
│ Items: iPhone, Samsung            │
├──────────────────────────────────┤
│ [👁️ View Details] [✕ Cancel]     │
└──────────────────────────────────┘
```

---

## ✅ Success Indicators

✓ Cancel button appears only for eligible orders  
✓ Modal appears when cancel clicked  
✓ Reason is optional, can be empty  
✓ Order status changes to "Cancelled"  
✓ Credits immediately refunded  
✓ User sees success message  
✓ Email sent to user  
✓ Notification in-app appears  
✓ Transaction record created  
✓ Logs show cancellation event  

---

**Status:** ✅ FULLY IMPLEMENTED  
**Date:** January 3, 2026  
**Version:** 1.0
