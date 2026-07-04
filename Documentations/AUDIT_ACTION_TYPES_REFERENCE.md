# Complete Audit Logging Action Types Reference

## All 21+ Logged Admin Actions

### Format
Each action can be filtered in the audit log at `/audit-log`

---

## Authentication Actions

### admin_login
**Route**: `/login`
**When**: Admin successfully logs in
**Data Captured**: 
- admin_id (from session)
- timestamp (UTC)
- ip_address (automatic)
**Query**: Filter audit log by action_type = 'admin_login'

### admin_logout
**Route**: `/logout`
**When**: Admin logs out (before session clear)
**Data Captured**:
- admin_id
- timestamp
- ip_address
**Query**: Filter audit log by action_type = 'admin_logout'

---

## User Management Actions

### ban_user
**Route**: `/ban_user/<user_id>` (POST)
**When**: Admin bans a user account
**Data Captured**:
- target: user (target_id, target_name = username)
- description: "User {username} banned"
- reason: ban_reason from form
- admin_id, timestamp, ip_address
**Query**: Filter by action_type = 'ban_user'

### unban_user
**Route**: `/unban_user/<user_id>` (POST)
**When**: Admin removes ban from user
**Data Captured**:
- target: user
- description: "User {username} unbanned"
- admin_id, timestamp
**Query**: Filter by action_type = 'unban_user'

### approve_unban
**Route**: `/approve_unban/<user_id>` (POST)
**When**: Admin approves unban request/appeal
**Data Captured**:
- target: user
- description: "Unban request approved for user {username}"
- admin_id, timestamp
**Query**: Filter by action_type = 'approve_unban'

### reject_unban
**Route**: `/reject_unban/<user_id>` (POST)
**When**: Admin rejects unban request
**Data Captured**:
- target: user
- description: "Unban request rejected for user {username}"
- admin_id, timestamp
**Query**: Filter by action_type = 'reject_unban'

### reject_unban_appeal
**Route**: `/reject_unban_appeal/<user_id>` (POST)
**When**: Admin rejects unban appeal message
**Data Captured**:
- target: user
- description: "Unban appeal rejected for user {username}"
- admin_id, timestamp
**Query**: Filter by action_type = 'reject_unban_appeal'

### delete_user
**Route**: `/delete_user/<user_id>` (POST)
**When**: Admin permanently deletes user account
**Data Captured**:
- target: user (target_id, target_name = username)
- description: "User account deleted. Items: X. All cascaded deleted."
- before_value: old_data (could be captured if needed)
- admin_id, timestamp
**Query**: Filter by action_type = 'delete_user'
**Note**: Cascades to items, orders, notifications

### edit_user
**Route**: `/user/<user_id>/edit` (POST)
**When**: Admin updates user credits
**Data Captured**:
- target: user
- description: "User credits updated"
- before_value: old_credits
- after_value: new_credits
- admin_id, timestamp
**Query**: Filter by action_type = 'edit_user'

### export_user_data
**Route**: `/user/<user_id>/export` (GET)
**When**: Admin exports user data (GDPR)
**Data Captured**:
- target: user
- description: "User data exported as PDF files in ZIP"
- admin_id, timestamp
**Query**: Filter by action_type = 'export_user_data'

---

## Item Management Actions

### approve_item
**Route**: `/approve/<item_id>` (POST)
**When**: Admin approves item for sale
**Data Captured**:
- target: item (target_id, target_name = item name)
- description: "Item approved"
- value: credits assigned to item
- admin_id, timestamp
**Query**: Filter by action_type = 'approve_item'
**Via**: log_item_approval() function

### reject_item
**Route**: `/reject/<item_id>` (POST)
**When**: Admin rejects item submission
**Data Captured**:
- target: item
- description: "Item rejected"
- reason: rejection_reason from form
- admin_id, timestamp
**Query**: Filter by action_type = 'reject_item'
**Via**: log_item_rejection() function

### update_item_status
**Route**: `/update-status` (POST)
**When**: Admin manually changes item status
**Data Captured**:
- target: item (target_id, target_name = item name)
- description: "Item status updated to {new_status}"
- before_value: old_status
- after_value: new_status
- admin_id, timestamp
**Query**: Filter by action_type = 'update_item_status'

### fix_misclassified_items
**Route**: `/fix-status` (POST)
**When**: Admin runs bulk status fix (pending → approved)
**Data Captured**:
- target_type: system
- description: "Fixed {count} misclassified items"
- after_value: count of items fixed
- admin_id, timestamp
**Query**: Filter by action_type = 'fix_misclassified_items'

---

## Order Management Actions

### update_order_status
**Route**: `/update_order_status/<order_id>` (POST)
**When**: Admin progresses order delivery status
**Data Captured**:
- target: order (target_id, target_name = "Order #{number}")
- description: "Order status updated to {new_status}"
- before_value: old_status (e.g., "Pending")
- after_value: new_status (e.g., "Shipped")
- admin_id, timestamp
**Query**: Filter by action_type = 'update_order_status'
**Status Flow**: Pending → Shipped → Out for Delivery → Delivered

---

## Pickup Station Management Actions

