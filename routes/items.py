from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify
from flask_login import login_required, current_user, logout_user
from flask_wtf.csrf import generate_csrf
import os
import time
from werkzeug.utils import secure_filename
from datetime import datetime

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
from services.ai_price_estimator import get_price_estimator

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

        form = UploadItemForm()
        if form.validate_on_submit():
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
            if form.images.data:
                for index, file in enumerate(form.images.data):
                    if file and file.filename:
                        try:
                            # Comprehensive file upload validation with STRICT security checks
                            validate_upload(
                                file, 
                                max_size=app.config.get('FILE_UPLOAD_MAX_SIZE', 10*1024*1024),
                                allowed_extensions=app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif'}),
                                enable_virus_scan=app.config.get('FILE_UPLOAD_ENABLE_VIRUS_SCAN', False)
                            )
                            
                            unique_filename = generate_safe_filename(file, current_user.id, item_id=new_item.id, index=index)
                            image_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                            file.save(image_path)
                            
                            item_image = ItemImage(
                                item_id=new_item.id,
                                image_url=f"/{image_path}",
                                is_primary=(index == 0),
                                order_index=index
                            )
                            db.session.add(item_image)
                            uploaded_images.append(item_image)
                            logger.info(f"Image uploaded for item - Item: {new_item.id}, File: {unique_filename}")
                        except FileUploadError as e:
                            db.session.rollback()
                            logger.warning(f"File validation failed for user {current_user.username}: {str(e)}")
                            flash(f"Image upload failed: {str(e)}", 'danger')
                            return redirect(url_for('items.upload_item'))
                        except Exception as e:
                            db.session.rollback()
                            logger.error(f"Error uploading image: {str(e)}", exc_info=True)
                            raise FileUploadError("Failed to upload one or more images")
            
            if uploaded_images:
                new_item.image_url = uploaded_images[0].image_url
            
            try:
                db.session.commit()
                logger.info(f"Item submitted for approval - Item: {new_item.id}, User: {current_user.username}, Images: {len(uploaded_images)}")
                flash(f"Item submitted for approval with {len(uploaded_images)} images!", "info")
                return redirect(url_for('marketplace.marketplace'))
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error committing item upload: {str(e)}", exc_info=True)
                raise DatabaseError("Failed to save item. Please try again.")
        else:
            # Log form validation errors
            if form.errors:
                logger.warning(f"Form validation failed for user {current_user.username}: {form.errors}")
                for field, errors in form.errors.items():
                    for error in errors:
                        flash(f"{field}: {error}", "danger")

        return render_template('upload.html', form=form)
        
    except (FileUploadError, DatabaseError) as e:
        logger.warning(f"Upload error: {str(e)}")
        flash(str(e.message), 'danger')
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
                raise CheckoutError(f"Item '{item.title}' is no longer available.")
            
            seller_id = getattr(item, "owner_id", None) or getattr(item, "user_id", None)
            if not seller_id:
                logger.error(f"[TXN:{transaction_id}] Item has no owner - Item: {item.id}")
                raise CheckoutError(f"Item '{item.title}' has invalid seller information.")
            
            if item.user_id == current_user.id:
                logger.warning(f"[TXN:{transaction_id}] User already owns item - Item: {item.id}")
                raise CheckoutError(f"You already own item '{item.title}'.")
            
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
                logger.debug(f"[TXN:{transaction_id}] Item purchased - Item: {item.id}, Title: {item.title}")
                
            except Exception as e:
                savepoint.rollback()
                failed_items.append({
                    'item_id': item.id,
                    'title': item.title,
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
        
        # Clear pending items from session
        session.pop('pending_checkout_items', None)
        flash(f"✓ Purchase complete! {len(purchased_items)} item(s) purchased.", "success")
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
                raise CheckoutError(f"Item '{item.title}' is no longer available.")
            
            seller_id = getattr(item, "owner_id", None) or getattr(item, "user_id", None)
            if not seller_id:
                logger.error(f"[TXN:{transaction_id}] Item has no owner - Item: {item.id}")
                raise CheckoutError(f"Item '{item.title}' has invalid seller information.")
            
            # Check that item is not already owned by current user (shouldn't happen, but double-check)
            if item.user_id == current_user.id:
                logger.warning(f"[TXN:{transaction_id}] User already owns item - Item: {item.id}, User: {current_user.id}")
                raise CheckoutError(f"You already own item '{item.title}'.")

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
                logger.debug(f"[TXN:{transaction_id}] Item processed - Item: {item.id}, Title: {item.title}")
                
            except Exception as e:
                # Rollback only THIS item's changes, not the entire transaction
                savepoint.rollback()
                failed_items.append({
                    'item_id': item.id,
                    'title': item.title,
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
                                 csrf_token=generate_csrf)
        
        except Exception as e:
            logger.error(f"Error in delivery setup for user {current_user.id}: {str(e)}", exc_info=True)
            flash('An error occurred while setting up delivery. Please try again.', 'danger')
            return render_template('order_item.html', form=form, stations=stations, items=items)
    
    return render_template('order_item.html', form=form, stations=stations, items=items)
    
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
                                 csrf_token=generate_csrf)
        
        except Exception as e:
            logger.error(f"Error in delivery setup for user {current_user.id}: {str(e)}", exc_info=True)
            flash('An error occurred while setting up delivery. Please try again.', 'danger')
            return render_template('order_item.html', form=form, stations=stations, items=items)
    
    return render_template('order_item.html', form=form, stations=stations, items=items)


# ==================== AI PRICE ESTIMATION API ====================

@items_bp.route('/api/estimate-price', methods=['POST'])
@rate_limit("5 per minute")  # Rate limit: 5 requests per minute per IP (stricter for AI processing)
@login_required
def estimate_item_price():
    """
    API endpoint to estimate item price using AI and web scraping
    Accepts image(s) + description and returns estimated market value
    Supports both single image (legacy) and multiple images (new)
    """
    try:
        # Get form data
        description = request.form.get('description', '')
        item_name = request.form.get('item_name', '')
        condition = request.form.get('condition', 'good')
        category = request.form.get('category', 'other')
        
        # Get image file(s) - support both single (legacy) and multiple (new)
        image_data = None
        image_count = 0
        primary_image_index = 0
        
        # Try multiple images first (new format)
        image_files = request.files.getlist('images')
        
        # Fallback to single image (legacy format)
        if not image_files:
            image_file = request.files.get('image')
            if image_file and allowed_file(image_file.filename):
                image_files = [image_file]
        
        # Process the first/primary image for estimation
        if image_files:
            primary_image_index = int(request.form.get('primary_image_index', 0))
            image_count = len(image_files)
            
            # Use the primary image or first image
            primary_file = image_files[min(primary_image_index, len(image_files) - 1)]
            if allowed_file(primary_file.filename):
                image_data = primary_file.read()
                primary_file.seek(0)
        
        # Validate inputs
        if not description or len(description.strip()) < 10:
            return jsonify({
                'success': False,
                'error': 'Please provide a detailed description (at least 10 characters)'
            }), 400
        
        # Get price estimator service
        estimator = get_price_estimator()
        
        # Estimate price
        item_label = item_name if item_name else description[:50]
        logger.info(f"Price estimation requested - User: {current_user.username}, Item: {item_label}, Images: {image_count}")
        logger.info(f"DEBUG: Calling estimate_price with condition='{condition}', category='{category}'")
        
        price_estimate = estimator.estimate_price(
            image_data=image_data,
            description=description,
            condition=condition,
            category=category
        )
        
        logger.info(f"DEBUG: estimate_price returned: {price_estimate}")
        
        # Adjust confidence based on number of images (optional enhancement)
        if image_count > 1:
            # Boost confidence slightly when multiple images provided
            original_confidence = price_estimate.get('confidence', 'Low')
            if original_confidence == 'Low':
                price_estimate['confidence'] = 'Medium'
            elif original_confidence == 'Medium':
                price_estimate['confidence'] = 'High'
        
        # Calculate credit value
        credit_info = estimator.get_credit_value_estimate(
            price_estimate['estimated_price']
        )
        
        # Combine results
        result = {
            'success': True,
            'price_estimate': price_estimate,
            'credit_value': credit_info,
            'message': 'Price estimation completed successfully',
            'confidence': price_estimate.get('confidence', 'Standard'),
            'images_analyzed': image_count
        }
        
        logger.info(f"Price estimated - Amount: ${price_estimate['estimated_price']}, Confidence: {price_estimate['confidence']}, Images: {image_count}")
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Price estimation API error: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'Unable to estimate price at this time. Please try again later.',
            'details': str(e) if app.debug else None
        }), 500

