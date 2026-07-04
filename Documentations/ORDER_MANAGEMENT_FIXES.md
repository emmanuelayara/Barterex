# Order Management - Implementation Guide

**Goal:** Fix critical issues and implement improvements to order management system

---

## FIX #1: Create Order Records During Purchase (CRITICAL)

### File: `routes/items.py`
### Location: Line ~540 (in `finalize_purchase()` before final `db.session.commit()`)

**Current Code (Missing):**
Order records are never created. Find this section:

```python
# Clear pending items from session
session.pop('pending_checkout_items', None)
flash(f"✓ Purchase complete! {len(purchased_items)} item(s) purchased.", "success")
return redirect(url_for('user.dashboard'))
```

**Replace with:**

```python
# CRITICAL: Create Order record for transaction history
import uuid
from datetime import timedelta

try:
    # Get delivery information from session
    pending_delivery = session.get('pending_delivery', {})
    
    # Generate order number: ORD-YYYYMMDD-XXXXX
    order_counter = Order.query.filter(
        Order.date_ordered >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    ).count()
    
    order_date = datetime.utcnow().strftime('%Y%m%d')
    order_number = f"ORD-{order_date}-{order_counter + 1:05d}"
    
    # Create Order record
    order = Order(
        user_id=current_user.id,
        delivery_method=pending_delivery.get('method', 'home delivery'),
        delivery_address=pending_delivery.get('delivery_address'),
        pickup_station_id=pending_delivery.get('pickup_station_id'),
        order_number=order_number,
        total_credits=total_cost,
        credits_used=total_cost,
        credits_balance_before=current_user.credits + total_cost,
        credits_balance_after=current_user.credits,
        status='Pending',
        date_ordered=datetime.utcnow(),
        estimated_delivery_date=datetime.utcnow() + timedelta(days=7),
        transaction_notes=f"Purchase of {len(purchased_items)} item(s)"
    )
    
    # Link items to order
    for item in purchased_items:
        order_item = OrderItem(order=order, item=item)
        db.session.add(order_item)
    
    db.session.add(order)
    db.session.commit()
    
    logger.info(f"[TXN:{transaction_id}] Order created - Order ID: {order.id}, Order #: {order_number}")
    
except Exception as e:
    logger.error(f"[TXN:{transaction_id}] Failed to create order record: {str(e)}", exc_info=True)
    # Don't fail the whole transaction, but log it
    flash("Warning: Order record could not be saved. Please contact support.", "warning")

# Clear pending items from session
session.pop('pending_checkout_items', None)
session.pop('pending_delivery', None)
flash(f"✓ Purchase complete! {len(purchased_items)} item(s) purchased. Order #{order_number if 'order' in locals() else 'unknown'}", "success")
return redirect(url_for('user.dashboard'))
```

### New Imports Needed (at top of routes/items.py):
```python
from models import Order, OrderItem
from datetime import timedelta
```

---

## FIX #2: Fix Order Status Reference (HIGH)

### File: `routes/admin.py`
### Location: Line ~1078 in `update_order_status()`

**Current Code:**
```python
item_names = ", ".join([f"{oi.item.name}" for oi in order.items])
```

**Should Be:**
```python
item_names = ", ".join([f"{oi.item.name}" for oi in order.order_items])
```

**Why:** Order model has `order_items` relationship, not `items`.

---

## FIX #3: Implement Order Status Validation (HIGH)

### File: `models.py`
### Location: Add to Order class (after relationships)

```python
# Add this to the Order class:

# Valid status transitions
VALID_TRANSITIONS = {
    'Pending': ['Confirmed', 'Cancelled'],
    'Confirmed': ['Shipped', 'Cancelled'],
    'Shipped': ['In Transit', 'Cancelled'],
    'In Transit': ['Delivered', 'Lost', 'Damaged'],
    'Delivered': ['Return Initiated', 'Return Completed'],
    'Lost': ['Refunded'],
    'Damaged': ['Refunded'],
    'Return Initiated': ['Return Completed'],
    'Return Completed': ['Refunded'],
    'Cancelled': ['Refunded'],
    'Refunded': []
}

def can_transition_to(self, new_status: str) -> bool:
    """Check if status transition is valid"""
    return new_status in self.VALID_TRANSITIONS.get(self.status, [])

def get_valid_next_statuses(self) -> list:
    """Get list of valid next statuses"""
    return self.VALID_TRANSITIONS.get(self.status, [])

def __repr__(self):
    return f'<Order {self.order_number}: {self.status}>'
```

---

## FIX #4: Replace Hard-Coded Status Logic (HIGH)

### File: `routes/admin.py`
### Location: Lines 1064-1145 in `update_order_status()`

**Current Code:**
```python
if order.status == "Pending":
    order.status = "Shipped"
elif order.status == "Shipped":
    order.status = "Out for Delivery"
elif order.status == "Out for Delivery":
    order.status = "Delivered"
```

**Replace with:**

