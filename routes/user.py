from flask import Blueprint, render_template, request, flash, redirect, url_for, send_file
from flask_login import login_required, current_user, logout_user
import os
from werkzeug.utils import secure_filename

from app import db, app
from models import Item, Trade, Notification, CreditTransaction, User, ItemImage, Order
from forms import UploadItemForm, ProfileUpdateForm
from logger_config import setup_logger
from exceptions import ResourceNotFoundError, ValidationError, AuthorizationError, FileUploadError
from error_handlers import handle_errors, safe_database_operation
from transaction_clarity import generate_pdf_receipt, generate_transaction_explanation
from file_upload_validator import validate_upload, generate_safe_filename

logger = setup_logger(__name__)

user_bp = Blueprint('user', __name__)

# ==================== HELPER FUNCTIONS ====================

# allowed_file is now replaced by validate_upload() from file_upload_validator

# ==================== ROUTES ====================

@user_bp.route('/dashboard')
@login_required
@handle_errors
def dashboard():
    try:
        if current_user.is_banned:
            logger.warning(f"Banned user attempted to access dashboard: {current_user.username}")
            flash('Your account has been banned.', 'danger')
            logout_user()
            return redirect(url_for('auth.login'))
        
        credits = current_user.credits
        item_count = Item.query.filter_by(user_id=current_user.id).count()
        pending_trades = Trade.query.filter(
            db.or_(Trade.sender_id == current_user.id, Trade.receiver_id == current_user.id),
            Trade.status == 'pending'
        ).count()

        recent_notifications = Notification.query.filter_by(user_id=current_user.id).order_by(
            Notification.timestamp.desc()
        ).limit(5).all()

        logger.info(f"User dashboard loaded - User: {current_user.username}, Credits: {credits}, Items: {item_count}")

        return render_template(
            'dashboard.html',
            user=current_user,
            credits=credits,
            item_count=item_count,
            pending_trades=pending_trades,
            recent_notifications=recent_notifications
        )
    except Exception as e:
        logger.error(f"Error loading dashboard for user {current_user.username}: {str(e)}", exc_info=True)
        flash('An error occurred while loading your dashboard.', 'danger')
        return redirect(url_for('marketplace.home'))


@user_bp.route('/user-items')
@login_required
@handle_errors
def user_items():
    try:
        page = request.args.get('page', 1, type=int)
        items = Item.query.filter_by(user_id=current_user.id).order_by(Item.id.desc()).paginate(page=page, per_page=10)
        logger.info(f"User items page accessed - User: {current_user.username}, Items: {items.total}")
        return render_template('user_items.html', items=items)
    except Exception as e:
        logger.error(f"Error loading user items for {current_user.username}: {str(e)}", exc_info=True)
        flash('An error occurred while loading your items.', 'danger')
        return redirect(url_for('user.dashboard'))


