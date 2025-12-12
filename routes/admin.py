from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from flask_wtf.csrf import generate_csrf
from functools import wraps
from sqlalchemy.orm import joinedload

from app import db
from models import Admin, User, Item, Order, PickupStation, Notification
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

        query = Item.query.options(joinedload(Item.user))

        if status != 'all':
            query = query.filter(Item.status == status)

        if search:
            query = query.join(User).filter(
                (Item.name.ilike(f"%{search}%")) | (User.username.ilike(f"%{search}%")) | (Item.item_number == search)
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
        user = User.query.get_or_404(user_id)
        items_uploaded = Item.query.filter_by(user_id=user.id).count()
        items_traded = Item.query.filter_by(user_id=user.id, is_available=False).count()
        logger.info(f"User profile viewed - User ID: {user_id}, Username: {user.username}")
        return render_template('admin/view_user.html', user=user,
                               items_uploaded=items_uploaded,
                               items_traded=items_traded)
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
        user = User.query.get_or_404(user_id)
        user.is_banned = False
        user.ban_reason = None
        user.unban_requested = False
        logger.info(f"User unbanned - User ID: {user_id}, Username: {user.username}, Admin ID: {session.get('admin_id')}")

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
        user = User.query.get_or_404(user_id)
        if user.is_banned:
            user.is_banned = False
            user.unban_requested = False
            user.ban_reason = None
            logger.info(f"Unban request approved - User ID: {user_id}, Username: {user.username}, Admin ID: {session.get('admin_id')}")
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
        logger.info(f"Item approvals page accessed - Pending items: {len(items)}")
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
    try:
        from trading_points import award_points_for_upload, create_level_up_notification
        
        item = Item.query.get_or_404(item_id)

        try:
            value = float(request.form['value'])
            if value <= 0:
                raise ValueError("Value must be positive")
        except ValueError:
            logger.warning(f"Invalid item value provided - Item ID: {item_id}, Value: {request.form.get('value')}, Admin ID: {session.get('admin_id')}")
            raise ValidationError("Item value must be a positive number", field="value")
            
        item.value = value
        item.is_approved = True
        item.is_available = True
        item.status = 'approved'

        item.user.credits += int(value)
        logger.info(f"Item approved - Item ID: {item_id}, Name: {item.name}, Value: {value}, User Credits: {item.user.credits}, Admin ID: {session.get('admin_id')}")

        # Award trading points for upload approval
        level_up_info = award_points_for_upload(item.user, item.name)
        
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
        db.session.commit()

        flash(f"Item '{item.name}' approved with value {value} credits.", "success")
        
    except ValidationError as e:
        logger.warning(f"Validation error approving item: {str(e)}")
        flash(str(e.message), 'danger')

    return redirect(url_for('admin.approve_items'))


@admin_bp.route('/reject/<int:item_id>', methods=['POST'])
@admin_login_required
@handle_errors
@safe_database_operation("reject_item")
def reject_item(item_id):
    try:
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
        flash(f'Item rejected. Reason: {reason}', 'warning')
        return redirect(url_for('admin.admin_dashboard'))
        
    except ValidationError as e:
        logger.warning(f"Validation error rejecting item: {str(e)}")
        flash(str(e.message), 'danger')
        return redirect(url_for('admin.approve_items'))


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
