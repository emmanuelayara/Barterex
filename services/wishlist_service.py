"""
Wishlist service for finding matches and sending notifications
"""

from models import db, Wishlist, WishlistMatch, Item, Notification, User
from datetime import datetime
from app import mail, app
from flask_mail import Message
from flask import render_template
from difflib import SequenceMatcher
import logging

logger = logging.getLogger(__name__)


def calculate_similarity(str1, str2):
    """Calculate string similarity ratio (0-1)"""
    if not str1 or not str2:
        return 0
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()


def find_wishlist_matches(item):
    """
    Find all wishlists that match a newly approved item.
    Returns list of (wishlist, user) tuples for items that should be notified.
    """
    try:
        logger.info(f'[WISHLIST] Starting wishlist matching for item: {item.id} - {item.name}')
        matches = []
        
        if not item or not item.is_approved:
            logger.warning(f'[WISHLIST] Item {item.id} is not approved or missing')
            return matches
        
        # Find active wishlists that match this item
        wishlists = Wishlist.query.filter_by(is_active=True).all()
        logger.info(f'[WISHLIST] Found {len(wishlists)} active wishlists to check')
        
        for wishlist in wishlists:
            should_match = False
            match_reason = None
            
            # Check for item name match (if searching for specific items)
            if wishlist.search_type == 'item' and wishlist.item_name:
                similarity = calculate_similarity(wishlist.item_name, item.name)
                logger.debug(f'[WISHLIST] Item search: Wishlist "{wishlist.item_name}" vs Item "{item.name}" - Similarity: {similarity:.2f}')
                # Match if similarity is >= 70%
                if similarity >= 0.7:
                    should_match = True
                    match_reason = f'Item name match (similarity: {similarity:.2f})'
            
            # Check for category match
            elif wishlist.search_type == 'category' and wishlist.category:
                if item.category and item.category.lower() == wishlist.category.lower():
                    should_match = True
                    match_reason = f'Category match: {wishlist.category}'
            
            if should_match:
                # Check if this match already exists
                existing_match = WishlistMatch.query.filter_by(
                    wishlist_id=wishlist.id,
                    item_id=item.id
                ).first()
                
                if not existing_match:
                    logger.info(f'[WISHLIST] MATCH FOUND - Wishlist ID: {wishlist.id}, User: {wishlist.user.username}, Reason: {match_reason}')
                    # Create new match
                    match = WishlistMatch(
                        wishlist_id=wishlist.id,
                        item_id=item.id
                    )
                    db.session.add(match)
                    matches.append((wishlist, wishlist.user))
                else:
                    logger.info(f'[WISHLIST] Match already exists for Wishlist ID: {wishlist.id}')
        
        db.session.commit()
        logger.info(f'[WISHLIST] Found {len(matches)} new wishlist matches for item {item.id}')
        return matches
        
    except Exception as e:
        db.session.rollback()
        logger.error(f'[WISHLIST] Error finding wishlist matches: {str(e)}', exc_info=True)
        return []


def send_wishlist_notification(wishlist, item, user=None):
    """
    Send notification to user about matched wishlist item.
    Sends both email and in-app notifications if enabled.
    """
    if not user:
        user = wishlist.user
    
    if not user:
        logger.warning(f'[WISHLIST] No user found for wishlist {wishlist.id}')
        return False
    
    try:
        logger.info(f'[WISHLIST] Processing wishlist notification - Wishlist ID: {wishlist.id}, Item: {item.name}, User: {user.username}')
        logger.debug(f'[WISHLIST] Notification settings - notify_via_email: {wishlist.notify_via_email}, notify_via_app: {wishlist.notify_via_app}')
        logger.debug(f'[WISHLIST] User email: {user.email}')
        
        notification_id = None
        
        # Create in-app notification if enabled
        if wishlist.notify_via_app:
            logger.info(f'[WISHLIST] Creating in-app notification for user {user.id}')
            try:
                notification = Notification(
                    user_id=user.id,
                    message=f'Wishlist Match! {item.name} is now available',
                    notification_type='wishlist_match',
                    category='alert',
                    data={'wishlist_id': wishlist.id, 'item_id': item.id}
                )
                db.session.add(notification)
                db.session.flush()
                notification_id = notification.id
                logger.info(f'[WISHLIST] In-app notification created with ID: {notification_id}')
            except Exception as notif_err:
                logger.error(f'[WISHLIST] Error creating notification: {str(notif_err)}', exc_info=True)
                raise
        else:
            logger.warning(f'[WISHLIST] In-app notification skipped - notify_via_app is False')
        
        # Send email notification if enabled
        if wishlist.notify_via_email and user.email:
            logger.info(f'[WISHLIST] Attempting to send email to {user.email}...')
            try:
                subject = f'Wishlist Alert: {item.name} is now available!'
                result = send_wishlist_email(
                    recipient=user.email,
                    user_name=user.username,
                    item_title=item.name,
                    item_id=item.id,
                    category=item.category,
                    condition=item.condition,
                    subject=subject,
                    item=item
                )
                logger.info(f'[WISHLIST] Email send result: {result}')
            except Exception as e:
                logger.error(f'[WISHLIST] Failed to send email to {user.email}: {str(e)}', exc_info=True)
        else:
            logger.warning(f'[WISHLIST] Email notification skipped - notify_via_email: {wishlist.notify_via_email}, user.email: {user.email}')
        
        # Update wishlist and match records
        wishlist.last_notified_at = datetime.utcnow()
        wishlist.notification_count = (wishlist.notification_count or 0) + 1
        
        # Update WishlistMatch
        match = WishlistMatch.query.filter_by(
            wishlist_id=wishlist.id,
            item_id=item.id,
            notification_id=None
        ).first()
        
        if match:
            match.notification_sent_at = datetime.utcnow()
            match.email_sent = wishlist.notify_via_email
            match.app_notification_sent = wishlist.notify_via_app
            match.notification_id = notification_id
        
        db.session.commit()
        logger.info(f'[WISHLIST] Sent wishlist notification to user {user.id} for item {item.id}')
        return True
        
    except Exception as e:
        db.session.rollback()
        logger.error(f'[WISHLIST] Error sending wishlist notification: {str(e)}', exc_info=True)
        return False


