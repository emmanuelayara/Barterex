# Database Migration: Add uploaded_by_id Field to Item Table

## Overview
This migration adds a new `uploaded_by_id` field to the Item table to track who originally uploaded each item, separate from who currently owns it (after purchases).

## Problem Fixed
- Previously, when a user purchased an item, the item's `user_id` was changed to the buyer's ID
- This caused the dashboard "Items Listed" count to incorrectly include purchased items
- Now `user_id` tracks current ownership, and `uploaded_by_id` tracks the original uploader

## Changes Made

### 1. Database Schema
- Added `uploaded_by_id` column to `item` table (nullable, references `user.id`)
- Populated existing items: `uploaded_by_id = user_id` (assumes current owner is original uploader)

### 2. Model Changes (models.py)
- Added field: `uploaded_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)`

### 3. Code Updates

#### routes/items.py (Item Creation)
- **Line ~163**: When creating new items, now sets `uploaded_by_id=current_user.id`

#### routes/user.py (Dashboard)
- **Line 52**: Changed dashboard item count from `filter_by(user_id=)` to `filter_by(uploaded_by_id=)`
- **Line 145**: Changed "my items" query from `filter_by(user_id=)` to `filter_by(uploaded_by_id=)`

#### routes/admin.py (Admin Dashboard)
- **Line ~380**: Updated admin user statistics to use `uploaded_by_id` for all item counts:
  - items_uploaded
  - items_approved
  - items_pending
  - items_rejected
  - items_traded

## Running the Migration

### Automatic Method (Python):
```python
cd c:\Users\ayara\Documents\Python\Barterex
python test_migration.py
```

### Manual Method (SQLite):
```sql
-- Check if column exists
PRAGMA table_info(item);

-- Add column if it doesn't exist
ALTER TABLE item ADD COLUMN uploaded_by_id INTEGER;

-- Populate for existing items
UPDATE item SET uploaded_by_id = user_id WHERE uploaded_by_id IS NULL;
```

### Via SQLite CLI:
```bash
sqlite3 c:\Users\ayara\Documents\Python\Barterex\barter.db < migration.sql
```

## Verification

After migration, verify the schema:
```python
import sqlite3
conn = sqlite3.connect('barter.db')
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(item)")
for col in cursor.fetchall():
    print(col)
```

You should see `uploaded_by_id` in the output.

## Impact

- ✓ Dashboard "Items Listed" now only counts uploaded items, not purchased items
- ✓ Admin user view shows accurate item upload statistics
- ✓ User "My Items" page only shows items they uploaded
- ✓ Backwards compatible: existing items mapped to original owner

## Notes
- The `user_id` field still tracks current ownership (important for permissions, orders, etc.)
- New items created after this change will have both `user_id` and `uploaded_by_id` set at creation
- The foreign key constraint is enforced by SQLAlchemy ORM
