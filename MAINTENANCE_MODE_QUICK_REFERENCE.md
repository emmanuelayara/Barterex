# Maintenance Mode Feature - Quick Reference

## What's New

A comprehensive maintenance mode system for platform administrators to temporarily take the platform offline for maintenance, updates, or emergencies while continuing to perform admin tasks.

## Quick Start

### Enable Maintenance Mode
1. Log in to Admin Dashboard
2. Click **🔧 Maintenance Mode** button
3. Enter a maintenance message (e.g., "Database migration in progress. Expected completion: 2 hours")
4. Click **Enable Maintenance Mode**
5. All users see maintenance page; admins continue working

### Disable Maintenance Mode
1. Go to **Maintenance Mode** page
2. Click **Disable Maintenance Mode** button
3. Platform returns to normal operation immediately

### Manage Feature Flags
1. Log in to Admin Dashboard
2. Click **⚙️ System Settings** button
3. Toggle features on/off:
   - 📤 Allow Item Uploads
   - 🤝 Allow Trading & Orders
   - 👀 Allow Browsing Marketplace
4. Click **Save Settings**

## What Users See

### During Maintenance Mode
- 🔧 Professional maintenance page
- Custom admin message
- Auto-refresh every 30 seconds
- Social media links
- Support contact information
- Can still login/logout

### When Feature Disabled
- Specific page showing feature unavailable
- Friendly message with estimated time
- Links to other available features

## New Admin Routes

| Route | Purpose | Access |
|-------|---------|--------|
| `/admin/maintenance` | Enable/disable maintenance mode | Admin only |
| `/admin/system_settings` | Control feature flags | Admin only |

## New Database Table

**Table:** `system_settings`

**Key Fields:**
- `maintenance_mode` - Is maintenance active? (True/False)
- `maintenance_message` - Custom message shown to users
- `maintenance_enabled_by` - Which admin enabled it
- `maintenance_enabled_at` - When it was enabled
- `allow_uploads` - Can users upload items?
- `allow_trading` - Can users trade?
- `allow_browsing` - Can users see marketplace?

## New Templates

| Template | Purpose | Location |
|----------|---------|----------|
| maintenance_page.html | User-facing maintenance page | templates/ |
| marketplace_disabled.html | User-facing feature unavailable page | templates/ |
| maintenance.html | Admin maintenance control page | templates/admin/ |
| system_settings.html | Admin feature flags page | templates/admin/ |

## How It Works

```
User Request
    ↓
Check if Maintenance Mode Enabled?
    ├─ YES → Redirect to maintenance_page.html (HTTP 503)
    └─ NO → Check Feature Flags
             ├─ Upload blocked? → Redirect
             ├─ Trading blocked? → Redirect
             └─ Browsing blocked? → Show disabled page

Admin Request
    ↓
Allow all admin routes regardless of maintenance state
Automatically logged to audit trail
```

## Audit Trail

All maintenance actions are logged:
- Admin username
- Action type (enabled/disabled)
- Timestamp
- Message (if enabled)
- Before/after settings

**View logs:** Admin Dashboard → Audit Log

## File Changes Summary

| File | Change | Type |
|------|--------|------|
| models.py | Added SystemSettings class | New Model |
| routes/admin.py | Added maintenance_mode() and system_settings() routes | New Routes |
| app.py | Added before_request() handler | New Middleware |
| templates/admin/dashboard.html | Added Maintenance & Settings buttons | Updated |
| migration file | system_settings table creation | Database |

## Example Use Cases

### Database Upgrade
```
Enable Maintenance Mode
↓
Message: "Upgrading database to v2.0. Estimated time: 4 hours."
↓
Perform upgrade (only admins working)
↓
Disable Maintenance Mode
↓
Users can access platform
```

### Emergency Maintenance
```
Enable Maintenance Mode immediately
↓
Message: "Critical security patch in progress"
↓
Disable specific features if needed
↓
Admins perform fixes (all logged to audit trail)
↓
Disable maintenance when ready
```

### Feature Testing
```
Enable System Settings
↓
Disable "Allow Trading" feature flag
↓
Test that trading doesn't work for users
↓
Re-enable when satisfied
```

## Security Features

✅ **Admin-Only Access**
- Both maintenance and settings require admin login
- CSRF protection on all forms

✅ **Audit Trail**
- Every change logged with admin name and timestamp
- Before/after values recorded

✅ **Data Protection**
- Settings stored securely in database
- No sensitive data in public messages

✅ **Graceful Degradation**
- Admin functions unaffected
- Users get friendly error pages
- Auto-refresh for users waiting

## Technical Details

**Language:** Python (Flask)
**Database:** SQLite/PostgreSQL/MySQL
**Middleware:** Flask before_request handler
**Templates:** Jinja2 with Bootstrap 5

**Key Classes:**
- `SystemSettings` - Model for storing settings
- `check_maintenance_mode()` - Request handler

**Key Routes:**
- `/admin/maintenance` - Admin maintenance control
- `/admin/system_settings` - Admin feature flags

## Performance Impact

✅ **Minimal Overhead**
- Settings cached in memory
- Single database query per request (if needed)
- Indexed columns for fast lookups
- No impact on normal operation

## Browser Compatibility

✅ **Maintenance Page Works On:**
- Chrome/Chromium
- Firefox
- Safari
- Edge
- Mobile browsers
- Tablets
- Responsive design

## Testing

Test these scenarios:

1. **Enable/Disable Maintenance**
   - Enable → Users see maintenance page
   - Disable → Users return to normal

2. **Custom Messages**
   - Enable with message → Message displays
   - Update message while enabled → Users see new message

3. **Admin Access**
   - During maintenance, admin can still:
     - View dashboard
     - Manage users
     - Approve/reject items
     - View audit logs

4. **Feature Flags**
   - Disable uploads → Users can't upload
   - Disable trading → Trading buttons hidden
   - Disable browsing → Users see disabled page

5. **Audit Logging**
   - Every action appears in audit log
   - Admin names recorded
   - Timestamps accurate

## Troubleshooting

**Issue:** Settings not saving
- **Solution:** Check database connection, verify admin login

**Issue:** Users still see normal page during maintenance
- **Solution:** Hard refresh browser (Ctrl+Shift+R), clear cache

**Issue:** Admin can't access dashboard during maintenance
- **Solution:** Maintenance allows all admin routes, check session

## Future Enhancements

- [ ] Schedule maintenance for future date/time
- [ ] Email notifications to users before maintenance
- [ ] Public status page showing component status
- [ ] Partial maintenance by region/feature
- [ ] Automatic enable/disable by schedule

## References

- [MAINTENANCE_MODE_IMPLEMENTATION.md](MAINTENANCE_MODE_IMPLEMENTATION.md) - Full documentation
- [models.py](models.py) - SystemSettings model definition
- [routes/admin.py](routes/admin.py) - Maintenance routes
- [app.py](app.py) - before_request handler

---

**Status:** 🟢 Production Ready

**Last Updated:** January 2, 2026

**Version:** 1.0
