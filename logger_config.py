"""
Logging configuration for Barterex application.
Sets up structured logging with file and console handlers.
"""

import logging
import logging.handlers
import os
from datetime import datetime

# Create logs directory if it doesn't exist
LOGS_DIR = 'logs'
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

# Log file path
LOG_FILE = os.path.join(LOGS_DIR, f'barterex_{datetime.now().strftime("%Y%m%d")}.log')

# Define logger format
LOG_FORMAT = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def setup_logger(name, level=logging.INFO):
    """
    Configure and return a logger instance.
    
    Args:
        name: Logger name (typically __name__)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid adding duplicate handlers
    if logger.handlers:
        return logger
    
    # File handler - logs to rotating file
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_FILE,
            maxBytes=10485760,  # 10MB
            backupCount=10
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(LOG_FORMAT)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Failed to setup file handler: {e}")
    
    # Console handler - logs to console
    try:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(LOG_FORMAT)
        logger.addHandler(console_handler)
    except Exception as e:
        print(f"Failed to setup console handler: {e}")
    
    return logger

# Module-level logger
logger = setup_logger(__name__)

def log_exception(logger, message, exc_info=True):
    """
    Log an exception with context.
    
    Args:
        logger: Logger instance
        message: Context message
        exc_info: Whether to include exception info
    """
    logger.error(message, exc_info=exc_info)

def log_database_error(logger, operation, entity_id=None):
    """
    Log database operation errors.
    
    Args:
        logger: Logger instance
        operation: Operation name (e.g., 'create', 'update', 'delete')
        entity_id: ID of affected entity
    """
    msg = f"Database error during {operation}"
    if entity_id:
        msg += f" for entity ID: {entity_id}"
    logger.error(msg, exc_info=True)

def log_validation_error(logger, field, value, reason):
    """
    Log validation errors.
    
    Args:
        logger: Logger instance
        field: Field name
        value: Invalid value
        reason: Reason for validation failure
    """
    logger.warning(f"Validation error - Field: {field}, Value: {value}, Reason: {reason}")

def log_auth_event(logger, event_type, username, success=True, ip_address=None):
    """
    Log authentication events.
    
    Args:
        logger: Logger instance
        event_type: 'login', 'logout', 'registration', 'password_reset'
        username: Username involved
        success: Whether event succeeded
        ip_address: Client IP address
    """
    status = "SUCCESS" if success else "FAILED"
    msg = f"Auth event: {event_type} [{status}] - User: {username}"
    if ip_address:
        msg += f" - IP: {ip_address}"
    
    if success:
        logger.info(msg)
    else:
        logger.warning(msg)

def log_business_event(logger, event_type, details):
    """
    Log important business events.
    
    Args:
        logger: Logger instance
        event_type: Type of business event
        details: Event details dictionary
    """
    logger.info(f"Business event: {event_type} - Details: {details}")
