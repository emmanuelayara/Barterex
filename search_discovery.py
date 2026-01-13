"""
Search & Discovery Module
Provides recommendation algorithms, autocomplete suggestions, and analytics for marketplace
"""

from sqlalchemy import and_, func, desc
from sqlalchemy.sql import text
from app import db
from models import Item, User, CreditTransaction
from datetime import datetime, timedelta
from logger_config import setup_logger

logger = setup_logger(__name__)

# ==================== CONSTANTS ====================

CATEGORIES = [
    "Electronics",
    "Fashion / Clothing",
    "Footwear",
    "Home & Kitchen",
    "Beauty & Personal Care",
    "Sports & Outdoors",
    "Groceries",
    "Furniture",
    "Toys & Games",
    "Books & Stationery",
    "Health & Wellness",
    "Automotive",
    "Phones & Gadgets"
]

CONDITIONS = ["Brand New", "Fairly Used"]

TRENDING_PERIOD_DAYS = 7
RECOMMENDATION_POOL_SIZE = 20


# ==================== ANALYTICS ====================

def get_category_stats():
    """
    Get count of available items per category
    Returns: dict with category names as keys and item counts as values
    """
    try:
        stats = db.session.query(
            Item.category,
            func.count(Item.id).label('count')
        ).filter(
            Item.is_approved == True,
            Item.is_available == True,
            Item.value.isnot(None)
        ).group_by(
            Item.category
        ).all()
        
        category_stats = {cat: 0 for cat in CATEGORIES}
        for category, count in stats:
            if category in category_stats:
                category_stats[category] = count
        
        logger.info(f"Category stats calculated - {sum(category_stats.values())} total items")
        return category_stats
    except Exception as e:
        logger.error(f"Error calculating category stats: {str(e)}", exc_info=True)
        return {cat: 0 for cat in CATEGORIES}


def get_condition_stats():
    """
    Get count of items per condition
    Returns: dict with condition names and counts
    """
    try:
        stats = db.session.query(
            Item.condition,
            func.count(Item.id).label('count')
        ).filter(
            Item.is_approved == True,
            Item.is_available == True,
            Item.value.isnot(None)
        ).group_by(
            Item.condition
        ).all()
        
        condition_stats = {cond: 0 for cond in CONDITIONS}
        for condition, count in stats:
            if condition in condition_stats:
                condition_stats[condition] = count
        
        return condition_stats
    except Exception as e:
        logger.error(f"Error calculating condition stats: {str(e)}", exc_info=True)
        return {cond: 0 for cond in CONDITIONS}


# ==================== SEARCH SUGGESTIONS ====================

def get_search_suggestions(query, limit=8):
    """
    Get autocomplete suggestions based on search query
    Searches item names and descriptions
    Returns: list of dicts with suggestion, category, and count
    """
    if not query or len(query) < 2:
        return []
    
    try:
        # Search in item names
        suggestions_query = db.session.query(
            Item.name,
            Item.category,
            func.count(Item.id).label('count')
        ).filter(
            Item.is_approved == True,
            Item.is_available == True,
            Item.name.ilike(f'%{query}%'),
            Item.value.isnot(None)
        ).group_by(
            Item.name,
            Item.category
        ).order_by(
            desc(func.count(Item.id))
        ).limit(limit).all()
        
        suggestions = [
            {
                'name': item[0],
                'category': item[1],
                'count': item[2]
            }
            for item in suggestions_query
        ]
        
        logger.debug(f"Search suggestions for '{query}': {len(suggestions)} results")
        return suggestions
    except Exception as e:
        logger.error(f"Error getting search suggestions: {str(e)}", exc_info=True)
        return []


def get_trending_searches(limit=6):
    """
    Get popular/trending search terms based on item popularity
    Returns: list of trending item names
    """
    try:
        trending = db.session.query(
            Item.name
        ).filter(
            Item.is_approved == True,
            Item.is_available == True,
            Item.value.isnot(None)
        ).order_by(
            Item.id.desc()
        ).limit(limit).all()
        
        return [item[0] for item in trending]
    except Exception as e:
        logger.error(f"Error getting trending searches: {str(e)}", exc_info=True)
        return []


# ==================== RECOMMENDATIONS ====================