def send_wishlist_email(recipient, user_name, item_title, item_id, category, condition, subject, item=None):
    """Send wishlist match email to user using professional template"""
    
    try:
        logger.info(f'[WISHLIST] Starting email send to {recipient} for item {item_id}')
        
        # Get full item details if not provided
        if not item:
            item = Item.query.get(item_id)
        
        # Get the item image if available
        item_image = None
        if item and item.images:
            item_image = item.images[0].image_url
        elif item:
            item_image = item.image_url
        
        # Prepare template context
        context = {
            'user_name': user_name,
            'wishlist_name': category if not item else item_title,
            'item_name': item_title,
            'item_category': category or 'Uncategorized',
            'item_condition': condition or 'Available',
            'item_location': item.location if item and item.location else 'Not specified',
            'item_value': item.value if item and item.value else 0,
            'item_image': item_image,
            'item_description': item.description if item and item.description else None,
            'view_item_url': f"{app.config.get('APP_URL', 'https://barterex.com')}/item/{item_id}",
            'dashboard_url': f"{app.config.get('APP_URL', 'https://barterex.com')}/dashboard",
            'wishlist_url': f"{app.config.get('APP_URL', 'https://barterex.com')}/wishlist",
            'marketplace_url': f"{app.config.get('APP_URL', 'https://barterex.com')}/marketplace",
            'unsubscribe_url': f"{app.config.get('APP_URL', 'https://barterex.com')}/settings/notifications"
        }
        
        logger.debug(f'[WISHLIST] Email context prepared: {list(context.keys())}')
        
        # Render template and send email within app context
        with app.app_context():
            # Render template
            try:
                html_body = render_template('emails/wishlist_notification.html', **context)
                logger.info(f'[WISHLIST] Template rendered successfully, body length: {len(html_body)} chars')
            except Exception as template_err:
                logger.error(f'[WISHLIST] Template rendering failed: {str(template_err)}', exc_info=True)
                raise
            
            # Get sender configuration
            sender = app.config.get('MAIL_DEFAULT_SENDER', ('Barterex', 'noreply@barterex.com'))
            logger.info(f'[WISHLIST] Using sender: {sender}')
            
            # Create and send email
            msg = Message(
                subject=subject,
                recipients=[recipient],
                html=html_body,
                sender=sender
            )
            
            logger.info(f'[WISHLIST] Message object created, attempting to send...')
            mail.send(msg)
            logger.info(f'[WISHLIST] Wishlist notification email sent to {recipient} for item {item_id}')
        
        return True
        
    except Exception as e:
        logger.error(f'[WISHLIST] Error sending wishlist email to {recipient} for item {item_id}: {str(e)}', exc_info=True)
        return False


def bulk_find_matches_for_item(item_id):
    """Find all wishlist matches for a specific item (for background tasks)"""
    try:
        item = Item.query.get(item_id)
        if not item:
            return
        
        matches = find_wishlist_matches(item)
        
        for wishlist, user in matches:
            send_wishlist_notification(wishlist, item, user)
        
        logger.info(f'Processed {len(matches)} wishlist notifications for item {item_id}')
        
    except Exception as e:
        logger.error(f'Error in bulk find matches: {str(e)}')


def deactivate_matched_wishlists(item_id):
    """
    After an item is purchased/unavailable, optionally deactivate or update 
    wishlists that matched it (implement based on business logic)
    """
    try:
        matches = WishlistMatch.query.filter_by(item_id=item_id).all()
        
        for match in matches:
            # Optional: update match to mark as 'sold'
            match.item_sold_at = datetime.utcnow()
        
        db.session.commit()
        logger.info(f'Updated {len(matches)} wishlist matches for sold item {item_id}')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error deactivating matched wishlists: {str(e)}')