### add_pickup_station
**Route**: `/pickup-stations/add` (POST)
**When**: Admin creates new pickup station
**Data Captured**:
- target: pickup_station (target_id, target_name = station name)
- description: "Pickup station added: {name}, {city}, {state}"
- admin_id, timestamp
**Query**: Filter by action_type = 'add_pickup_station'

### edit_pickup_station
**Route**: `/pickup_stations/edit/<station_id>` (POST)
**When**: Admin updates station details
**Data Captured**:
- target: pickup_station
- description: "Pickup station updated"
- before_value: "{old_name}, {old_address}, {old_city}, {old_state}"
- after_value: "{new_name}, {new_address}, {new_city}, {new_state}"
- admin_id, timestamp
**Query**: Filter by action_type = 'edit_pickup_station'

### delete_pickup_station
**Route**: `/pickup_stations/delete/<station_id>` (POST)
**When**: Admin deletes pickup station
**Data Captured**:
- target: pickup_station (target_id, target_name = station name)
- description: "Pickup station deleted: {name}"
- admin_id, timestamp
**Query**: Filter by action_type = 'delete_pickup_station'

---

## System & Credits Management Actions

### fix_missing_credits
**Route**: `/fix-missing-credits` (POST)
**When**: Admin runs bulk credit restoration
**Data Captured**:
- target_type: system
- description: "Fixed missing credits for {count} items. Total: ₦{amount}"
- after_value: total_credits_added
- admin_id, timestamp
**Query**: Filter by action_type = 'fix_missing_credits'

### maintenance_enabled
**Route**: `/maintenance` (POST with action=enable)
**When**: Admin enables maintenance mode
**Data Captured**:
- target_type: system (target_name = "Platform")
- description: "Maintenance mode enabled"
- reason: maintenance_message
- admin_id, timestamp
**Query**: Filter by action_type = 'maintenance_enabled'

### maintenance_disabled
**Route**: `/maintenance` (POST with action=disable)
**When**: Admin disables maintenance mode
**Data Captured**:
- target_type: system (target_name = "Platform")
- description: "Maintenance mode disabled"
- admin_id, timestamp
**Query**: Filter by action_type = 'maintenance_disabled'

### system_settings_updated
**Route**: `/system_settings` (POST)
**When**: Admin updates feature flags
**Data Captured**:
- target_type: system (target_name = "Platform Settings")
- description: "System settings updated"
- after_value: JSON of new settings
  ```json
  {
    "allow_uploads": true/false,
    "allow_trading": true/false,
    "allow_browsing": true/false
  }
  ```
- admin_id, timestamp
**Query**: Filter by action_type = 'system_settings_updated'

---

## Action Types Quick List

**User-related actions (8)**
- admin_login
- admin_logout
- ban_user
- unban_user
- approve_unban
- reject_unban
- reject_unban_appeal
- delete_user
- edit_user
- export_user_data

**Item-related actions (4)**
- approve_item
- reject_item
- update_item_status
- fix_misclassified_items

**Order-related actions (1)**
- update_order_status

**Station-related actions (3)**
- add_pickup_station
- edit_pickup_station
- delete_pickup_station

**System-related actions (4)**
- fix_missing_credits
- maintenance_enabled
- maintenance_disabled
- system_settings_updated

---

## How to Query Each Action Type

### In Audit Log Web UI
```
Go to /audit-log
Use dropdown: "Action Type"
Select the action you want to see
```

### In Python Code
```python
from models import AuditLog

# Get all approvals
approvals = AuditLog.query.filter_by(action_type='approve_item').all()

# Get all bans
bans = AuditLog.query.filter_by(action_type='ban_user').all()

# Get all deletions
deletions = AuditLog.query.filter_by(action_type='delete_user').all()

# Get all orders status changes
orders = AuditLog.query.filter_by(action_type='update_order_status').all()

# Get specific admin's actions
admin_actions = AuditLog.query.filter_by(admin_id=5).all()

# Get actions in last 7 days
from datetime import datetime, timedelta
recent = AuditLog.query.filter(
    AuditLog.timestamp >= datetime.utcnow() - timedelta(days=7)
).all()
```

---

## Data Retention & Archival

### Recommended Policy
- **Active Storage**: Last 2 years (searchable)
- **Archive**: 2-7 years (backup storage)
- **Purge**: After 7 years (unless legally required)

### Example Archive Query
```python
from datetime import datetime, timedelta
import csv

# Get logs older than 1 year
cutoff = datetime.utcnow() - timedelta(days=365)
old_logs = AuditLog.query.filter(AuditLog.timestamp < cutoff).all()

# Export to CSV
with open('audit_logs_archive.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['ID', 'Admin', 'Action', 'Target', 'Timestamp', 'Description'])
    for log in old_logs:
        writer.writerow([
            log.id, log.admin.username, log.action_type, 
            log.target_name, log.timestamp, log.description
        ])
```

---

## Summary Statistics

| Category | Count | Examples |
|----------|-------|----------|
| Authentication | 2 | login, logout |
| User Management | 8 | ban, unban, delete, etc. |
| Item Management | 4 | approve, reject, status, fix |
| Order Management | 1 | update_order_status |
| Pickup Stations | 3 | add, edit, delete |
| System Management | 4 | maintenance, settings, credits |
| **Total** | **22** | |

---

**Document Version**: 1.0
**Last Updated**: 2024
**Status**: Production Ready
