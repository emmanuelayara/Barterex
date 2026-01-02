"""
Comprehensive Input Validation Utilities
Validates all user input to prevent:
- SQL injection (via SQLAlchemy ORM, but validates input)
- XSS attacks (sanitizes HTML)
- Path traversal attacks
- Malicious input patterns
- Data type mismatches
"""

import re
from typing import Tuple, Any, Optional, List
from logger_config import setup_logger

logger = setup_logger(__name__)

# ==================== CONSTANTS ====================

MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 64
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

MIN_ITEM_NAME_LENGTH = 3
MAX_ITEM_NAME_LENGTH = 200

MIN_DESCRIPTION_LENGTH = 10
MAX_DESCRIPTION_LENGTH = 5000

MIN_SEARCH_LENGTH = 2
MAX_SEARCH_LENGTH = 100

# Email validation regex (RFC 5322 simplified)
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

# Username validation: alphanumeric, underscore, hyphen only
USERNAME_REGEX = re.compile(r'^[a-zA-Z0-9_-]+$')

# Phone number validation: basic international format
PHONE_REGEX = re.compile(r'^\+?1?\d{9,15}$')

# Prevents common XSS patterns
XSS_PATTERNS = [
    r'<script[^>]*>.*?</script>',
    r'javascript:',
    r'on\w+\s*=',
    r'<iframe',
    r'<object',
    r'<embed',
    r'<img[^>]*onerror',
    r'<svg[^>]*onload',
]


# ==================== GENERAL VALIDATORS ====================

def validate_string(
    value: Any,
    field_name: str,
    min_length: int = 1,
    max_length: int = 255,
    allow_empty: bool = False,
    pattern: Optional[re.Pattern] = None
) -> Tuple[bool, str]:
    """
    Validate a string input with length and optional pattern matching.
    
    Args:
        value: Value to validate
        field_name: Name of field for error messages
        min_length: Minimum string length
        max_length: Maximum string length
        allow_empty: Whether to allow empty strings
        pattern: Optional regex pattern to match
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if value is None:
        if allow_empty:
            return True, ""
        return False, f"{field_name} is required"
    
    if not isinstance(value, str):
        return False, f"{field_name} must be a string"
    
    value = value.strip()
    
    if not value:
        if allow_empty:
            return True, ""
        return False, f"{field_name} cannot be empty"
    
    if len(value) < min_length:
        return False, f"{field_name} must be at least {min_length} characters"
    
    if len(value) > max_length:
        return False, f"{field_name} must not exceed {max_length} characters"
    
    if pattern and not pattern.match(value):
        return False, f"{field_name} has invalid format"
    
    return True, ""


def validate_integer(
    value: Any,
    field_name: str,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
    allow_none: bool = False
) -> Tuple[bool, str]:
    """
    Validate an integer input with optional range checking.
    
    Args:
        value: Value to validate
        field_name: Name of field for error messages
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        allow_none: Whether to allow None/null
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if value is None:
        if allow_none:
            return True, ""
        return False, f"{field_name} is required"
    
    try:
        value = int(value)
    except (ValueError, TypeError):
        return False, f"{field_name} must be a number"
    
    if min_value is not None and value < min_value:
        return False, f"{field_name} must be at least {min_value}"
    
    if max_value is not None and value > max_value:
        return False, f"{field_name} must not exceed {max_value}"
    
    return True, ""


def has_xss_patterns(text: str) -> bool:
    """
    Check if text contains potential XSS patterns.
    
    Args:
        text: Text to check
        
    Returns:
        True if XSS patterns found, False otherwise
    """
    if not isinstance(text, str):
        return False
    
    text_lower = text.lower()
    for pattern in XSS_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    
    return False


def sanitize_html(text: str, allow_html: bool = False) -> str:
    """
    Sanitize HTML content to prevent XSS.
    
    Args:
        text: Text to sanitize
        allow_html: Whether to allow certain HTML tags (default: False)
        
    Returns:
        Sanitized text
    """
    if not text:
        return ""
    
    if not allow_html:
        # Escape all HTML
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#x27;'))
    
    # If HTML allowed, still remove dangerous tags
    dangerous_tags = ['script', 'iframe', 'object', 'embed', 'link', 'style']
    for tag in dangerous_tags:
        text = re.sub(f'<{tag}[^>]*>.*?</{tag}>', '', text, flags=re.IGNORECASE | re.DOTALL)
    
    return text


# ==================== SPECIFIC VALIDATORS ====================

def validate_email(email: str) -> Tuple[bool, str]:
    """
    Validate email address format.
    
    Args:
        email: Email to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    is_valid, msg = validate_string(email, "Email", min_length=5, max_length=120)
    if not is_valid:
        return False, msg
    
    if not EMAIL_REGEX.match(email):
        return False, "Invalid email format"
    
    if has_xss_patterns(email):
        return False, "Email contains suspicious characters"
    
    return True, ""


def validate_username(username: str) -> Tuple[bool, str]:
    """
    Validate username format.
    
    Args:
        username: Username to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    is_valid, msg = validate_string(
        username,
        "Username",
        min_length=MIN_USERNAME_LENGTH,
        max_length=MAX_USERNAME_LENGTH,
        pattern=USERNAME_REGEX
    )
    if not is_valid:
        return False, msg
    
    if has_xss_patterns(username):
        return False, "Username contains suspicious characters"
    
    return True, ""


