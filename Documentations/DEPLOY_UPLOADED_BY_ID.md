# Upload By ID Migration - Deployment Guide

## Problem Resolved
✓ Dashboard "Items Listed" now counts **only uploaded items**, not purchased items

## Status: CODE CHANGES ✓ COMPLETE

All necessary code modifications have been made:
- ✓ Model updated with `uploaded_by_id` field
- ✓ Item creation code sets `uploaded_by_id`
- ✓ Dashboard counts updated
- ✓ Admin views updated
- ✓ User items page updated

## Database Migration - Two Paths

### Path 1: Fresh Database (Recommended for new installations)

If your database is empty or you're just starting:

1. **Delete the existing empty database**
   ```bash
   rm barter.db  # or delete via File Explorer
   ```

2. **Run your Flask app normally**
   ```bash
   python app.py
   ```

The app will automatically create all tables including the `uploaded_by_id` column on first run.

### Path 2: Existing Database with Data

If you have existing data and the Item table already exists:

1. **Backup your database first**
   ```bash
   cp barter.db barter.db.backup
   ```

2. **Run the migration script**
   ```bash
   python migrate_direct.py
   ```

   The script will:
   - Check if the Item table exists
   - Add `uploaded_by_id` column if needed
   - Populate existing items (mapping original owner as uploader)

## Implementation Details

### Code Changes Made

**[models.py](models.py) - Line 286**
```python
uploaded_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
```

**[routes/items.py](routes/items.py) - Line ~163**
```python
new_item = Item(
    name=form.name.data,
    description=form.description.data,
    ...
    uploaded_by_id=current_user.id,  # NEW
    ...
)
```

**[routes/user.py](routes/user.py)**
- Line 52: Dashboard item count changed from `filter_by(user_id=)` to `filter_by(uploaded_by_id=)`
- Line 145: My Items query changed from `filter_by(user_id=)` to `filter_by(uploaded_by_id=)`

**[routes/admin.py](routes/admin.py) - Lines 380-384**
- Updated all item statistics to use `uploaded_by_id` instead of `user_id`:
  - items_uploaded
  - items_approved
  - items_pending
  - items_rejected
  - items_traded

## Verification After Deployment

```python
import sqlite3

# Connect to database
conn = sqlite3.connect('barter.db')
cursor = conn.cursor()

# Verify column exists
cursor.execute("PRAGMA table_info(Item)")
columns = {row[1] for row in cursor.fetchall()}
print("✓ uploaded_by_id exists" if 'uploaded_by_id' in columns else "✗ Column missing")

# Count items with uploader info
cursor.execute("SELECT COUNT(*) FROM Item WHERE uploaded_by_id IS NOT NULL")
print(f"Items with uploader info: {cursor.fetchone()[0]}")

conn.close()
```

## Testing the Fix

1. **As a User:**
   - Go to Dashboard
   - Check "Items Listed" count
   - It should now show ONLY items you uploaded
   - Items you purchased should NOT be counted

2. **In Admin:**
   - Go to Admin > Users
   - View a user's statistics
   - "Items Uploaded" shows accurate count of uploaded items only

3. **In My Items:**
   - Go to Settings > Your Account > Your Items
   - Should only show items you uploaded, not purchased

## Rollback (if needed)

If issues arise, you can rollback by:

1. **Restore the backup database**
   ```bash
   cp barter.db.backup barter.db
   ```

2. **Revert code changes** (git)
   ```bash
   git checkout -- routes/items.py routes/user.py routes/admin.py models.py
   ```

## Notes

- The migration is **safe** - it doesn't delete any data
- Existing items are mapped assuming the current owner is the uploader
- New items will have both `user_id` (current owner) and `uploaded_by_id` (original uploader) set correctly
- The `user_id` field remains important for purchase tracking and permissions

## Support

If the migration fails:
1. Check that Flask app has been run at least once
2. Ensure database file `barter.db` exists
3. Verify no other processes are using the database
4. Check file permissions in the directory

For the database-not-initialized error, run the Flask app first to bootstrap all tables, then run the migration script.
