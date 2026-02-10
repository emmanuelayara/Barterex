# Wishlist Feature - Quick Start for Developers

## ⚡ 30-Second Summary

Users can create wishlists of items/categories they want. When those items are approved in the marketplace, they're automatically notified via email + in-app notification.

**Status**: ✅ Complete & Ready for UI Development

---

## 🎯 For Frontend Developers

### Dashboard Integration

Add this section to the user dashboard:

```html
<section class="wishlist-section">
  <h2>My Wishlist</h2>
  <button class="btn-primary" onclick="openAddWishlistModal()">+ Add to Wishlist</button>
  <div id="wishlist-list"></div>
</section>
```

### API Endpoints for UI

**Get User's Wishlist**:
```javascript
fetch('/wishlist/view?page=1&per_page=20')
  .then(r => r.json())
  .then(data => {
    console.log(data.wishlists);  // Array of wishlist items
    console.log(data.pagination);  // Page info
  });
```

**Add Item to Wishlist**:
```javascript
fetch('/wishlist/add', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    item_name: 'iPhone 15 Pro',  // OR
    category: 'Electronics',      // use one or the other
    search_type: 'item',          // 'item' or 'category'
    notify_via_email: true,
    notify_via_app: true
  })
})
.then(r => r.json())
.then(data => console.log(data.wishlist_id));
```

**Remove from Wishlist**:
```javascript
fetch(`/wishlist/remove/42`, { method: 'POST' })
  .then(r => r.json())
  .then(data => console.log(data));
```

**Pause/Resume**:
```javascript
fetch(`/wishlist/pause/42`, { method: 'POST' });  // Pause
fetch(`/wishlist/resume/42`, { method: 'POST' });  // Resume
```

**View Matches for Wishlist**:
```javascript
fetch('/wishlist/matches/42?page=1')
  .then(r => r.json())
  .then(data => {
    console.log(data.wishlist);   // The wishlist item
    console.log(data.matches);    // Items that matched
  });
```

### Sample UI Components

**Add Wishlist Modal** (HTML template):
```html
<div class="modal" id="add-wishlist-modal">
  <h3>Add to Wishlist</h3>
  <form id="add-wishlist-form">
    <label>
      <input type="radio" name="type" value="item" checked> Search for Item
      <input type="text" name="item_name" placeholder="e.g., iPhone 15 Pro">
    </label>
    <label>
      <input type="radio" name="type" value="category"> Browse Category
      <select name="category">
        <option>Electronics</option>
        <option>Furniture</option>
        <option>Books</option>
      </select>
    </label>
    <label>
      <input type="checkbox" name="email" checked> Email me when found
    </label>
    <label>
      <input type="checkbox" name="app" checked> Show dashboard notification
    </label>
    <button type="submit">Add to Wishlist</button>
  </form>
</div>
```

**Wishlist Items List** (with actions):
```html
<div class="wishlist-items">
  <div class="wishlist-item" data-id="42">
    <div class="item-info">
      <strong>iPhone 15 Pro</strong>
      <span class="badge">0 matches</span>
    </div>
    <div class="item-actions">
      <button class="btn-pause" onclick="pauseWishlist(42)">Pause</button>
      <button class="btn-browse" onclick="viewMatches(42)">Browse Matches</button>
      <button class="btn-remove" onclick="removeWishlist(42)">Remove</button>
    </div>
  </div>
</div>
```

---

## 🔧 For Backend/Full-Stack Developers

### Quick Deploy

```bash
# 1. Verify migrations applied
flask db current
# Should show: 119211f50d0a (head)

# 2. If not, apply migrations
flask db upgrade

# 3. Test import
python -c "from app import app; print('✓ Ready')"

# 4. Start app
flask run
```

### Key Files to Know

| File | Purpose | Edit? |
|------|---------|-------|
| `routes/wishlist.py` | API endpoints | ❌ No |
| `services/wishlist_service.py` | Matching logic | 🟡 Only if tweaking |
| `models.py` | Wishlist models | ❌ No |
| `app.py` | Blueprint registration | ❌ No |

### Customization Points

**1. Change Similarity Threshold** (70% → something else):

In `services/wishlist_service.py`:
```python
SIMILARITY_THRESHOLD = 0.70  # Line 8, change this number
```
- 0.50 = Very loose matching (more false positives)
- 0.70 = Current (recommended)
- 0.90 = Very strict (might miss matches)

