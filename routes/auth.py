from flask import Blueprint, render_template, redirect, url_for, flash, current_app, request, session
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer
from threading import Thread
from datetime import datetime, timedelta

from models import User
from forms import RegisterForm, LoginForm, ForgotPasswordForm, ResetPasswordForm
from logger_config import setup_logger
from exceptions import AuthenticationError, UserBannedError, EmailSendError
from error_handlers import handle_errors, safe_database_operation

logger = setup_logger(__name__)

auth_bp = Blueprint('auth', __name__)

# ==================== HELPER FUNCTIONS ====================

def send_async_email(app, msg):
    """Send email in background thread to avoid blocking requests"""
    with app.app_context():
        try:
            from flask_mail import Mail
            mail = Mail(app)
            mail.send(msg)
            print(f"✅ Email sent successfully to {msg.recipients}")
        except Exception as e:
            print(f"❌ Email sending failed: {e}")

def send_email_async(subject, recipients, html_body, sender=None):
    """Helper function to send emails asynchronously"""
    try:
        from flask_mail import Message
        msg = Message(
            subject=subject,
            sender=sender or (current_app.config.get('MAIL_DEFAULT_SENDER', 'noreply@barterex.com')),
            recipients=recipients if isinstance(recipients, list) else [recipients]
        )
        msg.html = html_body
        Thread(target=send_async_email, args=(current_app._get_current_object(), msg), daemon=True).start()
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

def generate_reset_token(email, expires_sec=3600):
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return s.dumps(email, salt='password-reset-salt')

def verify_reset_token(token, expires_sec=3600):
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = s.loads(token, salt='password-reset-salt', max_age=expires_sec)
    except Exception:
        return None
    return email

# ==================== ROUTES ====================

@auth_bp.route('/register', methods=['GET', 'POST'])
@handle_errors
def register():
    from app import db
    
    form = RegisterForm()
    if form.validate_on_submit():
        try:
            hashed_password = generate_password_hash(form.password.data)
            user = User(
                username=form.username.data,
                email=form.email.data,
                password_hash=hashed_password,
                credits=5000,
                first_login=True
            )
            db.session.add(user)
            db.session.commit()
            
            logger.info(f"New user registered: {user.username}")

            html = render_template("emails/welcome_email.html", username=user.username)
            send_email_async(
                subject="🎉 Welcome to Barterex!",
                recipients=[user.email],
                html_body=html
            )

            flash('Registration successful. Please log in.', 'success')
            return redirect(url_for('auth.login'))
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Registration error: {str(e)}", exc_info=True)
            flash('Registration failed. Please try again later.', 'danger')
            return render_template('register.html', form=form)

    return render_template('register.html', form=form)


@auth_bp.route('/login', methods=['GET', 'POST'])
@handle_errors
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        
        try:
            from app import db
            user = User.query.filter_by(username=username).first()

            # Check if account is locked due to failed attempts
            if user and user.account_locked_until and datetime.utcnow() < user.account_locked_until:
                remaining_time = (user.account_locked_until - datetime.utcnow()).total_seconds() / 60
                logger.warning(f"Locked account login attempt: {username}")
                flash(f'Account temporarily locked due to failed login attempts. Try again in {int(remaining_time)} minutes.', 'danger')
                return redirect(url_for('auth.login'))

            if user and user.is_banned:
                logger.warning(f"Banned user attempted login: {username}")
                return render_template(
                    "banned.html",
                    reason=user.ban_reason,
                    unban_requested=user.unban_requested
                )

            if user and check_password_hash(user.password_hash, password):
                # Successful login - reset failed attempts
                user.failed_login_attempts = 0
                user.account_locked_until = None
                db.session.commit()

                login_user(user)
                logger.info(f"User logged in: {username}")

                if user.first_login:
                    flash(
                        "Welcome Beta Tester! You've been given 5000 credits as a signup bonus.",
                        "success"
                    )
                    user.first_login = False
                    db.session.commit()
                else:
                    flash('Login successful!', 'success')

                return redirect(url_for('user.dashboard'))
            else:
                # Failed login attempt - increment counter
                if user:
                    user.failed_login_attempts = user.failed_login_attempts + 1
                    
                    # Lock account after 5 failed attempts for 15 minutes
                    if user.failed_login_attempts >= 5:
                        user.account_locked_until = datetime.utcnow() + timedelta(minutes=15)
                        db.session.commit()
                        logger.warning(f"Account locked: {username} after 5 failed login attempts")
                        flash('Account locked due to too many failed login attempts. Try again in 15 minutes.', 'danger')
                        return redirect(url_for('auth.login'))
                    
                    db.session.commit()

                logger.warning(f"Failed login attempt for username: {username} (attempt {user.failed_login_attempts if user else 'unknown'})")
                flash('Invalid username or password.', 'danger')
        
        except Exception as e:
            logger.error(f"Login error: {str(e)}", exc_info=True)
            flash('An error occurred during login. Please try again.', 'danger')
    
    return render_template('login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('marketplace.marketplace'))


@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            token = generate_reset_token(user.email)
            reset_url = url_for('auth.reset_password', token=token, _external=True)

            html = render_template(
                "emails/reset_password_email.html",
                username=user.username,
                reset_url=reset_url
            )
            send_email_async(
                subject="🔑 Reset Your Password",
                recipients=[user.email],
                html_body=html
            )

        flash('If that email exists, a reset link has been sent.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('forgot_password.html', form=form)


@auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    from app import db
    
    email = verify_reset_token(token)
    if not email:
        flash('The reset link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=email).first()
        if user:
            user.password_hash = generate_password_hash(form.password.data)
            db.session.commit()
            flash('Your password has been updated! Please log in.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('reset_password.html', form=form)


@auth_bp.route('/banned')
def banned():
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))

    if not current_user.is_banned:
        return redirect(url_for('auth.login'))

    return render_template(
        'banned.html',
        reason=current_user.ban_reason,
        unban_requested=current_user.unban_requested
    )


@auth_bp.route('/request_unban', methods=['POST'])
@login_required
def request_unban():
    from app import db
    
    if not current_user.is_banned:
        flash("You are not banned.", "info")
        return redirect(url_for('user.dashboard'))

    if not current_user.unban_requested:
        current_user.unban_requested = True
        db.session.commit()
        flash('Your unban request has been submitted. Please wait for admin review.', 'info')
    else:
        flash('You have already submitted an unban request.', 'warning')

    return redirect(url_for('auth.banned'))
