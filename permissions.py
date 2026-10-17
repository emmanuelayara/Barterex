"""
Admin permission catalog and endpoint -> permission map.

Every action an admin can take is listed in PERMISSION_GROUPS. Super admins
implicitly hold every permission; sub-admins hold only the ones ticked when
they were created/edited. Enforcement happens in the admin blueprint's
before_request hook (routes/admin.py): any /admin endpoint that is not mapped
here is treated as super-admin-only, so new routes fail closed.
"""

# (group title, icon, [(permission key, label, description), ...])
PERMISSION_GROUPS = [
    ('Item Review', 'bi-search', [
        ('items.review', 'Review items', 'View the item queue and approve or reject submitted items'),
        ('items.preverification', 'Pre-verification', 'Approve or reject items in the pre-verification queue'),
        ('items.video_review', 'Video review', 'Approve or reject activation videos'),
        ('items.reconfirmation', 'Reconfirmations', 'Review failed-seller title reconfirmations'),
        ('items.manage', 'Manage items', 'Delete items and change or fix item statuses'),
    ]),
    ('Logistics & Settlement', 'bi-box-seam', [
        ('settlement.manage', 'Settlement queue', 'Quote delivery, record backing returns and verify settlement items'),
        ('verification.intake', 'Verification intake', 'View the intake log and record custody of received items'),
        ('inventory.view', 'Clearing inventory', 'View clearing inventory'),
        ('orders.manage', 'Orders', 'View orders and update order statuses'),
        ('pickup.manage', 'Pickup stations', 'Add, edit and delete pickup stations'),
    ]),
    ('Users', 'bi-people', [
        ('users.view', 'View users', 'List users and view user profiles'),
        ('users.edit', 'Adjust credits', 'Edit user credits and run credit corrections'),
        ('users.ban', 'Ban / unban users', 'Ban and unban users and view banned users'),
        ('users.appeals', 'Unban appeals', 'Review and decide unban appeals and requests'),
        ('users.delete', 'Delete users', 'Permanently delete user accounts'),
        ('users.export', 'Export user data', 'Download a user\'s personal data export'),
    ]),
    ('Support', 'bi-envelope', [
        ('messages.manage', 'Contact messages', 'Read and update contact form messages'),
    ]),
    ('System', 'bi-sliders', [
        ('audit.view', 'Audit log', 'View the admin audit log'),
        ('system.settings', 'System settings', 'Change system settings and maintenance mode'),
    ]),
]

PERMISSION_LABELS = {
    key: label
    for _, _, perms in PERMISSION_GROUPS
    for key, label, _ in perms
}
ALL_PERMISSIONS = frozenset(PERMISSION_LABELS)

# Reachable without any admin session.
PUBLIC_ENDPOINTS = frozenset({
    'admin.admin_login',
    'admin.admin_logout',
})

# Reachable by every active admin (the landing page adapts to their permissions).
AUTHENTICATED_ENDPOINTS = frozenset({
    'admin.admin_dashboard',
})

# Sentinel for endpoints only a super admin may use.
SUPER_ADMIN_ONLY = '__super_admin__'

ENDPOINT_PERMISSIONS = {
    # Item review
    'admin.approve_items': 'items.review',
    'admin.approve_item': 'items.review',
    'admin.reject_item': 'items.review',
    'admin.preverification_queue': 'items.preverification',
    'admin.approve_preverification': 'items.preverification',
    'admin.reject_preverification': 'items.preverification',
    'admin.video_review_queue': 'items.video_review',
    'admin.approve_activation_video': 'items.video_review',
    'admin.reject_activation_video': 'items.video_review',
    'admin.reconfirmation_review_queue': 'items.reconfirmation',
    'admin.approve_reconfirmation': 'items.reconfirmation',
    'admin.reject_reconfirmation': 'items.reconfirmation',
    'admin.delete_item': 'items.manage',
    'admin.update_item_status': 'items.manage',
    'admin.fix_misclassified_items': 'items.manage',

    # Logistics & settlement
    'admin.settlement_queue': 'settlement.manage',
    'admin.set_reservation_delivery_quote': 'settlement.manage',
    'admin.record_reservation_backing_return': 'settlement.manage',
    'admin.verify_seller_item_route': 'settlement.manage',
    'admin.verify_backing_asset_route': 'settlement.manage',
    'admin.verification_intake_log': 'verification.intake',
    'admin.record_verification_custody': 'verification.intake',
    'admin.clearing_inventory': 'inventory.view',
    'admin.manage_orders': 'orders.manage',
    'admin.update_order_status': 'orders.manage',
    'admin.orders_stream': 'orders.manage',
    'admin.get_order_updates': 'orders.manage',
    'admin.get_order_details': 'orders.manage',
    'admin.manage_pickup_stations': 'pickup.manage',
    'admin.add_pickup_station': 'pickup.manage',
    'admin.edit_pickup_station': 'pickup.manage',
    'admin.delete_pickup_station': 'pickup.manage',

    # Users
    'admin.manage_users': 'users.view',
    'admin.view_user': 'users.view',
    'admin.edit_user': 'users.edit',
    'admin.fix_missing_credits': 'users.edit',
    'admin.ban_user': 'users.ban',
    'admin.unban_user': 'users.ban',
    'admin.admin_banned_users': 'users.ban',
    'admin.pending_appeals': 'users.appeals',
    'admin.reject_unban_appeal': 'users.appeals',
    'admin.approve_unban': 'users.appeals',
    'admin.reject_unban': 'users.appeals',
    'admin.delete_user': 'users.delete',
    'admin.export_user_data': 'users.export',

    # Support
    'admin.view_messages': 'messages.manage',
    'admin.mark_message_read': 'messages.manage',
    'admin.update_message_status': 'messages.manage',

    # System
    'admin.audit_log': 'audit.view',
    'admin.system_settings': 'system.settings',
    'admin.maintenance_mode': 'system.settings',

    # Admin account management: only super admins
    'admin.admin_register': SUPER_ADMIN_ONLY,
    'admin.manage_admins': SUPER_ADMIN_ONLY,
    'admin.edit_admin': SUPER_ADMIN_ONLY,
    'admin.toggle_admin_active': SUPER_ADMIN_ONLY,
    'admin.delete_admin': SUPER_ADMIN_ONLY,
}


def clean_permissions(keys):
    """Keep only known permission keys, de-duplicated, in catalog order."""
    wanted = set(keys or ())
    return [key for key in PERMISSION_LABELS if key in wanted]
