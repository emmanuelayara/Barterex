"""
Error handling utilities for Barterex application.
Provides decorators and utilities for error handling and recovery.
"""

from functools import wraps
from flask import jsonify, render_template, redirect, url_for, flash
from logger_config import setup_logger
from exceptions import BarterexException

logger = setup_logger(__name__)

def handle_errors(f):
    """
    Decorator for handling errors in route handlers.
    Catches exceptions and returns appropriate responses.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        
        except BarterexException as e:
            logger.warning(f"Business logic error in {f.__name__}: {e.message}")
            flash(e.message, 'danger')
            return redirect(url_for('marketplace.marketplace')), e.status_code
        
        except Exception as e:
            logger.error(f"Unexpected error in {f.__name__}: {str(e)}", exc_info=True)
            flash('An unexpected error occurred. Please try again later.', 'danger')
            return redirect(url_for('marketplace.marketplace')), 500
    
    return decorated_function

def handle_api_errors(f):
    """
    Decorator for handling errors in API endpoints.
    Returns JSON responses instead of HTML.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        
        except BarterexException as e:
            logger.warning(f"API error in {f.__name__}: {e.message}")
            return jsonify({
                'success': False,
                'error': e.message,
                'status_code': e.status_code
            }), e.status_code
        
        except Exception as e:
            logger.error(f"Unexpected API error in {f.__name__}: {str(e)}", exc_info=True)
            return jsonify({
                'success': False,
                'error': 'An unexpected error occurred',
                'status_code': 500
            }), 500
    
    return decorated_function

def safe_database_operation(operation_name):
    """
    Decorator for safe database operations.
    Handles commit/rollback automatically with detailed error logging.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from app import db
            try:
                result = f(*args, **kwargs)
                # CRITICAL: Debug logging before commit
                logger.debug(f"[{operation_name}] About to commit transaction")
                logger.debug(f"[{operation_name}] Session state: new={len(db.session.new)}, dirty={len(db.session.dirty)}, deleted={len(db.session.deleted)}")
                
                # Commit the transaction
                db.session.commit()
                logger.info(f"Database operation '{operation_name}' completed successfully")
                logger.debug(f"[{operation_name}] Transaction committed successfully")
                return result
            
            except Exception as e:
                logger.error(f"Database operation '{operation_name}' failed during commit: {str(e)}", exc_info=True)
                db.session.rollback()
                logger.error(f"Database operation '{operation_name}' rolled back due to error: {str(e)}")
                raise BarterexException(f"Database operation failed: {str(e)}", 500)
        
        return decorated_function
    return decorator

def validate_input(validation_rules):
    """
    Decorator for input validation.
    
    Args:
        validation_rules: Dictionary of {field: validator_function}
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from flask import request
            from exceptions import ValidationError
            
            try:
                data = request.form if request.method == 'POST' else request.args
                
                for field, validator in validation_rules.items():
                    value = data.get(field)
                    if not validator(value):
                        raise ValidationError(
                            f"Invalid value for {field}",
                            field=field
                        )
                
                return f(*args, **kwargs)
            
            except ValidationError as e:
                logger.warning(f"Validation error in {f.__name__}: {e.message}")
                flash(e.message, 'warning')
                return redirect(request.referrer or url_for('marketplace.marketplace'))
        
        return decorated_function
    return decorator

class ErrorContext:
    """Context manager for error handling."""
    
    def __init__(self, operation_name, logger_instance=None):
        self.operation_name = operation_name
        self.logger = logger_instance or logger
    
    def __enter__(self):
        self.logger.debug(f"Starting operation: {self.operation_name}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.logger.debug(f"Operation completed successfully: {self.operation_name}")
            return True
        
        self.logger.error(
            f"Operation failed: {self.operation_name} - {exc_type.__name__}: {exc_val}",
            exc_info=(exc_type, exc_val, exc_tb)
        )
        return False

def retry_operation(max_retries=3, delay=1, backoff=2):
    """
    Decorator for retrying failed operations with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries (seconds)
        backoff: Multiplier for delay after each retry
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            import time
            current_delay = delay
            
            for attempt in range(1, max_retries + 1):
                try:
                    logger.debug(f"Attempt {attempt} of {max_retries} for {f.__name__}")
                    return f(*args, **kwargs)
                
                except Exception as e:
                    if attempt == max_retries:
                        logger.error(f"All {max_retries} attempts failed for {f.__name__}")
                        raise
                    
                    logger.warning(
                        f"Attempt {attempt} failed for {f.__name__}, retrying in {current_delay}s: {str(e)}"
                    )
                    time.sleep(current_delay)
                    current_delay *= backoff
        
        return decorated_function
    return decorator