```python
@admin_bp.route('/update_order_status/<int:order_id>', methods=['POST'])
@admin_login_required
@handle_errors
@safe_database_operation("update_order_status")
def update_order_status(order_id):
    try:
        from trading_points import award_points_for_purchase, create_level_up_notification
        from datetime import datetime
        
        order = Order.query.get_or_404(order_id)
        new_status = request.form.get('status', '').strip()
        notes = request.form.get('notes', '').strip()
        
        # Validate status transition
        if not new_status or not order.can_transition_to(new_status):
            valid_statuses = order.get_valid_next_statuses()
            flash(f"Cannot transition from {order.status} to {new_status}. Valid options: {', '.join(valid_statuses)}", "danger")
            return redirect(url_for('admin.manage_orders'))
        
        old_status = order.status
        order.status = new_status
        
        # Update delivery timestamp if delivered
        if new_status == 'Delivered' and old_status != 'Delivered':
            order.actual_delivery_date = datetime.utcnow()
        
        # Add transaction notes
        if notes:
            order.transaction_notes = f"{order.transaction_notes}\n[{datetime.utcnow().strftime('%Y-%m-%d %H:%M')}] {notes}"
        
        # Create notification message based on status
        status_messages = {
            'Confirmed': f"Your order {order.order_number} has been confirmed and is being prepared.",
            'Shipped': f"Your order {order.order_number} has been shipped!",
            'In Transit': f"Your order {order.order_number} is in transit.",
            'Delivered': f"Your order {order.order_number} has been delivered! 🎉",
            'Return Initiated': f"Your return request for order {order.order_number} has been received.",
            'Return Completed': f"Return for order {order.order_number} is complete.",
            'Refunded': f"Refund for order {order.order_number} has been processed.",
            'Cancelled': f"Order {order.order_number} has been cancelled.",
            'Lost': f"Unfortunately, order {order.order_number} appears to be lost in transit.",
            'Damaged': f"Order {order.order_number} arrived damaged. We're processing a replacement.",
        }
        
        notification = Notification(
            user_id=order.user_id,
            message=status_messages.get(new_status, f"Order {order.order_number} status updated to {new_status}"),
            notification_type='order',
            category='status_update',
            action_url=url_for('user.view_order_details', order_id=order.id, _external=False),
            data={'order_id': order.id, 'status': new_status},
            priority='high'
        )
        db.session.add(notification)
        
        # Award points only on first delivery (prevent double-awarding)
        if new_status == 'Delivered' and old_status != 'Delivered':
            user = order.user
            level_up_info = award_points_for_purchase(user, order.order_number)
            
            if level_up_info:
                create_level_up_notification(user, level_up_info)
                # Update notification message with level-up info
                notification.message = (
                    f"Your order {order.order_number} has been delivered! 🎉 "
                    f"You earned 20 trading points and reached Level {level_up_info['new_level']} "
                    f"({level_up_info['new_tier']})! "
                    f"Bonus reward: {level_up_info['credits_awarded']} credits!"
                )
            else:
                notification.message = f"Your order {order.order_number} has been delivered! You earned 20 trading points."
        
        # Create audit log
        try:
            from models import OrderAuditLog
            audit = OrderAuditLog(
                order_id=order.id,
                admin_id=session.get('admin_id'),
                action=f"Status changed: {old_status} → {new_status}",
                old_value=old_status,
                new_value=new_status,
                timestamp=datetime.utcnow()
            )
            db.session.add(audit)
        except Exception as e:
            logger.warning(f"Failed to create audit log: {str(e)}")
        
        db.session.commit()
        
        logger.info(f"Order status updated - Order ID: {order_id}, {old_status} → {new_status}, Admin: {session.get('admin_username')}")
        flash(f"Order status updated to {new_status}", "success")
        return redirect(url_for('admin.manage_orders'))
        
    except Exception as e:
        logger.error(f"Error updating order status: {str(e)}", exc_info=True)
        flash('An error occurred while updating the order status.', 'danger')
        return redirect(url_for('admin.manage_orders'))
```

---

## FIX #5: Improve Admin Manage Orders Route (HIGH)

### File: `routes/admin.py`
### Location: Lines 1049-1063, replace `manage_orders()` function

