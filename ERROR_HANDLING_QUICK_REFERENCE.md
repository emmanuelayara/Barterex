# Error Handling & Messages - Quick Reference

## 🎯 Quick Overview

Error handling system now provides:
- ✅ Friendly error pages (404, 500, 403, 400)
- ✅ Real-time form validation with hints
- ✅ Recovery suggestions in error messages
- ✅ Consistent, user-friendly language

---

## 📍 Error Pages

### Error 404 - Not Found
```
What you see: 🔍 404 - Page Not Found
Recovery options:
  • Browse Marketplace
  • Go Home  
  • My Dashboard / Sign In
```

### Error 500 - Server Error
```
What you see: ⚙️ 500 - Internal Server Error
Recovery options:
  • Refresh the page
  • Clear cache and try again
  • Try different browser
  • Contact support
```

### Error 403 - Access Denied
```
What you see: 🔒 403 - Access Denied
Recovery options:
  • Log in with correct account
  • Check account restrictions
  • Contact support
```

### Error 400 - Bad Request
```
What you see: ⚠️ 400 - Bad Request
Recovery options:
  • Check all fields are filled
  • Verify input format
  • Try submitting again
  • Contact support
```

---

## 📝 Form Validation

### Login Form
```
Username Field:
  Hint: "Min. 3 characters, alphanumeric only"
  Valid: Green border + green background
  Invalid: Red border + red background
  Error: "Username must be at least 3 characters"

Password Field:
  Hint: "Your password for account security"
  Valid: Green border
  Invalid: Red border with message
  Error: "Password must be at least 6 characters"
```

### Register Form
```
Email:
  Hint: "We'll never share your email"
  Format example: name@example.com
  
Username:
  Hint: "3-20 characters, letters and numbers"
  
Password:
  Hint: "Min. 8 characters with uppercase, lowercase, and number"
  Shows strength bar (Weak → Good → Strong)
  
Confirm Password:
  Hint: "Must match your password exactly"
```

---

## 🚨 Common Error Messages

| Scenario | Message | Action |
|----------|---------|--------|
| Session Expired | "Your session has expired" | Log in again |
| Insufficient Credits | "Not enough credits" | Earn more or contact support |
| Item Not Found | "Item no longer available" | Browse similar items |
| Duplicate Username | "Username already taken" | Choose different username |
| Invalid Email | "Invalid email address" | Use format: name@example.com |
| Weak Password | "Password too weak" | Use uppercase, lowercase, number |
| File Too Large | "File is too large" | Max 2MB, compress image |
| Payment Failed | "Payment could not process" | Check info and retry |

---

## 🎨 Visual Indicators

### Field States
```
VALID (✓)
  Border: Green (#10b981)
  Background: Light green (#f0fdf4)
  Message: Green checkmark

INVALID (✕)
  Border: Red (#ef4444)
  Background: Light red (#fef2f2)
  Message: Red X with guidance

FOCUS
  Border: Orange (#ff7a00)
  Hint: Shows field requirements

EMPTY
  Border: Light gray (#e2e8f0)
  Hint: Hidden
```

---

## 💻 For Developers

### Using Error Messages in Code

```python
# Import at top
from error_messages import (
    format_error_toast,
    get_error_message,
    format_error_page
)

# In route handler
if not item:
    msg = format_error_toast('ITEM_NOT_FOUND')
    flash(msg, 'danger')
    return redirect(url_for('marketplace.marketplace'))

# Get full error info
error_info = get_error_message('INSUFFICIENT_CREDITS')
# Returns dict with message, action, recovery_link
```

### Common Error Keys
```
AUTH ERRORS:
  - SESSION_EXPIRED
  - UNAUTHORIZED_ACCESS
  - ACCOUNT_BANNED

ITEM ERRORS:
  - ITEM_NOT_FOUND
  - ITEM_OUT_OF_STOCK
  - ITEM_ALREADY_IN_CART

CREDIT ERRORS:
  - INSUFFICIENT_CREDITS
  - PAYMENT_FAILED

FORM ERRORS:
  - DUPLICATE_USERNAME
  - DUPLICATE_EMAIL
  - INVALID_EMAIL
  - PASSWORD_TOO_WEAK
  - PASSWORD_MISMATCH

FILE ERRORS:
  - FILE_TOO_LARGE
  - INVALID_FILE_TYPE
  - NO_IMAGE_SELECTED

ORDER ERRORS:
  - ORDER_NOT_FOUND
  - ORDER_ALREADY_COMPLETED
```

### Adding New Error Message

```python
# In error_messages.py, ErrorMessages class:

NEW_ERROR = {
    'message': 'User-friendly description',
    'action': 'What the user should do',
    'recovery_link': 'route.endpoint',
    'recovery_label': 'Button Text',
    'suggestion': 'Optional hint'
}

# Then use:
msg = format_error_toast('NEW_ERROR')
```

---

## 📱 Mobile Experience

- Error messages stack vertically
- Buttons full-width on mobile
- Touch-friendly sizing (48px+ height)
- Responsive font sizes
- Icons visible and accessible
- Help text centered and readable

---

## ✨ Features

### Real-Time Validation
- As you type, fields validate
- Green checkmark = valid
- Red X = invalid with specific error
- Hints show on focus
- Errors hide when corrected

### Recovery Suggestions
Every error includes:
1. What happened (clear message)
2. Why it happened (context)
3. What to do next (action)
4. Where to go (link)

### Consistent Experience
- Same styling everywhere
- Familiar color scheme
- Predictable error messages
- Clear navigation options

---

## 🐛 Debugging

### To Test Error Pages
```
Visit: http://localhost/nonexistent    # 404
Visit: /admin (when not admin)         # 403
Try form with bad data                 # 400/422
Simulate server error                  # 500
```

### To Test Form Validation
```
Type in login username (real-time feedback)
Type in password (real-time feedback)
Tab between fields (on blur validation)
Submit invalid form (shows errors)
```

### Browser DevTools
```
Check console for warnings
Check Network tab for requests
Check Application → Cookies for session
```

---

## 🔐 Security Notes

- CSRF tokens properly validated (message if expired)
- File upload size limits enforced (2MB max)
- Input sanitization warnings shown
- Password strength feedback helps users
- Server-side validation always enforced

---

## 📊 Error Tracking

All errors logged with:
- Timestamp
- Error type/code
- User info
- Request details
- Full traceback (server logs only)

Check `logs/` directory for details.

---

**Last Updated**: December 7, 2025  
**Version**: 1.0 - Initial Implementation