@user_bp.route('/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
@handle_errors
@safe_database_operation("edit_item")
def edit_item(item_id):
    try:
        item = Item.query.get_or_404(item_id)
        
        if item.user_id != current_user.id:
            logger.warning(f"Unauthorized edit attempt - User: {current_user.username}, Item: {item_id}")
            raise AuthorizationError("You do not have permission to edit this item")

        if item.is_approved:
            logger.info(f"Edit denied for approved item - User: {current_user.username}, Item: {item_id}")
            flash("This item has already been approved by the admin and cannot be edited.", "warning")
            return redirect(url_for('user.dashboard'))

        form = UploadItemForm(obj=item)

        if form.validate_on_submit():
            item.name = form.name.data
            item.description = form.description.data
            item.condition = form.condition.data
            item.category = form.category.data

            # Handle image if provided
            if form.images.data and len(form.images.data) > 0:
                file = form.images.data[0]
                if file and file.filename:
                    try:
                        # Comprehensive file upload validation
                        validate_upload(file, max_size=10*1024*1024, allowed_extensions=app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif'}))
                        
                        if item.image_url:
                            old_path = os.path.join(app.root_path, item.image_url.strip("/"))
                            if os.path.exists(old_path):
                                os.remove(old_path)

                        unique_filename = generate_safe_filename(file, current_user.id)
                        new_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                        file.save(new_path)
                        item.image_url = f"/{new_path}"
                        logger.info(f"Item image updated - Item: {item_id}, File: {unique_filename}")
                    except FileUploadError as e:
                        logger.warning(f"File validation failed: {str(e)}")
                        flash(f"Image upload failed: {str(e)}", 'danger')

            logger.info(f"Item updated successfully - Item: {item_id}, User: {current_user.username}")
            flash("Item updated successfully!", "success")
            return redirect(url_for('user.user_items', item_id=item.id))

        return render_template('edit_item.html', form=form, item=item)
        
    except AuthorizationError as e:
        logger.warning(f"Authorization error in edit_item: {str(e)}")
        flash(str(e.message), 'danger')
        return redirect(url_for('user.dashboard'))


@user_bp.route('/my-trades')
@login_required
@handle_errors
def my_trades():
    try:
        page = request.args.get('page', 1, type=int)
        sent_trades = Trade.query.filter_by(sender_id=current_user.id).order_by(Trade.timestamp.desc()).paginate(page=page, per_page=9)
        received_trades = Trade.query.filter_by(receiver_id=current_user.id).order_by(Trade.timestamp.desc()).paginate(page=page, per_page=9)
        
        logger.info(f"Trades page accessed - User: {current_user.username}, Sent: {sent_trades.total}, Received: {received_trades.total}")
        return render_template('my_trades.html', sent_trades=sent_trades, received_trades=received_trades)
    except Exception as e:
        logger.error(f"Error loading trades for user {current_user.username}: {str(e)}", exc_info=True)
        flash('An error occurred while loading your trades.', 'danger')
        return redirect(url_for('user.dashboard'))


@user_bp.route('/credit-history')
@login_required
@handle_errors
def credit_history():
    try:
        history = CreditTransaction.query.filter_by(user_id=current_user.id).order_by(CreditTransaction.id.desc()).all()
        logger.info(f"Credit history accessed - User: {current_user.username}, Transactions: {len(history)}")
        return render_template('credit_history.html', history=history)
    except Exception as e:
        logger.error(f"Error loading credit history for user {current_user.username}: {str(e)}", exc_info=True)
        flash('An error occurred while loading your credit history.', 'danger')
        return redirect(url_for('user.dashboard'))


@user_bp.route('/notifications')
@login_required
@handle_errors
def notifications():
    try:
        page = request.args.get('page', 1, type=int)
        filter_type = request.args.get('filter', 'unread')
        
        query = Notification.query.filter_by(user_id=current_user.id)
        
        if filter_type == 'unread':
            query = query.filter_by(is_read=False)
        elif filter_type == 'read':
            query = query.filter_by(is_read=True)
        
        notes = query.order_by(Notification.created_at.desc()).paginate(page=page, per_page=9)
        
        total_count = Notification.query.filter_by(user_id=current_user.id).count()
        unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        read_count = Notification.query.filter_by(user_id=current_user.id, is_read=True).count()
        
        logger.info(f"Notifications accessed - User: {current_user.username}, Total: {total_count}, Unread: {unread_count}, Filter: {filter_type}")
        
        return render_template(
            'notifications.html', 
            notifications=notes,
            current_filter=filter_type,
            total_count=total_count,
            unread_count=unread_count,
            read_count=read_count
        )
    except Exception as e:
        logger.error(f"Error loading notifications for user {current_user.username}: {str(e)}", exc_info=True)
        flash('An error occurred while loading your notifications.', 'danger')
        return redirect(url_for('user.dashboard'))


@user_bp.route('/notifications/mark_read/<int:note_id>', methods=['POST'])
@login_required
@handle_errors
@safe_database_operation("mark_notification_read")
def mark_notification_read(note_id):
    try:
        note = Notification.query.get_or_404(note_id)
        if note.user_id == current_user.id:
            note.is_read = True
            logger.info(f"Notification marked as read - Note ID: {note_id}, User: {current_user.username}")
        else:
            logger.warning(f"Unauthorized notification read attempt - Note ID: {note_id}, User: {current_user.username}")
        return redirect(url_for('user.notifications'))
    except Exception as e:
        logger.error(f"Error marking notification as read: {str(e)}", exc_info=True)
        flash('An error occurred while updating the notification.', 'danger')
        return redirect(url_for('user.notifications'))


@user_bp.route('/notification-settings')
@login_required
@handle_errors
def notification_settings():
    """Display notification preferences settings page."""
    try:
        logger.info(f"Notification settings accessed - User: {current_user.username}")
        return render_template('notification_settings.html', user=current_user)
    except Exception as e:
        logger.error(f"Error loading notification settings for user {current_user.username}: {str(e)}", exc_info=True)
        flash('An error occurred while loading notification settings.', 'danger')
        return redirect(url_for('user.dashboard'))


@user_bp.route('/profile-settings', methods=['GET', 'POST'])
@login_required
@handle_errors
@safe_database_operation("profile_settings")
def profile_settings():
    try:
        form = ProfileUpdateForm(obj=current_user)

        if request.method == 'POST':
            current_user.email = request.form['email']
            current_user.phone_number = request.form['phone_number']
            current_user.address = request.form['address']
            current_user.city = request.form['city']
            current_user.state = request.form['state']
            
            if form.profile_picture.data:
                file = form.profile_picture.data
                if file.filename:
                    try:
                        # Comprehensive file upload validation
                        validate_upload(file, max_size=5*1024*1024, allowed_extensions=app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif'}))
                        
                        unique_filename = generate_safe_filename(file, current_user.id)
                        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                        file.save(file_path)
                        current_user.profile_picture = f"/{file_path}"
                        logger.info(f"Profile picture updated - User: {current_user.username}, File: {unique_filename}")
                    except FileUploadError as e:
                        logger.warning(f"Profile picture upload failed: {str(e)}")
                        flash(f"Profile picture upload failed: {str(e)}", 'danger')
            else:
                current_user.profile_picture = None
            
            logger.info(f"Profile updated successfully - User: {current_user.username}, Email: {current_user.email}")
            flash('Profile updated successfully', 'success')
            return redirect(url_for('user.dashboard'))

        return render_template('profile_settings.html', user=current_user, form=form)
        
    except Exception as e:
        logger.error(f"Error updating profile for user {current_user.username}: {str(e)}", exc_info=True)
        flash('An error occurred while updating your profile.', 'danger')
        return redirect(url_for('user.dashboard'))


@user_bp.route('/my_orders')
@login_required
@handle_errors
def user_orders():
    try:
        from models import Order
        page = request.args.get('page', 1, type=int)
        orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.date_ordered.desc()).paginate(page=page, per_page=6)
        logger.info(f"User orders accessed - User: {current_user.username}, Orders: {orders.total}")
        return render_template('user_orders.html', orders=orders)
    except Exception as e:
        logger.error(f"Error loading orders for user {current_user.username}: {str(e)}", exc_info=True)
        flash('An error occurred while loading your orders.', 'danger')
        return redirect(url_for('user.dashboard'))


@user_bp.route('/order/<int:order_id>')
@login_required
@handle_errors
def view_order_details(order_id):
    """View detailed order information with transaction clarity"""
    try:
        order = Order.query.get_or_404(order_id)
        
        # Verify user owns this order
        if order.user_id != current_user.id:
            logger.warning(f"Unauthorized order access attempt - User: {current_user.username}, Order: {order_id}")
            raise AuthorizationError("You don't have access to this order")
        
        # Generate transaction explanation
        transaction_exp = generate_transaction_explanation(order, current_user)
        
        logger.info(f"Order details viewed - User: {current_user.username}, Order: {order_id}")
        return render_template('order_details.html', order=order, transaction_exp=transaction_exp)
    except AuthorizationError as e:
        logger.warning(f"Authorization error: {str(e)}")
        flash(str(e.message), 'danger')
        return redirect(url_for('user.user_orders'))
    except Exception as e:
        logger.error(f"Error loading order details: {str(e)}", exc_info=True)
        flash('An error occurred while loading order details.', 'danger')
        return redirect(url_for('user.user_orders'))


@user_bp.route('/order/<int:order_id>/download-receipt')
@login_required
@handle_errors
def download_receipt(order_id):
    """Download order receipt as PDF"""
    try:
        order = Order.query.get_or_404(order_id)
        
        # Verify user owns this order
        if order.user_id != current_user.id:
            logger.warning(f"Unauthorized receipt download attempt - User: {current_user.username}, Order: {order_id}")
            raise AuthorizationError("You don't have access to this order's receipt")
        
        # Generate PDF receipt
        pdf_buffer = generate_pdf_receipt(order, current_user)
        
        if pdf_buffer:
            # Mark receipt as downloaded
            order.receipt_downloaded = True
            db.session.commit()
            
            logger.info(f"Receipt downloaded - User: {current_user.username}, Order: {order_id}")
            
            return send_file(
                pdf_buffer,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f"Receipt-{order.order_number}.pdf"
            )
        else:
            flash('Error generating receipt. Please try again.', 'danger')
            return redirect(url_for('user.view_order_details', order_id=order_id))
    
    except AuthorizationError as e:
        logger.warning(f"Authorization error: {str(e)}")
        flash(str(e.message), 'danger')
        return redirect(url_for('user.user_orders'))
    except Exception as e:
        logger.error(f"Error downloading receipt: {str(e)}", exc_info=True)
        flash('An error occurred while downloading the receipt.', 'danger')
        return redirect(url_for('user.view_order_details', order_id=order_id))
