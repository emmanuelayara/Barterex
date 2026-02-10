# Wishlist API - Quick Reference

## Base URL
```
http://localhost:5000/wishlist
```

## Authentication
All endpoints require login. Include session cookie or auth token.

---

## Endpoints

### 1. Add to Wishlist
**POST** `/wishlist/add`

Create a new wishlist entry for an item or category.

**Request Body:**
```json
{
  "item_name": "iPhone 15 Pro",
  "category": null,
  "search_type": "item",
  "notify_via_email": true,
  "notify_via_app": true
}
```

Or for category:
```json
{
  "item_name": null,
  "category": "Electronics",
  "search_type": "category",
  "notify_via_email": true,
  "notify_via_app": true
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Item added to wishlist",
  "wishlist_id": 42
}
```

**Errors:**
- `400` - Missing or invalid field
- `400` - Both item_name and category provided
- `400` - Duplicate wishlist entry
- `401` - Not logged in

---

### 2. View Wishlist
**GET** `/wishlist/view`

Get user's wishlist items with pagination.

**Query Parameters:**
- `page` (optional, default=1): Page number
- `per_page` (optional, default=20): Items per page

**Example:**
```
GET /wishlist/view?page=1&per_page=20
```

**Response (200 OK):**
```json
{
  "success": true,
  "wishlists": [
    {
      "id": 42,
      "item_name": "iPhone 15 Pro",
      "category": null,
      "search_type": "item",
      "is_active": true,
      "notify_via_email": true,
      "notify_via_app": true,
      "created_at": "2024-01-15T10:30:00",
      "last_notified_at": null,
      "notification_count": 0,
      "match_count": 0
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total_pages": 1,
    "total_items": 1
  }
}
```

**Errors:**
- `401` - Not logged in

---

### 3. Remove from Wishlist
**POST** `/wishlist/remove/<int:wishlist_id>`

Delete a wishlist entry and its matches.

**URL Parameters:**
- `wishlist_id`: ID of wishlist item to remove

**Example:**
```
POST /wishlist/remove/42
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Item removed from wishlist"
}
```

**Errors:**
- `404` - Wishlist not found
- `403` - Not authorized (not owner)
- `401` - Not logged in

---

### 4. Pause Wishlist
**POST** `/wishlist/pause/<int:wishlist_id>`

Disable notifications for a wishlist item (keeps it saved).

**URL Parameters:**
- `wishlist_id`: ID of wishlist item to pause

**Example:**
```
POST /wishlist/pause/42
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Wishlist paused"
}
```

**Errors:**
- `404` - Wishlist not found
- `403` - Not authorized (not owner)
- `401` - Not logged in

---

### 5. Resume Wishlist
**POST** `/wishlist/resume/<int:wishlist_id>`

Re-enable notifications for a paused wishlist item.

**URL Parameters:**
- `wishlist_id`: ID of wishlist item to resume

**Example:**
```
POST /wishlist/resume/42
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Wishlist resumed"
}
```

**Errors:**
- `404` - Wishlist not found
- `403` - Not authorized (not owner)
- `401` - Not logged in

---

### 6. View Matched Items
**GET** `/wishlist/matches/<int:wishlist_id>`

Get all items that matched this wishlist entry.

**URL Parameters:**
- `wishlist_id`: ID of wishlist entry

**Query Parameters:**
- `page` (optional, default=1): Page number
- `per_page` (optional, default=20): Items per page

**Example:**
```
GET /wishlist/matches/42?page=1
```

**Response (200 OK):**
```json
{
  "success": true,
  "wishlist": {
    "id": 42,
    "item_name": "iPhone 15 Pro",
    "search_type": "item"
  },
  "matches": [
    {
      "id": 1,
      "item_id": 123,
      "item_name": "iPhone 15 Pro 256GB",
      "item_price": 999.99,
      "notification_sent_at": "2024-01-15T10:30:00",
      "email_sent": true,
      "app_notification_sent": true,
      "available": true
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total_pages": 1,
    "total_items": 1
  }
}
```

**Errors:**
- `404` - Wishlist not found
- `403` - Not authorized (not owner)
- `401` - Not logged in

---

## Common Response Codes

| Code | Meaning |
|------|---------|
| 200 | Successful request |
| 400 | Bad request (invalid data) |
| 401 | Not authenticated |
| 403 | Not authorized (not owner) |
| 404 | Wishlist not found |
| 500 | Server error |

---

## Matching Logic

**For Item Searches:**
- Uses 70% string similarity threshold
- Compares against all active items in marketplace
- Case-insensitive matching
- Partial match (substring) doesn't auto-match

**For Category Searches:**
- Requires exact category match
- Case-insensitive comparison
- Matches all items in that category

---

## Notifications

**When Item Matches:**
1. **In-App Notification**: Instantly created in Notification table
   - User sees on dashboard
   - Can be marked as read/unread

2. **Email Notification**: Sent immediately
   - HTML email with item details
   - Link to item in marketplace
   - User preference respected (notify_via_email flag)

**Tracking:**
- WishlistMatch record created
- `notification_sent_at` timestamp recorded
- `email_sent` and `app_notification_sent` flags set
- `notification_count` incremented on Wishlist

---

## Examples

### JavaScript (Fetch API)

**Add to Wishlist:**
```javascript
const response = await fetch('/wishlist/add', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    item_name: 'iPhone 15 Pro',
    category: null,
    search_type: 'item',
    notify_via_email: true,
    notify_via_app: true
  })
});
const data = await response.json();
console.log(data);
```

**View Wishlist:**
```javascript
const response = await fetch('/wishlist/view?page=1&per_page=20');
const data = await response.json();
console.log(data.wishlists);
```

**Remove from Wishlist:**
```javascript
const response = await fetch('/wishlist/remove/42', {
  method: 'POST'
});
const data = await response.json();
console.log(data);
```

---

## Error Handling

All error responses follow this format:

```json
{
  "success": false,
  "error": "Error message here",
  "error_code": "ERROR_TYPE"
}
```

**Common Error Codes:**
- `WISHLIST_NOT_FOUND` - Item doesn't exist or already deleted
- `NOT_AUTHORIZED` - User doesn't own this wishlist
- `INVALID_INPUT` - Validation failed
- `DUPLICATE_ENTRY` - Wishlist already exists
- `NOT_AUTHENTICATED` - Must be logged in

---

## Rate Limiting

Subject to application's global rate limiting (if enabled).
Default: No specific rate limit on wishlist endpoints.

---

## Performance Notes

- **Pagination**: Default 20 items per page (recommended max: 100)
- **Matching**: Happens only on item approval (background-friendly)
- **Email**: Sent asynchronously when possible
- **Database**: Indexes on `user_id`, `is_active`, `created_at`

---

## Status Codes by Feature

**Item Addition:**
- ✅ Supports duplicate checking
- ✅ Validates input
- ✅ Tracks notification preferences

**Item Removal:**
- ✅ Cascades to WishlistMatch records
- ✅ Soft delete not used (hard delete)

**Pause/Resume:**
- ✅ Keeps history intact
- ✅ Toggles `is_active` flag only

**Match Retrieval:**
- ✅ Paginated for performance
- ✅ Shows notification status
- ✅ Links to original items

---

## Integration Points

**Admin Item Approval Flow:**
When admin approves item:
1. Admin UI calls standard approval endpoint
2. On success, system automatically:
   - Finds matching wishlists (similarity >70% OR category match)
   - Creates WishlistMatch records
   - Sends notifications to users
   - Updates tracking fields

**No manual integration needed** - happens automatically post-approval.