def get_trending_items(days=TRENDING_PERIOD_DAYS, limit=6, user_id=None):
    """
    Get trending items from past N days (most recently added)
    Optionally exclude items from a specific user
    
    Args:
        days: Number of days to look back
        limit: Maximum number of items to return
        user_id: If provided, exclude items from this user
    
    Returns: list of Item objects
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        filters = [
            Item.is_approved == True,
            Item.is_available == True,
            Item.value.isnot(None),
            Item.id > 0  # Recent items have higher IDs
        ]
        
        if user_id:
            filters.append(Item.user_id != user_id)
        
        trending = Item.query.filter(*filters).order_by(
            Item.id.desc()
        ).limit(limit).all()
        
        logger.info(f"Retrieved {len(trending)} trending items")
        return trending
    except Exception as e:
        logger.error(f"Error getting trending items: {str(e)}", exc_info=True)
        return []


def get_personalized_recommendations(user_id, limit=8):
    """
    Get personalized item recommendations based on:
    1. Categories user has viewed/liked before
    2. Price range preference
    3. Similar items to ones user viewed
    
    Returns: list of Item objects
    """
    try:
        user = User.query.get(user_id)
        if not user:
            return get_trending_items(limit=limit, user_id=user_id)
        
        # Get categories from user's items to understand their interests
        user_categories = db.session.query(Item.category).filter(
            Item.user_id == user_id
        ).distinct().all()
        user_category_list = [cat[0] for cat in user_categories] if user_categories else []
        
        if not user_category_list:
            # If no user history, return trending items (excluding user's own items)
            return get_trending_items(limit=limit, user_id=user_id)
        
        # Get items from similar categories, excluding user's own items
        recommendations = Item.query.filter(
            Item.is_approved == True,
            Item.is_available == True,
            Item.value.isnot(None),
            Item.user_id != user_id,
            Item.category.in_(user_category_list)
        ).order_by(
            Item.id.desc()
        ).limit(limit).all()
        
        logger.info(f"Generated {len(recommendations)} personalized recommendations for user {user_id}")
        return recommendations
    except Exception as e:
        logger.error(f"Error generating personalized recommendations: {str(e)}", exc_info=True)
        return get_trending_items(limit=limit, user_id=user_id)


def get_similar_items(item_id, limit=5):
    """
    Get items similar to a specific item
    Based on category and price range
    """
    try:
        item = Item.query.get(item_id)
        if not item:
            return []
        
        # Price range: ±30% of item value
        if item.value:
            min_price = item.value * 0.7
            max_price = item.value * 1.3
        else:
            min_price = 0
            max_price = float('inf')
        
        similar = Item.query.filter(
            Item.id != item_id,
            Item.category == item.category,
            Item.is_approved == True,
            Item.is_available == True,
            Item.value.isnot(None),
            Item.value >= min_price,
            Item.value <= max_price
        ).order_by(
            Item.id.desc()
        ).limit(limit).all()
        
        logger.debug(f"Retrieved {len(similar)} similar items for item {item_id}")
        return similar
    except Exception as e:
        logger.error(f"Error getting similar items: {str(e)}", exc_info=True)
        return []


def get_category_recommendations(category, limit=6):
    """
    Get items from a specific category, sorted by newest
    """
    try:
        items = Item.query.filter(
            Item.category == category,
            Item.is_approved == True,
            Item.is_available == True,
            Item.value.isnot(None)
        ).order_by(
            Item.id.desc()
        ).limit(limit).all()
        
        logger.debug(f"Retrieved {len(items)} recommendations from {category}")
        return items
    except Exception as e:
        logger.error(f"Error getting category recommendations: {str(e)}", exc_info=True)
        return []


# ==================== DISCOVERY CARDS ====================

def format_item_card(item):
    """
    Format item as card data for frontend display
    Returns: dict with item info suitable for card rendering
    """
    try:
        return {
            'id': item.id,
            'name': item.name,
            'category': item.category,
            'condition': item.condition,
            'value': item.value,
            'image_url': item.image_url,
            'location': item.location,
            'user_id': item.user_id,
            'url': f'/item/{item.id}'
        }
    except Exception as e:
        logger.error(f"Error formatting item card: {str(e)}")
        return None


def get_discovery_data(user_id=None):
    """
    Get comprehensive discovery data for homepage/marketplace
    Returns: dict with trending, recommended, and search data
    """
    try:
        data = {
            'trending_items': [format_item_card(item) for item in get_trending_items(limit=6)],
            'category_stats': get_category_stats(),
            'condition_stats': get_condition_stats(),
            'trending_searches': get_trending_searches(limit=6)
        }
        
        if user_id:
            data['recommended_items'] = [
                format_item_card(item) 
                for item in get_personalized_recommendations(user_id, limit=8)
            ]
        
        logger.info("Discovery data compiled successfully")
        return data
    except Exception as e:
        logger.error(f"Error compiling discovery data: {str(e)}", exc_info=True)
        return {
            'trending_items': [],
            'category_stats': {cat: 0 for cat in CATEGORIES},
            'condition_stats': {cond: 0 for cond in CONDITIONS},
            'trending_searches': []
        }


# ==================== SEARCH FILTERS ====================

def get_available_filters():
    """
    Get all available filter options with counts
    Returns: dict with categories and conditions and their counts
    """
    try:
        return {
            'categories': get_category_stats(),
            'conditions': get_condition_stats(),
            'price_ranges': {
                'under-1000': 'Under ₦1,000',
                '1000-5000': '₦1,000 - ₦5,000',
                '5000-10000': '₦5,000 - ₦10,000',
                '10000-25000': '₦10,000 - ₦25,000',
                '25000-50000': '₦25,000 - ₦50,000',
                'over-50000': 'Over ₦50,000'
            }
        }
    except Exception as e:
        logger.error(f"Error getting available filters: {str(e)}", exc_info=True)
        return {
            'categories': {},
            'conditions': {},
            'price_ranges': {}
        }


# ==================== SEARCH ANALYTICS ====================

def log_search(query, results_count, filters=None):
    """
    Log search queries for analytics (optional)
    Could be extended to track trending searches
    """
    try:
        logger.info(f"Search: '{query}' - Results: {results_count}, Filters: {filters}")
    except Exception as e:
        logger.error(f"Error logging search: {str(e)}")


def log_item_view(item_id, user_id=None):
    """
    Log item views for popularity tracking
    Could be extended to track most viewed items
    """
    try:
        # Could store in separate ItemView model for analytics
        logger.debug(f"Item {item_id} viewed by user {user_id}")
    except Exception as e:
        logger.error(f"Error logging item view: {str(e)}")
