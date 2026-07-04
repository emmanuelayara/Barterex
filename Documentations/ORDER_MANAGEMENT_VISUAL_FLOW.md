# Order Management System - Visual Code Flow & Architecture

---

## CURRENT ORDER CREATION FLOW (Broken)

```
┌─────────────────────────────────────────────────────────────────┐
│                      USER CHECKOUT FLOW                          │
└─────────────────────────────────────────────────────────────────┘

1. USER ADDS ITEMS TO CART
   └─> Cart → CartItem records created ✅

2. USER CLICKS "CHECKOUT"
   └─> routes/items.py:checkout()
       ├─> Validates items are available ✅
       ├─> Checks user has enough credits ✅
       ├─> Stores pending_checkout_items in session
       └─> Redirects to order_item page ✅

3. USER SETS UP DELIVERY
   └─> routes/items.py:order_item()
       ├─> Shows form with pickup stations or address field
       ├─> Validates delivery details ✅
       ├─> Stores pending_delivery in session
       └─> Shows order review page ✅

4. USER CONFIRMS PURCHASE
   └─> routes/items.py:finalize_purchase()
       ├─> Re-validates items still available ✅
       ├─> Acquires database locks on items ✅
       ├─> Deducts credits from user account ✅
       ├─> Marks items as purchased (user_id set) ✅
       ├─> Creates Trade records ✅
       ├─> Awards trading points ✅
       ├─> Removes items from cart ✅
       │
       ├─ MISSING: Create Order record ❌❌❌
       │   │
       │   └─> order = Order(user_id=..., delivery_method=...)
       │   └─> db.session.add(order)
       │   └─> db.session.commit()
       │
       └─> Returns success message ✅

5. RESULT IN DATABASE:
   ├─> User.credits decreased ✅
   ├─> Item.user_id changed ✅
   ├─> Item.is_available = False ✅
   ├─> Trade record created ✅
   ├─> Notification created ✅
   └─> Order record created? ❌ NO!

┌─────────────────────────────────────────────────────────────────┐
│  SO WHEN USER VISITS /my_orders                                  │
│  Query: Order.query.filter_by(user_id=current_user.id)          │
│  Result: Empty list (no orders exist!)                           │
│                                                                   │
│  Admin visits /manage_orders                                     │
│  Query: Order.query.all()                                        │
│  Result: Empty list (no orders exist!)                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## WHAT SHOULD HAPPEN (Fixed Flow)

```
finalize_purchase() - AFTER CREDITS DEDUCTED & ITEMS LINKED:

    # 1. Generate unique order number
    order_counter = Order.query.filter(
        Order.date_ordered >= today_start
    ).count()
    order_number = f"ORD-{today}-{counter+1:05d}"
    # Example: ORD-20241215-00042

    # 2. Get delivery info from session
    pending_delivery = session.get('pending_delivery')
    # {
    #   'method': 'home delivery',
    #   'delivery_address': '123 Main St, Lagos',
    #   'pickup_station_id': None
    # }

    # 3. Create Order record
    order = Order(
        user_id=current_user.id,                    # Who bought
        delivery_method=pending_delivery['method'], # How to deliver
        delivery_address=pending_delivery['address'],
        pickup_station_id=pending_delivery['station_id'],
        order_number=order_number,                  # ORD-20241215-00042
        total_credits=total_cost,                   # ₦50,000
        credits_used=total_cost,                    # ₦50,000
        credits_balance_before=old_balance,         # ₦100,000
        credits_balance_after=new_balance,          # ₦50,000
        status='Pending',
        date_ordered=datetime.utcnow(),
        estimated_delivery_date=datetime.utcnow() + 7 days,
        transaction_notes=f"Purchase of {len(items)} items"
    )

    # 4. Link items to order
    for item in purchased_items:
        order_item = OrderItem(order=order, item=item)
        db.session.add(order_item)

    # 5. Save to database
    db.session.add(order)
    db.session.commit()

    # 6. Clear session
    session.pop('pending_delivery')
    session.pop('pending_checkout_items')

    # 7. Show success
    flash(f"Order {order_number} created successfully!")
    return redirect(url_for('user.dashboard'))

