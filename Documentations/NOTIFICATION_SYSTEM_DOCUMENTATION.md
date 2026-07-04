# Notification System Documentation

## Overview

The Barterex notification system provides comprehensive, real-time notifications for users across multiple channels (in-app, email, and UI toasts). This system is built with a service-oriented architecture that allows notifications to be triggered from anywhere in the application.

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (base.html)                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  NotificationManager (JavaScript)                   │   │
│  │  - Polling every 10 seconds                         │   │
│  │  - Updates notification badge                       │   │
│  │  - Displays toast notifications                     │   │
│  │  - Manages preferences                              │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────┬─────────────────────────────────────────────────┘
             │ HTTP/JSON
┌────────────▼─────────────────────────────────────────────────┐
│           API Layer (routes/notifications_api.py)            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  20+ REST Endpoints                                 │   │
│  │  - /api/notifications/real-time                     │   │
│  │  - /api/notifications/preferences                   │   │
│  │  - /api/notifications/order-status                  │   │
│  │  - ... and more                                     │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────┬─────────────────────────────────────────────────┘
             │
┌────────────▼─────────────────────────────────────────────────┐
│      Service Layer (notifications.py)                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  NotificationService Class                          │   │
│  │  - Business logic for notifications                 │   │
│  │  - Email integration                                │   │
│  │  - Preference management                            │   │
│  │  - Notification filtering                           │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────┬─────────────────────────────────────────────────┘
             │
┌────────────▼─────────────────────────────────────────────────┐
│      Data Layer (models.py)                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Notification Model                                 │   │
│  │  - Stores all notification data                     │   │
│  │  - Types, categories, priority levels               │   │
│  │                                                     │   │
│  │  User Model                                         │   │
│  │  - notification_preferences JSON                    │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Database Models

### Notification Model

```python
class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(512), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    notification_type = db.Column(db.String(50), default='system')  # cart, order, message, etc.
    category = db.Column(db.String(50), default='general')  # quick_action, status_update, alert, etc.
    action_url = db.Column(db.String(256))  # URL for notification click
    data = db.Column(db.JSON)  # Additional context (order_id, item_id, etc.)
    is_email_sent = db.Column(db.Boolean, default=False)
    priority = db.Column(db.String(20), default='normal')  # low, normal, high, urgent
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
```

### User Preferences

User model includes a `notification_preferences` JSON column with the following structure:

```python
{
    "email_order_updates": True,           # Email on order confirmation/status
    "email_cart_items": False,             # Email on cart item additions
    "email_messages": True,                # Email on new messages
    "email_listing_activities": True,      # Email on listing interactions
    "email_recommendations": False,        # Email for recommendations
    "push_cart_items": True,               # In-app notification for cart items
    "push_order_updates": True,            # In-app notification for orders
    "push_messages": True,                 # In-app notification for messages
    "push_listing_activities": True,       # In-app notification for listings
    "push_recommendations": False,         # In-app notification for recommendations
    "notification_frequency": "instant"    # instant, daily, weekly
}
```

## Service Layer (notifications.py)

### Main Class: NotificationService

#### Methods

##### 1. create_notification()
Creates and stores a notification in the database.

```python
def create_notification(user_id, message, notification_type='system', 
                       category='general', action_url=None, data=None, 
                       priority='normal', send_email=False)
```

**Parameters:**
- `user_id`: Target user ID
- `message`: Notification message
- `notification_type`: Type of notification (default: 'system')
- `category`: Category for grouping (default: 'general')
- `action_url`: URL for the notification to link to
- `data`: JSON object with additional context
- `priority`: Importance level (default: 'normal')
- `send_email`: Whether to send email (default: False)

**Returns:** Created Notification object

**Example:**
```python
from notifications import notify_order_placed

notify_order_placed(user_id=1, order_id=123)
```

##### 2. send_email_notification()
Sends an email notification based on template.

```python
def send_email_notification(user_id, notification_type, message, 
                           action_url=None, data=None)
```

**Parameters:**
- `user_id`: Target user ID
- `notification_type`: Type of notification
- `message`: Email message
- `action_url`: Link in email
- `data`: Template data dictionary

**Returns:** Boolean indicating success

##### 3. Specialized Notification Methods

- `notify_item_added_to_cart(user_id, item_id)`
- `notify_order_placed(user_id, order_id)`
- `notify_order_status_update(user_id, order_id, status)`
- `notify_item_sold(user_id, item_id)`
- `notify_new_message(user_id, sender_name, message_preview)`
- `notify_trade_request(user_id, requester_name, item_name)`
- `notify_recommendation(user_id, item_name, item_id)`

##### 4. Preference Methods

```python
def get_user_preferences(user_id)
```
Returns user's notification preferences.

```python
def update_user_preferences(user_id, preferences)
```
Updates user's notification preferences.

**Example:**
```python
prefs = {
    'email_order_updates': True,
    'notification_frequency': 'daily'
}
NotificationService.update_user_preferences(user_id, prefs)
```

##### 5. Query Methods

