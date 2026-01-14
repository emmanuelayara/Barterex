from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify
from flask_login import login_required, current_user, logout_user
from flask_wtf.csrf import generate_csrf
import os
import time
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta

from app import db, app
from models import Item, ItemImage, Cart, CartItem, Trade, Order, OrderItem, PickupStation, Notification
from forms import UploadItemForm, OrderForm
from routes.auth import send_email_async
from logger_config import setup_logger
from exceptions import ValidationError, InsufficientCreditsError, ItemNotAvailableError, FileUploadError, DatabaseError, CheckoutError
from error_handlers import handle_errors, safe_database_operation, retry_operation
from transaction_clarity import calculate_estimated_delivery, generate_transaction_explanation
from file_upload_validator import validate_upload, generate_safe_filename
from trading_points import award_points_for_purchase, create_level_up_notification
from upload_validation_helper import (
    validate_upload_request, validate_image_type, validate_image_size, 
    validate_image_dimensions, get_user_friendly_error_message
)

# Import limiter - handle gracefully if not available
try:
    from app import limiter
except ImportError:
    limiter = None

# Helper decorator for conditional rate limiting
def rate_limit(limit_str):
    """Decorator that applies rate limiting if available, otherwise passes through"""
    def decorator(func):
        if limiter is not None:
            return limiter.limit(limit_str)(func)
        return func
    return decorator

logger = setup_logger(__name__)

items_bp = Blueprint('items', __name__)

# ==================== HELPER FUNCTIONS ====================

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif'})