┌─────────────────────────────────────────────────────────────────┐
│  NOW WHEN USER VISITS /my_orders                                 │
│  Query: Order.query.filter_by(user_id=current_user.id)          │
│  Result: [<Order ORD-20241215-00042: Pending>]                  │
│                                                                   │
│  Admin visits /manage_orders                                     │
│  Query: Order.query.all()                                        │
│  Result: [<Order ORD-20241215-00042>, <Order ORD-20241215-00043>]
└─────────────────────────────────────────────────────────────────┘
```

---

## DATA FLOW DIAGRAM

```
┌─────────────────┐
│   USER ACCOUNT  │
│   (credits=100) │
└────────┬────────┘
         │
         │ Deduct ₦50
         ▼
    ┌──────────────────────┐
    │   CreditTransaction  │
    │   (purchase record)  │
    └──────────────────────┘
    
    
┌──────────┐      ┌──────────┐      ┌──────────┐
│  Item 1  │      │  Item 2  │      │  Item 3  │
│ user_id= │      │ user_id= │      │ user_id= │
│ ORIGINAL │      │ ORIGINAL │      │ ORIGINAL │
│          │      │          │      │          │
└────┬─────┘      └────┬─────┘      └────┬─────┘
     │ Link to buyer   │ Link to buyer   │ Link to buyer
     ▼                 ▼                 ▼
     
┌────────────────────────────────────────┐
│  Item 1, Item 2, Item 3                │
│  (now belong to current_user)          │
│  is_available = False                  │
└────────────────────────────────────────┘

         ↓
         
┌────────────────────────────────────────────┐
│         ✅ Trade Records Created           │
│  (records that items were traded)          │
│  sender_id = current_user                  │
│  receiver_id = original_seller             │
└────────────────────────────────────────────┘

         ↓
         
┌────────────────────────────────────────────┐
│  ❌ ORDER RECORD NOT CREATED               │
│  (THIS IS THE BUG!)                        │
│                                            │
│  Should have:                              │
│  ├─ order_id                               │
│  ├─ order_number = ORD-20241215-00042      │
│  ├─ user_id = current_user                 │
│  ├─ total_credits = 50                     │
│  ├─ status = Pending                       │
│  ├─ delivery_method = home_delivery        │
│  └─ OrderItem links to Item 1, 2, 3        │
│                                            │
│  But this order exists NOWHERE in DB!      │
└────────────────────────────────────────────┘
```

---

## DATABASE SCHEMA (Current)

```
User
├─ id (PK)
├─ username
├─ credits
├─ orders (FK)  ← Points to Order table
└─ ... other fields

Item
├─ id (PK)
├─ name
├─ user_id (FK) ← After purchase, points to new owner
├─ value
├─ is_available
└─ ... other fields

Trade (Old system - still used)
├─ id (PK)
├─ sender_id (FK to User)
├─ receiver_id (FK to User)
├─ item_id (FK to Item)
├─ status
└─ ... other fields

Order ← THIS TABLE IS EMPTY! 
├─ id (PK)
├─ user_id (FK) ← Should be filled
├─ order_number (UNIQUE) ← Should be ORD-20241215-00042
├─ delivery_method ← Should be "home delivery" or "pickup"
├─ delivery_address ← Should be filled
├─ status ← Should be "Pending"
├─ total_credits ← Should be filled
├─ credits_used ← Should be filled
├─ date_ordered ← Should be filled
├─ actual_delivery_date ← Will be filled when delivered
└─ ... other fields

OrderItem ← REFERENCES Order (so also empty)
├─ id (PK)
├─ order_id (FK to Order) ← Should link to above Order
├─ item_id (FK to Item)
└─ ... other fields
```

---

## ADMIN ORDER MANAGEMENT FLOW

```
CURRENT (Broken):
┌──────────────────────────┐
│  Admin visits /manage_orders
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ routes/admin.py:1049     │
│ manage_orders()          │
└──────────┬───────────────┘
           │
           ├─> orders = Order.query.all()
           │           ↓
           │      Returns: [] (empty!)
           │
           └─> render_template('admin/manage_orders.html', orders=[])
               │
               ▼
        ┌──────────────────────┐
        │  Displays empty table │
        │  "No orders found"    │
        └──────────────────────┘

