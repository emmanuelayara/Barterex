from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user, logout_user
from flask_wtf.csrf import generate_csrf
from sqlalchemy import and_

from app import db
from models import Item, ItemImage
from logger_config import setup_logger
from exceptions import ResourceNotFoundError, DatabaseError
from error_handlers import handle_errors
from search_discovery import (
    get_search_suggestions,
    get_trending_items,
    get_personalized_recommendations,
    get_similar_items,
    get_category_stats,
    get_available_filters,
    log_search,
    log_item_view,
    format_item_card
)

logger = setup_logger(__name__)

marketplace_bp = Blueprint('marketplace', __name__)

# ==================== ROUTES ====================

@marketplace_bp.route('/')
@marketplace_bp.route('/marketplace')
@handle_errors
def marketplace():
    try:
        page = request.args.get('page', 1, type=int)
        condition_filter = request.args.get('condition')
        category_filter = request.args.get('category')
        search = request.args.get('search', '')
        state = request.args.get('state', '')
        price_range = request.args.get('price_range')

        logger.info(f"Marketplace search - Page: {page}, Search: '{search}', Category: {category_filter}, Condition: {condition_filter}")

        filters = [Item.is_approved == True, Item.is_available == True]

        if condition_filter:
            filters.append(Item.condition == condition_filter)

        if category_filter:
            filters.append(Item.category == category_filter)

        if search:
            filters.append(Item.name.ilike(f'%{search}%'))

        if state:
            filters.append(Item.location == state)

        if price_range:
            price_ranges = {
                'under-1000': (None, 1000),
                '1000-5000': (1000, 5000),
                '5000-10000': (5000, 10000),
                '10000-25000': (10000, 25000),
                '25000-50000': (25000, 50000),
                'over-50000': (50000, None)
            }
            
            if price_range in price_ranges:
                min_p, max_p = price_ranges[price_range]
                if min_p is not None:
                    filters.append(Item.value >= min_p)
                if max_p is not None:
                    filters.append(Item.value <= max_p)
            else:
                logger.warning(f"Invalid price range filter: {price_range}")

        filters.append(Item.value.isnot(None))

        items = Item.query.filter(and_(*filters)).order_by(Item.id.desc()).all()
        
        # Build breadcrumbs
        breadcrumbs = ['Marketplace']
        if category_filter:
            breadcrumbs.append(category_filter)
        if search:
            breadcrumbs.append(f'Search: {search}')
        
        logger.info(f"Marketplace search completed - Found {len(items)} items")
        return render_template('marketplace.html', items=items, breadcrumbs=breadcrumbs)
        
    except Exception as e:
        logger.error(f"Marketplace search error: {str(e)}", exc_info=True)
        flash('An error occurred while searching the marketplace. Please try again.', 'danger')
        return redirect(url_for('marketplace.marketplace'))


@marketplace_bp.route('/home')
@handle_errors
def home():
    try:
        trending_items = Item.query.filter_by(is_approved=True).order_by(Item.id.desc()).limit(6).all()
        logger.info(f"Home page loaded - {len(trending_items)} trending items displayed")
        breadcrumbs = ['Home']
        return render_template('home.html', trending_items=trending_items, breadcrumbs=breadcrumbs)
    except Exception as e:
        logger.error(f"Error loading home page: {str(e)}", exc_info=True)
        flash('An error occurred while loading the home page. Please refresh.', 'danger')
        return render_template('home.html', trending_items=[], breadcrumbs=['Home'])


@marketplace_bp.route('/item/<int:item_id>', methods=['GET', 'POST'])
@handle_errors
def view_item(item_id):
    try:
        item = Item.query.get_or_404(item_id)
        
        item_images = ItemImage.query.filter_by(item_id=item.id).order_by(ItemImage.order_index).all()
        
        if not item_images and item.image_url:
            class TempImage:
                def __init__(self, url, is_primary=True):
                    self.image_url = url
                    self.is_primary = is_primary
            
            item_images = [TempImage(item.image_url)]

        related_items = Item.query.filter(
            Item.category == item.category,
            Item.id != item.id,
            Item.is_available == True
        ).limit(5).all()

        logger.info(f"Item viewed - Item ID: {item_id}, Name: {item.name}, User: {item.user_id}")
        breadcrumbs = ['Marketplace', item.category, item.name[:50]]  # Truncate long names
        return render_template('item_detail.html', item=item, item_images=item_images, related_items=related_items, csrf_token=generate_csrf, breadcrumbs=breadcrumbs)
        
    except Exception as e:
        logger.error(f"Error viewing item {item_id}: {str(e)}", exc_info=True)
        flash(f'Could not load item. It may have been removed.', 'danger')
        return redirect(url_for('marketplace.marketplace'))


# ==================== API ENDPOINTS ====================

@marketplace_bp.route('/api/search-suggestions')
@handle_errors
def api_search_suggestions():
    """
    API endpoint for search autocomplete suggestions
    Query parameter: q (search query)
    Returns: JSON with suggestions array
    """
    try:
        query = request.args.get('q', '').strip()
        if not query or len(query) < 2:
            return jsonify({'suggestions': []})
        
        suggestions = get_search_suggestions(query, limit=8)
        return jsonify({'suggestions': suggestions})
    except Exception as e:
        logger.error(f"Error in search suggestions API: {str(e)}", exc_info=True)
        return jsonify({'suggestions': [], 'error': 'Failed to fetch suggestions'}), 500


