import os
from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate
from datetime import datetime, timedelta
from flask_mail import Mail, Message
from dotenv import load_dotenv

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    LIMITER_AVAILABLE = True
except ImportError:
    LIMITER_AVAILABLE = False

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

UPLOAD_FOLDER = 'static/uploads/'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # Max size: 50MB (global limit)
app.config['ALLOWED_EXTENSIONS'] = ALLOWED_EXTENSIONS

# ✅ File upload security configuration
app.config['FILE_UPLOAD_MAX_SIZE'] = 10 * 1024 * 1024  # 10MB default per file
app.config['FILE_UPLOAD_ENABLE_VIRUS_SCAN'] = False  # Set to True if ClamAV is available (apt-get install clamav)

# ✅ Load config from environment variables
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///barter.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ✅ Session security settings
app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS only
app.config['SESSION_COOKIE_HTTPONLY'] = True  # No JavaScript access
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # 7 days for standard sessions
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)  # Remember Me cookie lasts 30 days
app.config['REMEMBER_COOKIE_SECURE'] = True  # HTTPS only for remember cookie
app.config['REMEMBER_COOKIE_HTTPONLY'] = True  # No JavaScript access to remember cookie
app.config['WTF_CSRF_ENABLED'] = True  # Enable CSRF protection
app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # CSRF tokens expire after 1 hour (security best practice)

# ✅ Mail config from environment
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() in ['true', '1', 'yes']
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'False').lower() in ['true', '1', 'yes']
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
mail_sender_name, mail_sender_email = os.getenv('MAIL_DEFAULT_SENDER', 'Barter Express,info.barterex@gmail.com').split(',')
app.config['MAIL_DEFAULT_SENDER'] = (mail_sender_name.strip(), mail_sender_email.strip())

# ✅ Suppress Flask-Mail debug output
app.config['MAIL_DEBUG'] = os.getenv('MAIL_DEBUG', 'False').lower() in ['true', '1', 'yes']

# ✅ Initialize extensions FIRST
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'
login_manager.remember_cookie_duration = timedelta(days=30)  # Remember Me for 30 days
login_manager.remember_cookie_secure = True  # HTTPS only
login_manager.remember_cookie_httponly = True  # No JavaScript access
migrate = Migrate(app, db)
mail = Mail(app)

# ✅ Initialize rate limiter BEFORE importing routes (to avoid circular import)
if LIMITER_AVAILABLE:
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://"
    )
else:
    limiter = None

# Import models and blueprints
from models import *
from routes import auth_bp, marketplace_bp, user_bp, items_bp, admin_bp
from routes.notifications_api import notifications_bp
from routes_account import account_bp
from notifications import NotificationService

# ✅ User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ✅ Jinja filter to ensure image URLs are absolute paths
@app.template_filter('image_url')
def format_image_url(url):
    """Convert image URLs to absolute paths for proper serving"""
    if not url:
        return '/static/placeholder.png'
    
    # If URL already has /static/ in it, return as-is
    if '/static/' in url:
        # Clean up any double slashes
        return url.replace('//', '/')
    
    # Otherwise prepend /static/uploads/
    # Remove any leading/trailing slashes from the filename
    url = url.strip('/')
    return f'/static/uploads/{url}'

# ✅ Maintenance Mode Handler
@app.before_request
def check_maintenance_mode():
    """Check if maintenance mode is enabled and restrict user actions"""
    from models import SystemSettings
    
    # Allow admin routes even in maintenance mode
    if request.blueprint and request.blueprint.startswith('admin'):
        return
    
    # Check maintenance mode
    settings = SystemSettings.get_settings()
    if settings.maintenance_mode:
        # Allow only essential user routes (login, etc.)
        allowed_routes = ['auth.login', 'auth.logout', 'auth.register', 'static']
        current_route = request.endpoint
        
        if current_route not in allowed_routes:
            return render_template('maintenance_page.html', 
                                 message=settings.maintenance_message), 503
    
    # Check individual feature flags for user actions
    if settings and not settings.maintenance_mode:
        current_route = request.endpoint or ''
        
        # Check upload restrictions
        if 'upload' in current_route and not settings.allow_uploads:
            flash('Item uploads are currently disabled. Please try again later.', 'warning')
            return redirect(url_for('marketplace.index'))
        
        # Check trading restrictions
        if any(x in current_route for x in ['trade', 'order', 'checkout']) and not settings.allow_trading:
            flash('Trading is currently disabled. Please try again later.', 'warning')
            return redirect(url_for('marketplace.index'))
        
        # Check browsing restrictions
        if 'marketplace' in current_route and not settings.allow_browsing:
            return render_template('marketplace_disabled.html'), 503

