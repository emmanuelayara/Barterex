from flask import Blueprint, render_template, redirect, url_for, request, session, flash, send_file
from flask_wtf.csrf import generate_csrf
from functools import wraps
from datetime import datetime
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import func
import json
import csv
import io
import zipfile

from app import db
from models import Admin, User, Item, Order, OrderItem, PickupStation, Notification, SystemSettings, ActivityLog
from forms import AdminRegisterForm, AdminLoginForm, PickupStationForm
from werkzeug.security import generate_password_hash, check_password_hash
from logger_config import setup_logger
from exceptions import ValidationError, DatabaseError, AuthenticationError, AuthorizationError
from error_handlers import handle_errors, safe_database_operation

logger = setup_logger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# ==================== DECORATORS ====================

def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Please log in as admin.', 'warning')
            return redirect(url_for('admin.admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# ==================== CONTEXT PROCESSOR ====================

@admin_bp.context_processor
def inject_admin_context():
    """Inject admin-wide context variables into all admin templates"""
    try:
        # Get count of pending items
        pending_items_count = Item.query.filter_by(status='pending').count()
        return dict(pending_items_count=pending_items_count)
    except Exception as e:
        logger.error(f"Error in admin context processor: {str(e)}")
        return dict(pending_items_count=0)

# ==================== ROUTES ====================

@admin_bp.route('/register', methods=['GET', 'POST'])
@handle_errors
def admin_register():
    try:
        form = AdminRegisterForm()

        if form.validate_on_submit():
            username = form.username.data
            email = form.email.data
            password = form.password.data

            # Check if admin already exists
            existing_admin = Admin.query.filter_by(email=email).first()
            if existing_admin:
                logger.warning(f"Admin registration attempt with existing email: {email}")
                raise ValidationError("An admin with this email already exists", field="email")

            hashed_password = generate_password_hash(password)

            new_admin = Admin(username=username, email=email, password=hashed_password)
            db.session.add(new_admin)
            db.session.commit()

            logger.info(f"New admin registered: {username}")
            flash('Admin registered successfully!', 'success')
            return redirect(url_for('admin.admin_login'))

        return render_template('admin/register.html', form=form)
        
    except ValidationError as e:
        logger.warning(f"Admin registration error: {str(e)}")
        flash(str(e.message), 'danger')
        return render_template('admin/register.html', form=form)


@admin_bp.route('/login', methods=['GET', 'POST'])
@handle_errors
def admin_login():
    try:
        from datetime import datetime, timedelta
        
        form = AdminLoginForm()
        
        if form.validate_on_submit():
            email = form.email.data
            password = form.password.data

            admin = Admin.query.filter_by(email=email).first()
            
            # Check if account is locked
            if admin and admin.account_locked_until and datetime.utcnow() < admin.account_locked_until:
                remaining_time = (admin.account_locked_until - datetime.utcnow()).total_seconds() / 60
                logger.warning(f"Locked admin account login attempt: {email}")
                flash(f'Admin account temporarily locked. Try again in {int(remaining_time)} minutes.', 'danger')
                return render_template('admin/login.html', form=form)
            
            if admin and check_password_hash(admin.password, password):
                # Successful login - reset failed attempts
                admin.failed_login_attempts = 0
                admin.account_locked_until = None
                db.session.commit()
                
                session['admin_id'] = admin.id
                logger.info(f"Admin logged in successfully: {admin.username}")
                flash('Logged in successfully!', 'success')
                return redirect(url_for('admin.admin_dashboard'))
            else:
                # Failed login attempt
                if admin:
                    admin.failed_login_attempts = admin.failed_login_attempts + 1
                    
                    # Lock account after 5 failed attempts
                    if admin.failed_login_attempts >= 5:
                        admin.account_locked_until = datetime.utcnow() + timedelta(minutes=15)
                        db.session.commit()
                        logger.warning(f"Admin account locked: {email} after 5 failed attempts")
                        flash('Admin account locked due to too many failed attempts. Try again in 15 minutes.', 'danger')
                        return render_template('admin/login.html', form=form)
                    
                    db.session.commit()
                
                logger.warning(f"Failed admin login attempt - Email: {email} (attempt {admin.failed_login_attempts if admin else 'unknown'})")
                flash('Invalid email or password', 'danger')
        
        return render_template('admin/login.html', form=form)
        
    except Exception as e:
        logger.error(f"Admin login error: {str(e)}", exc_info=True)
        flash('An error occurred during login. Please try again.', 'danger')
        return render_template('admin/login.html')


@admin_bp.route('/logout')
def admin_logout():
    admin_id = session.get('admin_id')
    session.pop('admin_id', None)
    if admin_id:
        logger.info(f"Admin logged out - Admin ID: {admin_id}")
    flash('Logged out successfully', 'info')
    return redirect(url_for('admin.admin_login'))


@admin_bp.route('/dashboard')
@admin_login_required
@handle_errors
def admin_dashboard():
    try:
        page = request.args.get('page', 1, type=int)
        search = request.args.get('search', '').strip()
        status = request.args.get('status', 'pending')

        # CRITICAL: Validate search input to prevent SQL injection
        # SQLAlchemy's ilike() provides protection, but we add defense-in-depth
        if search:
            # Limit search length to prevent DoS attacks
            if len(search) > 100:
                logger.warning(f"Search input exceeds maximum length - Length: {len(search)}, Value: {search[:50]}...")
                search = search[:100]
            
            # Check for suspicious patterns (SQL keywords, special chars)
            suspicious_patterns = ['--', '/*', '*/', 'union', 'select', 'insert', 'delete', 'drop', ';', '\\x00']
            search_lower = search.lower()
            if any(pattern in search_lower for pattern in suspicious_patterns):
                logger.warning(f"Suspicious search pattern detected - Value: {search}")
                flash("Invalid search characters detected.", "warning")
                search = ""  # Clear search to prevent exploitation

        query = Item.query.options(joinedload(Item.user))

        if status != 'all':
            query = query.filter(Item.status == status)

        if search:
            # CRITICAL: Use ilike() with proper parameter binding to prevent SQL injection
            # ilike() automatically escapes the search term and uses parameterized queries
            search_term = f"%{search}%"
            query = query.join(User).filter(
                (Item.name.ilike(search_term)) | (User.username.ilike(search_term)) | (Item.item_number == search)
            )

        items = query.order_by(Item.id.desc()).paginate(page=page, per_page=10)

        total_users = User.query.count()
        total_items = Item.query.count()
        approved_items = Item.query.filter_by(status='approved').count()
        pending_items = Item.query.filter_by(status='pending').count()
        rejected_items = Item.query.filter_by(status='rejected').count()
        traded_items = Item.query.filter_by(is_available=False).count()
        total_credits_traded = db.session.query(db.func.sum(Item.value)).filter_by(is_available=False).scalar() or 0

        logger.info(f"Admin dashboard accessed - Page: {page}, Search: '{search}', Status: {status}")

        return render_template(
            'admin/dashboard.html',
            items=items,
            total_users=total_users,
            total_items=total_items,
            approved_items=approved_items,
            pending_items=pending_items,
            rejected_items=rejected_items,
            traded_items=traded_items,
            total_credits_traded=total_credits_traded,
            search=search,
            status=status
        )
        
    except Exception as e:
        logger.error(f"Error loading admin dashboard: {str(e)}", exc_info=True)
        flash('An error occurred while loading the dashboard.', 'danger')
        return redirect(url_for('admin.admin_login'))


@admin_bp.route('/users')
@admin_login_required
@handle_errors
def manage_users():
    try:
        users = User.query.all()
        unban_requests = User.query.filter_by(unban_requested=True, is_banned=True).all()
        banned_users = User.query.filter_by(is_banned=True).all()
        logger.info(f"User management page accessed - Total users: {len(users)}, Banned: {len(banned_users)}")
        return render_template('admin/users.html', users=users, unban_requests=unban_requests,
            banned_users=banned_users, csrf_token=generate_csrf)
    except Exception as e:
        logger.error(f"Error loading user management: {str(e)}", exc_info=True)
        flash('An error occurred while loading users.', 'danger')
        return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/view_user/<int:user_id>')
@admin_login_required
@handle_errors
def view_user(user_id):
    try:
        from datetime import datetime, timedelta
        from sqlalchemy import func
        
        user = User.query.get_or_404(user_id)
        
        # Item statistics
        items_uploaded = Item.query.filter_by(user_id=user.id).count()
        items_approved = Item.query.filter_by(user_id=user.id, is_approved=True).count()
        items_pending = Item.query.filter_by(user_id=user.id, is_approved=False, status='pending').count()
        items_rejected = Item.query.filter_by(user_id=user.id, status='rejected').count()
        items_traded = Item.query.filter_by(user_id=user.id, is_available=False).count()
        
        # Account age calculation
        account_created = user.created_at
        account_age = datetime.utcnow() - account_created
        account_age_days = account_age.days
        if account_age_days < 1:
            account_age_str = "Less than 1 day old"
        elif account_age_days == 1:
            account_age_str = "1 day old"
        elif account_age_days < 7:
            account_age_str = f"{account_age_days} days old"
        elif account_age_days < 30:
            weeks = account_age_days // 7
            account_age_str = f"{weeks} week{'s' if weeks > 1 else ''} old"
        else:
            months = account_age_days // 30
            account_age_str = f"{months} month{'s' if months > 1 else ''} old"
        
        # Order/Trade statistics - Orders placed by this user
        orders_placed = Order.query.filter_by(user_id=user.id).count()
        orders_completed = Order.query.filter_by(user_id=user.id, status='Delivered').count()
        
        # Orders received - when user's items were sold to someone else
        # This is tracked through OrderItems - items they uploaded that were in completed orders
        user_items_sold = db.session.query(func.count(OrderItem.id)).join(
            Item, OrderItem.item_id == Item.id
        ).filter(
            Item.user_id == user.id,
            Order.status == 'Delivered'
        ).join(Order, OrderItem.order_id == Order.id).scalar() or 0
        
        # Trade completion rate
        trade_completion_rate = 0
        if orders_placed > 0:
            trade_completion_rate = round((orders_completed / orders_placed) * 100, 1)
        
        # Email verification status
        email_verified = user.email_verified
        
        # Last login info
        last_login = user.last_login
        if last_login:
            last_login_ago = datetime.utcnow() - last_login
            if last_login_ago.days == 0:
                last_login_str = "Today"
            elif last_login_ago.days == 1:
                last_login_str = "Yesterday"
            elif last_login_ago.days < 7:
                last_login_str = f"{last_login_ago.days} days ago"
            else:
                last_login_str = last_login.strftime('%Y-%m-%d %H:%M')
        else:
            last_login_str = "Never"
        
        # User rating/score
        user_rating = getattr(user, 'rating', None) or 5.0  # Default to 5.0 if not available
        
        logger.info(f"User profile viewed - User ID: {user_id}, Username: {user.username}")
        
        return render_template('admin/view_user.html', 
                             user=user,
                             items_uploaded=items_uploaded,
                             items_approved=items_approved,
                             items_pending=items_pending,
                             items_rejected=items_rejected,
                             items_traded=items_traded,
                             account_age_str=account_age_str,
                             account_age_days=account_age_days,
                             email_verified=email_verified,
                             last_login=last_login,
                             last_login_str=last_login_str,
                             orders_placed=orders_placed,
                             orders_sold=user_items_sold,
                             orders_completed=orders_completed,
                             total_orders=orders_placed + user_items_sold,
                             trade_completion_rate=trade_completion_rate,
                             user_rating=user_rating)
    except Exception as e:
        logger.error(f"Error viewing user {user_id}: {str(e)}", exc_info=True)
        flash('An error occurred while loading the user profile.', 'danger')
        return redirect(url_for('admin.manage_users'))


@admin_bp.route('/ban_user/<int:user_id>', methods=['POST'])
@admin_login_required
@handle_errors
@safe_database_operation("ban_user")
def ban_user(user_id):
    try:
        from routes.auth import send_email_async
        
        user = User.query.get_or_404(user_id)

        if user.id == session.get('admin_id'):
            logger.warning(f"Admin attempted self-ban - Admin ID: {session.get('admin_id')}")
            flash("You can't ban yourself.", 'danger')
            return redirect(url_for('admin.manage_users'))

        reason = request.form.get('ban_reason')
        if not reason.strip():
            logger.warning(f"Ban attempted without reason - User ID: {user_id}, Admin ID: {session.get('admin_id')}")
            raise ValidationError("You must provide a reason for banning this user", field="ban_reason")

        user.is_banned = True
        user.ban_reason = reason
        logger.warning(f"User banned - User ID: {user_id}, Username: {user.username}, Reason: {reason}, Admin ID: {session.get('admin_id')}")

        # Send ban notification email
        try:
            html_body = render_template('emails/account_banned.html', 
                                      username=user.username,
                                      reason=reason)
            send_email_async(
                subject="Your account has been banned",
                recipients=[user.email],
                html_body=html_body
            )
            logger.info(f"Ban notification email sent - User ID: {user_id}, Email: {user.email}")
        except Exception as e:
            logger.error(f"Error sending ban email: {str(e)}", exc_info=True)
            # Don't fail the ban process if email fails
        
        # Log to audit log
        try:
            from audit_logger import log_user_ban
            log_user_ban(user_id, user.username, reason)
        except Exception as e:
            logger.error(f"Error logging ban to audit log: {str(e)}", exc_info=True)

        flash(f'User {user.username} has been banned.', 'warning')
        return redirect(url_for('admin.manage_users'))
        
    except ValidationError as e:
        logger.warning(f"Validation error during ban: {str(e)}")
        flash(str(e.message), 'danger')
        return redirect(url_for('admin.manage_users'))


@admin_bp.route('/banned_users')
@admin_login_required
@handle_errors
def admin_banned_users():
    try:
        users = User.query.all()
        banned_users = User.query.filter_by(is_banned=True).all()
        logger.info(f"Banned users list accessed - Total banned: {len(banned_users)}")
        return render_template('admin/users.html', users=users, banned_users=banned_users, csrf_token=generate_csrf)
    except Exception as e:
        logger.error(f"Error loading banned users: {str(e)}", exc_info=True)
        flash('An error occurred while loading banned users.', 'danger')
        return redirect(url_for('admin.manage_users'))


@admin_bp.route('/unban_user/<int:user_id>', methods=['POST'])
@admin_login_required
@handle_errors
@safe_database_operation("unban_user")
def unban_user(user_id):
    try:
        from routes.auth import send_email_async
        
        user = User.query.get_or_404(user_id)
        user.is_banned = False
        user.ban_reason = None
        user.unban_requested = False
        logger.info(f"User unbanned - User ID: {user_id}, Username: {user.username}, Admin ID: {session.get('admin_id')}")

        # Send unban notification email
        try:
            html_body = render_template('emails/account_unbanned.html', 
                                      username=user.username)
            send_email_async(
                subject="Your account has been restored",
                recipients=[user.email],
                html_body=html_body
            )
            logger.info(f"Unban notification email sent - User ID: {user_id}, Email: {user.email}")
        except Exception as e:
            logger.error(f"Error sending unban email: {str(e)}", exc_info=True)
            # Don't fail the unban process if email fails

        flash(f"{user.username} has been unbanned.", "success")
        return redirect(url_for('admin.admin_banned_users'))
        
    except Exception as e:
        logger.error(f"Error unbanning user {user_id}: {str(e)}", exc_info=True)
        flash('An error occurred while unbanning the user.', 'danger')
        return redirect(url_for('admin.admin_banned_users'))


@admin_bp.route('/approve_unban/<int:user_id>', methods=['POST'])
@admin_login_required
@handle_errors
@safe_database_operation("approve_unban")
def approve_unban(user_id):
    try:
        from routes.auth import send_email_async
        
        user = User.query.get_or_404(user_id)
        if user.is_banned:
            user.is_banned = False
            user.unban_requested = False
            user.ban_reason = None
            logger.info(f"Unban request approved - User ID: {user_id}, Username: {user.username}, Admin ID: {session.get('admin_id')}")
            
            # Send unban notification email
            try:
                html_body = render_template('emails/account_unbanned.html', 
                                          username=user.username)
                send_email_async(
                    subject="Your account has been restored",
                    recipients=[user.email],
                    html_body=html_body
                )
                logger.info(f"Unban approval email sent - User ID: {user_id}, Email: {user.email}")
            except Exception as e:
                logger.error(f"Error sending unban approval email: {str(e)}", exc_info=True)
                # Don't fail the unban process if email fails
            
            flash(f'User {user.username} has been unbanned.', 'success')
        return redirect(url_for('admin.manage_users'))
        
    except Exception as e:
        logger.error(f"Error approving unban for user {user_id}: {str(e)}", exc_info=True)
        flash('An error occurred while approving the unban request.', 'danger')
        return redirect(url_for('admin.manage_users'))


@admin_bp.route('/reject_unban/<int:user_id>', methods=['POST'])
@admin_login_required
@handle_errors
@safe_database_operation("reject_unban")
def reject_unban(user_id):
    try:
        user = User.query.get_or_404(user_id)
        if user.is_banned and user.unban_requested:
            user.unban_requested = False
            logger.info(f"Unban request rejected - User ID: {user_id}, Username: {user.username}, Admin ID: {session.get('admin_id')}")
            flash(f'User {user.username}\'s unban request has been rejected.', 'danger')
        return redirect(url_for('admin.manage_users'))
        
    except Exception as e:
        logger.error(f"Error rejecting unban for user {user_id}: {str(e)}", exc_info=True)
        flash('An error occurred while rejecting the unban request.', 'danger')
        return redirect(url_for('admin.manage_users'))


@admin_bp.route('/delete_user/<int:user_id>', methods=['POST'])
@admin_login_required
@handle_errors
@safe_database_operation("delete_user")
def delete_user(user_id):
    try:
        user = User.query.get_or_404(user_id)
        username = user.username
        
        # Prevent admin from deleting themselves
        if user.id == session.get('admin_id'):
            logger.warning(f"Admin attempted self-deletion - Admin ID: {session.get('admin_id')}")
            flash("You cannot delete your own admin account.", 'danger')
            return redirect(url_for('admin.manage_users'))
        
        # Get user's items for cleanup
        user_items = Item.query.filter_by(user_id=user.id).all()
        
        # Delete user and cascade delete related data
        # This will automatically delete items, orders, notifications, etc. due to cascade rules
        db.session.delete(user)
        db.session.commit()
        
        logger.warning(f"User account deleted - User ID: {user_id}, Username: {username}, Items: {len(user_items)}, Admin ID: {session.get('admin_id')}")
        flash(f'User account "{username}" has been permanently deleted along with all associated data.', 'success')
        return redirect(url_for('admin.manage_users'))
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting user {user_id}: {str(e)}", exc_info=True)
        flash('An error occurred while deleting the user account.', 'danger')
        return redirect(url_for('admin.manage_users'))


@admin_bp.route('/user/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_login_required
@handle_errors
@safe_database_operation("edit_user")
def edit_user(user_id):
    try:
        user = User.query.get_or_404(user_id)

        if request.method == 'POST':
            new_credits = request.form.get('credits', type=int)
            if new_credits is None or new_credits < 0:
                logger.warning(f"Invalid credit amount provided - User ID: {user_id}, Credits: {new_credits}, Admin ID: {session.get('admin_id')}")
                raise ValidationError("Credits must be a non-negative number", field="credits")
            
            old_credits = user.credits
            user.credits = new_credits
            logger.info(f"User credits updated - User ID: {user_id}, Old: {old_credits}, New: {new_credits}, Admin ID: {session.get('admin_id')}")
            flash(f"{user.username}'s credits updated from {old_credits} to {new_credits}.", "success")
            return redirect(url_for('admin.manage_users'))

        return render_template('edit_user.html', user=user)
        
    except ValidationError as e:
        logger.warning(f"Validation error editing user: {str(e)}")
        flash(str(e.message), 'danger')
        return render_template('edit_user.html', user=user)


@admin_bp.route('/approvals')
@admin_login_required
@handle_errors
def approve_items():
    try:
        items = Item.query.filter_by(status='pending').all()
        pending_count = Item.query.filter_by(status='pending').count()
        logger.info(f"Item approvals page accessed - Pending items: {len(items)}, Count query: {pending_count}")
        
        # Debug: Log all item statuses to understand database state
        all_items = Item.query.all()
        status_breakdown = {}
        for item in all_items:
            status = item.status
            if status not in status_breakdown:
                status_breakdown[status] = 0
            status_breakdown[status] += 1
        logger.debug(f"Database status breakdown: {status_breakdown}")
        
        return render_template('admin/approvals.html', items=items)
    except Exception as e:
        logger.error(f"Error loading approvals page: {str(e)}", exc_info=True)
        flash('An error occurred while loading approvals.', 'danger')
        return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/approve/<int:item_id>', methods=['POST'])
@admin_login_required
@handle_errors
@safe_database_operation("approve_item")
def approve_item(item_id):
    from trading_points import award_points_for_upload, create_level_up_notification
    from referral_rewards import award_referral_bonus
    from audit_logger import log_item_approval
    
    try:
        item = Item.query.get_or_404(item_id)

        # CRITICAL: Check if item is already approved to prevent double-crediting
        if item.is_approved:
            logger.warning(f"Attempted to approve already-approved item - Item ID: {item_id}, Name: {item.name}, Admin ID: {session.get('admin_id')}")
            flash(f"Item '{item.name}' is already approved.", "info")
            return redirect(url_for('admin.approve_items'))

        # Validate and parse item value
        try:
            value = float(request.form['value'])
            if value <= 0:
                raise ValueError("Value must be positive")
        except ValueError:
            logger.warning(f"Invalid item value provided - Item ID: {item_id}, Value: {request.form.get('value')}, Admin ID: {session.get('admin_id')}")
            raise ValidationError("Item value must be a positive number", field="value")
            
        # Update item approval status
        item.value = value
        item.is_approved = True
        item.is_available = True
        item.status = 'approved'

        # Award credits to user (only once, since we checked is_approved above)
        item.user.credits += int(value)
        # Mark item as modified to ensure changes persist through subsequent operations
        flag_modified(item, 'status')
        flag_modified(item, 'is_approved')
        flag_modified(item, 'is_available')
        flag_modified(item, 'value')
        
        # Log to audit log
        log_item_approval(item_id, item.name, value)
        
        logger.info(f"Item approved - Item ID: {item_id}, Name: {item.name}, Value: {value}, User Credits: {item.user.credits}, Admin ID: {session.get('admin_id')}")
        
        # CRITICAL: Detach item from session to prevent it from being reloaded by subsequent flushes
        # in award_points_for_upload and award_referral_bonus functions
        db.session.expunge(item)

        # Award trading points for upload approval
        level_up_info = award_points_for_upload(item.user, item.name)
        
        # Award referral bonus if user was referred
        referral_result = award_referral_bonus(item.user_id, 'item_upload', amount=100)
        if referral_result['success']:
            logger.info(f"Referral bonus awarded: {referral_result['message']}")
        
        # Re-attach item to session after award operations
        # Merge reattaches the item with all its changes intact
        item = db.session.merge(item)
        
        # Create level up notification and send email if applicable
        if level_up_info:
            create_level_up_notification(item.user, level_up_info)
            notification = Notification(
                user_id=item.user_id,
                message=f"🎉 Your item '{item.name}' has been approved! You earned 10 trading points. "
                        f"New Balance: ₦{item.user.credits:,} credits. "
                        f"Congratulations on reaching Level {level_up_info['new_level']} ({level_up_info['new_tier']})! "
                        f"You earned {level_up_info['credits_awarded']} bonus credits. Keep trading!"
            )
        else:
            notification = Notification(
                user_id=item.user_id,
                message=f"🎉 Your item '{item.name}' has been approved for ₦{item.value} credits! "
                        f"You earned 10 trading points. New Balance: ₦{item.user.credits:,} credits. "
                        f"Keep using Barterex for seamless trading."
            )
        
        db.session.add(notification)
        flash(f"Item '{item.name}' approved with value {value} credits.", "success")
        
    except ValidationError as e:
        logger.warning(f"Validation error approving item: {str(e)}")
        flash(str(e.message), 'danger')
        raise  # Re-raise so decorator knows to rollback

    return redirect(url_for('admin.approve_items'))


@admin_bp.route('/reject/<int:item_id>', methods=['POST'])
@admin_login_required
@handle_errors
@safe_database_operation("reject_item")
def reject_item(item_id):
    try:
        from audit_logger import log_item_rejection
        
        item = Item.query.get_or_404(item_id)
        reason = request.form.get("rejection_reason", "").strip()

        if not reason:
            logger.warning(f"Item rejection without reason - Item ID: {item_id}, Admin ID: {session.get('admin_id')}")
            raise ValidationError("You must provide a rejection reason", field="rejection_reason")

        item.is_approved = False
        item.is_available = False
        item.status = 'rejected'
        item.rejection_reason = reason

        logger.info(f"Item rejected - Item ID: {item_id}, Name: {item.name}, Reason: {reason}, Admin ID: {session.get('admin_id')}")
        
        # Log to audit log
        log_item_rejection(item_id, item.name, reason)
        
        # Send rejection email to user
        try:
            from flask_mail import Message
            from app import mail
            
            user = item.user
            subject = f"Item '{item.name}' Rejection Notice"
            
            html_body = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                    .item-details {{ background-color: #fff3cd; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid #ffc107; }}
                    .reason {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                    .footer {{ color: #6c757d; font-size: 12px; text-align: center; margin-top: 30px; }}
                    h2 {{ color: #dc3545; }}
                    .btn {{ display: inline-block; padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px; margin-top: 15px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>Item Rejection Notice</h2>
                        <p>Hello {user.username},</p>
                        <p>Your item listing has been reviewed and unfortunately was not approved for the marketplace.</p>
                    </div>
                    
                    <div class="item-details">
                        <h3>Item Details:</h3>
                        <p><strong>Item:</strong> {item.name}</p>
                        <p><strong>Item #:</strong> {item.item_number}</p>
                    </div>
                    
                    <div class="reason">
                        <h3>Rejection Reason:</h3>
                        <p>{reason}</p>
                    </div>
                    
                    <div style="margin-top: 20px;">
                        <h3>What You Can Do:</h3>
                        <ul>
                            <li>Review the feedback and make necessary improvements to your item listing</li>
                            <li>Update your item with better images, clearer description, or more accurate information</li>
                            <li>Resubmit your item for review once improvements are made</li>
                            <li>Contact our support team if you have questions about this decision</li>
                        </ul>
                    </div>
                    
                    <p style="margin-top: 30px;">
                        <a href="{{{{ url_for('items.upload_item', _external=True) }}}}" class="btn">Upload Another Item</a>
                    </p>
                    
                    <div class="footer">
                        <p>This is an automated message from Barter Express. Please do not reply to this email.</p>
                        <p>If you believe this is an error, please contact our support team.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            msg = Message(
                subject=subject,
                recipients=[user.email],
                html=html_body
            )
            mail.send(msg)
            logger.info(f"Rejection email sent to user - User ID: {user.id}, Email: {user.email}, Item ID: {item_id}")
            
        except Exception as e:
            logger.error(f"Error sending rejection email: {str(e)}", exc_info=True)
            # Don't raise - email failure shouldn't block the rejection
        
        # Create notification for user
        notification = Notification(
            user_id=item.user_id,
            message=f"❌ Your item '{item.name}' was not approved. Reason: {reason}. "
                    f"Please review the feedback and resubmit with improvements."
        )
        db.session.add(notification)
        
        flash(f'Item rejected. Reason: {reason}', 'warning')
        
    except ValidationError as e:
        logger.warning(f"Validation error rejecting item: {str(e)}")
        flash(str(e.message), 'danger')
        raise  # Re-raise so decorator knows to rollback

    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/update-status', methods=['POST'])
@admin_login_required
@handle_errors
@safe_database_operation("update_item_status")
def update_item_status():
    try:
        item_id = request.form.get('item_id')
        new_status = request.form.get('status')

        item = Item.query.get_or_404(item_id)
        item.status = new_status
        logger.info(f"Item status updated - Item ID: {item_id}, Name: {item.name}, New Status: {new_status}, Admin ID: {session.get('admin_id')}")

        flash(f"Item '{item.name}' has been marked as {new_status}.", "success")
        return redirect(url_for('admin.admin_dashboard', status='pending'))
        
    except Exception as e:
        logger.error(f"Error updating item status: {str(e)}", exc_info=True)
        flash('An error occurred while updating the item status.', 'danger')
        return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/fix-status', methods=['POST'])
@admin_login_required
@handle_errors
@safe_database_operation("fix_misclassified_items")
def fix_misclassified_items():
    try:
        items_to_fix = Item.query.filter(Item.is_approved == True, Item.status == 'pending').all()
        count = 0

        for item in items_to_fix:
            item.status = 'approved'
            count += 1

        logger.info(f"Fixed misclassified items - Count: {count}, Admin ID: {session.get('admin_id')}")
        flash(f"{count} item(s) with approved status were moved from 'pending' to 'approved'.", "info")
        return redirect(url_for('admin.admin_dashboard', status='approved'))
        
    except Exception as e:
        logger.error(f"Error fixing misclassified items: {str(e)}", exc_info=True)
        flash('An error occurred while fixing items.', 'danger')
        return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/fix-missing-credits', methods=['POST'])
@admin_login_required
@handle_errors
@safe_database_operation("fix_missing_credits")
def fix_missing_credits():
    try:
        items_to_fix = Item.query.filter(
            Item.is_approved == True,
            Item.credited == False,
            Item.is_available == True
        ).all()

        count = 0
        total_credits = 0
        for item in items_to_fix:
            if item.user:
                item.user.credits += item.value or 0
                total_credits += item.value or 0
                item.credited = True
                count += 1

        logger.info(f"Fixed missing credits - Items: {count}, Total Credits: {total_credits}, Admin ID: {session.get('admin_id')}")
        flash(f"{count} item(s) were fixed and {total_credits} credits added to users.", "success")
        return redirect(url_for('admin.admin_dashboard'))
        
    except Exception as e:
        logger.error(f"Error fixing missing credits: {str(e)}", exc_info=True)
        flash('An error occurred while fixing credits.', 'danger')
        return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/pickup-stations/add', methods=['GET', 'POST'])
@admin_login_required
@handle_errors
@safe_database_operation("add_pickup_station")
def add_pickup_station():
    try:
        form = PickupStationForm()
        if form.validate_on_submit():
            station = PickupStation(
                name=form.name.data,
                address=form.address.data,
                state=form.state.data,
                city=form.city.data
            )
            db.session.add(station)
            logger.info(f"Pickup station added - Name: {station.name}, State: {station.state}, Admin ID: {session.get('admin_id')}")
            flash("Pickup station added successfully!", "success")
            return redirect(url_for('admin.manage_pickup_stations'))

        stations = PickupStation.query.all()
        return render_template(
            "admin/manage_pickup_stations.html",
            form=form,
            stations=stations
        )
        
    except Exception as e:
        logger.error(f"Error adding pickup station: {str(e)}", exc_info=True)
        flash('An error occurred while adding the pickup station.', 'danger')
        return redirect(url_for('admin.manage_pickup_stations'))


@admin_bp.route('/pickup_stations/edit/<int:station_id>', methods=['GET', 'POST'])
@admin_login_required
@handle_errors
@safe_database_operation("edit_pickup_station")
def edit_pickup_station(station_id):
    try:
        station = PickupStation.query.get_or_404(station_id)
        form = PickupStationForm(obj=station)

        if form.validate_on_submit():
            station.name = form.name.data
            station.address = form.address.data
            station.city = form.city.data
            station.state = form.state.data
            logger.info(f"Pickup station updated - ID: {station_id}, Name: {station.name}, Admin ID: {session.get('admin_id')}")
            flash('Pickup station updated successfully!', 'success')
            return redirect(url_for('admin.manage_pickup_stations'))

        return render_template(
            'admin/edit_pickup_station.html',
            form=form,
            station=station
        )
        
    except Exception as e:
        logger.error(f"Error editing pickup station {station_id}: {str(e)}", exc_info=True)
        flash('An error occurred while editing the pickup station.', 'danger')
        return redirect(url_for('admin.manage_pickup_stations'))


@admin_bp.route('/pickup_stations/delete/<int:station_id>', methods=['POST'])
@admin_login_required
@handle_errors
@safe_database_operation("delete_pickup_station")
def delete_pickup_station(station_id):
    try:
        station = PickupStation.query.get_or_404(station_id)
        station_name = station.name
        db.session.delete(station)
        logger.info(f"Pickup station deleted - ID: {station_id}, Name: {station_name}, Admin ID: {session.get('admin_id')}")
        flash('Pickup Station deleted successfully!', 'danger')
        return redirect(url_for('admin.manage_pickup_stations'))
        
    except Exception as e:
        logger.error(f"Error deleting pickup station {station_id}: {str(e)}", exc_info=True)
        flash('An error occurred while deleting the pickup station.', 'danger')
        return redirect(url_for('admin.manage_pickup_stations'))


@admin_bp.route('/pickup-stations', methods=['GET'])
@admin_login_required
@handle_errors
def manage_pickup_stations():
    try:
        form = PickupStationForm()
        stations = PickupStation.query.all()
        logger.info(f"Pickup stations management page accessed - Total stations: {len(stations)}")
        return render_template(
            "admin/manage_pickup_stations.html",
            form=form,
            stations=stations
        )
    except Exception as e:
        logger.error(f"Error loading pickup stations: {str(e)}", exc_info=True)
        flash('An error occurred while loading pickup stations.', 'danger')
        return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/manage_orders')
@admin_login_required
@handle_errors
def manage_orders():
    try:
        orders = Order.query.order_by(Order.date_ordered.desc()).all()
        items = Item.query.all()
        logger.info(f"Order management page accessed - Total orders: {len(orders)}")
        return render_template('admin/manage_orders.html', orders=orders, items=items)
    except Exception as e:
        logger.error(f"Error loading orders management: {str(e)}", exc_info=True)
        flash('An error occurred while loading orders.', 'danger')
        return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/update_order_status/<int:order_id>', methods=['POST'])
@admin_login_required
@handle_errors
@safe_database_operation("update_order_status")
def update_order_status(order_id):
    try:
        from trading_points import award_points_for_purchase, create_level_up_notification
        
        order = Order.query.get_or_404(order_id)
        old_status = order.status
        
        if order.status == "Pending":
            order.status = "Shipped"
        elif order.status == "Shipped":
            order.status = "Out for Delivery"
        elif order.status == "Out for Delivery":
            order.status = "Delivered"

        item_names = ", ".join([f"{oi.item.name}" for oi in order.items])

        status_messages = {
            "Shipped": f"Your order for {item_names} has been shipped.",
            "Out for Delivery": f"Your order for {item_names} is out for delivery.",
            "Delivered": f"Your order for {item_names} has been delivered. 🎉",
        }

        note = Notification(
            user_id=order.user_id,
            message=status_messages.get(order.status, f"Order status updated to {order.status}")
        )
        db.session.add(note)
        
        # Award points when order is delivered
        if order.status == "Delivered" and old_status != "Delivered":
            user = order.user
            level_up_info = award_points_for_purchase(user, order.order_number)
            
            # Create level up notification if applicable
            if level_up_info:
                create_level_up_notification(user, level_up_info)
                # Add bonus to the status notification
                note.message = (
                    f"{status_messages.get(order.status, f'Order status updated to {order.status}')} "
                    f"🎉 You earned 20 trading points and reached Level {level_up_info['new_level']} ({level_up_info['new_tier']})! "
                    f"Bonus reward: {level_up_info['credits_awarded']} credits added!"
                )
            else:
                # Add points earned message if no level up
                note.message = f"{status_messages.get(order.status, f'Order status updated to {order.status}')} You earned 20 trading points!"
            
            db.session.add(note)

        logger.info(f"Order status updated - Order ID: {order_id}, New Status: {order.status}, Admin ID: {session.get('admin_id')}")
        flash(f"Order status updated to {order.status}", "success")
        return redirect(url_for('admin.manage_orders'))
        
    except Exception as e:
        logger.error(f"Error updating order status: {str(e)}", exc_info=True)
        flash('An error occurred while updating the order status.', 'danger')
        return redirect(url_for('admin.manage_orders'))


@admin_bp.route('/audit-log', methods=['GET'])
@admin_login_required
@handle_errors
def audit_log():
    """Display admin activity audit log with filters"""
    try:
        from models import AuditLog, User
        from datetime import datetime, timedelta
        import csv
        from io import StringIO
        
        # Get filter parameters
        admin_id = request.args.get('admin_id', type=int)
        action_type = request.args.get('action_type')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        export = request.args.get('export')  # CSV export flag
        
        # Build query
        query = AuditLog.query
        
        if admin_id:
            query = query.filter_by(admin_id=admin_id)
        
        if action_type:
            query = query.filter_by(action_type=action_type)
        
        if date_from:
            try:
                from_date = datetime.strptime(date_from, '%Y-%m-%d')
                query = query.filter(AuditLog.timestamp >= from_date)
            except ValueError:
                pass
        
        if date_to:
            try:
                to_date = datetime.strptime(date_to, '%Y-%m-%d')
                to_date = to_date.replace(hour=23, minute=59, second=59)
                query = query.filter(AuditLog.timestamp <= to_date)
            except ValueError:
                pass
        
        # Order by newest first
        audit_logs = query.order_by(AuditLog.timestamp.desc()).all()
        
        # Get unique admins for filter dropdown
        admins = User.query.filter(User.is_admin == True).order_by(User.username).all()
        
        # Get unique action types
        action_types_query = db.session.query(AuditLog.action_type.distinct()).all()
        action_types = [a[0] for a in action_types_query if a[0]]
        action_types.sort()
        
        # CSV Export
        if export == 'csv':
            output = StringIO()
            writer = csv.writer(output)
            
            # Header
            writer.writerow([
                'Timestamp',
                'Admin',
                'Action',
                'Target Type',
                'Target ID',
                'Target Name',
                'Description',
                'Reason',
                'Before Value',
                'After Value',
                'IP Address'
            ])
            
            # Rows
            for log in audit_logs:
                writer.writerow([
                    log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    log.admin.username if log.admin else 'Unknown',
                    log.action_type,
                    log.target_type,
                    log.target_id or '',
                    log.target_name or '',
                    log.description or '',
                    log.reason or '',
                    log.before_value or '',
                    log.after_value or '',
                    log.ip_address or ''
                ])
            
            # Return CSV response
            from flask import make_response
            response = make_response(output.getvalue())
            response.headers['Content-Disposition'] = f'attachment; filename=audit_log_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            response.headers['Content-Type'] = 'text/csv'
            return response
        
        logger.info(f"Audit log viewed - Admin: {session.get('admin_id')}, Filters: admin_id={admin_id}, action={action_type}, date_range={date_from} to {date_to}")
        
        return render_template(
            'admin/audit_log.html',
            audit_logs=audit_logs,
            admins=admins,
            action_types=action_types,
            selected_admin_id=admin_id,
            selected_action_type=action_type,
            date_from=date_from,
            date_to=date_to,
            total_logs=len(audit_logs)
        )
        
    except Exception as e:
        logger.error(f"Error viewing audit log: {str(e)}", exc_info=True)
        flash('An error occurred while loading the audit log.', 'danger')
        return redirect(url_for('admin.admin_dashboard'))


# ==================== MAINTENANCE MODE ====================

@admin_bp.route('/maintenance', methods=['GET', 'POST'])
@admin_login_required
@handle_errors
def maintenance_mode():
    """Manage system maintenance mode"""
    try:
        settings = SystemSettings.get_settings()
        admin = Admin.query.get(session.get('admin_id'))
        
        if request.method == 'POST':
            action = request.form.get('action')
            
            if action == 'enable':
                settings.maintenance_mode = True
                settings.maintenance_message = request.form.get('message', settings.maintenance_message)
                settings.maintenance_enabled_by = admin.id
                settings.maintenance_enabled_at = datetime.utcnow()
                
                logger.warning(f"Maintenance mode ENABLED by Admin {admin.username} (ID: {admin.id}). Message: {settings.maintenance_message}")
                flash('Maintenance mode enabled. Users will see the maintenance message.', 'warning')
                
                # Log to audit log
                try:
                    from audit_logger import log_audit_action
                    log_audit_action(
                        action_type='maintenance_enabled',
                        target_type='system',
                        target_id=1,
                        target_name='Platform',
                        description=f'Maintenance mode enabled',
                        reason=settings.maintenance_message
                    )
                except Exception as e:
                    logger.error(f"Error logging maintenance enable: {str(e)}")
                
            elif action == 'disable':
                settings.maintenance_mode = False
                logger.warning(f"Maintenance mode DISABLED by Admin {admin.username} (ID: {admin.id})")
                flash('Maintenance mode disabled. Platform is now operational.', 'success')
                
                # Log to audit log
                try:
                    from audit_logger import log_audit_action
                    log_audit_action(
                        action_type='maintenance_disabled',
                        target_type='system',
                        target_id=1,
                        target_name='Platform',
                        description=f'Maintenance mode disabled'
                    )
                except Exception as e:
                    logger.error(f"Error logging maintenance disable: {str(e)}")
            
            db.session.commit()
            return redirect(url_for('admin.maintenance_mode'))
        
        return render_template('admin/maintenance.html', 
                             settings=settings,
                             csrf_token=generate_csrf)
        
    except Exception as e:
        logger.error(f"Error managing maintenance mode: {str(e)}", exc_info=True)
        flash('An error occurred while managing maintenance mode.', 'danger')
        return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/system_settings', methods=['GET', 'POST'])
@admin_login_required
@handle_errors
def system_settings():
    """Manage system-wide settings"""
    try:
        settings = SystemSettings.get_settings()
        admin = Admin.query.get(session.get('admin_id'))
        
        if request.method == 'POST':
            # Update feature flags
            settings.allow_uploads = request.form.get('allow_uploads') == 'on'
            settings.allow_trading = request.form.get('allow_trading') == 'on'
            settings.allow_browsing = request.form.get('allow_browsing') == 'on'
            
            logger.info(f"System settings updated by Admin {admin.username}. "
                       f"Allow uploads: {settings.allow_uploads}, "
                       f"Allow trading: {settings.allow_trading}, "
                       f"Allow browsing: {settings.allow_browsing}")
            
            # Log to audit log
            try:
                from audit_logger import log_audit_action
                log_audit_action(
                    action_type='system_settings_updated',
                    target_type='system',
                    target_id=1,
                    target_name='Platform Settings',
                    description='System settings updated',
                    after_value={
                        'allow_uploads': settings.allow_uploads,
                        'allow_trading': settings.allow_trading,
                        'allow_browsing': settings.allow_browsing
                    }
                )
            except Exception as e:
                logger.error(f"Error logging settings update: {str(e)}")
            
            db.session.commit()
            flash('System settings updated successfully.', 'success')
            return redirect(url_for('admin.system_settings'))
        
        return render_template('admin/system_settings.html', 
                             settings=settings,
                             csrf_token=generate_csrf)
        
    except Exception as e:
        logger.error(f"Error managing system settings: {str(e)}", exc_info=True)
        flash('An error occurred while managing system settings.', 'danger')
        return redirect(url_for('admin.admin_dashboard'))


# ==================== USER DATA EXPORT (GDPR) ====================

@admin_bp.route('/user/<int:user_id>/export', methods=['GET'])
@admin_login_required
@handle_errors
def export_user_data(user_id):
    """Export all user data as ZIP file (GDPR compliance)"""
    try:
        from models import CreditTransaction
        
        user = User.query.get_or_404(user_id)
        admin = Admin.query.get(session.get('admin_id'))
        
        # Create ZIP file in memory
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            
            # 1. USER PROFILE DATA
            profile_data = {
                'User ID': user.id,
                'Username': user.username,
                'Email': user.email,
                'Phone': user.phone_number,
                'Address': user.address,
                'City': user.city,
                'State': user.state,
                'Account Created': user.created_at.isoformat() if user.created_at else None,
                'Last Login': user.last_login.isoformat() if user.last_login else None,
                'Account Status': 'Banned' if user.is_banned else 'Active',
                'Ban Reason': user.ban_reason if user.is_banned else None,
                'Email Verified': user.email_verified,
                'Level': user.level,
                'Tier': user.tier,
                'Trading Points': user.trading_points,
                'Credits': user.credits,
                'Two-Factor Enabled': user.two_factor_enabled,
                'GDPR Consent Date': user.gdpr_consent_date.isoformat() if user.gdpr_consent_date else None,
            }
            
            profile_json = json.dumps(profile_data, indent=2)
            zip_file.writestr('01_user_profile.json', profile_json)
            
            # 2. ITEMS LISTING
            items = Item.query.filter_by(user_id=user_id).all()
            items_data = []
            
            for item in items:
                items_data.append({
                    'Item ID': item.id,
                    'Name': item.name,
                    'Item Number': item.item_number,
                    'Description': item.description,
                    'Category': item.category,
                    'Status': item.status,
                    'Is Approved': item.is_approved,
                    'Is Available': item.is_available,
                    'Created At': item.created_at.isoformat() if item.created_at else None,
                    'Rejection Reason': item.rejection_reason if item.status == 'rejected' else None,
                })
            
            items_csv = io.StringIO()
            if items_data:
                writer = csv.DictWriter(items_csv, fieldnames=items_data[0].keys())
                writer.writeheader()
                writer.writerows(items_data)
            else:
                items_csv.write('No items found for this user.')
            
            zip_file.writestr('02_items_listing.csv', items_csv.getvalue())
            
            # 3. TRADING HISTORY
            orders = Order.query.filter_by(user_id=user_id).all()
            trading_data = []
            
            for order in orders:
                trading_data.append({
                    'Order ID': order.id,
                    'Status': order.status,
                    'Total Price': order.total_price,
                    'Created At': order.created_at.isoformat() if order.created_at else None,
                    'Updated At': order.updated_at.isoformat() if order.updated_at else None,
                    'Number of Items': len(order.order_items) if order.order_items else 0,
                })
            
            trading_csv = io.StringIO()
            if trading_data:
                writer = csv.DictWriter(trading_csv, fieldnames=trading_data[0].keys())
                writer.writeheader()
                writer.writerows(trading_data)
            else:
                trading_csv.write('No trading history found for this user.')
            
            zip_file.writestr('03_trading_history.csv', trading_csv.getvalue())
            
            # 4. ACCOUNT ACTIVITY / LOGIN HISTORY
            activity_logs = ActivityLog.query.filter_by(user_id=user_id).order_by(ActivityLog.timestamp.desc()).all()
            activity_data = []
            
            for log in activity_logs:
                activity_data.append({
                    'Timestamp': log.timestamp.isoformat() if log.timestamp else None,
                    'Action': log.action,
                    'Details': log.details,
                    'IP Address': log.ip_address,
                })
            
            activity_csv = io.StringIO()
            if activity_data:
                writer = csv.DictWriter(activity_csv, fieldnames=activity_data[0].keys())
                writer.writeheader()
                writer.writerows(activity_data)
            else:
                activity_csv.write('No activity logs found for this user.')
            
            zip_file.writestr('04_activity_history.csv', activity_csv.getvalue())
            
            # 5. CREDIT TRANSACTIONS
            transactions = CreditTransaction.query.filter_by(user_id=user_id).order_by(CreditTransaction.created_at.desc()).all()
            credits_data = []
            
            for trans in transactions:
                credits_data.append({
                    'Transaction ID': trans.id,
                    'Amount': trans.amount,
                    'Type': trans.type,
                    'Description': trans.description,
                    'Reason': trans.reason,
                    'Balance Before': trans.balance_before,
                    'Balance After': trans.balance_after,
                    'Created At': trans.created_at.isoformat() if trans.created_at else None,
                })
            
            credits_csv = io.StringIO()
            if credits_data:
                writer = csv.DictWriter(credits_csv, fieldnames=credits_data[0].keys())
                writer.writeheader()
                writer.writerows(credits_data)
            else:
                credits_csv.write('No credit transactions found for this user.')
            
            zip_file.writestr('05_credit_transactions.csv', credits_csv.getvalue())
            
            # 6. EXPORT METADATA
            metadata = {
                'Export Date': datetime.utcnow().isoformat(),
                'Exported By Admin': admin.username if admin else 'Unknown',
                'User ID': user.id,
                'Username': user.username,
                'Email': user.email,
                'Total Items': len(items),
                'Total Orders': len(orders),
                'Total Activity Logs': len(activity_logs),
                'Total Transactions': len(transactions),
                'Purpose': 'GDPR Data Export Request',
            }
            
            metadata_json = json.dumps(metadata, indent=2)
            zip_file.writestr('00_EXPORT_METADATA.json', metadata_json)
        
        # Prepare ZIP file for download
        zip_buffer.seek(0)
        
        # Log the export action
        logger.warning(f"User data exported - User ID: {user_id}, Username: {user.username}, "
                      f"Exported by Admin: {admin.username}, IP: {request.remote_addr}")
        
        # Log to audit log
        try:
            from audit_logger import log_audit_action
            log_audit_action(
                action_type='user_data_exported',
                target_type='user',
                target_id=user_id,
                target_name=user.username,
                description=f'User data exported as ZIP file',
                reason='GDPR data export request'
            )
        except Exception as e:
            logger.error(f"Error logging data export: {str(e)}")
        
        # Return ZIP file
        filename = f'user_data_{user.username}_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.zip'
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        logger.error(f"Error exporting user data for user {user_id}: {str(e)}", exc_info=True)
        flash('An error occurred while exporting user data.', 'danger')
        return redirect(url_for('admin.manage_users'))
