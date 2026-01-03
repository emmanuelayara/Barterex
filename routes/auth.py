from flask import Blueprint, render_template, redirect, url_for, flash, current_app, request, session
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer
from threading import Thread
from datetime import datetime, timedelta

from models import User, CreditTransaction, Notification
from forms import RegisterForm, LoginForm, ForgotPasswordForm, ResetPasswordForm
from logger_config import setup_logger
from exceptions import AuthenticationError, UserBannedError, EmailSendError
from error_handlers import handle_errors, safe_database_operation
from app import db

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
            logger.info(f"✅ Email sent successfully to {msg.recipients}")
        except Exception as e:
            logger.error(f"❌ Email sending failed: {e}", exc_info=True)

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
        logger.debug(f"Sending email to {recipients} with subject: {subject}")
        Thread(target=send_async_email, args=(current_app._get_current_object(), msg), daemon=True).start()
        logger.info(f"Email task queued for {recipients}")
    except Exception as e:
        logger.error(f"❌ Failed to queue email: {e}", exc_info=True)

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
    from models import Referral
    
    form = RegisterForm()
    if form.validate_on_submit():
        try:
            hashed_password = generate_password_hash(form.password.data)
            user = User(
                username=form.username.data,
                email=form.email.data,
                password_hash=hashed_password,
                credits=1000,
                first_login=True,
                email_verified=False  # ✅ Email must be verified before account is active
            )
            db.session.add(user)
            db.session.commit()
            
            # ✅ Generate email verification token
            verification_token = user.generate_email_verification_token()
            db.session.commit()
            
            # ✅ Send verification email BEFORE handling referrals
            from flask import url_for
            verification_link = url_for('auth.verify_email', token=verification_token, _external=True)
            support_url = url_for('marketplace.marketplace', _external=True)
            
            html = render_template(
                "emails/verify_email.html", 
                username=user.username,
                verification_token=verification_token,
                verification_link=verification_link,
                support_url=support_url
            )
            send_email_async(
                subject="✅ Verify Your Barterex Email Address",
                recipients=[user.email],
                html_body=html
            )
            
            logger.info(f"Verification email sent to new user: {user.username} ({user.email})")
            
            # Handle referral if provided
            if form.referral_code.data:
                referrer = User.query.filter_by(referral_code=form.referral_code.data).first()
                if referrer:
                    referral = Referral(
                        referrer_id=referrer.id,
                        referred_user_id=user.id,
                        referral_code_used=form.referral_code.data,
                        signup_bonus_earned=True  # Award bonus on signup
                    )
                    db.session.add(referral)
                    
                    # Award 100 naira to referrer on signup
                    referrer.credits += 100
                    referrer.referral_count += 1
                    referrer.referral_bonus_earned += 100
                    
                    # Log the transaction
                    transaction = CreditTransaction(
                        user_id=referrer.id,
                        amount=100,
                        transaction_type='referral_signup_bonus'
                    )
                    db.session.add(transaction)
                    
                    # Create notification for referrer
                    notification = Notification(
                        user_id=referrer.id,
                        message=f'🎉 {user.username} signed up using your referral code! You earned ₦100',
                        notification_type='referral',
                        category='reward'
                    )
                    db.session.add(notification)
                    
                    db.session.commit()
                    logger.info(f"Referral processed: {referrer.username} referred {user.username}")
            
            logger.info(f"New user registered (pending email verification): {user.username}")

            # ✅ Show message about email verification required
            flash('✅ Registration successful! Please check your email to verify your account before logging in.', 'info')
            return redirect(url_for('auth.login'))
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Registration error: {str(e)}", exc_info=True)
            flash('Registration failed. Please try again later.', 'danger')
            return render_template('register.html', form=form)

    return render_template('register.html', form=form)