```python
def get_user_notifications(user_id, limit=10, unread_only=False, 
                          notification_type=None)
```
Retrieves notifications for a user.

```python
def get_unread_count(user_id)
```
Returns count of unread notifications.

```python
def mark_as_read(notification_id, user_id)
```
Marks a single notification as read.

```python
def mark_all_as_read(user_id)
```
Marks all notifications as read.

```python
def delete_notification(notification_id, user_id)
```
Deletes a notification.

### Module-Level Functions

For convenience, the notifications.py module provides shorthand functions:

```python
from notifications import (
    notify_order_placed,
    notify_order_status,
    notify_cart_item,
    get_unread_count,
    get_notifications
)
```

## API Endpoints

### Real-Time Notifications

#### GET /api/notifications/real-time
Fetches unread notifications for real-time updates.

**Response:**
```json
{
    "status": "success",
    "notifications": [
        {
            "id": 1,
            "message": "Your order has been placed",
            "notification_type": "order",
            "category": "status_update",
            "priority": "high",
            "action_url": "/orders/123",
            "is_read": false,
            "created_at": "2024-01-15T10:30:00"
        }
    ],
    "count": 1
}
```

#### POST /api/notifications/toast
Sends a quick toast notification.

**Request:**
```json
{
    "message": "Item added to cart",
    "type": "success",
    "duration": 3000
}
```

#### GET /api/notifications/unread-count
Gets count of unread notifications.

**Response:**
```json
{
    "status": "success",
    "unread_count": 3,
    "total_count": 15
}
```

### Order Notifications

#### POST /api/notifications/order-status
Updates order status notification.

**Request:**
```json
{
    "order_id": 123,
    "status": "shipped",
    "message": "Your order has been shipped"
}
```

#### POST /api/notifications/order-placed
Sends order confirmation.

**Request:**
```json
{
    "order_id": 123
}
```

### Notification Management

#### POST /api/notifications/mark-read/<id>
Marks notification as read.

#### POST /api/notifications/mark-all-read
Marks all notifications as read.

#### DELETE /api/notifications/delete/<id>
Deletes a notification.

#### GET /api/notifications/list
Lists notifications with filtering.

**Query Parameters:**
- `limit`: Results per page (default: 10)
- `offset`: Pagination offset (default: 0)
- `type`: Filter by notification type
- `category`: Filter by category

### Preferences

#### GET /api/notifications/preferences
Retrieves user's notification preferences.

**Response:**
```json
{
    "status": "success",
    "preferences": {
        "email_order_updates": true,
        "email_cart_items": false,
        "notification_frequency": "instant"
    }
}
```

#### POST /api/notifications/preferences
Updates user's notification preferences.

**Request:**
```json
{
    "email_order_updates": true,
    "notification_frequency": "daily"
}
```

### Other Notifications

- `POST /api/notifications/cart/item-added` - Cart item notification
- `POST /api/notifications/item-sold` - Seller notification
- `POST /api/notifications/new-message` - Message notification
- `POST /api/notifications/trade-request` - Trade request notification
- `POST /api/notifications/recommendation` - Recommendation notification

## Frontend Integration

### NotificationManager Class

The NotificationManager JavaScript class handles all client-side notification logic.

#### Methods

```javascript
// Start polling for notifications
notificationManager.start()

// Stop polling
notificationManager.stop()

// Manually fetch notifications
notificationManager.fetchNotifications()

// Handle incoming notifications
notificationManager.handleNotifications(notifications)

// Display a notification as toast
notificationManager.displayNotification(notification)

// Update unread count badge
notificationManager.updateUnreadCount(count)

// Get current unread count
notificationManager.getUnreadCount()

// Mark notification as read
notificationManager.markAsRead(notificationId)

// Delete notification
notificationManager.deleteNotification(notificationId)

// Get preferences
notificationManager.getPreferences()

// Update preferences
notificationManager.updatePreferences(preferences)
```

#### Auto-Start

The NotificationManager automatically starts when the page loads (if user is authenticated):

```javascript
document.addEventListener('DOMContentLoaded', function() {
    if (window.isAuthenticated) {
        window.notificationManager = new NotificationManager();
        window.notificationManager.start();
    }
});
```

#### Quick-Action Functions

Global functions for immediate notifications:

```javascript
// Cart notification
notifyItemAddedToCart(itemId, itemName)

// Order notification
notifyOrderPlaced(orderId)

// Order status notification
notifyOrderStatus(orderId, status)
```

## Settings Page

### URL
`/notification-settings` (GET)

### Features

- Email notification preferences (5 toggles)
- In-app notification preferences (5 toggles)
- Notification frequency selector (instant/daily/weekly)
- Save/Reset buttons
- Success/error messages

### JavaScript Integration

The settings page automatically:
1. Loads current preferences on page load
2. Sends updates to `/api/notifications/preferences`
3. Shows success/error toasts
4. Supports reset to defaults

## Email Templates

Email templates are located in `templates/emails/`:

### 1. order_confirmation.html
Sent when an order is placed.

**Template Variables:**
- `user_name`
- `order_id`
- `order_date`
- `total_amount`
- `action_url`