@marketplace_bp.route('/api/categories-stats')
@handle_errors
def api_categories_stats():
    """
    API endpoint for category counts with current filters applied
    Query parameters: condition, category, state, price_range, search
    Returns: JSON with category statistics
    """
    try:
        # Get filter params
        condition_filter = request.args.get('condition')
        category_filter = request.args.get('category')
        search = request.args.get('search', '')
        state = request.args.get('state', '')
        price_range = request.args.get('price_range')

        filters = [Item.is_approved == True, Item.is_available == True, Item.value.isnot(None)]

        if condition_filter:
            filters.append(Item.condition == condition_filter)
        if category_filter:
            filters.append(Item.category == category_filter)
        if search:
            filters.append(Item.name.ilike(f'%{search}%'))
        if state:
            filters.append(Item.location == state)
        if price_range:
            price_ranges = {
                'under-1000': (None, 1000),
                '1000-5000': (1000, 5000),
                '5000-10000': (5000, 10000),
                '10000-25000': (10000, 25000),
                '25000-50000': (25000, 50000),
                'over-50000': (50000, None)
            }
            if price_range in price_ranges:
                min_p, max_p = price_ranges[price_range]
                if min_p is not None:
                    filters.append(Item.value >= min_p)
                if max_p is not None:
                    filters.append(Item.value <= max_p)

        # Get current filter counts
        available_filters = get_available_filters()
        
        # Apply filters and get category counts
        from sqlalchemy import func
        category_counts = db.session.query(
            Item.category,
            func.count(Item.id).label('count')
        ).filter(and_(*filters)).group_by(Item.category).all()
        
        category_data = {}
        for category, count in category_counts:
            category_data[category] = count

        return jsonify({
            'categories': category_data,
            'total': sum(category_data.values())
        })
    except Exception as e:
        logger.error(f"Error in categories stats API: {str(e)}", exc_info=True)
        return jsonify({'categories': {}, 'total': 0, 'error': 'Failed to fetch stats'}), 500


@marketplace_bp.route('/api/trending')
@handle_errors
def api_trending():
    """
    API endpoint for trending items
    Optional query parameter: limit (default 6)
    Returns: JSON with trending items array
    """
    try:
        limit = request.args.get('limit', 6, type=int)
        limit = min(limit, 20)  # Max 20 items
        
        trending = get_trending_items(limit=limit)
        items_data = [format_item_card(item) for item in trending if item]
        
        return jsonify({'trending': items_data})
    except Exception as e:
        logger.error(f"Error in trending API: {str(e)}", exc_info=True)
        return jsonify({'trending': [], 'error': 'Failed to fetch trending items'}), 500


@marketplace_bp.route('/api/recommended')
@login_required
@handle_errors
def api_recommended():
    """
    API endpoint for personalized recommendations
    Only available to logged-in users
    Optional query parameter: limit (default 8)
    Returns: JSON with recommended items array
    """
    try:
        limit = 4  # Fixed to 4 items
        recommendations = get_personalized_recommendations(current_user.id, limit=limit)
        items_data = [format_item_card(item) for item in recommendations if item]
        
        return jsonify({'recommended': items_data})
    except Exception as e:
        logger.error(f"Error in recommendations API: {str(e)}", exc_info=True)
        return jsonify({'recommended': [], 'error': 'Failed to fetch recommendations'}), 500


@marketplace_bp.route('/api/similar/<int:item_id>')
@handle_errors
def api_similar(item_id):
    """
    API endpoint for items similar to a specific item
    Path parameter: item_id
    Optional query parameter: limit (default 5)
    Returns: JSON with similar items array
    """
    try:
        limit = request.args.get('limit', 5, type=int)
        limit = min(limit, 15)  # Max 15 items
        
        similar = get_similar_items(item_id, limit=limit)
        items_data = [format_item_card(item) for item in similar if item]
        
        return jsonify({'similar': items_data})
    except Exception as e:
        logger.error(f"Error in similar items API: {str(e)}", exc_info=True)
        return jsonify({'similar': [], 'error': 'Failed to fetch similar items'}), 500


@marketplace_bp.route('/api/filters')
@handle_errors
def api_filters():
    """
    API endpoint for available filter options
    Returns: JSON with all available categories, conditions, and price ranges
    """
    try:
        filters = get_available_filters()
        return jsonify(filters)
    except Exception as e:
        logger.error(f"Error in filters API: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to fetch filters'}), 500


@marketplace_bp.route('/contact')
@handle_errors
def contact():
    logger.info("Contact page accessed")
    breadcrumbs = ['Contact Us']
    return render_template('contact.html', breadcrumbs=breadcrumbs)


@marketplace_bp.route('/about')
@handle_errors
def about():
    logger.info("About page accessed")
    breadcrumbs = ['About Us']
    return render_template('about.html', breadcrumbs=breadcrumbs)


@marketplace_bp.route('/faq')
@handle_errors
def faq():
    logger.info("FAQ page accessed")
    breadcrumbs = ['FAQ']
    return render_template('faq.html', breadcrumbs=breadcrumbs)


@marketplace_bp.route('/safety')
@handle_errors
def safety():
    logger.info("Safety page accessed")
    breadcrumbs = ['Safety Tips']
    return render_template('safety.html', breadcrumbs=breadcrumbs)


@marketplace_bp.route('/how-it-works')
@handle_errors
def how_it_works():
    logger.info("How It Works page accessed")
    return render_template('how_it_works.html')


@marketplace_bp.route('/terms')
@handle_errors
def terms():
    logger.info("Terms of Use page accessed")
    return render_template('terms_of_use.html')


@marketplace_bp.route('/privacy')
@handle_errors
def privacy():
    logger.info("Privacy page accessed")
    return render_template('privacy.html')
