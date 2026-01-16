from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, Response
from flask_login import login_required, current_user
from flask_wtf.csrf import generate_csrf
from typing import Union, Tuple

from app import db
from models import Favorite, Item
from logger_config import setup_logger
from exceptions import ResourceNotFoundError, DatabaseError
from error_handlers import handle_errors

logger = setup_logger(__name__)

favorites_bp = Blueprint('favorites', __name__)

# ==================== HELPER FUNCTIONS ====================

def get_or_create_favorites_list(user_id):
    """Get or create a favorites list for user"""
    # In this case, we don't need to create anything as we use Favorite model directly
    # This is more of a conceptual function for consistency with Cart
    return Favorite.query.filter_by(user_id=user_id).all()


def is_item_favorited(user_id: int, item_id: int) -> bool:
    """Check if an item is favorited by the user"""
    return Favorite.query.filter_by(user_id=user_id, item_id=item_id).first() is not None


def get_user_favorites_count(user_id: int) -> int:
    """Get count of favorited items for a user"""
    return Favorite.query.filter_by(user_id=user_id).count()


# ==================== ROUTES ====================

@favorites_bp.route('/favorites')
@login_required
@handle_errors
def view_favorites() -> Union[str, Response]:
    """View all favorited items"""
    try:
        favorites = Favorite.query.filter_by(user_id=current_user.id).all()
        
        # Get all favorited items, regardless of availability
        favorited_items = [fav.item for fav in favorites]
        
        # Separate available and unavailable items for display
        available_items = [item for item in favorited_items if item.is_available]
        unavailable_items = [item for item in favorited_items if not item.is_available]
        
        logger.info(f"User viewed favorites - User: {current_user.username}, Available: {len(available_items)}, Unavailable: {len(unavailable_items)}")
        return render_template(
            'favorites.html',
            favorited_items=favorited_items,
            available_items=available_items,
            unavailable_items=unavailable_items,
            total_favorites=len(favorited_items),
            csrf_token=generate_csrf
        )
        
    except Exception as e:
        logger.error(f"Error viewing favorites for user {current_user.username}: {str(e)}", exc_info=True)
        flash('An error occurred while loading your saved items.', 'danger')
        return redirect(url_for('marketplace.marketplace'))


@favorites_bp.route('/add_to_favorites/<int:item_id>', methods=['POST', 'GET'])
@login_required
@handle_errors
def add_to_favorites(item_id: int) -> Union[str, Response]:
    """Add item to favorites"""
    try:
        item = Item.query.get_or_404(item_id)
        
        if not item.is_available:
            logger.warning(f"Attempt to favorite unavailable item - Item: {item_id}, User: {current_user.username}")
            flash("This item is no longer available.", "warning")
            return redirect(url_for('marketplace.marketplace'))
        
        if item.user_id == current_user.id:
            logger.info(f"User attempted to favorite own item - Item: {item_id}, User: {current_user.username}")
            flash("You cannot favorite your own item.", "info")
            return redirect(url_for('marketplace.marketplace'))
        
        # Check if already favorited
        existing_favorite = Favorite.query.filter_by(user_id=current_user.id, item_id=item_id).first()
        if existing_favorite:
            logger.info(f"Item already in favorites - Item: {item_id}, User: {current_user.username}")
            flash("This item is already in your saved items.", "info")
            return redirect(url_for('marketplace.marketplace'))
        
        # Add to favorites
        favorite = Favorite(user_id=current_user.id, item_id=item_id)
        db.session.add(favorite)
        db.session.commit()
        
        logger.info(f"Item added to favorites - Item: {item_id}, User: {current_user.username}")
        flash(f"✓ '{item.name}' saved to your favorites!", "success")
        return redirect(request.referrer or url_for('marketplace.marketplace'))
        
    except Exception as e:
        logger.error(f"Error adding item to favorites: {str(e)}", exc_info=True)
        flash('An error occurred while saving the item.', 'danger')
        return redirect(request.referrer or url_for('marketplace.marketplace'))


@favorites_bp.route('/remove_from_favorites/<int:item_id>', methods=['POST'])
@login_required
@handle_errors
def remove_from_favorites(item_id: int) -> Union[str, Response]:
    """Remove item from favorites"""
    try:
        favorite = Favorite.query.filter_by(user_id=current_user.id, item_id=item_id).first()
        
        if favorite:
            db.session.delete(favorite)
            db.session.commit()
            logger.info(f"Item removed from favorites - Item: {item_id}, User: {current_user.username}")
            flash("Item removed from your saved items.", "success")
        else:
            logger.warning(f"Attempted to remove non-existent favorite - Item: {item_id}, User: {current_user.username}")
            flash("This item is not in your saved items.", "info")
        
        return redirect(request.referrer or url_for('favorites.view_favorites'))
        
    except Exception as e:
        logger.error(f"Error removing item from favorites: {str(e)}", exc_info=True)
        flash('An error occurred while removing the item.', 'danger')
        return redirect(request.referrer or url_for('favorites.view_favorites'))


# ==================== AJAX ENDPOINTS ====================

@favorites_bp.route('/api/favorites/toggle/<int:item_id>', methods=['POST'])
@login_required
def toggle_favorite(item_id: int):
    """AJAX endpoint to toggle favorite status (add/remove)"""
    try:
        item = Item.query.get(item_id)
        
        if not item:
            return jsonify({'error': 'Item not found'}), 404
        
        if item.user_id == current_user.id:
            return jsonify({'error': 'Cannot favorite your own item'}), 400
        
        # Check if already favorited
        favorite = Favorite.query.filter_by(user_id=current_user.id, item_id=item_id).first()
        
        if favorite:
            # Remove from favorites
            db.session.delete(favorite)
            db.session.commit()
            logger.info(f"Item removed from favorites via AJAX - Item: {item_id}, User: {current_user.username}")
            return jsonify({
                'success': True,
                'is_favorited': False,
                'message': 'Removed from favorites'
            }), 200
        else:
            # Add to favorites
            favorite = Favorite(user_id=current_user.id, item_id=item_id)
            db.session.add(favorite)
            db.session.commit()
            logger.info(f"Item added to favorites via AJAX - Item: {item_id}, User: {current_user.username}")
            return jsonify({
                'success': True,
                'is_favorited': True,
                'message': 'Added to favorites'
            }), 201
        
    except Exception as e:
        logger.error(f"Error toggling favorite status: {str(e)}", exc_info=True)
        return jsonify({'error': 'An error occurred'}), 500


@favorites_bp.route('/api/favorites/check/<int:item_id>', methods=['GET'])
@login_required
def check_favorite_status(item_id: int):
    """AJAX endpoint to check if item is favorited"""
    try:
        is_favorited = is_item_favorited(current_user.id, item_id)
        
        return jsonify({
            'success': True,
            'is_favorited': is_favorited,
            'item_id': item_id
        }), 200
        
    except Exception as e:
        logger.error(f"Error checking favorite status: {str(e)}", exc_info=True)
        return jsonify({'error': 'An error occurred'}), 500


@favorites_bp.route('/api/favorites/count', methods=['GET'])
@login_required
def get_favorites_count():
    """AJAX endpoint to get count of favorited items"""
    try:
        count = get_user_favorites_count(current_user.id)
        
        return jsonify({
            'success': True,
            'count': count
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting favorites count: {str(e)}", exc_info=True)
        return jsonify({'error': 'An error occurred'}), 500