### 2. order_status_update.html
Sent when order status changes.

**Template Variables:**
- `user_name`
- `order_id`
- `updated_date`
- `status` (processing, shipped, delivered, cancelled)
- `status_message`
- `action_url`

### 3. item_sold.html
Sent to seller when item is sold.

**Template Variables:**
- `seller_name`
- `item_name`
- `item_id`
- `buyer_name`
- `sale_date`
- `sale_price`
- `action_url`

### 4. new_message.html
Sent when user receives a message.

**Template Variables:**
- `recipient_name`
- `sender_name`
- `received_date`
- `message_preview`
- `action_url`

### 5. trade_request.html
Sent when trade request is received.

**Template Variables:**
- `recipient_name`
- `requester_name`
- `item_name`
- `request_date`
- `trade_notes`
- `action_url`

### 6. recommendation.html
Sent for personalized recommendations.

**Template Variables:**
- `user_name`
- `item_name`
- `item_condition`
- `item_price`
- `item_category`
- `item_description`
- `recommendation_reason`
- `action_url`

## Usage Examples

### Creating Notifications Programmatically

```python
from notifications import NotificationService

# Simple notification
notify = NotificationService.create_notification(
    user_id=1,
    message="Welcome to Barterex!",
    notification_type='system',
    category='general',
    priority='low'
)

# With email
notify = NotificationService.create_notification(
    user_id=1,
    message="Your order has been placed",
    notification_type='order',
    category='status_update',
    action_url='/orders/123',
    data={'order_id': 123},
    priority='high',
    send_email=True
)
```

### Integrating with Routes

```python
from notifications import notify_order_placed

@app.route('/place-order', methods=['POST'])
@login_required
def place_order():
    # ... create order logic ...
    
    # Notify user
    notify_order_placed(current_user.id, order.id)
    
    # ... rest of logic ...
```

### Managing Preferences

```python
from notifications import NotificationService

# Get preferences
prefs = NotificationService.get_user_preferences(user_id)

# Update preferences
new_prefs = {
    'email_order_updates': True,
    'notification_frequency': 'daily',
    'push_cart_items': False
}
NotificationService.update_user_preferences(user_id, new_prefs)
```

## Configuration

### Environment Variables

Add to `.env`:

```
# Notification preferences
NOTIFICATION_ENABLE_EMAIL=True
NOTIFICATION_EMAIL_DELAY=0  # Seconds
NOTIFICATION_RETENTION_DAYS=30  # Archive old notifications
```

### Email Configuration

Configure Flask-Mail in `app.py`:

```python
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
```

## Troubleshooting

### Notifications Not Appearing

1. Check NotificationManager is running:
   - Open DevTools Console
   - Check for errors
   - Verify `window.notificationManager` exists

2. Verify API endpoints are accessible:
   - Check `/api/notifications/real-time` in Network tab
   - Should return 200 with notification data

3. Check preferences:
   - Visit `/notification-settings`
   - Verify toggles are enabled
   - Check browser console for errors

### Emails Not Sending

1. Verify Flask-Mail configuration:
   ```python
   from app import mail, app
   with app.app_context():
       msg = Message("Test", recipients=['test@example.com'])
       mail.send(msg)
   ```

2. Check email preferences:
   - User may have disabled email notifications
   - Visit `/notification-settings` to enable

3. Check logs for errors:
   - Look for email sending errors
   - Check `is_email_sent` flag in database

### Badge Not Updating

1. Clear browser cache
2. Hard refresh page (Ctrl+Shift+R)
3. Check `data-notification-badge` element exists in base.html
4. Verify JavaScript runs: `console.log(window.notificationManager)`

## Best Practices

### For Developers

1. **Always use NotificationService** - Don't create Notification objects directly
2. **Include action URLs** - Provide links users can click
3. **Use appropriate priority** - Help users focus on important notifications
4. **Respect user preferences** - Always check before sending emails
5. **Add context in data** - Include IDs, references for debugging

### For Users

1. **Customize settings** - Visit `/notification-settings` to control what you receive
2. **Set frequency** - Use daily/weekly digests if instant notifications are distracting
3. **Check notification center** - Visit `/notifications` to see full history
4. **Mark as read** - Keep notification center organized

## Performance Considerations

- Real-time polling uses 10-second intervals (configurable)
- Notifications paginated to 10 per request
- Email sending is non-blocking (ready for async implementation)
- Database indexes on `user_id` and `is_read` for fast queries
- Old notifications automatically archived after 30 days

## Future Enhancements

1. **WebSocket Support** - Replace polling with true real-time via WebSocket
2. **Browser Notifications** - Use Web Push API for system-level alerts
3. **SMS Notifications** - Add SMS as a notification channel
4. **Notification History** - Archive and search old notifications
5. **Batch Digests** - Collect and send daily/weekly summaries
6. **Notification Rules** - Let users create custom notification rules
7. **Desktop App Support** - Push notifications to desktop/mobile apps

## Support

For issues or questions:
1. Check this documentation
2. Review logs in `logs/` directory
3. Contact development team at support@barterex.com