@auth_bp.route('/verify-email/<token>')
@handle_errors
def verify_email(token):
    """
    Verify user email address using the token sent in email.
    This route activates the user account.
    """
    from app import db
    
    if not token:
        logger.warning("Email verification attempted without token")
        flash('❌ Invalid verification link. Please request a new one.', 'danger')
        return redirect(url_for('auth.login'))
    
    try:
        # Find user with this verification token
        user = User.query.filter_by(email_verification_token=token).first()
        
        if not user:
            logger.warning(f"Email verification attempted with invalid token: {token[:10]}...")
            flash('❌ Invalid verification link. This link may have expired or been already used.', 'danger')
            return redirect(url_for('auth.login'))
        
        # Check if token is still valid
        if not user.verify_email_token(token):
            logger.warning(f"Email verification token expired or invalid for user: {user.username}")
            flash('❌ Verification link has expired. Please request a new verification email.', 'warning')
            return redirect(url_for('auth.resend_verification', email=user.email))
        
        # Mark email as verified
        user.mark_email_verified()
        db.session.commit()
        
        logger.info(f"✅ Email verified for user: {user.username}")
        
        # Send welcome email after verification
        html = render_template("emails/welcome_email.html", username=user.username)
        send_email_async(
            subject="🎉 Welcome to Barterex!",
            recipients=[user.email],
            html_body=html
        )
        
        flash('✅ Email verified successfully! Your account is now active. You can log in now.', 'success')
        return redirect(url_for('auth.login'))
        
    except Exception as e:
        logger.error(f"Error during email verification: {str(e)}", exc_info=True)
        flash('An error occurred during verification. Please try again later.', 'danger')
        return redirect(url_for('auth.login'))


@auth_bp.route('/resend-verification', methods=['GET', 'POST'])
@handle_errors
def resend_verification():
    """
    Resend verification email to user.
    """
    from app import db
    from flask import request
    
    email = request.args.get('email') or request.form.get('email', '')
    
    if request.method == 'GET':
        return render_template('resend_verification.html', email=email)
    
    # POST request - resend verification
    email = request.form.get('email', '').strip().lower()
    
    if not email:
        flash('❌ Please enter your email address.', 'danger')
        return render_template('resend_verification.html')
    
    try:
        user = User.query.filter_by(email=email).first()
        
        if not user:
            # Don't reveal whether email exists
            logger.info(f"Resend verification requested for non-existent email: {email}")
            flash('✅ If an account exists with this email, a verification link has been sent.', 'info')
            return redirect(url_for('auth.login'))
        
        if user.email_verified:
            logger.info(f"Resend verification requested for already verified user: {user.username}")
            flash('ℹ️ Your email is already verified! You can log in now.', 'info')
            return redirect(url_for('auth.login'))
        
        # Generate new verification token
        verification_token = user.generate_email_verification_token()
        db.session.commit()
        
        # Send verification email
        from flask import url_for
        verification_link = url_for('auth.verify_email', token=verification_token, _external=True)
        support_url = url_for('marketplace.marketplace', _external=True)
        
        html = render_template(
            "emails/verify_email.html", 
            username=user.username,
            verification_token=verification_token,
            verification_link=verification_link,
            support_url=support_url
        )
        send_email_async(
            subject="✅ Verify Your Barterex Email Address",
            recipients=[user.email],
            html_body=html
        )
        
        logger.info(f"Verification email resent to user: {user.username}")
        flash('✅ Verification email sent! Please check your inbox.', 'success')
        return redirect(url_for('auth.login'))
        
    except Exception as e:
        logger.error(f"Error resending verification email: {str(e)}", exc_info=True)
        flash('An error occurred. Please try again later.', 'danger')
        return render_template('resend_verification.html', email=email)


