# Error Handling & Logging Guide

## Overview

Barterex now has comprehensive error handling and logging throughout the application. This includes:

- ✅ Structured logging with file and console output
- ✅ Custom exception classes for specific error scenarios
- ✅ Error handlers at route and application levels
- ✅ Request/response logging
- ✅ Database operation error recovery
- ✅ Input validation utilities
- ✅ Retry logic for fault-tolerant operations

## Architecture

### 1. Logging System (`logger_config.py`)

Provides structured logging with multiple output streams:

```python
from logger_config import setup_logger

# Get logger for a module
logger = setup_logger(__name__)

# Log messages
logger.info("User registered successfully")
logger.warning("Validation failed for field: email")
logger.error("Database connection failed", exc_info=True)
```

**Features:**
- Rotating file handlers (max 10MB per file, 10 backups)
- Console output for development
- Structured format with timestamps and line numbers
- Automatic log directory creation

**Log Location:** `logs/barterex_YYYYMMDD.log`

### 2. Custom Exceptions (`exceptions.py`)

Type-safe exception hierarchy for specific error scenarios:

```python
from exceptions import (
    ValidationError,
    AuthenticationError,
    ResourceNotFoundError,
    DatabaseError,
    InsufficientCreditsError,
    ItemNotAvailableError
)

# Usage examples
if not email:
    raise ValidationError("Email is required", field="email")

if not user:
    raise ResourceNotFoundError("User", user_id)

if user.credits < amount:
    raise InsufficientCreditsError(amount, user.credits)
```

**Exception Classes:**
- `ValidationError` (400) - Input validation failures
- `AuthenticationError` (401) - Auth failures
- `AuthorizationError` (403) - Permission denied
- `ResourceNotFoundError` (404) - Resource not found
- `DatabaseError` (500) - Database operation failures
- `FileUploadError` (400) - File upload issues
- `InsufficientCreditsError` (400) - Insufficient credits
- `ItemNotAvailableError` (400) - Item not available
- `UserBannedError` (403) - User banned
- `EmailSendError` (500) - Email sending failures

### 3. Error Handlers (`error_handlers.py`)

Decorators and utilities for automatic error handling:

#### Route Error Handler
```python
from error_handlers import handle_errors

@bp.route('/user/items')
@login_required
@handle_errors
def user_items():
    # Exceptions automatically caught and converted to user-friendly messages
    items = Item.query.filter_by(user_id=current_user.id).all()
    return render_template('user_items.html', items=items)
```

#### API Error Handler
```python
from error_handlers import handle_api_errors

@bp.route('/api/items/<int:item_id>', methods=['GET'])
@handle_api_errors
def get_item_api(item_id):
    # Returns JSON error responses instead of HTML
    item = Item.query.get_or_404(item_id)
    return jsonify(item.to_dict())
```

#### Safe Database Operations
```python
from error_handlers import safe_database_operation
from app import db

@bp.route('/item/<int:item_id>/approve', methods=['POST'])
@safe_database_operation("approve_item")
def approve_item(item_id):
    # Automatic commit/rollback on success/failure
    item = Item.query.get_or_404(item_id)
    item.status = 'approved'
    return redirect(url_for('admin.admin_dashboard'))
```

#### Automatic Retry with Backoff
```python
from error_handlers import retry_operation

@retry_operation(max_retries=3, delay=1, backoff=2)
def send_email(recipient, subject, body):
    # Retries up to 3 times with 1s, 2s, 4s delays
    mail.send(Message(subject=subject, recipients=[recipient], body=body))
```

#### Error Context Manager
```python
from error_handlers import ErrorContext
from logger_config import setup_logger

logger = setup_logger(__name__)

with ErrorContext("process_order", logger) as ctx:
    # Logs entry/exit and handles exceptions
    order = Order.query.get(order_id)
    order.status = 'processing'
    db.session.commit()
```

### 4. Global Error Handlers (in `app.py`)

Flask error handlers for application-level error management:

```python
@app.errorhandler(404)
def not_found(error):
    """Handle 404 Not Found errors."""
    logger.info(f"Resource not found: {request.path}")
    flash('The page you are looking for does not exist.', 'warning')
    return render_template('error.html', error_code=404, ...), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 Internal Server errors."""
    logger.error(f"Internal server error: {error}", exc_info=True)
    db.session.rollback()
    flash('An internal server error occurred.', 'danger')
    return render_template('error.html', error_code=500, ...), 500

@app.before_request
def log_request():
    """Log incoming requests."""
    logger.debug(f"Request: {request.method} {request.path}")

@app.after_request
def log_response(response):
    """Log outgoing responses."""
    logger.debug(f"Response: {response.status_code}")
    return response
```

## Usage Examples

### Example 1: Safe User Registration

```python
from logger_config import setup_logger
from exceptions import ValidationError, DatabaseError
from error_handlers import handle_errors, safe_database_operation

logger = setup_logger(__name__)

@auth_bp.route('/register', methods=['POST'])
@handle_errors
def register():
    try:
        # Validate input
        if not request.form.get('email'):
            raise ValidationError("Email is required", field="email")
        
        # Create user
        user = User(
            username=request.form['username'],
            email=request.form['email'],
            password_hash=generate_password_hash(request.form['password'])
        )
        
        db.session.add(user)
        db.session.commit()
        
        logger.info(f"New user registered: {user.username}")
        flash("Registration successful", 'success')
        
    except ValidationError as e:
        logger.warning(f"Validation failed: {e.message}")
        raise
    except Exception as e:
        logger.error(f"Registration error: {str(e)}", exc_info=True)
        db.session.rollback()
        raise DatabaseError("Failed to create user account")
```

