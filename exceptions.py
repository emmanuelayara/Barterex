"""
Custom exception classes for Barterex application.
Provides specific exceptions for different error scenarios.
"""

class BarterexException(Exception):
    """Base exception for all Barterex errors."""
    def __init__(self, message, status_code=500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class ValidationError(BarterexException):
    """Raised when input validation fails."""
    def __init__(self, message, field=None):
        self.field = field
        super().__init__(message, 400)


class AuthenticationError(BarterexException):
    """Raised when authentication fails."""
    def __init__(self, message="Authentication failed"):
        super().__init__(message, 401)


class AuthorizationError(BarterexException):
    """Raised when user lacks required permissions."""
    def __init__(self, message="You do not have permission to perform this action"):
        super().__init__(message, 403)


class ResourceNotFoundError(BarterexException):
    """Raised when a requested resource is not found."""
    def __init__(self, resource_type, resource_id=None):
        if resource_id:
            message = f"{resource_type} with ID {resource_id} not found"
        else:
            message = f"{resource_type} not found"
        super().__init__(message, 404)


class DatabaseError(BarterexException):
    """Raised when database operations fail."""
    def __init__(self, message, operation=None):
        self.operation = operation
        super().__init__(message, 500)


class FileUploadError(BarterexException):
    """Raised when file upload fails."""
    def __init__(self, message, filename=None):
        self.filename = filename
        super().__init__(message, 400)


class InsufficientCreditsError(BarterexException):
    """Raised when user has insufficient credits for purchase."""
    def __init__(self, required, available):
        message = f"Insufficient credits. Required: {required}, Available: {available}"
        super().__init__(message, 400)


class ItemNotAvailableError(BarterexException):
    """Raised when item is no longer available."""
    def __init__(self, item_name):
        message = f"Item '{item_name}' is no longer available"
        super().__init__(message, 400)


class UserBannedError(BarterexException):
    """Raised when banned user tries to access restricted features."""
    def __init__(self, username, reason=None):
        message = f"User '{username}' is banned"
        if reason:
            message += f": {reason}"
        super().__init__(message, 403)


class EmailSendError(BarterexException):
    """Raised when email sending fails."""
    def __init__(self, recipient, reason=None):
        message = f"Failed to send email to {recipient}"
        if reason:
            message += f": {reason}"
        super().__init__(message, 500)


class ConfigurationError(BarterexException):
    """Raised when application configuration is invalid."""
    def __init__(self, message):
        super().__init__(message, 500)
