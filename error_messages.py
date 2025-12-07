"""
User-friendly error messages and recovery suggestions for common scenarios in Barterex.
Maps error conditions to helpful messages and actionable recovery steps.
"""

class ErrorMessages:
    """Collection of user-friendly error messages with recovery suggestions."""
    
    # Authentication & Session Errors
    SESSION_EXPIRED = {
        'message': 'Your session has expired for security reasons.',
        'action': 'Please log in again to continue.',
        'recovery_link': 'auth.login'
    }
    
    UNAUTHORIZED_ACCESS = {
        'message': 'You do not have permission to access this resource.',
        'action': 'Make sure you are logged in with the correct account.',
        'recovery_link': 'auth.login'
    }
    
    ACCOUNT_BANNED = {
        'message': 'Your account has been restricted.',
        'action': 'Contact support if you believe this is a mistake or to request an unban.',
        'recovery_link': 'marketplace.contact'
    }
    
    # Item/Product Errors
    ITEM_NOT_FOUND = {
        'message': 'The item you are looking for is no longer available.',
        'action': 'The item may have been sold or removed. Browse other available items.',
        'recovery_link': 'marketplace.marketplace',
        'recovery_label': 'Browse Marketplace'
    }
    
    ITEM_ALREADY_IN_CART = {
        'message': 'This item is already in your cart.',
        'action': 'View your cart to update quantities or proceed to checkout.',
        'recovery_link': 'items.view_cart',
        'recovery_label': 'View Cart'
    }
    
    ITEM_OUT_OF_STOCK = {
        'message': 'This item is currently out of stock.',
        'action': 'Check back later or browse similar items.',
        'recovery_link': 'marketplace.marketplace',
        'recovery_label': 'Browse Similar Items'
    }
    
    # Credit/Payment Errors
    INSUFFICIENT_CREDITS = {
        'message': 'You do not have enough credits to complete this purchase.',
        'action': 'Earn more credits by trading items or contact support for assistance.',
        'recovery_link': 'marketplace.marketplace',
        'recovery_label': 'View Trading Opportunities'
    }
    
    PAYMENT_FAILED = {
        'message': 'Your payment could not be processed.',
        'action': 'Please check your information and try again. Contact support if the problem persists.',
        'recovery_link': 'items.view_cart',
        'recovery_label': 'Return to Checkout'
    }
    
    # Form/Validation Errors
    DUPLICATE_USERNAME = {
        'message': 'This username is already taken.',
        'action': 'Choose a different username and try again.',
        'suggestion': 'Add a number or underscore to make it unique'
    }
    
    DUPLICATE_EMAIL = {
        'message': 'An account with this email already exists.',
        'action': 'Use a different email or try logging in if you already have an account.',
        'recovery_link': 'auth.login',
        'recovery_label': 'Sign In'
    }
    
    INVALID_EMAIL = {
        'message': 'Please enter a valid email address.',
        'action': 'Make sure your email follows the format: name@example.com',
        'suggestion': 'Example: user@example.com'
    }
    
    PASSWORD_TOO_WEAK = {
        'message': 'Your password is too weak.',
        'action': 'Use at least 8 characters with a mix of uppercase, lowercase, numbers, and symbols.',
        'suggestion': 'Example: MyP@ssw0rd!'
    }
    
    PASSWORD_MISMATCH = {
        'message': 'Passwords do not match.',
        'action': 'Re-enter your password to confirm it matches.',
        'suggestion': 'Passwords must match exactly'
    }
    
    # Upload/File Errors
    FILE_TOO_LARGE = {
        'message': 'File is too large.',
        'action': 'Maximum file size is 2MB. Please choose a smaller file.',
        'suggestion': 'Compress the image before uploading'
    }
    
    INVALID_FILE_TYPE = {
        'message': 'Invalid file type.',
        'action': 'Only images (PNG, JPG, JPEG, GIF) are allowed.',
        'suggestion': 'Allowed formats: .png, .jpg, .jpeg, .gif'
    }
    
    NO_IMAGE_SELECTED = {
        'message': 'Please select at least one image.',
        'action': 'Upload at least one image for your item.',
        'suggestion': 'Click "Add Image" to select photos'
    }
    
    # Order/Transaction Errors
    ORDER_NOT_FOUND = {
        'message': 'The order could not be found.',
        'action': 'The order may have been deleted. View your order history.',
        'recovery_link': 'user.user_orders',
        'recovery_label': 'View Orders'
    }
    
    ORDER_ALREADY_COMPLETED = {
        'message': 'This order has already been completed.',
        'action': 'You cannot modify a completed order.',
        'recovery_link': 'user.user_orders',
        'recovery_label': 'View Orders'
    }

def get_error_message(error_key, **kwargs):
    """
    Get user-friendly error message with recovery suggestions.
    
    Args:
        error_key: Key from ErrorMessages dict
        **kwargs: Additional context variables
    
    Returns:
        dict: Message, action, and recovery information
    """
    error_info = getattr(ErrorMessages, error_key, None)
    
    if error_info is None:
        # Fallback for unknown errors
        return {
            'message': 'An error occurred.',
            'action': 'Please try again or contact support.',
            'recovery_link': 'marketplace.marketplace'
        }
    
    # Format with kwargs if provided
    result = error_info.copy()
    for key in ['message', 'action', 'suggestion', 'recovery_label']:
        if key in result and kwargs:
            try:
                result[key] = result[key].format(**kwargs)
            except KeyError:
                pass
    
    return result

def format_error_toast(error_key, **kwargs):
    """Format error message for toast notification."""
    error_info = get_error_message(error_key, **kwargs)
    return error_info.get('message', 'An error occurred.')

def format_error_page(error_key, **kwargs):
    """Format error message for error page display."""
    error_info = get_error_message(error_key, **kwargs)
    return {
        'message': error_info.get('message'),
        'action': error_info.get('action'),
        'suggestion': error_info.get('suggestion'),
        'recovery_link': error_info.get('recovery_link'),
        'recovery_label': error_info.get('recovery_label', 'Continue')
    }

# Common error scenarios in Flask
CSRF_FAILED = {
    'message': 'Security verification failed.',
    'action': 'Please go back and try again.',
    'recovery_link': 'marketplace.marketplace'
}

VALIDATION_ERROR = {
    'message': 'Please check your input.',
    'action': 'Make sure all required fields are filled correctly.',
    'recovery_link': None
}

DATABASE_ERROR = {
    'message': 'A database error occurred.',
    'action': 'Please try again later.',
    'recovery_link': 'marketplace.marketplace'
}

PERMISSION_ERROR = {
    'message': 'You do not have permission for this action.',
    'action': 'Make sure you are logged in with the correct account.',
    'recovery_link': 'auth.login'
}

# Mapping of exception types to error messages
EXCEPTION_MAPPING = {
    'ItemNotFound': 'ITEM_NOT_FOUND',
    'InsufficientCredits': 'INSUFFICIENT_CREDITS',
    'ValidationError': 'VALIDATION_ERROR',
    'PermissionError': 'UNAUTHORIZED_ACCESS',
    'FileUploadError': 'FILE_TOO_LARGE',
}