### Example 2: Item Approval with Logging

```python
from error_handlers import safe_database_operation

@admin_bp.route('/item/<int:item_id>/approve', methods=['POST'])
@admin_login_required
@safe_database_operation("approve_item")
def approve_item(item_id):
    item = Item.query.get_or_404(item_id)
    
    try:
        value = float(request.form['value'])
        item.value = value
        item.status = 'approved'
        item.user.credits += int(value)
        
        logger.info(f"Item approved: {item.id} by admin {session.get('admin_id')}")
        flash(f"Item '{item.name}' approved", 'success')
        
    except ValueError:
        logger.warning(f"Invalid item value provided: {request.form.get('value')}")
        raise ValidationError("Invalid item value")
    
    return redirect(url_for('admin.admin_dashboard'))
```

### Example 3: Resilient Email Sending

```python
from error_handlers import retry_operation

@retry_operation(max_retries=3, delay=2, backoff=2)
def send_order_confirmation(user_email, order_id):
    """
    Send order confirmation with retry logic.
    Retries up to 3 times: wait 2s, 4s, 8s between attempts
    """
    try:
        message = Message(
            subject="Order Confirmation",
            recipients=[user_email],
            html=render_template('emails/order_confirmation.html', order_id=order_id)
        )
        mail.send(message)
        logger.info(f"Order confirmation email sent to {user_email}")
    except Exception as e:
        logger.warning(f"Attempt to send email failed: {str(e)}")
        raise
```

## Best Practices

### 1. Always Log Important Events
```python
# ✅ Good
logger.info(f"User {user.username} logged in from {request.remote_addr}")

# ❌ Avoid
print("User logged in")  # Won't appear in logs
```

### 2. Log Errors with Context
```python
# ✅ Good
logger.error(
    f"Failed to process order {order_id} for user {user_id}: {str(e)}",
    exc_info=True
)

# ❌ Avoid
logger.error("An error occurred")  # No context
```

### 3. Use Specific Exception Classes
```python
# ✅ Good
if not item:
    raise ResourceNotFoundError("Item", item_id)

# ❌ Avoid
if not item:
    raise Exception("Item not found")  # Generic exception
```

### 4. Use Decorators for Error Handling
```python
# ✅ Good
@handle_errors
def user_items():
    # Exceptions automatically handled
    return render_template(...)

# ❌ Avoid
def user_items():
    try:
        return render_template(...)
    except Exception:
        pass  # Silent failures
```

### 5. Validate Input Early
```python
# ✅ Good
@auth_bp.route('/register', methods=['POST'])
@handle_errors
def register():
    if not request.form.get('email'):
        raise ValidationError("Email is required")
    # ... rest of code

# ❌ Avoid
def register():
    # Try to use potentially None value
    email = request.form.get('email')
    # ... code that may crash
```

## Log Levels

| Level | Usage | Example |
|-------|-------|---------|
| DEBUG | Detailed diagnostic info | Request/response logging, variable values |
| INFO | Significant events | User login, item approval, successful operations |
| WARNING | Warning signs | Failed login attempt, validation failure, retry |
| ERROR | Error events | Database errors, email failures, exceptions |
| CRITICAL | Severe errors | System unavailable, configuration errors |

```python
logger.debug("Processing request for item ID: 123")
logger.info("Order #456 created successfully")
logger.warning("Failed login attempt from IP: 192.168.1.1")
logger.error("Database connection failed", exc_info=True)
logger.critical("SMTP server unreachable")
```

## Monitoring & Debugging

### View Logs in Real-Time
```bash
# Linux/Mac
tail -f logs/barterex_*.log

# Windows PowerShell
Get-Content logs/barterex_*.log -Tail 20 -Wait
```

### Search Logs
```bash
# Find all errors
grep "ERROR" logs/barterex_*.log

# Find specific user's activities
grep "user@example.com" logs/barterex_*.log

# Find failed operations
grep "FAILED\|ERROR\|exception" logs/barterex_*.log
```

### Log Rotation
- Logs are automatically rotated at 10MB
- 10 backup files are kept
- Old files are named: `barterex_20250101.log.1`, `.log.2`, etc.

## Testing Error Handling

```python
# Test exception handling
from exceptions import ValidationError

def test_validation_error():
    with pytest.raises(ValidationError):
        raise ValidationError("Test error", field="test_field")

# Test logging
def test_logging(caplog):
    logger.info("Test message")
    assert "Test message" in caplog.text
```

## Performance Considerations

- Logging to file has minimal performance impact
- Debug logging is disabled in production
- Request/response logging adds ~1-2ms per request
- Rotating file handlers prevent unlimited disk growth

## Security Considerations

- Never log sensitive data (passwords, credit card numbers, tokens)
- Sanitize user input before logging
- Logs contain user IPs (useful for security analysis)
- Restrict log file access with proper permissions

## Future Improvements

- [ ] Implement Sentry for error tracking
- [ ] Add email alerts for critical errors
- [ ] Create admin dashboard for log viewing
- [ ] Implement structured logging (JSON format)
- [ ] Add distributed tracing for microservices