FIXED (What should happen):
┌──────────────────────────┐
│  Admin visits /manage_orders
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ routes/admin.py:1049     │
│ manage_orders()          │
└──────────┬───────────────┘
           │
           ├─> page = 1, status = 'all'
           ├─> query = Order.query.options(
           │       joinedload(Order.user),
           │       joinedload(Order.order_items)
           │   )
           ├─> orders = query.paginate(page=1, per_page=20)
           │           ↓
           │      Returns: [<Order: ORD-20241215-00042>, ...]
           │
           └─> render_template('admin/manage_orders.html', orders=orders)
               │
               ▼
        ┌──────────────────────┐
        │  Displays orders:     │
        │  Order #42            │
        │  Status: Pending      │
        │  Customer: john_doe   │
        │  [Update Status] btn   │
        └──────────────────────┘
```

---

## STATUS UPDATE FLOW

```
CURRENT (Hard-coded, inflexible):
┌─────────────────────────────────┐
│ Admin clicks "Update Status"     │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│ if order.status == "Pending":   │
│     order.status = "Shipped"    │
│ elif order.status == "Shipped": │
│     order.status = "Out for..."  │
│ elif order.status == "Out...":   │
│     order.status = "Delivered"  │
└──────────┬──────────────────────┘
           │
           ├─ Award trading points
           ├─ Create notification
           └─> db.session.commit()

ISSUES:
❌ Can only go forward (no reversals)
❌ Can't cancel orders
❌ No validation of transitions
❌ No audit trail
❌ Status is string (typos possible)

FIXED (Validation with state machine):
┌─────────────────────────────────┐
│ Admin selects status from list  │
│ (only valid options shown)      │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│ new_status = request.form['status']
│ if not order.can_transition_to(new_status):
│     return error("Invalid transition")
│ 
│ valid_transitions = {
│     'Pending': ['Shipped', 'Cancelled'],
│     'Shipped': ['In Transit', 'Cancelled'],
│     'In Transit': ['Delivered', 'Lost'],
│     'Delivered': ['Return Initiated'],
│     ...
│ }
└──────────┬──────────────────────┘
           │
           ├─ ✅ Validate transition
           ├─ Update order.status
           ├─ Update actual_delivery_date if delivered
           ├─ Create OrderAuditLog (who/when/what)
           ├─ Send email notification to user
           ├─ Award points (only if first delivery)
           └─> db.session.commit()

BENEFITS:
✅ Prevents invalid transitions
✅ Supports cancellations, returns, refunds
✅ Full audit trail
✅ User always knows status
✅ Typed status (Enum)
```

---

## QUERY PERFORMANCE ANALYSIS

```
Current Query (Inefficient):
┌────────────────────────────────────────┐
│ orders = Order.query.all()             │
│ items = Item.query.all()  ← WASTEFUL! │
│                                        │
│ For each order:                        │
│   For each order_item:                 │
│     SELECT item FROM items ← N+1!      │
│     SELECT user FROM users ← N+1!      │
│                                        │
│ Result: 1 + 1 + n + n queries!        │
└────────────────────────────────────────┘

Fixed Query (Optimized):
┌────────────────────────────────────────┐
│ orders = Order.query.options(          │
│     joinedload(Order.user),            │
│     joinedload(Order.order_items)      │
│       .joinedload(OrderItem.item)      │
│       .joinedload(Item.user)           │
│ ).paginate(page=1, per_page=20)        │
│                                        │
│ Result: 1 single query with all data! │
│ Performance improvement: 10-100x       │
└────────────────────────────────────────┘
```

---

## SUMMARY: What's Broken vs Fixed

| Aspect | Current | Fixed |
|--------|---------|-------|
| **Order Creation** | ❌ Never happens | ✅ After finalize_purchase() |
| **Order Records** | ❌ 0 in database | ✅ Thousands after fix |
| **User Order History** | ❌ Empty always | ✅ Shows all purchases |
| **Admin Management** | ❌ No orders to manage | ✅ Full order list |
| **Status Updates** | ❌ Hard-coded logic | ✅ Flexible state machine |
| **Status Validation** | ❌ None | ✅ Validates transitions |
| **Audit Trail** | ❌ None | ✅ Full history logged |
| **Email Notifications** | ❌ Sent but order missing | ✅ Matches actual order |
| **Query Performance** | ❌ N+1 problems | ✅ Optimized with joins |
| **Delivery Tracking** | ❌ No dates recorded | ✅ actual_delivery_date set |

---