def get_or_create_cart(user_id):
    cart = Cart.query.filter_by(user_id=user_id).first()
    if not cart:
        cart = Cart(user_id=user_id, created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        db.session.add(cart)
        db.session.commit()
    return cart

def create_notification(user_id, message):
    """Create notification and send email asynchronously"""
    from models import User
    
    notification = Notification(user_id=user_id, message=message)
    db.session.add(notification)
    db.session.commit()

    user = User.query.get(user_id)
    if user and user.email:
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .message {{ background: #f4f4f4; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>📬 New Notification from Barterex</h2>
                <div class="message">{message}</div>
                <p>Thanks for using Barterex!</p>
                <div class="footer">
                    <p>This is an automated message. Please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        send_email_async(
            subject="New notification from Barter Express",
            recipients=[user.email],
            html_body=html
        )

# ==================== ROUTES ====================

@items_bp.route('/upload', methods=['GET', 'POST'])
@login_required
@handle_errors
def upload_item():
    try:
        if current_user.is_banned:
            logger.warning(f"Banned user attempted to upload item: {current_user.username}")
            flash('Your account has been banned.', 'danger')
            logout_user()
            return redirect(url_for('auth.login'))

        # Check if user has completed their profile before allowing item upload
        if not current_user.is_profile_complete():
            incomplete_fields = current_user.get_incomplete_profile_fields()
            logger.warning(f"User with incomplete profile attempted to upload item: {current_user.username}, Missing: {incomplete_fields}")
            flash(f'Please complete your profile before uploading items. Missing: {", ".join(incomplete_fields)}', 'warning')
            return redirect(url_for('user.settings'))

        form = UploadItemForm()
        
        # Debug: Log what we received
        logger.info(f"Upload request received - User: {current_user.username}")
        logger.info(f"Request files: {list(request.files.keys())}")
        
        # Manual image validation before form.validate_on_submit()
        # because MultipleFileField has issues with form validation in AJAX submissions
        images_from_request = request.files.getlist('images')
        logger.info(f"Images from request: {len(images_from_request)} files")
        
        if images_from_request:
            for idx, img in enumerate(images_from_request):
                logger.info(f"  Image {idx}: name={img.filename}, type={img.content_type}, size={len(img.read())} bytes")
                img.seek(0)  # Reset file pointer
        
        # Validate images manually with user-friendly error messages
        allowed_extensions = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
        image_validation_errors = []
        
        if not images_from_request or len([f for f in images_from_request if f and f.filename]) == 0:
            image_validation_errors.append('Please upload at least one image so buyers can see your item.')
        else:
            # Check image count
            valid_images = [f for f in images_from_request if f and f.filename]
            if len(valid_images) > 6:
                image_validation_errors.append(
                    f'You\'ve uploaded {len(valid_images)} images, but the maximum is 6 images. '
                    f'Please remove {len(valid_images) - 6} image(s) and try again.'
                )
            
            # Check each image type
            for img_file in valid_images:
                is_valid, error_msg = validate_image_type(img_file.filename, allowed_extensions)
                if not is_valid:
                    image_validation_errors.append(error_msg)
                    logger.warning(f"Invalid file type rejected - File: {img_file.filename}")
        
        if image_validation_errors:
            for error in image_validation_errors:
                flash(error, 'danger')
        
        if form.validate_on_submit() and not image_validation_errors:
            new_item = Item(
                name=form.name.data,
                description=form.description.data,
                condition=form.condition.data,
                category=form.category.data,
                user_id=current_user.id,
                location=current_user.state,
                is_available=False,
                is_approved=False,
                status='pending'
            )
            db.session.add(new_item)
            db.session.flush()
            
            uploaded_images = []
            upload_error_occurred = False
            
            # Use images_from_request instead of form.images.data since AJAX FormData doesn't populate form fields properly
            if images_from_request:
                from image_analyzer import analyze_image_url
                import json
                
                for index, file in enumerate(images_from_request):
                    if file and file.filename:
                        try:
                            # First validate file type
                            is_valid, error_msg = validate_image_type(file.filename, allowed_extensions)
                            if not is_valid:
                                flash(error_msg, 'danger')
                                upload_error_occurred = True
                                continue
                            
                            # Check file size before full validation
                            file.seek(0, 2)  # Seek to end
                            file_size = file.tell()
                            file.seek(0)  # Reset
                            
                            is_valid, error_msg = validate_image_size(file_size, file.filename, max_size_mb=10)
                            if not is_valid:
                                flash(error_msg, 'danger')
                                upload_error_occurred = True
                                continue
                            
                            # Comprehensive file upload validation with STRICT security checks
                            try:
                                validate_upload(
                                    file, 
                                    max_size=app.config.get('FILE_UPLOAD_MAX_SIZE', 10*1024*1024),
                                    allowed_extensions=app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif', 'webp'}),
                                    enable_virus_scan=app.config.get('FILE_UPLOAD_ENABLE_VIRUS_SCAN', False)
                                )
                            except FileUploadError as e:
                                # Convert technical error to user-friendly message
                                user_message = get_user_friendly_error_message(str(e), 'images')
                                flash(user_message, 'danger')
                                logger.warning(f"File validation failed for user {current_user.username}: {str(e)}")
                                upload_error_occurred = True
                                continue
                            
                            unique_filename = generate_safe_filename(file, current_user.id, item_id=new_item.id, index=index)
                            image_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                            file.save(image_path)
                            
                            # Store ONLY the filename, not the full path - the image_url filter will construct the proper URL
                            image_url = unique_filename
                            
                            # Analyze image for metadata and quality issues (pass relative path)
                            analysis = analyze_image_url(image_url)
                            
                            # Validate image dimensions if available
                            if analysis.get('width') and analysis.get('height'):
                                is_valid, error_msg = validate_image_dimensions(
                                    analysis.get('width'),
                                    analysis.get('height'),
                                    file.filename,
                                    min_width=400,
                                    min_height=300
                                )
                                if not is_valid:
                                    # Log warning but don't block - just inform user
                                    logger.warning(f"Image dimension warning for {file.filename}: {error_msg}")
                            
                            item_image = ItemImage(
                                item_id=new_item.id,
                                image_url=image_url,
                                is_primary=(index == 0),
                                order_index=index,
                                width=analysis.get('width'),
                                height=analysis.get('height'),
                                file_size=analysis.get('file_size'),
                                quality_flags=json.dumps(analysis.get('quality_flags', []))
                            )
                            db.session.add(item_image)
                            uploaded_images.append(item_image)
                            logger.info(f"Image uploaded for item - Item: {new_item.id}, File: {unique_filename}, Size: {analysis.get('file_size')} bytes")
                        except Exception as e:
                            db.session.rollback()
                            logger.error(f"Error uploading image: {str(e)}", exc_info=True)
                            user_message = get_user_friendly_error_message(str(e), 'images')
                            flash(user_message, 'danger')
                            upload_error_occurred = True
                            continue
            
            # If any images failed to upload, abort the entire transaction
            if upload_error_occurred:
                db.session.rollback()
                logger.warning(f"Item upload aborted due to image errors - User: {current_user.username}")
                return redirect(url_for('items.upload_item'))
            
            if not uploaded_images:
                db.session.rollback()
                flash('No images were successfully uploaded. Please try again.', 'danger')
                return redirect(url_for('items.upload_item'))
            
            if uploaded_images:
                new_item.image_url = uploaded_images[0].image_url
            
            try:
                db.session.commit()
                logger.info(f"Item submitted for approval - Item: {new_item.id}, User: {current_user.username}, Images: {len(uploaded_images)}")
                flash(f'✅ Success! Your item has been submitted for approval with {len(uploaded_images)} image(s). We\'ll review it shortly.', "success")
                return redirect(url_for('marketplace.marketplace'))
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error committing item upload: {str(e)}", exc_info=True)
                flash('There was a problem saving your item. Please try again.', 'danger')
                return redirect(url_for('items.upload_item'))
        else:
            # Log form validation errors and show user-friendly messages
            if form.errors:
                logger.warning(f"Form validation failed for user {current_user.username}: {form.errors}")
                for field, errors in form.errors.items():
                    for error in errors:
                        # Show user-friendly field names
                        field_names = {
                            'name': 'Item Name',
                            'description': 'Item Description',
                            'condition': 'Item Condition',
                            'category': 'Item Category'
                        }
                        field_display = field_names.get(field, field)
                        flash(f"{field_display}: {error}", "danger")

        return render_template('upload.html', form=form)
        
    except (FileUploadError, DatabaseError) as e:
        logger.warning(f"Upload error: {str(e)}")
        user_message = get_user_friendly_error_message(str(e))
        flash(user_message, 'danger')
        return redirect(url_for('items.upload_item'))


@items_bp.route('/add_to_cart/<int:item_id>', methods=['POST', 'GET'])
@login_required
@handle_errors
@safe_database_operation("add_to_cart")
def add_to_cart(item_id):
    try:
        # CRITICAL: Use row-level lock to prevent race condition
        # Item could be purchased by another user between validation and add_to_cart
        item = Item.query.filter_by(id=item_id).with_for_update().first_or_404()

        if not item.is_available:
            logger.warning(f"Attempt to add unavailable item to cart - Item: {item_id}, User: {current_user.username}")
            raise ItemNotAvailableError(f"'{item.name}' is no longer available")

        if item.user_id == current_user.id:
            logger.info(f"User attempted to add own item to cart - Item: {item_id}, User: {current_user.username}")
            flash("You cannot add your own item to cart.", "info")
            return redirect(url_for('marketplace.marketplace'))

        cart = get_or_create_cart(current_user.id)

        existing_cart_item = CartItem.query.filter_by(cart_id=cart.id, item_id=item_id).first()
        if existing_cart_item:
            logger.info(f"Item already in cart - Item: {item_id}, User: {current_user.username}")
            flash("This item is already in your cart.", "info")
            return redirect(url_for('items.view_cart'))

        cart_item = CartItem(cart_id=cart.id, item_id=item_id)
        db.session.add(cart_item)
        
        cart.updated_at = datetime.utcnow()
        logger.info(f"Item added to cart - Item: {item_id}, User: {current_user.username}")
        flash(f"'{item.name}' has been added to your cart.", "success")
        return redirect(url_for('items.view_cart'))
        
    except ItemNotAvailableError as e:
        logger.warning(f"Item not available error: {str(e)}")
        flash(str(e.message), 'danger')
        return redirect(url_for('marketplace.marketplace'))


@items_bp.route('/cart')
@login_required
@handle_errors
def view_cart():
    try:
        cart = Cart.query.filter_by(user_id=current_user.id).first()
        
        if not cart:
            cart_items = []
            total_cost = 0
        else:
            cart_items = [ci for ci in cart.items if ci.item.is_available]
            total_cost = cart.get_total_cost()
            
            unavailable_items = [ci for ci in cart.items if not ci.item.is_available]
            if unavailable_items:
                for ci in unavailable_items:
                    db.session.delete(ci)
                db.session.commit()
                logger.info(f"Removed {len(unavailable_items)} unavailable items from cart - User: {current_user.username}")
                if len(unavailable_items) == 1:
                    flash("1 item was removed from your cart as it's no longer available.", "warning")
                else:
                    flash(f"{len(unavailable_items)} items were removed from your cart as they're no longer available.", "warning")
        
        return render_template('cart.html', cart_items=cart_items, total_cost=total_cost, csrf_token=generate_csrf)
        
    except Exception as e:
        logger.error(f"Error viewing cart for user {current_user.username}: {str(e)}", exc_info=True)
        flash('An error occurred while loading your cart.', 'danger')
        return redirect(url_for('marketplace.marketplace'))


@items_bp.route('/remove_from_cart/<int:item_id>', methods=['POST'])
@login_required
@handle_errors
@safe_database_operation("remove_from_cart")
def remove_from_cart(item_id):
    try:
        cart = Cart.query.filter_by(user_id=current_user.id).first()
        
        if cart:
            cart_item = CartItem.query.filter_by(cart_id=cart.id, item_id=item_id).first()
            if cart_item:
                db.session.delete(cart_item)
                cart.updated_at = datetime.utcnow()
                logger.info(f"Item removed from cart - Item: {item_id}, User: {current_user.username}")
                flash("Item removed from cart.", "success")
            else:
                logger.warning(f"Attempted to remove non-existent cart item - Item: {item_id}, User: {current_user.username}")
        
        return redirect(url_for('items.view_cart'))
        
    except Exception as e:
        logger.error(f"Error removing item from cart: {str(e)}", exc_info=True)
        flash('An error occurred while removing the item.', 'danger')
        return redirect(url_for('items.view_cart'))


@items_bp.route('/clear_cart', methods=['POST'])
@login_required
@handle_errors
@safe_database_operation("clear_cart")
def clear_cart():
    try:
        cart = Cart.query.filter_by(user_id=current_user.id).first()
        
        if cart:
            item_count = len(cart.items)
            # Delete all cart items directly
            CartItem.query.filter_by(cart_id=cart.id).delete()
            db.session.commit()
            logger.info(f"Cart cleared - User: {current_user.username}, Items: {item_count}")
            flash(f"Cleared {item_count} item{'s' if item_count != 1 else ''} from your cart.", "success")
        else:
            flash("Your cart is already empty.", "info")
        
        return redirect(url_for('items.view_cart'))
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error clearing cart for user {current_user.username}: {str(e)}", exc_info=True)
        flash('An error occurred while clearing your cart.', 'danger')
        return redirect(url_for('items.view_cart'))


@items_bp.route('/checkout')
@rate_limit("10 per minute")  # Rate limit: 10 requests per minute per IP
@login_required
@handle_errors
def checkout():
    """
    NEW FLOW: Checkout now only validates items and sets up pending order.
    Does NOT purchase yet - user must complete delivery setup first.
    """
    try:
        cart = Cart.query.filter_by(user_id=current_user.id).first()
        
        if not cart or not cart.items:
            logger.info(f"Checkout attempt with empty cart - User: {current_user.username}")
            flash("Your cart is empty.", "info")
            return redirect(url_for('marketplace.marketplace'))
        
        available_items = [ci for ci in cart.items if ci.item.is_available]
        
        if not available_items:
            logger.warning(f"Checkout attempt with no available items - User: {current_user.username}")
            flash("No available items in your cart.", "info")
            return redirect(url_for('items.view_cart'))
        
        total_cost = sum(ci.item.value for ci in available_items)
        
        if current_user.credits < total_cost:
            logger.warning(f"Insufficient credits for checkout - User: {current_user.username}, Required: {total_cost}, Available: {current_user.credits}")
            raise InsufficientCreditsError(total_cost, current_user.credits)
        
        # Store pending items in session (for delivery setup before purchase)
        # Do NOT purchase yet - user must set up delivery first
        session['pending_checkout_items'] = [ci.item_id for ci in available_items]
        logger.info(f"Checkout initialized - User: {current_user.username}, Items: {len(available_items)}, Total: {total_cost}")
        
        # Redirect to delivery setup page (no purchase yet)
        return redirect(url_for('items.order_item'))
        
    except InsufficientCreditsError as e:
        logger.warning(f"Insufficient credits: {str(e)}")
        flash(str(e.message), 'danger')
        return redirect(url_for('items.view_cart'))


@items_bp.route('/finalize_purchase', methods=['POST'])
@rate_limit("10 per minute")  # Rate limit: 10 requests per minute per IP
@login_required
@handle_errors
@safe_database_operation("finalize_purchase")
def finalize_purchase():
    """
    NEW FLOW: This is called AFTER user sets up delivery details.
    Finalizes the purchase by:
    1. Re-validating all items are still available
    2. Deducting credits
    3. Linking items to user
    4. Creating trades
    5. Clearing cart
    """
    import uuid
    from referral_rewards import award_referral_bonus
    
    # Generate unique transaction ID for audit trail
    transaction_id = str(uuid.uuid4())[:8]
    
    try:
        # Get pending checkout items from session
        pending_item_ids = session.get('pending_checkout_items', [])
        
        if not pending_item_ids:
            logger.warning(f"[TXN:{transaction_id}] Finalize purchase with no pending items - User: {current_user.username}")
            flash("No items to purchase. Please start from checkout.", "info")
            return redirect(url_for('marketplace.marketplace'))
        
        # Get items that are pending for purchase
        items_to_purchase = Item.query.filter(Item.id.in_(pending_item_ids)).all()
        
        if not items_to_purchase:
            logger.warning(f"[TXN:{transaction_id}] Pending items not found - User: {current_user.username}")
            flash("Items not found. Please start from checkout.", "info")
            return redirect(url_for('marketplace.marketplace'))
        
        # CRITICAL: Acquire row-level locks on all items to prevent race condition
        logger.debug(f"[TXN:{transaction_id}] Acquiring locks on items: {pending_item_ids}")
        locked_items = Item.query.filter(Item.id.in_(pending_item_ids)).with_for_update().all()
        locked_items_dict = {item.id: item for item in locked_items}
        
        # PHASE 1: VALIDATION - Re-check all items are still available
        logger.debug(f"[TXN:{transaction_id}] Phase 1: Re-validating items")
        available = []
        for item_id in pending_item_ids:
            item = locked_items_dict.get(item_id)
            if not item:
                logger.warning(f"[TXN:{transaction_id}] Item not found - Item: {item_id}")
                raise CheckoutError(f"Item became unavailable (not found)")
            
            if not item.is_available:
                logger.warning(f"[TXN:{transaction_id}] Item became unavailable - Item: {item.id}")
                raise CheckoutError(f"Item '{item.name}' is no longer available.")
            
            seller_id = getattr(item, "owner_id", None) or getattr(item, "user_id", None)
            if not seller_id:
                logger.error(f"[TXN:{transaction_id}] Item has no owner - Item: {item.id}")
                raise CheckoutError(f"Item '{item.name}' has invalid seller information.")
            
            if item.user_id == current_user.id:
                logger.warning(f"[TXN:{transaction_id}] User already owns item - Item: {item.id}")
                raise CheckoutError(f"You already own item '{item.name}'.")
            
            available.append(item)
        
        # PHASE 2: CALCULATE - Compute total cost
        logger.debug(f"[TXN:{transaction_id}] Phase 2: Calculating total cost")
        total_cost = sum(item.value for item in available)
        
        if current_user.credits < total_cost:
            logger.warning(f"[TXN:{transaction_id}] Insufficient credits - Required: {total_cost}, Available: {current_user.credits}")
            raise InsufficientCreditsError(total_cost, current_user.credits)
        
        # PHASE 3: PROCESS - Atomic credit deduction and item linking
        logger.debug(f"[TXN:{transaction_id}] Phase 3: Processing purchase (deducting credits, linking items)")
        
        purchased_items = []
        level_up_notifications = []
        failed_items = []
        
        # Single atomic credit deduction (all-or-nothing)
        current_user.credits -= total_cost
        current_user.last_checkout_transaction_id = transaction_id
        current_user.last_checkout_timestamp = datetime.utcnow()
        
        # Process each item with savepoint for per-item error recovery
        for item in available:
            savepoint = db.session.begin_nested()
            
            try:
                # Get seller ID BEFORE any changes
                seller_id = getattr(item, "owner_id", None) or getattr(item, "user_id", None)
                
                # Link item to buyer
                item.user_id = current_user.id
                item.is_available = False
                
                # Create trade record
                trade = Trade(
                    sender_id=current_user.id,
                    receiver_id=seller_id,
                    item_id=item.id,
                    item_received_id=item.id,
                    status='completed'
                )
                db.session.add(trade)

                # Award trading points for purchase
                level_up_info = award_points_for_purchase(current_user, f"item-{item.id}")
                if level_up_info:
                    level_up_notifications.append(level_up_info)
                
                # Commit this item's savepoint
                savepoint.commit()
                purchased_items.append(item)
                logger.debug(f"[TXN:{transaction_id}] Item purchased - Item: {item.id}, Title: {item.name}")
                
            except Exception as e:
                savepoint.rollback()
                failed_items.append({
                    'item_id': item.id,
                    'title': item.name,
                    'error': str(e)
                })
                logger.warning(f"[TXN:{transaction_id}] Item purchase failed - Item: {item.id}, Error: {str(e)}")
        
        # If no items were successfully purchased, refund credits
        if not purchased_items and total_cost > 0:
            current_user.credits += total_cost
            logger.warning(f"[TXN:{transaction_id}] All items failed - Refunding credits: {total_cost}")
            raise CheckoutError("Could not process any items in your order.")
        
        # Commit main transaction
        db.session.commit()
        
        # Award referral bonus for purchase (after commit)
        try:
            referral_result = award_referral_bonus(current_user.id, 'purchase', amount=100)
            if referral_result['success']:
                logger.info(f"[TXN:{transaction_id}] Referral bonus awarded: {referral_result['message']}")
        except Exception as e:
            logger.warning(f"[TXN:{transaction_id}] Failed to award referral bonus: {str(e)}")
        
        # Create level-up notifications (after commit)
        for level_up_info in level_up_notifications:
            try:
                create_level_up_notification(current_user, level_up_info)
            except Exception as e:
                logger.error(f"[TXN:{transaction_id}] Failed to create level-up notification: {str(e)}")

        # Remove items from cart since they're now purchased
        cart = Cart.query.filter_by(user_id=current_user.id).first()
        if cart:
            CartItem.query.filter(CartItem.cart_id == cart.id, CartItem.item_id.in_(pending_item_ids)).delete()
            db.session.commit()

        logger.info(f"[TXN:{transaction_id}] ✓ Purchase FINALIZED - User: {current_user.username}, Items: {len(purchased_items)}, Credits Deducted: {total_cost}")
        if failed_items:
            logger.warning(f"[TXN:{transaction_id}] ⚠ Some items failed: {failed_items}")
        
        # CRITICAL: Create Order record for transaction history
        order_number = None
        try:
            # Get delivery information from session
            pending_delivery = session.get('pending_delivery', {})
            
            # Generate order number: ORD-YYYYMMDD-XXXXX
            order_counter = Order.query.filter(
                Order.date_ordered >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            ).count()
            
            order_date = datetime.utcnow().strftime('%Y%m%d')
            order_number = f"ORD-{order_date}-{order_counter + 1:05d}"
            
            # Create Order record
            order = Order(
                user_id=current_user.id,
                delivery_method=pending_delivery.get('method', 'home delivery'),
                delivery_address=pending_delivery.get('delivery_address'),
                pickup_station_id=pending_delivery.get('pickup_station_id'),
                order_number=order_number,
                total_credits=total_cost,
                credits_used=total_cost,
                credits_balance_before=current_user.credits + total_cost,
                credits_balance_after=current_user.credits,
                status='Pending',
                date_ordered=datetime.utcnow(),
                estimated_delivery_date=datetime.utcnow() + timedelta(days=7),
                transaction_notes=f"Purchase of {len(purchased_items)} item(s)"
            )
            
            # Link items to order
            for item in purchased_items:
                order_item = OrderItem(order=order, item=item)
                db.session.add(order_item)
            
            db.session.add(order)
            db.session.commit()
            
            logger.info(f"[TXN:{transaction_id}] Order created - Order ID: {order.id}, Order #: {order_number}")
            
        except Exception as e:
            logger.error(f"[TXN:{transaction_id}] Failed to create order record: {str(e)}", exc_info=True)
            flash("Warning: Order record could not be saved. Please contact support.", "warning")
        
        # Clear pending items from session
        session.pop('pending_checkout_items', None)
        session.pop('pending_delivery', None)
        
        # CRITICAL: Create order confirmation notification and email
        try:
            pending_delivery = session.get('pending_delivery', {})
            delivery_method = pending_delivery.get('method', 'home delivery')
            delivery_info = ""
            
            if delivery_method == 'home delivery':
                delivery_address = pending_delivery.get('delivery_address', 'Not specified')
                delivery_info = f"Delivery Address: {delivery_address}"
            else:  # pickup
                pickup_station_id = pending_delivery.get('pickup_station_id')
                if pickup_station_id:
                    station = PickupStation.query.get(pickup_station_id)
                    if station:
                        delivery_info = f"Pickup Station: {station.name} ({station.state})"
            
            # Build items list for notification
            items_list = "<br>".join([
                f"• {item.name} - ₦{item.value:,.0f} Credits"
                for item in purchased_items
            ])
            
            notification_message = f"""
            ✓ Order Confirmed!<br><br>
            Order #: {order_number}<br>
            Items: {len(purchased_items)}<br>
            Total Cost: ₦{total_cost:,.0f} Credits<br><br>
            <strong>Items Ordered:</strong><br>
            {items_list}<br><br>
            <strong>Delivery Method:</strong> {delivery_method.title()}<br>
            {delivery_info}<br><br>
            <strong>Estimated Delivery:</strong> 7 business days<br><br>
            Your purchase has been processed successfully. You will receive updates about your order shortly.
            """
            
            # Create notification in database
            notification = Notification(user_id=current_user.id, message=notification_message)
            db.session.add(notification)
            db.session.commit()
            
            # Send confirmation email
            if current_user.email:
                email_html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <style>
                        body {{ font-family: 'Arial', sans-serif; line-height: 1.6; color: #333; background: #f8f9fa; }}
                        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; background: white; border-radius: 10px; }}
                        .header {{ background: linear-gradient(135deg, #ff7a00 0%, #ff9533 100%); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                        .header h1 {{ margin: 0; font-size: 28px; }}
                        .order-details {{ background: #f8f9fa; padding: 20px; margin: 20px 0; border-left: 4px solid #ff7a00; }}
                        .order-number {{ font-size: 18px; font-weight: bold; color: #ff7a00; }}
                        .items-section {{ margin: 20px 0; }}
                        .item {{ background: white; padding: 10px; margin: 8px 0; border-left: 3px solid #ff7a00; }}
                        .summary {{ background: #f0f0f0; padding: 15px; margin: 15px 0; border-radius: 5px; }}
                        .summary-row {{ display: flex; justify-content: space-between; margin: 8px 0; }}
                        .total {{ font-size: 18px; font-weight: bold; color: #ff7a00; }}
                        .delivery-info {{ background: #e8f5e9; padding: 15px; margin: 15px 0; border-radius: 5px; border-left: 4px solid #10b981; }}
                        .next-steps {{ background: #fff3cd; padding: 15px; margin: 15px 0; border-radius: 5px; }}
                        .next-steps h3 {{ margin-top: 0; color: #ff7a00; }}
                        .next-steps ol {{ margin: 10px 0; padding-left: 20px; }}
                        .next-steps li {{ margin: 8px 0; }}
                        .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; text-align: center; font-size: 12px; color: #666; }}
                        .button {{ display: inline-block; background: #ff7a00; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; margin: 15px 0; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>✓ Order Confirmed!</h1>
                            <p>Your purchase has been successfully processed</p>
                        </div>
                        
                        <div class="order-details">
                            <p>Thank you for your purchase, <strong>{current_user.username}</strong>!</p>
                            <p class="order-number">Order #: {order_number}</p>
                            <p>Order Date: {datetime.utcnow().strftime('%B %d, %Y at %I:%M %p')}</p>
                        </div>
                        
                        <div class="items-section">
                            <h3 style="color: #333; border-bottom: 2px solid #ff7a00; padding-bottom: 10px;">Items Ordered ({len(purchased_items)})</h3>
                            {''.join([f'<div class="item">{item.name}<br><span style="color: #ff7a00; font-weight: bold;">₦{item.value:,.0f} Credits</span></div>' for item in purchased_items])}
                        </div>
                        
                        <div class="summary">
                            <div class="summary-row">
                                <span>Subtotal:</span>
                                <span>₦{total_cost:,.0f}</span>
                            </div>
                            <div class="summary-row total">
                                <span>Total Cost:</span>
                                <span>₦{total_cost:,.0f} Credits</span>
                            </div>
                        </div>
                        
                        <div class="delivery-info">
                            <h3 style="margin-top: 0; color: #10b981;">🚚 Delivery Information</h3>
                            <p><strong>Delivery Method:</strong> {delivery_method.title()}</p>
                            {'<p><strong>Delivery Address:</strong> ' + pending_delivery.get('delivery_address', 'Not specified') + '</p>' if delivery_method == 'home delivery' else ''}
                            {f'<p><strong>Pickup Station:</strong> {PickupStation.query.get(pending_delivery.get("pickup_station_id")).name} ({PickupStation.query.get(pending_delivery.get("pickup_station_id")).state})</p>' if delivery_method == 'pickup' and pending_delivery.get('pickup_station_id') else ''}
                            <p><strong>Estimated Delivery:</strong> 7 business days from order date</p>
                        </div>
                        
                        <div class="next-steps">
                            <h3>📋 What Happens Next?</h3>
                            <ol>
                                <li><strong>Order Confirmation:</strong> Your order has been recorded and is being processed</li>
                                <li><strong>Item Preparation:</strong> The seller(s) will prepare your items for delivery</li>
                                <li><strong>Shipping:</strong> Your items will be shipped to your {'delivery address' if delivery_method == 'home delivery' else 'pickup station'}</li>
                                <li><strong>Tracking:</strong> You will receive updates about your order status</li>
                                <li><strong>Delivery:</strong> Items will arrive within the estimated timeframe</li>
                            </ol>
                        </div>
                        
                        <div style="text-align: center; margin: 20px 0;">
                            <a href="{url_for('user.dashboard', _external=True)}" class="button">Track Your Order</a>
                        </div>
                        
                        <div class="footer">
                            <p>This is an automated confirmation email. Please do not reply to this email.</p>
                            <p>If you have any questions, please contact our support team.</p>
                            <p>© 2026 Barterex. All rights reserved.</p>
                        </div>
                    </div>
                </body>
                </html>
                """
                
                send_email_async(
                    subject=f"Order Confirmation #{order_number} - Barterex",
                    recipients=[current_user.email],
                    html_body=email_html
                )
                logger.info(f"[TXN:{transaction_id}] Order confirmation email sent to {current_user.email}")
            
        except Exception as e:
            logger.error(f"[TXN:{transaction_id}] Failed to create order notification/email: {str(e)}", exc_info=True)
        
        flash(f"✓ Purchase complete! {len(purchased_items)} item(s) purchased. Order #{order_number if order_number else 'unknown'}", "success")
        return redirect(url_for('user.dashboard'))

    except InsufficientCreditsError as e:
        logger.warning(f"[TXN:{transaction_id}] Insufficient credits error: {str(e)}")
        flash(str(e.message), 'danger')
        return redirect(url_for('items.view_cart'))
    except CheckoutError as e:
        logger.error(f"[TXN:{transaction_id}] Checkout error: {str(e)}")
        flash(str(e), 'danger')
        return redirect(url_for('items.view_cart'))
    except Exception as e:
        logger.error(f"[TXN:{transaction_id}] Unexpected error during purchase finalization: {str(e)}", exc_info=True)
        flash("Something went wrong while finalizing your purchase. Please contact support.", "danger")
        return redirect(url_for('items.view_cart'))
        
        if not available:
            logger.warning(f"[TXN:{transaction_id}] Checkout attempted with no available items - User: {current_user.username}")
            flash("No available items in your cart.", "info")
            return redirect(url_for('items.view_cart'))

        # CRITICAL: Acquire row-level locks on all items to prevent race condition
        # This ensures no other user can purchase the same items concurrently
        item_ids = [ci.item_id for ci in available]
        logger.debug(f"[TXN:{transaction_id}] Acquiring locks on items: {item_ids}")
        
        # Lock items with FOR UPDATE to prevent concurrent modifications
        # This uses database-level locking: no other transaction can modify these rows
        locked_items = Item.query.filter(Item.id.in_(item_ids)).with_for_update().all()
        locked_items_dict = {item.id: item for item in locked_items}
        
        # Re-validate items after acquiring locks to prevent race condition
        # (item could have been purchased by another user between validation and lock)
        for ci in available:
            item = locked_items_dict.get(ci.item_id)
            if not item:
                logger.warning(f"[TXN:{transaction_id}] Item not found during lock acquisition - Item: {ci.item_id}")
                raise CheckoutError(f"Item became unavailable (not found in database)")
            
            if not item.is_available:
                logger.warning(f"[TXN:{transaction_id}] Item became unavailable during validation - Item: {item.id}")
                raise CheckoutError(f"Item '{item.name}' is no longer available.")
            
            seller_id = getattr(item, "owner_id", None) or getattr(item, "user_id", None)
            if not seller_id:
                logger.error(f"[TXN:{transaction_id}] Item has no owner - Item: {item.id}")
                raise CheckoutError(f"Item '{item.name}' has invalid seller information.")
            
            # Check that item is not already owned by current user (shouldn't happen, but double-check)
            if item.user_id == current_user.id:
                logger.warning(f"[TXN:{transaction_id}] User already owns item - Item: {item.id}, User: {current_user.id}")
                raise CheckoutError(f"You already own item '{item.name}'.")

        # PHASE 2: CALCULATE - Compute total cost
        logger.debug(f"[TXN:{transaction_id}] Phase 2: Calculating total cost")
        # Use locked items for cost calculation (not original cart items)
        total_cost = sum(locked_items_dict[ci.item_id].value for ci in available)
        
        if current_user.credits < total_cost:
            logger.warning(f"[TXN:{transaction_id}] Insufficient credits - Required: {total_cost}, Available: {current_user.credits}")
            raise InsufficientCreditsError(total_cost, current_user.credits)

        # PHASE 3: PROCESS - Atomic credit deduction and item linking
        logger.debug(f"[TXN:{transaction_id}] Phase 3: Processing checkout (deducting credits, linking items)")
        
        purchased_items = []
        level_up_notifications = []
        failed_items = []
        
        # Single atomic credit deduction (not per-item)
        # This ensures all-or-nothing: either all items purchased or none
        current_user.credits -= total_cost
        current_user.last_checkout_transaction_id = transaction_id
        current_user.last_checkout_timestamp = datetime.utcnow()
        
        # Process each item with savepoint for per-item error recovery
        # Use locked items to ensure no race condition
        for ci in available:
            # Get locked item (guaranteed to be locked and not modified by other transactions)
            item = locked_items_dict.get(ci.item_id)
            savepoint = db.session.begin_nested()
            
            try:
                # CRITICAL: Get seller ID BEFORE any changes
                seller_id = getattr(item, "owner_id", None) or getattr(item, "user_id", None)
                
                # Link item to buyer
                item.user_id = current_user.id
                item.is_available = False
                
                # Create trade record
                trade = Trade(
                    sender_id=current_user.id,
                    receiver_id=seller_id,
                    item_id=item.id,
                    item_received_id=item.id,
                    status='completed'
                )
                db.session.add(trade)

                # Award trading points for purchase (20 points per item)
                level_up_info = award_points_for_purchase(current_user, f"item-{item.id}")
                if level_up_info:
                    level_up_notifications.append(level_up_info)

                # Remove from cart
                db.session.delete(ci)
                
                # Commit this item's savepoint
                savepoint.commit()
                purchased_items.append(item)
                logger.debug(f"[TXN:{transaction_id}] Item processed - Item: {item.id}, Title: {item.name}")
                
            except Exception as e:
                # Rollback only THIS item's changes, not the entire transaction
                savepoint.rollback()
                failed_items.append({
                    'item_id': item.id,
                    'title': item.name,
                    'error': str(e)
                })
                logger.warning(f"[TXN:{transaction_id}] Item processing failed - Item: {item.id}, Error: {str(e)}")
        
        # If no items were successfully purchased, refund credits
        if not purchased_items and total_cost > 0:
            current_user.credits += total_cost
            logger.warning(f"[TXN:{transaction_id}] All items failed - Refunding credits: {total_cost}")
            raise CheckoutError("Could not process any items in your cart.")
        
        # Commit main transaction (credits deducted, items linked)
        db.session.commit()
        
        # Award referral bonus for purchase (after commit)
        try:
            referral_result = award_referral_bonus(current_user.id, 'purchase', amount=100)
            if referral_result['success']:
                logger.info(f"[TXN:{transaction_id}] Referral bonus awarded: {referral_result['message']}")
        except Exception as e:
            logger.warning(f"[TXN:{transaction_id}] Failed to award referral bonus: {str(e)}")
        
        # Create level-up notifications (after commit)
        for level_up_info in level_up_notifications:
            try:
                create_level_up_notification(current_user, level_up_info)
            except Exception as e:
                logger.error(f"[TXN:{transaction_id}] Failed to create level-up notification: {str(e)}")

        # Log successful checkout
        logger.info(f"[TXN:{transaction_id}] ✓ Checkout SUCCESSFUL - User: {current_user.username}, Items: {len(purchased_items)}, Credits Deducted: {total_cost}")
        if failed_items:
            logger.warning(f"[TXN:{transaction_id}] ⚠ Some items failed: {failed_items}")

    except InsufficientCreditsError as e:
        logger.warning(f"[TXN:{transaction_id}] Insufficient credits error: {str(e)}")
        flash(str(e.message), 'danger')
        return redirect(url_for('items.view_cart'))
    except CheckoutError as e:
        logger.error(f"[TXN:{transaction_id}] Checkout error: {str(e)}")
        flash(str(e), 'danger')
        return redirect(url_for('items.view_cart'))
    except Exception as e:
        logger.error(f"[TXN:{transaction_id}] Unexpected error during checkout: {str(e)}", exc_info=True)
        flash("Something went wrong while processing your purchase. Please contact support if credits were deducted.", "danger")
        return redirect(url_for('items.view_cart'))

    if not purchased_items:
        logger.warning(f"[TXN:{transaction_id}] No items purchased - redirecting to cart")
        return redirect(url_for('items.view_cart'))

    # Success: Set up delivery for purchased items
    session['pending_order_items'] = [i.id for i in purchased_items]
    flash(f"✓ Purchase complete! {len(purchased_items)} item(s) purchased. Now set up delivery.", "success")
    logger.info(f"[TXN:{transaction_id}] Redirecting to order setup - Items: {[i.id for i in purchased_items]}")
    return redirect(url_for('items.order_item'))


@items_bp.route('/order_item', methods=['GET', 'POST'])
@login_required
@handle_errors
@safe_database_operation("order_item")
def order_item():
    """
    NEW FLOW: User sets up delivery BEFORE purchase is finalized.
    The purchase happens when they click "Confirm Purchase" button,
    which calls finalize_purchase().
    """
    form = OrderForm()
    stations = PickupStation.query.filter_by(state=current_user.state).all()
    form.pickup_station.choices = [(s.id, s.name) for s in stations]
    
    # Get pending items from checkout (not yet purchased)
    pending_item_ids = session.get('pending_checkout_items', [])
    items = Item.query.filter(Item.id.in_(pending_item_ids)).all() if pending_item_ids else []
    
    if not items:
        logger.warning(f"Order setup attempted with no pending items - User: {current_user.username}")
        flash("No items to set up delivery for. Please start from checkout.", "info")
        return redirect(url_for('items.view_cart'))
    
    if request.method == 'GET' and current_user.address:
        form.delivery_address.data = current_user.address
    
    if form.validate_on_submit():
        try:
            delivery_method = form.delivery_method.data
            pickup_station_id = form.pickup_station.data if delivery_method == 'pickup' else None
            delivery_address = form.delivery_address.data if delivery_method == 'home delivery' else None
            
            # Store delivery details in session for finalize_purchase to use
            session['pending_delivery'] = {
                'method': delivery_method,
                'pickup_station_id': pickup_station_id,
                'delivery_address': delivery_address
            }
            logger.info(f"Delivery setup completed - User: {current_user.username}, Method: {delivery_method}")
            
            # Render the order review page with delivery details and purchase confirmation button
            total_credits = sum(item.value for item in items)
            return render_template('order_review.html', 
                                 form=form, 
                                 items=items,
                                 delivery_method=delivery_method,
                                 delivery_address=delivery_address,
                                 pickup_station_id=pickup_station_id,
                                 total_credits=total_credits,
                                 stations=stations,
                                 csrf_token=generate_csrf)
        
        except Exception as e:
            logger.error(f"Error in delivery setup for user {current_user.id}: {str(e)}", exc_info=True)
            flash('An error occurred while setting up delivery. Please try again.', 'danger')
            return render_template('order_item.html', form=form, stations=stations, items=items)
    
    return render_template('order_item.html', form=form, stations=stations, items=items)