# ✅ Context processor for cart info and CSRF token
@app.context_processor
def inject_cart_info():
    from flask_login import current_user
    from flask_wtf.csrf import generate_csrf
    
    if current_user.is_authenticated:
        cart = Cart.query.filter_by(user_id=current_user.id).first()
        if cart:
            cart_count = cart.get_item_count()
        else:
            cart_count = 0
        return {'cart_count': cart_count, 'csrf_token': generate_csrf}
    return {'cart_count': 0, 'csrf_token': generate_csrf}

# ✅ Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(marketplace_bp)
app.register_blueprint(user_bp)
app.register_blueprint(items_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(notifications_bp)
app.register_blueprint(account_bp)

# ✅ Error Handlers
from logger_config import setup_logger
from exceptions import BarterexException

logger = setup_logger(__name__)

@app.errorhandler(400)
def bad_request(error):
    """Handle 400 Bad Request errors with user-friendly messages."""
    logger.warning(f"Bad request: {error}")
    error_details = str(error)
    
    # Provide specific messages based on error type
    if 'CSRF' in error_details:
        message = 'Security token expired. Please try your action again.'
    elif 'multipart' in error_details.lower():
        message = 'Invalid file upload. Please check your file and try again.'
    else:
        message = 'Invalid request. Please check your input and try again.'
    
    flash(message, 'danger')
    return render_template('error.html', 
                          error_code=400, 
                          error_message='Bad Request',
                          error_details=message), 400

@app.errorhandler(404)
def not_found(error):
    """Handle 404 Not Found errors with recovery suggestions."""
    logger.info(f"Resource not found: {request.path}")
    
    # Provide helpful message
    message = 'The page or item you are looking for does not exist.'
    flash(message, 'warning')
    return render_template('error.html', 
                          error_code=404, 
                          error_message='Page Not Found',
                          error_details=message), 404

@app.errorhandler(403)
def forbidden(error):
    """Handle 403 Forbidden errors."""
    logger.warning(f"Access forbidden: {request.path}")
    message = 'You do not have permission to access this resource.'
    flash(message, 'danger')
    return render_template('error.html', 
                          error_code=403, 
                          error_message='Access Denied',
                          error_details=message), 403

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 Internal Server errors with helpful recovery info."""
    logger.error(f"Internal server error: {error}", exc_info=True)
    db.session.rollback()
    
    message = 'Something unexpected happened on our end. Our team has been notified and is investigating.'
    flash(message, 'danger')
    return render_template('error.html', 
                          error_code=500, 
                          error_message='Internal Server Error',
                          error_details=message), 500

@app.errorhandler(BarterexException)
def handle_barterex_exception(error):
    """Handle custom Barterex exceptions with specific messages."""
    logger.warning(f"Business logic error: {error.message}")
    
    # Format message for display
    message = error.message
    if not message.endswith('!') and not message.endswith('.') and not message.endswith('?'):
        message += '.'
    
    flash(message, 'warning')
    return render_template('error.html', 
                          error_code=error.status_code or 400, 
                          error_message='Error',
                          error_details=message), error.status_code or 400

@app.errorhandler(Exception)
def handle_unexpected_error(error):
    """Handle unexpected exceptions with diagnostic info."""
    logger.error(f"Unexpected error: {str(error)}", exc_info=True)
    db.session.rollback()
    
    message = 'An unexpected error occurred. Our support team has been notified.'
    flash(message, 'danger')
    return render_template('error.html', 
                          error_code=500, 
                          error_message='Unexpected Error',
                          error_details=message), 500

# ✅ Request logging
@app.before_request
def log_request():
    """Log incoming requests."""
    logger.debug(f"Request: {request.method} {request.path} from {request.remote_addr}")

@app.after_request
def log_response(response):
    """Log outgoing responses."""
    logger.debug(f"Response: {response.status_code} for {request.method} {request.path}")
    return response

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        logger.info("Barterex application started")
    app.run()
