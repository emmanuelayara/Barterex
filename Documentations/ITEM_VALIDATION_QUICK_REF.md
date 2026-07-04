# Item Validation - Quick Reference

## ✅ What's Fixed

**Security Issue:** Admins could approve items with negative prices or invalid conditions
**Solution:** Added SQLAlchemy validators to Item model

---

## Valid Values

### Price (value field)
- ✅ Any positive number: 100, 5000, 10.50
- ❌ Negative: -5000, -100
- ❌ Zero: 0
- ❌ Text: "5000"
- ✅ NULL: None

### Condition field
✅ **Exactly one of these:**
- Brand New
- Like New
- Lightly Used
- Fairly Used
- Used
- For Parts

❌ Everything else: "Perfect", "Best Deal", "New", etc.

---

## Code Examples

### Creating Valid Items
```python
# ✅ All valid
item = Item(
    name="iPhone 12",
    value=25000,  # Positive number
    condition="Like New",  # From valid list
    category="Electronics",
    user_id=1
)
db.session.add(item)
db.session.commit()
```

### Admin Approval
```python
@admin.route('/approve/<int:item_id>')
def approve_item(item_id):
    item = Item.query.get(item_id)
    
    try:
        item.is_approved = True
        db.session.commit()
        flash("Item approved!", "success")
    except ValueError as e:
        flash(f"Cannot approve: {e}", "error")
        db.session.rollback()
    
    return redirect(url_for('admin.pending_items'))
```

### Error Handling
```python
try:
    item.value = -5000  # ❌ Triggers validator
    db.session.commit()
except ValueError as e:
    print(f"Error: {e}")  # "Price cannot be negative"
```

---

## Admin UI Checklist

When admins submit items or approve them:

- [ ] Price field shows only positive numbers
- [ ] Price input type="number" with min="0.01"
- [ ] Condition uses `<select>` dropdown (not free text)
- [ ] Both fields are required
- [ ] Error messages display clearly if invalid

**Example Form:**
```html
<form method="POST">
    <input type="text" name="name" required>
    <input type="number" name="value" min="0.01" step="0.01" required>
    
    <select name="condition" required>
        <option value="">Select condition...</option>
        <option value="Brand New">Brand New</option>
        <option value="Like New">Like New</option>
        <option value="Lightly Used">Lightly Used</option>
        <option value="Fairly Used">Fairly Used</option>
        <option value="Used">Used</option>
        <option value="For Parts">For Parts</option>
    </select>
    
    <button type="submit">Submit</button>
</form>
```

---

## Testing

Run: `python test_item_validators.py`

All 9 tests should pass:
- ✓ Valid positive price
- ✓ Negative price blocked
- ✓ Zero price blocked
- ✓ Valid condition accepted
- ✓ Invalid condition blocked
- ✓ All 6 valid conditions work
- ✓ Non-numeric price blocked
- ✓ NULL price allowed
- ✓ NULL condition allowed

---

## Files Changed

- **models.py** - Added validators to Item class
- **test_item_validators.py** - Test script (new file)
- **ITEM_VALIDATION_FIX.md** - Full documentation

---

## Common Issues

### "Price must be a number"
You passed text instead of a number
```python
item.value = "5000"  # ❌ Wrong
item.value = 5000    # ✅ Right
```

### "Price cannot be negative"
You passed a negative price
```python
item.value = -5000  # ❌ Wrong
item.value = 5000   # ✅ Right
```

### "Invalid condition"
You used a condition not in the valid list
```python
item.condition = "Perfect"  # ❌ Wrong
item.condition = "Like New" # ✅ Right
```

---

## API Integration

### Form Validation (Frontend)
Use `<select>` dropdown and `type="number" min="0.01"`

### Validation (Backend)
Automatic - validators run when Item object is created or modified

### Error Response
```python
{
    "error": "Invalid condition. Must be one of: Brand New, Fairly Used, ...",
    "status": 400
}
```

---

## Performance Impact

✅ **Minimal** - Validators run only during object creation/modification, not on queries

---

## Status

**✅ ACTIVE** - All validators working and tested