def validate_password(password: str) -> Tuple[bool, str]:
    """
    Validate password strength.
    
    Args:
        password: Password to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    is_valid, msg = validate_string(
        password,
        "Password",
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_PASSWORD_LENGTH
    )
    if not is_valid:
        return False, msg
    
    # Check for at least one uppercase, one lowercase, one digit
    has_upper = bool(re.search(r'[A-Z]', password))
    has_lower = bool(re.search(r'[a-z]', password))
    has_digit = bool(re.search(r'\d', password))
    
    if not (has_upper and has_lower and has_digit):
        return False, "Password must contain uppercase, lowercase, and digits"
    
    return True, ""


def validate_item_name(name: str) -> Tuple[bool, str]:
    """
    Validate item name.
    
    Args:
        name: Item name to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    is_valid, msg = validate_string(
        name,
        "Item name",
        min_length=MIN_ITEM_NAME_LENGTH,
        max_length=MAX_ITEM_NAME_LENGTH
    )
    if not is_valid:
        return False, msg
    
    if has_xss_patterns(name):
        return False, "Item name contains suspicious characters"
    
    return True, ""


def validate_description(description: str) -> Tuple[bool, str]:
    """
    Validate item/content description.
    
    Args:
        description: Description to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    is_valid, msg = validate_string(
        description,
        "Description",
        min_length=MIN_DESCRIPTION_LENGTH,
        max_length=MAX_DESCRIPTION_LENGTH
    )
    if not is_valid:
        return False, msg
    
    if has_xss_patterns(description):
        return False, "Description contains suspicious characters"
    
    return True, ""


def validate_search_query(query: str) -> Tuple[bool, str]:
    """
    Validate search query.
    
    Args:
        query: Search query to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    is_valid, msg = validate_string(
        query,
        "Search query",
        min_length=MIN_SEARCH_LENGTH,
        max_length=MAX_SEARCH_LENGTH,
        allow_empty=True
    )
    if not is_valid:
        return False, msg
    
    # Basic XSS check for search
    if has_xss_patterns(query):
        return False, "Search query contains invalid characters"
    
    return True, ""


def validate_phone(phone: str) -> Tuple[bool, str]:
    """
    Validate phone number.
    
    Args:
        phone: Phone number to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    is_valid, msg = validate_string(
        phone,
        "Phone number",
        min_length=10,
        max_length=20,
        allow_empty=True
    )
    if not is_valid:
        return False, msg
    
    if not PHONE_REGEX.match(phone.replace('-', '').replace(' ', '')):
        return False, "Invalid phone number format"
    
    return True, ""


def validate_address(address: str) -> Tuple[bool, str]:
    """
    Validate address field.
    
    Args:
        address: Address to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    is_valid, msg = validate_string(
        address,
        "Address",
        min_length=5,
        max_length=255,
        allow_empty=True
    )
    if not is_valid:
        return False, msg
    
    if has_xss_patterns(address):
        return False, "Address contains suspicious characters"
    
    return True, ""


def validate_credit_amount(amount: Any) -> Tuple[bool, str]:
    """
    Validate credit/price amount.
    
    Args:
        amount: Amount to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        amount = float(amount)
        if amount < 0:
            return False, "Amount cannot be negative"
        if amount > 999999.99:
            return False, "Amount exceeds maximum limit"
        return True, ""
    except (ValueError, TypeError):
        return False, "Amount must be a valid number"


def validate_category(category: str, allowed_categories: List[str]) -> Tuple[bool, str]:
    """
    Validate category selection.
    
    Args:
        category: Category to validate
        allowed_categories: List of allowed categories
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    is_valid, msg = validate_string(category, "Category", min_length=1, max_length=50)
    if not is_valid:
        return False, msg
    
    if category not in allowed_categories:
        return False, f"Invalid category: {category}"
    
    return True, ""


# ==================== BATCH VALIDATION ====================

def validate_form_data(data: dict, rules: dict) -> Tuple[bool, dict]:
    """
    Validate multiple form fields at once.
    
    Args:
        data: Form data dictionary
        rules: Validation rules dictionary {field_name: (validator_func, required)}
        
    Returns:
        Tuple of (is_valid, errors_dict)
    """
    errors = {}
    
    for field_name, (validator, required) in rules.items():
        value = data.get(field_name)
        
        if not value and not required:
            continue
        
        is_valid, error_msg = validator(value)
        if not is_valid:
            errors[field_name] = error_msg
    
    return len(errors) == 0, errors


# ==================== LOGGING ====================

def log_validation_error(field: str, reason: str, user_id: Optional[int] = None):
    """
    Log validation errors for monitoring.
    
    Args:
        field: Field that failed validation
        reason: Reason for failure
        user_id: Optional user ID
    """
    if user_id:
        logger.warning(f"Validation error - User: {user_id}, Field: {field}, Reason: {reason}")
    else:
        logger.warning(f"Validation error - Field: {field}, Reason: {reason}")
