#!/usr/bin/env python3
"""
Script to update url_for() calls in templates to use blueprint namespaces.
This script maps old route names to new blueprint.route format.
"""

import os
import re
from pathlib import Path

# Mapping of old routes to new blueprint routes
ROUTE_MAPPING = {
    'home': 'marketplace.home',
    'marketplace': 'marketplace.marketplace',
    'view_item': 'marketplace.view_item',
    'contact': 'marketplace.contact',
    'about': 'marketplace.about',
    
    'login': 'auth.login',
    'register': 'auth.register',
    'logout': 'auth.logout',
    'forgot_password': 'auth.forgot_password',
    'reset_password': 'auth.reset_password',
    'banned': 'auth.banned',
    'request_unban': 'auth.request_unban',
    
    'dashboard': 'user.dashboard',
    'user_items': 'user.user_items',
    'edit_item': 'user.edit_item',
    'my_trades': 'user.my_trades',
    'credit_history': 'user.credit_history',
    'notifications': 'user.notifications',
    'mark_notification_read': 'user.mark_notification_read',
    'profile_settings': 'user.profile_settings',
    'user_orders': 'user.user_orders',
    'my_orders': 'user.user_orders',
    
    'upload_item': 'items.upload_item',
    'add_to_cart': 'items.add_to_cart',
    'view_cart': 'items.view_cart',
    'remove_from_cart': 'items.remove_from_cart',
    'clear_cart': 'items.clear_cart',
    'checkout': 'items.checkout',
    'process_checkout': 'items.process_checkout',
    'order_item': 'items.order_item',
    
    'admin_register': 'admin.admin_register',
    'admin_login': 'admin.admin_login',
    'admin_logout': 'admin.admin_logout',
    'admin_dashboard': 'admin.admin_dashboard',
    'manage_users': 'admin.manage_users',
    'view_user': 'admin.view_user',
    'ban_user': 'admin.ban_user',
    'admin_banned_users': 'admin.admin_banned_users',
    'unban_user': 'admin.unban_user',
    'approve_unban': 'admin.approve_unban',
    'reject_unban': 'admin.reject_unban',
    'edit_user': 'admin.edit_user',
    'approve_items': 'admin.approve_items',
    'approve_item': 'admin.approve_item',
    'reject_item': 'admin.reject_item',
    'update_item_status': 'admin.update_item_status',
    'fix_misclassified_items': 'admin.fix_misclassified_items',
    'fix_missing_credits': 'admin.fix_missing_credits',
    'add_pickup_station': 'admin.add_pickup_station',
    'edit_pickup_station': 'admin.edit_pickup_station',
    'delete_pickup_station': 'admin.delete_pickup_station',
    'manage_pickup_stations': 'admin.manage_pickup_stations',
    'manage_orders': 'admin.manage_orders',
    'update_order_status': 'admin.update_order_status',
}

def update_file(filepath):
    """Update a single file with new blueprint routes."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Replace url_for() calls
    for old_route, new_route in ROUTE_MAPPING.items():
        # Pattern: url_for('old_route' or url_for("old_route"
        pattern = rf"url_for\(['\"]({re.escape(old_route)})(['\"])"
        replacement = rf"url_for('{new_route}\2"
        content = re.sub(pattern, replacement, content)
    
    # Also update request.endpoint checks
    for old_route, new_route in ROUTE_MAPPING.items():
        pattern = rf"request\.endpoint == ['\"]({re.escape(old_route)})['\"]"
        replacement = rf"request.endpoint == '{new_route}'"
        content = re.sub(pattern, replacement, content)
    
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    templates_dir = Path('templates')
    updated_count = 0
    
    for template_file in templates_dir.rglob('*.html'):
        if update_file(template_file):
            print(f"✅ Updated: {template_file}")
            updated_count += 1
        else:
            print(f"⏭️  No changes: {template_file}")
    
    print(f"\n📝 Total files updated: {updated_count}")

if __name__ == '__main__':
    main()
