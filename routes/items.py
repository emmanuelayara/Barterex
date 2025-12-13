from flask import Blueprint, render_template, request, flash, redirect, url_for, session
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
from exceptions import ValidationError, InsufficientCreditsError, ItemNotAvailableError, FileUploadError, DatabaseError
from error_handlers import handle_errors, safe_database_operation, retry_operation
from transaction_clarity import calculate_estimated_delivery, generate_transaction_explanation
from file_upload_validator import validate_upload, generate_safe_filename
from trading_points import award_points_for_purchase, create_level_up_notification

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
                            # Comprehensive file upload validation (magic bytes, size, integrity)
                            validate_upload(file, max_size=10*1024*1024, allowed_extensions=app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif'}))
                            
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
        item = Item.query.get_or_404(item_id)

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
@login_required
@handle_errors
def checkout():
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
        
        return render_template('checkout.html', cart_items=available_items, total_cost=total_cost, csrf_token=generate_csrf)
        
    except InsufficientCreditsError as e:
        logger.warning(f"Insufficient credits: {str(e)}")
        flash(str(e.message), 'danger')
        return redirect(url_for('items.view_cart'))


@items_bp.route('/process_checkout', methods=['POST'])
@login_required
@handle_errors
@safe_database_operation("process_checkout")
def process_checkout():
    try:
        from referral_rewards import award_referral_bonus
        
        cart = Cart.query.filter_by(user_id=current_user.id).first()

        if not cart or not cart.items:
            logger.warning(f"Checkout attempted with empty cart - User: {current_user.username}")
            flash("Your cart is empty.", "info")
            return redirect(url_for('marketplace.marketplace'))

        available = [ci for ci in cart.items if ci.item and ci.item.is_available]
        if not available:
            logger.warning(f"Checkout attempted with no available items - User: {current_user.username}")
            flash("No available items in your cart.", "info")
            return redirect(url_for('items.view_cart'))

        total_cost = sum(ci.item.value for ci in available)
        if current_user.credits < total_cost:
            logger.warning(f"Insufficient credits during checkout - User: {current_user.username}, Required: {total_cost}, Available: {current_user.credits}")
            raise InsufficientCreditsError(total_cost, current_user.credits)

        purchased_items = []
        level_up_notifications = []  # Track all level-ups
        
        for ci in available:
            item = ci.item
            if not item.is_available:
                logger.warning(f"Item became unavailable during checkout - Item: {item.id}, User: {current_user.username}")
                continue

            seller_id = getattr(item, "owner_id", None) or getattr(item, "user_id", None)
            current_user.credits -= item.value
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
            # Use item.id as order reference for consistent tracking
            level_up_info = award_points_for_purchase(current_user, f"item-{item.id}")
            if level_up_info:
                level_up_notifications.append(level_up_info)

            purchased_items.append(item)
            db.session.delete(ci)
        
        # Commit all changes
        db.session.commit()
        
        # Award referral bonus for purchase
        referral_result = award_referral_bonus(current_user.id, 'purchase', amount=100)
        if referral_result['success']:
            logger.info(f"Referral bonus awarded: {referral_result['message']}")
        
        # Create level up notifications for all level-ups that occurred (after commit)
        for level_up_info in level_up_notifications:
            try:
                create_level_up_notification(current_user, level_up_info)
            except Exception as e:
                # Log but don't fail the checkout if notification fails
                logger.error(f"Failed to create level-up notification: {str(e)}", exc_info=True)

        logger.info(f"Checkout completed successfully - User: {current_user.username}, Items: {len(purchased_items)}, Total: {total_cost}")

    except InsufficientCreditsError as e:
        logger.warning(f"Insufficient credits error: {str(e)}")
        flash(str(e.message), 'danger')
        return redirect(url_for('items.view_cart'))
    except Exception as e:
        logger.error(f"Error during checkout: {str(e)}", exc_info=True)
        flash("Something went wrong while processing your purchase.", "danger")
        return redirect(url_for('items.view_cart'))

    if not purchased_items:
        return redirect(url_for('items.view_cart'))

    session['pending_order_items'] = [i.id for i in purchased_items]
    flash("Now set up delivery for your purchased items.", "info")
    return redirect(url_for('items.order_item'))


@items_bp.route('/order_item', methods=['GET', 'POST'])
@login_required
@handle_errors
@safe_database_operation("order_item")
def order_item():
    form = OrderForm()
    stations = PickupStation.query.filter_by(state=current_user.state).all()
    form.pickup_station.choices = [(s.id, s.name) for s in stations]
    pending_item_ids = session.get('pending_order_items', [])
    items = Item.query.filter(Item.id.in_(pending_item_ids)).all()
    
    if request.method == 'GET' and current_user.address:
        form.delivery_address.data = current_user.address
    
    if form.validate_on_submit():
        try:
            # Check if order was already created for this session to prevent duplicates
            order_created_key = f"order_created_{pending_item_ids}"
            if session.get(order_created_key):
                logger.info(f"Duplicate order submission detected - User: {current_user.username}")
                flash("Order already being processed. Please wait...", "info")
                return redirect(url_for('user.dashboard'))
            
            # Mark this order as being processed
            session[order_created_key] = True
            
            delivery_method = form.delivery_method.data
            pickup_station_id = form.pickup_station.data if delivery_method == 'pickup' else None
            delivery_address = form.delivery_address.data if delivery_method == 'home delivery' else None
            
            # Calculate total credits for this order
            total_credits = sum(item.value for item in items)
            
            # Generate unique order number with sequential counter to prevent duplicates
            from datetime import datetime as dt
            import random
            # Add random component to ensure uniqueness even on same day
            random_suffix = random.randint(1000, 9999)
            order_number = f"ORD-{dt.utcnow().strftime('%Y%m%d')}-{current_user.id:05d}-{random_suffix}"
            
            # Create order with transaction clarity fields
            order = Order(
                user_id=current_user.id,
                order_number=order_number,
                delivery_method=delivery_method,
                delivery_address=delivery_address,
                pickup_station_id=pickup_station_id,
                total_credits=total_credits,
                credits_used=total_credits,
                credits_balance_before=current_user.credits,
                credits_balance_after=current_user.credits - total_credits,
                estimated_delivery_date=calculate_estimated_delivery(delivery_method),
                status='Pending'
            )
            db.session.add(order)
            
            for item_id in pending_item_ids:
                db.session.add(OrderItem(order=order, item_id=item_id))
            
            db.session.commit()
            
            logger.info(f"Order created - User: {current_user.username}, Items: {len(items)}, Method: {delivery_method}, Order#: {order_number}")
            
            if delivery_method == "pickup":
                station = PickupStation.query.get(pickup_station_id)
                extra_info = f"Pickup Station: {station.name}, {station.address}" if station else ""
            else:
                extra_info = f"Delivery Address: {delivery_address}"
            
            item_names = [item.name for item in items]
            if len(item_names) == 1:
                item_info = f"Item: '{item_names[0]}' keep using Barterex for seamless trading."
            else:
                item_info = f"Items: {', '.join(item_names)} keep using Barterex for seamless trading."
            
            create_notification(
                current_user.id,
                f"📦 Your order has been set up for delivery via {delivery_method}. {item_info}. {extra_info}"
            )
            
            # Send confirmation email ONCE
            email_data = {
                'username': current_user.username,
                'order_id': order.id,
                'items': items,
                'delivery_method': delivery_method,
                'delivery_address': delivery_address,
                'pickup_station': PickupStation.query.get(pickup_station_id) if pickup_station_id else None,
                'order_date': order.created_at.strftime('%B %d, %Y at %I:%M %p') if hasattr(order, 'created_at') else 'Today'
            }
            
            html = render_template("emails/order_confirmation.html", **email_data)
            send_email_async(
                subject="📦 Order Confirmation - Barterex",
                recipients=[current_user.email],
                html_body=html
            )
            
            session.pop('pending_order_items', None)
            session.pop(order_created_key, None)
            logger.info(f"Order confirmation email sent - User: {current_user.username}, Order: {order.id}")
            flash("Delivery set up successfully for your purchased items! Confirmation email sent.", "success")
            return redirect(url_for('user.dashboard'))
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating order for user {current_user.id}: {str(e)}", exc_info=True)
            flash('An error occurred while creating your order. Please try again.', 'danger')
            return render_template('order_item.html', form=form, stations=stations, items=items)
    
    return render_template('order_item.html', form=form, stations=stations, items=items)
