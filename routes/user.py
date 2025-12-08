from flask import Blueprint, render_template, request, flash, redirect, url_for, send_file
from flask_login import login_required, current_user, logout_user
import os
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash

from app import db, app
from models import Item, Trade, Notification, CreditTransaction, User, ItemImage, Order, OrderItem
from forms import UploadItemForm, ProfileUpdateForm, ChangePasswordForm, DeleteAccountForm
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
        
        # Generate referral code if not exists
        if not current_user.referral_code:
            current_user.generate_referral_code()
            db.session.commit()
        
        credits = current_user.credits
        item_count = Item.query.filter_by(user_id=current_user.id).count()
        pending_trades = Trade.query.filter(
            db.or_(Trade.sender_id == current_user.id, Trade.receiver_id == current_user.id),
            Trade.status == 'pending'
        ).count()

        recent_notifications = Notification.query.filter_by(user_id=current_user.id).order_by(
            Notification.timestamp.desc()
        ).limit(3).all()
        
        # Calculate profile completion percentage
        profile_fields = [
            current_user.email,
            current_user.phone_number,
            current_user.address,
            current_user.city,
            current_user.state,
            current_user.profile_picture
        ]
        profile_completion = int((sum(1 for field in profile_fields if field) / len(profile_fields)) * 100)
        
        # Calculate trading goals
        completed_trades = Trade.query.filter(
            db.or_(Trade.sender_id == current_user.id, Trade.receiver_id == current_user.id),
            Trade.status == 'completed'
        ).count()
        
        # Orders placed (purchasing goal)
        orders_placed = Order.query.filter_by(user_id=current_user.id).count()
        
        # Get similar items (recommendations) - get 2 most recent items from users with similar trades
        similar_items = Item.query.filter(
            Item.user_id != current_user.id,
            Item.status == 'available'
        ).order_by(Item.id.desc()).limit(2).all()
        
        # Calculate progress percentages for widgets
        upload_progress = min(item_count * 10, 100)
        trading_progress = min((completed_trades + orders_placed) * 5, 100)
        
        # Calculate SVG offsets for progress rings (stroke-dasharray circumference = 163.36 for r=16)
        profile_offset = 163.36 * (1 - profile_completion / 100)
        upload_offset = 163.36 * (1 - upload_progress / 100)
        trading_offset = 163.36 * (1 - trading_progress / 100)
        
        logger.info(f"User dashboard loaded - User: {current_user.username}, Credits: {credits}, Items: {item_count}")

        return render_template(
            'dashboard.html',
            user=current_user,
            credits=credits,
            item_count=item_count,
            pending_trades=pending_trades,
            recent_notifications=recent_notifications,
            profile_completion=profile_completion,
            completed_trades=completed_trades,
            orders_placed=orders_placed,
            upload_progress=upload_progress,
            trading_progress=trading_progress,
            profile_offset=profile_offset,
            upload_offset=upload_offset,
            trading_offset=trading_offset,
            similar_items=similar_items
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
        # Get items uploaded by the user, excluding items that were purchased (in OrderItem)
        items = Item.query.filter_by(user_id=current_user.id).filter(
            ~Item.id.in_(db.session.query(OrderItem.item_id))
        ).order_by(Item.id.desc()).paginate(page=page, per_page=10)
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


# ==================== SETTINGS ROUTES ====================

@user_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@handle_errors
def settings():
    """Central settings page for profile, password, and account management"""
    try:
        profile_form = ProfileUpdateForm(obj=current_user)
        password_form = ChangePasswordForm()
        delete_form = DeleteAccountForm()
        
        # Handle form submissions
        if request.method == 'POST':
            form_type = request.form.get('form_type')
            
            # ========== PROFILE UPDATE ==========
            if form_type == 'profile':
                current_user.email = request.form['email']
                current_user.phone_number = request.form['phone_number']
                current_user.address = request.form['address']
                current_user.city = request.form['city']
                current_user.state = request.form['state']
                
                if profile_form.profile_picture.data:
                    file = profile_form.profile_picture.data
                    if file.filename:
                        try:
                            validate_upload(file, max_size=5*1024*1024, allowed_extensions=app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif'}))
                            unique_filename = generate_safe_filename(file, current_user.id)
                            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                            file.save(file_path)
                            current_user.profile_picture = f"/{file_path}"
                            logger.info(f"Profile picture updated - User: {current_user.username}, File: {unique_filename}")
                        except FileUploadError as e:
                            logger.warning(f"Profile picture upload failed: {str(e)}")
                            flash(f"Profile picture upload failed: {str(e)}", 'danger')
                            return redirect(url_for('user.settings'))
                else:
                    current_user.profile_picture = None
                
                db.session.commit()
                logger.info(f"Profile updated successfully - User: {current_user.username}, Email: {current_user.email}")
                flash('✅ Profile updated successfully', 'success')
                return redirect(url_for('user.settings'))
            
            # ========== PASSWORD CHANGE ==========
            elif form_type == 'password':
                current_password = request.form.get('current_password')
                new_password = request.form.get('new_password')
                confirm_password = request.form.get('confirm_password')
                
                # Validate current password
                if not check_password_hash(current_user.password_hash, current_password):
                    flash('❌ Current password is incorrect', 'danger')
                    return redirect(url_for('user.settings'))
                
                # Validate new password
                if len(new_password) < 8:
                    flash('❌ New password must be at least 8 characters long', 'danger')
                    return redirect(url_for('user.settings'))
                
                # Check passwords match
                if new_password != confirm_password:
                    flash('❌ New passwords do not match', 'danger')
                    return redirect(url_for('user.settings'))
                
                # Check new password is different from current
                if check_password_hash(current_user.password_hash, new_password):
                    flash('❌ New password must be different from current password', 'danger')
                    return redirect(url_for('user.settings'))
                
                # Update password
                current_user.password_hash = generate_password_hash(new_password)
                db.session.commit()
                logger.info(f"Password changed successfully - User: {current_user.username}")
                flash('✅ Password changed successfully', 'success')
                return redirect(url_for('user.settings'))
            
            # ========== ACCOUNT DELETION ==========
            elif form_type == 'delete':
                confirm_delete = request.form.get('confirm_delete')
                confirm_username = request.form.get('confirm_username')
                
                # Validate confirmation
                if not confirm_delete or confirm_delete != 'on':
                    flash('❌ You must confirm account deletion', 'danger')
                    return redirect(url_for('user.settings'))
                
                if confirm_username != current_user.username:
                    flash(f'❌ Username does not match. Please type "{current_user.username}"', 'danger')
                    return redirect(url_for('user.settings'))
                
                # Capture user info before deletion
                username = current_user.username
                user_email = current_user.email
                user_id = current_user.id
                
                # Send goodbye email
                try:
                    from routes.auth import send_email_async
                    goodbye_html = f"""
                    <html>
                        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                                <h2 style="color: #ff7a00; margin-bottom: 20px;">👋 We'll Miss You!</h2>
                                
                                <p style="font-size: 16px;">Hi <strong>{username}</strong>,</p>
                                
                                <p style="font-size: 16px;">
                                    Your Barterex account has been successfully deleted. All your personal information, 
                                    items, trades, and transactions have been permanently removed from our system.
                                </p>
                                
                                <div style="background: #f8fafc; padding: 20px; border-left: 4px solid #ff7a00; margin: 20px 0;">
                                    <h3 style="margin-top: 0; color: #054e97;">What was deleted:</h3>
                                    <ul style="margin: 0; padding-left: 20px;">
                                        <li>Profile information and settings</li>
                                        <li>All uploaded items</li>
                                        <li>Trading history and transactions</li>
                                        <li>Orders and credit balance</li>
                                        <li>Notifications and preferences</li>
                                    </ul>
                                </div>
                                
                                <p style="font-size: 16px;">
                                    If this was a mistake or you'd like to create a new account, you're welcome to 
                                    <a href="{url_for('auth.register', _external=True)}" style="color: #ff7a00; text-decoration: none; font-weight: bold;">register again anytime</a>.
                                </p>
                                
                                <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 30px 0;">
                                
                                <p style="font-size: 14px; color: #64748b;">
                                    We appreciate you being part of the Barterex community. If you have any feedback 
                                    about your experience, feel free to reach out to us at 
                                    <a href="mailto:info.barterex@gmail.com" style="color: #ff7a00; text-decoration: none;">info.barterex@gmail.com</a>.
                                </p>
                                
                                <p style="font-size: 14px; color: #64748b;">
                                    Best regards,<br>
                                    <strong>The Barterex Team</strong>
                                </p>
                            </div>
                        </body>
                    </html>
                    """
                    
                    send_email_async(
                        subject='Goodbye from Barterex - Account Deleted',
                        recipients=[user_email],
                        html_body=goodbye_html
                    )
                    logger.info(f"Goodbye email sent to {user_email} for deleted account {username}")
                except Exception as e:
                    logger.warning(f"Failed to send goodbye email: {str(e)}")
                
                # Delete related data
                Item.query.filter_by(user_id=user_id).delete()
                Trade.query.filter((Trade.sender_id == user_id) | (Trade.receiver_id == user_id)).delete()
                Notification.query.filter_by(user_id=user_id).delete()
                CreditTransaction.query.filter_by(user_id=user_id).delete()
                Order.query.filter_by(user_id=user_id).delete()
                
                # Delete user
                db.session.delete(current_user)
                db.session.commit()
                
                logger.warning(f"Account deleted - User: {username} (ID: {user_id})")
                logout_user()
                flash('Account deleted successfully. Redirecting to marketplace...', 'success')
                return redirect(url_for('marketplace.marketplace'))
        
        return render_template('settings.html', 
                             profile_form=profile_form,
                             password_form=password_form,
                             delete_form=delete_form,
                             user=current_user)
        
    except Exception as e:
        logger.error(f"Error in settings for user {current_user.username}: {str(e)}", exc_info=True)
        flash('An error occurred. Please try again.', 'danger')
        return redirect(url_for('user.dashboard'))
