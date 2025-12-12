"""
Rank Rewards Module
Handles rank-specific logic, tier names, and reward mechanisms for the Barterex platform.
Works in conjunction with trading_points.py for the gamification system.
"""

from logger_config import setup_logger

logger = setup_logger(__name__)

# ==================== RANK TIER DEFINITIONS ====================

RANK_TIERS = {
    'Beginner': {
        'level_range': (1, 5),
        'description': 'Just getting started with trading',
        'badge_icon': '🌱',
        'color': '#10b981'
    },
    'Novice': {
        'level_range': (6, 10),
        'description': 'Learning the ropes of the platform',
        'badge_icon': '⭐',
        'color': '#3b82f6'
    },
    'Intermediate': {
        'level_range': (11, 15),
        'description': 'Becoming an experienced trader',
        'badge_icon': '💎',
        'color': '#8b5cf6'
    },
    'Advanced': {
        'level_range': (16, 20),
        'description': 'A seasoned trading expert',
        'badge_icon': '👑',
        'color': '#f59e0b'
    },
    'Expert': {
        'level_range': (21, 30),
        'description': 'Master of the trading platform',
        'badge_icon': '🏆',
        'color': '#ef4444'
    }
}


def get_tier_info(level):
    """
    Get complete tier information for a given level
    
    Args:
        level (int): User level
        
    Returns:
        dict: Tier information including name, badge, color, description
    """
    for tier_name, tier_data in RANK_TIERS.items():
        min_level, max_level = tier_data['level_range']
        if min_level <= level <= max_level:
            return {
                'name': tier_name,
                'badge_icon': tier_data['badge_icon'],
                'color': tier_data['color'],
                'description': tier_data['description'],
                'level_range': tier_data['level_range']
            }
    
    # Default to Expert for any level above 30 - reference existing tier
    expert_tier = RANK_TIERS['Expert']
    return {
        'name': 'Expert',
        'badge_icon': expert_tier['badge_icon'],
        'color': expert_tier['color'],
        'description': expert_tier['description'],
        'level_range': expert_tier['level_range']
    }


def get_tier_name(level):
    """
    Get tier name for a given level
    
    Args:
        level (int): User level
        
    Returns:
        str: Tier name (Beginner, Novice, Intermediate, Advanced, Expert)
    """
    tier_info = get_tier_info(level)
    return tier_info['name']


def get_tier_badge(level):
    """
    Get tier badge icon for a given level
    
    Args:
        level (int): User level
        
    Returns:
        str: Badge icon emoji
    """
    tier_info = get_tier_info(level)
    return tier_info['badge_icon']


def get_tier_color(level):
    """
    Get tier color for a given level
    
    Args:
        level (int): User level
        
    Returns:
        str: Hex color code
    """
    tier_info = get_tier_info(level)
    return tier_info['color']


def format_level_display(level, include_badge=True):
    """
    Format level for display with tier name and optional badge
    
    Args:
        level (int): User level
        include_badge (bool): Whether to include badge icon
        
    Returns:
        str: Formatted level display
    """
    tier_info = get_tier_info(level)
    if include_badge:
        return f"{tier_info['badge_icon']} Level {level} - {tier_info['name']}"
    else:
        return f"Level {level} - {tier_info['name']}"


def get_all_tiers():
    """
    Get all tier information
    
    Returns:
        dict: All tier definitions
    """
    return RANK_TIERS


# ==================== RANK PROGRESSION ====================

def calculate_progress_to_next_tier(level, total_points, level_thresholds):
    """
    Calculate progress percentage to next tier
    
    Args:
        level (int): Current level
        total_points (int): User's total trading points
        level_thresholds (dict): Dictionary of level thresholds from trading_points
        
    Returns:
        dict: Progress information including percentage and points needed
    """
    current_tier = get_tier_name(level)
    
    # Find the next tier
    next_tier = None
    next_tier_start_level = None
    for tier_name, tier_data in RANK_TIERS.items():
        min_level, max_level = tier_data['level_range']
        if min_level > level:
            next_tier = tier_name
            next_tier_start_level = min_level
            break
    
    if not next_tier or level >= 30:
        # Already at max tier
        return {
            'current_tier': current_tier,
            'next_tier': None,
            'progress_percent': 100,
            'points_to_next_tier': 0,
            'next_tier_level': None
        }
    
    # Get current tier range
    current_tier_info = get_tier_info(level)
    tier_start_level, tier_end_level = current_tier_info['level_range']
    
    # Calculate points within current tier
    tier_start_points = level_thresholds.get(tier_start_level, 0)
    next_tier_start_points = level_thresholds.get(next_tier_start_level, 0)
    
    points_in_tier = total_points - tier_start_points
    points_needed_for_tier = next_tier_start_points - tier_start_points
    
    progress_percent = min(100, int((points_in_tier / points_needed_for_tier) * 100)) if points_needed_for_tier > 0 else 0
    points_to_next_tier = max(0, next_tier_start_points - total_points)
    
    return {
        'current_tier': current_tier,
        'next_tier': next_tier,
        'progress_percent': progress_percent,
        'points_to_next_tier': points_to_next_tier,
        'next_tier_level': next_tier_start_level
    }