@auth_bp.route('/login', methods=['GET', 'POST'])
@handle_errors
def login():
    form = LoginForm()
    next_page = request.args.get('next')
    
    # Validate next_page to prevent open redirect attacks
    if next_page and (not next_page.startswith('/') or next_page.startswith('//')):
        next_page = None
    
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
                return redirect(url_for('auth.login', next=next_page))

            if user and user.is_banned:
                logger.warning(f"Banned user attempted login: {username}")
                # ✅ FIX: Log them in so they can submit unban appeals
                if user and check_password_hash(user.password_hash, password):
                    user.failed_login_attempts = 0
                    user.account_locked_until = None
                    db.session.commit()
                    login_user(user, remember=False)
                    logger.info(f"Banned user session created for appeal submission: {username}")
                return render_template(
                    "banned.html",
                    reason=user.ban_reason,
                    unban_requested=user.unban_requested,
                    appeal_message=user.appeal_message,
                    ban_date=user.ban_date,
                    unban_request_date=user.unban_request_date,
                    username=user.username,
                    user_email=user.email
                )

            if user and check_password_hash(user.password_hash, password):
                # ✅ Check if email is verified BEFORE allowing login
                if not user.email_verified:
                    logger.info(f"Unverified email login attempt: {username}")
                    flash('❌ Please verify your email address before logging in. Check your inbox for the verification link.', 'warning')
                    return render_template('login.html', form=form, show_resend=True, email=user.email)
                
                # Successful login - reset failed attempts and update last login
                user.failed_login_attempts = 0
                user.account_locked_until = None
                user.last_login = datetime.utcnow()
                db.session.commit()

                # ✅ Handle Remember Me functionality
                remember_me = form.remember_me.data if hasattr(form, 'remember_me') else False
                login_user(user, remember=remember_me)
                
                logger.info(f"User logged in: {username} (Remember Me: {remember_me})")

                if user.first_login:
                    flash(
                        "Welcome Beta Tester! You've been given 5000 credits as a signup bonus.",
                        "success"
                    )
                    user.first_login = False
                    db.session.commit()
                else:
                    if remember_me:
                        flash('Login successful! You will stay logged in for 30 days.', 'success')
                    else:
                        flash('Login successful!', 'success')

                # Redirect to next_page if provided and safe, otherwise to dashboard
                if next_page:
                    return redirect(next_page)
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
                        return redirect(url_for('auth.login', next=next_page))
                    
                    db.session.commit()

                logger.warning(f"Failed login attempt for username: {username} (attempt {user.failed_login_attempts if user else 'unknown'})")
                flash('Invalid username or password.', 'danger')
        
        except Exception as e:
            logger.error(f"Login error: {str(e)}", exc_info=True)
            flash('An error occurred during login. Please try again.', 'danger')
    
    return render_template('login.html', form=form, next_page=next_page)


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

    from datetime import datetime, timedelta
    
    # Calculate days since ban
    ban_date = current_user.ban_date
    if ban_date:
        days_since_ban = (datetime.utcnow() - ban_date).days
    else:
        days_since_ban = 0

    return render_template(
        'banned.html',
        reason=current_user.ban_reason,
        unban_requested=current_user.unban_requested,
        appeal_message=current_user.appeal_message,
        ban_date=current_user.ban_date,
        unban_request_date=current_user.unban_request_date,
        username=current_user.username,
        user_email=current_user.email,
        days_since_ban=days_since_ban
    )


@auth_bp.route('/request_unban', methods=['POST'])
@login_required
def request_unban():
    from app import db
    from datetime import datetime
    
    if not current_user.is_banned:
        flash("You are not banned.", "info")
        return redirect(url_for('user.dashboard'))

    # Get appeal message from form
    appeal_message = request.form.get('appeal_message', '').strip()
    
    if not appeal_message:
        flash('Please provide an explanation for your unban request.', 'warning')
        return redirect(url_for('auth.banned'))

    if len(appeal_message) < 20:
        flash('Your appeal message must be at least 20 characters long.', 'warning')
        return redirect(url_for('auth.banned'))

    if len(appeal_message) > 2000:
        flash('Your appeal message cannot exceed 2000 characters.', 'warning')
        return redirect(url_for('auth.banned'))

    try:
        # Always update/save the appeal message and date
        current_user.unban_requested = True
        current_user.unban_request_date = datetime.utcnow()
        current_user.appeal_message = appeal_message
        db.session.commit()
        
        flash('Your unban appeal has been submitted. Our team will review it within 3-5 business days.', 'success')
        logger.info(f"Unban appeal submitted - User ID: {current_user.id}, Username: {current_user.username}, Message length: {len(appeal_message)}")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error submitting unban appeal for user {current_user.id}: {str(e)}", exc_info=True)
        flash('An error occurred while submitting your appeal. Please try again.', 'danger')

    return redirect(url_for('auth.banned'))