**2. Change Page Size** (20 items → different):

In `routes/wishlist.py`:
```python
per_page = request.args.get('per_page', 20, type=int)  # Line 65, change 20
```

**3. Add More Search Types**:

In `routes/wishlist.py` validate function (line 20):
```python
if search_type not in ['item', 'category', 'brand']:  # Add 'brand'
    return error(400, 'Invalid search_type')
```

Then in `services/wishlist_service.py` matching function.

**4. Disable Email Notifications**:

In `routes/admin.py` (line ~915):
```python
# Comment out to disable
# send_wishlist_notification(wishlist, item, user)
```

---

## 🧪 Quick Test

**Test in Flask Shell**:
```bash
flask shell
```

```python
from app import db
from models import User, Wishlist, WishlistMatch, Item

# Get test user
user = User.query.first()

# Add wishlist item
w = Wishlist(
    user_id=user.id,
    item_name='iPhone 15 Pro',
    search_type='item'
)
db.session.add(w)
db.session.commit()

# View it
wishlists = Wishlist.query.filter_by(user_id=user.id).all()
print(f"Found {len(wishlists)} wishlist items")

# Clean up
db.session.delete(w)
db.session.commit()
```

---

## 📊 Feature Checklist

- [x] Database models created
- [x] All 6 API endpoints working
- [x] Admin auto-trigger on approval
- [x] Email notifications
- [x] In-app notifications
- [x] Matching algorithm (70% similarity)
- [x] Pagination support
- [x] Authorization checks
- [ ] UI dashboard component (Next - Frontend)
- [ ] Category autocomplete (Optional)
- [ ] Email template styling (Optional)

---

## 🎁 Bonus Features (Future)

**Easy Adds** (~1-2 hours each):
- Sort wishlist by date added / match count
- Export wishlist to CSV
- Share wishlist link with friends
- Favorite certain wishlists
- Bulk add multiple items

**Medium** (~4-6 hours each):
- AI-powered category suggestions
- Price tracking (show price drops)
- Daily digest email instead of individual emails
- Search history

**Complex** (~8+ hours each):
- ML-based matching (beyond similarity score)
- Product recommendations
- Trending items in user's wishlist categories

---

## 🚨 Common Gotchas

**1. Forgot to Apply Migrations**
- Error: "no such table: wishlist"
- Fix: Run `flask db upgrade`

**2. Email Not Sending**
- Check Flask-Mail configuration in `app.py`
- Verify `notify_via_email=True` on wishlist

**3. No Matches Found**
- Wishlist might be paused (`is_active=False`)
- Item similarity might be <70%
- Test with `calculate_similarity('text1', 'text2')`

**4. Circular Import in Tests**
- Wrong: `from services.wishlist_service import ...`
- Right: Inside Flask app context
  ```python
  from app import app
  with app.app_context():
      from services.wishlist_service import ...
  ```

---

## 📞 Quick Reference

**All Wishlist Routes**:
```
POST   /wishlist/add                    - Add item
GET    /wishlist/view                   - List wishlist
POST   /wishlist/remove/<id>            - Delete item
POST   /wishlist/pause/<id>             - Disable notifications
POST   /wishlist/resume/<id>            - Enable notifications
GET    /wishlist/matches/<id>           - View matched items
```

**Success Response Format**:
```json
{
  "success": true,
  "message": "...",
  "data": { }
}
```

**Error Response Format**:
```json
{
  "success": false,
  "error": "Error message",
  "error_code": "ERROR_TYPE"
}
```

---

## 🎯 Next Steps

**For Frontend Dev**:
1. Add wishlist section to dashboard
2. Implement Add modal
3. Implement wishlist item list with controls
4. Implement match browser
5. Add real-time notifications

**For Backend Dev**:
1. Monitor logs for issues
2. Adjust similarity threshold if needed
3. Add category autocomplete API (optional)
4. Performance monitoring (if needed)

**For QA/Testers**:
1. Test all 6 endpoints
2. Test dashboard flow
3. Test email notifications
4. Test authorization (can't access others' wishlists)
5. Test pagination with >100 items

---

**Everything is ready. Happy coding! ✨**