```python
@admin_bp.route('/manage_orders')
@admin_login_required
@handle_errors
def manage_orders():
    try:
        page = request.args.get('page', 1, type=int)
        status_filter = request.args.get('status', 'all')
        search_query = request.args.get('search', '').strip()
        sort_by = request.args.get('sort', 'date-desc')
        
        # Build base query with eager loading
        query = Order.query.options(
            joinedload(Order.user),
            joinedload(Order.pickup_station),
            joinedload(Order.order_items).joinedload(OrderItem.item)
        )
        
        # Apply status filter
        if status_filter != 'all':
            query = query.filter_by(status=status_filter)
        
        # Apply search filter
        if search_query:
            # Search by order number or user
            search_term = f"%{search_query}%"
            query = query.filter(
                db.or_(
                    Order.order_number.ilike(search_term),
                    Order.id.cast(String).ilike(search_term),
                    User.username.ilike(search_term)
                )
            ).outerjoin(User)
        
        # Apply sorting
        sort_map = {
            'date-desc': Order.date_ordered.desc(),
            'date-asc': Order.date_ordered.asc(),
            'id-desc': Order.id.desc(),
            'id-asc': Order.id.asc(),
            'status': Order.status.asc(),
            'user': User.username.asc(),
        }
        query = query.order_by(sort_map.get(sort_by, Order.date_ordered.desc()))
        
        # Paginate
        orders = query.paginate(page=page, per_page=20)
        
        # Get all available statuses
        all_statuses = ['Pending', 'Confirmed', 'Shipped', 'In Transit', 'Delivered', 'Cancelled', 'Lost', 'Damaged', 'Return Initiated', 'Return Completed', 'Refunded']
        
        logger.info(f"Order management page accessed - Total orders: {orders.total}, Filter: {status_filter}")
        
        return render_template(
            'admin/manage_orders.html',
            orders=orders,
            all_statuses=all_statuses,
            current_status=status_filter,
            search_query=search_query,
            sort_by=sort_by
        )
    except Exception as e:
        logger.error(f"Error loading orders management: {str(e)}", exc_info=True)
        flash('An error occurred while loading orders.', 'danger')
        return redirect(url_for('admin.admin_dashboard'))
```

### Required Imports:
```python
from sqlalchemy import String
from sqlalchemy.orm import joinedload
```

---

## FIX #6: Add OrderAuditLog Model (MEDIUM)

### File: `models.py`
### Location: Add new model class (around line 465, after OrderItem)

```python
class OrderAuditLog(db.Model):
    """Audit trail for all order status changes"""
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(255), nullable=False)  # e.g., "Status changed: Pending → Shipped"
    old_value = db.Column(db.String(255), nullable=True)
    new_value = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    order = db.relationship('Order', backref='audit_logs', cascade='all, delete-orphan')
    admin = db.relationship('User', backref='order_audit_logs', foreign_keys=[admin_id])
    
    def __repr__(self):
        return f'<OrderAuditLog {self.id}: {self.action}>'
```

---

## FIX #7: Add Database Indexes (MEDIUM)

### File: `models.py`
### Location: Modify Order class relationships section

```python
# Add these indexes to the Order model (within the class, after relationships):

# Indexes for common queries
__table_args__ = (
    db.Index('ix_order_user_date', 'user_id', 'date_ordered'),
    db.Index('ix_order_status_date', 'status', 'date_ordered'),
    db.Index('ix_order_number', 'order_number'),  # Already unique, but make sure it's indexed
)
```

---

## FIX #8: Update Admin Templates (MEDIUM)

### File: `templates/admin/manage_orders.html`
### Location: Update the status update form

Replace the status update button section with:

```html
<td class="status-update">
    <form method="POST" action="{{ url_for('admin.update_order_status', order_id=order.id) }}" class="d-inline">
        <div class="input-group input-group-sm">
            <select name="status" class="form-select form-select-sm">
                <option value="">Change status...</option>
                {% for valid_status in order.get_valid_next_statuses() %}
                    <option value="{{ valid_status }}">{{ valid_status }}</option>
                {% endfor %}
            </select>
            <button type="submit" class="btn btn-sm btn-primary" title="Update status">Update</button>
        </div>
    </form>
</td>
```

---

## FIX #9: Testing Checklist

After implementing these fixes, test:

```
ORDER CREATION TESTS:
✓ Purchase 1 item → Order created with correct order_number
✓ Purchase multiple items → Order created with all items linked
✓ Order has correct delivery method (home/pickup)
✓ Order has correct delivery address
✓ Order status defaults to 'Pending'
✓ Order has estimated delivery date (7 days out)
✓ Order displays in user order history

STATUS UPDATE TESTS:
✓ Admin can change status through dropdown
✓ Can only transition to valid next statuses
✓ Invalid transitions show error message
✓ Audit log created for each change
✓ User notification sent when status changes
✓ Timestamp updated when delivered

PERFORMANCE TESTS:
✓ Load manage_orders with 1000+ orders < 1 second
✓ Search functionality works correctly
✓ Status filter works
✓ No N+1 queries (check logs)
✓ Pagination works correctly

EDGE CASES:
✓ User can't see other users' orders
✓ Can't manually set invalid statuses via URL
✓ Order numbers are unique
✓ Cancelled orders prevent refunds
✓ Receipt download works
```

---

## SUMMARY

**Total Fixes:** 9
**Critical:** 3 (Order creation, status validation, hard-coded logic)
**High:** 3 (Reference fix, improve route, template updates)
**Medium:** 3 (Audit log, indexes, testing)

**Estimated Time:** 3-4 hours to implement all fixes
**Testing Time:** 2-3 hours

**Next Steps:**
1. Implement Fix #1 (Order creation) - CRITICAL
2. Test Fix #1 thoroughly
3. Implement Fixes #2-4 (validation & logic)
4. Implement Fixes #5-9 (improvements & polish)
5. Run full testing suite
6. Deploy to production

