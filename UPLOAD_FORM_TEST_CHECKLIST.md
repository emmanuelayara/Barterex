# Upload Form Fix - Testing Verification Checklist

## What Was Fixed
1. **FormData CSRF token** - Now explicitly added to the AJAX request
2. **File validation** - Moved from WTForms (broken with MultipleFileField) to route handler
3. **File handling** - Using `request.files` directly instead of unreliable form field binding
4. **Allowed extensions** - Updated to match app.py config (jpg, jpeg, png, gif, webp)

## Before Testing
- [ ] Close any running Flask dev servers
- [ ] Clear browser cache (Ctrl+Shift+Delete)
- [ ] Open browser DevTools (F12) and keep open during test

## Testing Steps

### Step 1: Navigate to Upload Page
- [ ] Start Flask app: `python app.py`
- [ ] Go to http://127.0.0.1:5000/upload
- [ ] Page should load with upload form

### Step 2: Fill Form
- [ ] Item Name: "Test Samsung Phone"
- [ ] Description: "Samsung Galaxy A23 in excellent condition, barely used, original box and charger included"
- [ ] Condition: "Brand New" or "Fairly Used"
- [ ] Category: "Phones & Gadgets"

### Step 3: Select Images
- [ ] Click image upload area
- [ ] Select 1-3 image files (JPG, PNG, GIF, or WEBP)
- [ ] Verify preview shows selected images
- [ ] Note number shown (e.g., "2 / 6 images selected")

### Step 4: Monitor Console
**Open DevTools Console (F12) before clicking Submit**
- [ ] Look for messages:
  - `Form fields: {name: "Test...", ...}`
  - `CSRF token added: <token>`
  - `Number of files to upload: 1`
  - `File 0: {name: "image.jpg", size: ..., type: "image/jpeg"}`

### Step 5: Submit Form
- [ ] Click "Submit Item" button
- [ ] Watch for loading spinner
- [ ] Monitor DevTools Network tab (should see POST request to /upload)

### Step 6: Verify Success
- [ ] Should see one of these:
  - Redirect to `/marketplace`
  - Message: "Item submitted for approval"
  - Redirect happens within 2 seconds

### Step 7: Check Admin Dashboard
- [ ] Login as admin if not already
- [ ] Go to `/admin/approvals`
- [ ] Your item should appear in "Pending Items" list
- [ ] Should show item name, images, and pending status

## Troubleshooting

### If You See "Images only!" Error
**Console logs will show:**
```
2026-01-01 11:XX:XX - routes.items - WARNING - Form validation failed for user Nicanor: {'images': ['Images only!']}
```

**Solutions:**
1. Clear browser cache (Ctrl+Shift+Delete)
2. Hard refresh (Ctrl+Shift+R)
3. Close and reopen browser
4. Check file extensions (must be: jpg, jpeg, png, gif, webp)
5. Try with a different image

### If CSRF Token Not Found
**Console will show:**
```
WARNING: CSRF token not found!
```

**Solution:**
- Clear browser cache
- Check that `{{ form.hidden_tag() }}` is in upload.html
- Check that Flask-WTF is properly configured in app.py

### If Files Are Not Uploading
**Check Flask terminal for error messages:**
```
2026-01-01 11:XX:XX - routes.items - ERROR - Error uploading image: ...
```

**Common causes:**
- File size too large (max 10MB per file)
- Invalid file extension
- Permissions issue in uploads folder
- Insufficient disk space

## Success Criteria

✅ **Minimum Success:** Item appears in `/admin/approvals` as "Pending Approval"

✅ **Full Success:** 
- Item uploads without form validation errors
- Item shows in admin dashboard
- Admin can view, approve, and assign value to item
- Item then appears in marketplace with value

## Files to Check

| File | Change | Line(s) |
|------|--------|---------|
| forms.py | Removed FileAllowed validator | 140-143 |
| upload.html | Add CSRF token explicitly | 1395-1427 |
| routes/items.py | Manual image validation | 105-140, 145-165 |

## Quick Rollback (if needed)
If something goes wrong, the changes are contained to:
- `forms.py` - Remove the MultipleFileField line (one line changed)
- `templates/upload.html` - The FormData creation section
- `routes/items.py` - The image validation and handling logic

All changes are backward compatible with the existing database schema.

---

## Testing Log Template

Date: __________
Tester: __________

| Test | Result | Notes |
|------|--------|-------|
| Form page loads | [ ] Pass [ ] Fail | |
| Images select | [ ] Pass [ ] Fail | |
| Console shows CSRF | [ ] Pass [ ] Fail | |
| Form submits | [ ] Pass [ ] Fail | |
| Item in admin | [ ] Pass [ ] Fail | |
| Admin can approve | [ ] Pass [ ] Fail | |

Overall Result: [ ] PASS [ ] FAIL

Comments:
_____________________________________________________________________________
_____________________________________________________________________________
