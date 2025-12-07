"""
Routes package for Barterex application
"""

from routes.auth import auth_bp
from routes.marketplace import marketplace_bp
from routes.user import user_bp
from routes.items import items_bp
from routes.admin import admin_bp

__all__ = ['auth_bp', 'marketplace_bp', 'user_bp', 'items_bp', 'admin_bp']
