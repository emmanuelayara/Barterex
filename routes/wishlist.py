from flask import Blueprint, request, jsonify, session, send_file
from flask_login import login_required, current_user
from models import db, Wishlist, WishlistMatch, Item
from datetime import datetime
import logging
import csv
import io
from sqlalchemy import or_, and_

wishlist_bp = Blueprint('wishlist', __name__, url_prefix='/wishlist')
logger = logging.getLogger(__name__)


@wishlist_bp.route('/add', methods=['POST'])
@login_required
def add_to_wishlist():
    """Add an item or category to user's wishlist"""
    try:
        data = request.get_json()
        item_name = (data.get('item_name') or '').strip()
        category = (data.get('category') or '').strip()
        search_type = data.get('search_type', 'item')  # 'item' or 'category'
        notify_via_email = data.get('notify_via_email', True)
        notify_via_app = data.get('notify_via_app', True)
        
        # Validation
        if not item_name and not category:
            return jsonify({'error': 'Either item_name or category is required'}), 400
        
        if search_type not in ['item', 'category']:
            return jsonify({'error': 'search_type must be "item" or "category"'}), 400
        
        # Check if already in wishlist
        existing = Wishlist.query.filter_by(
            user_id=current_user.id,
            item_name=item_name if search_type == 'item' else None,
            category=category if search_type == 'category' else None,
            search_type=search_type
        ).first()
        
        if existing:
            return jsonify({'error': 'Item already in your wishlist', 'id': existing.id}), 409
        
        # Create new wishlist entry
        wishlist_item = Wishlist(
            user_id=current_user.id,
            item_name=item_name if search_type == 'item' else None,
            category=category if search_type == 'category' else None,
            search_type=search_type,
            is_active=True,
            notify_via_email=notify_via_email,
            notify_via_app=notify_via_app,
            created_at=datetime.utcnow()
        )
        
        db.session.add(wishlist_item)
        db.session.commit()
        
        logger.info(f'User {current_user.id} added {search_type} to wishlist: {item_name or category}')
        
        return jsonify({
            'success': True,
            'id': wishlist_item.id,
            'message': f'{search_type.capitalize()} added to wishlist'
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error adding to wishlist: {str(e)}')
        return jsonify({'error': 'Failed to add to wishlist'}), 500


@wishlist_bp.route('/view', methods=['GET'])
@login_required
def view_wishlist():
    """Get user's wishlist with pagination, search, sort, and filter"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        search = request.args.get('search', '').strip()
        sort_by = request.args.get('sort_by', 'created_at')  # created_at, name, status, matches
        sort_order = request.args.get('sort_order', 'desc')  # asc, desc
        status_filter = request.args.get('status', 'all')  # all, active, paused
        search_type_filter = request.args.get('search_type', 'all')  # all, item, category
        
        # Build base query
        query = Wishlist.query.filter_by(user_id=current_user.id)
        
        # Apply search filter
        if search:
            query = query.filter(
                or_(
                    Wishlist.item_name.ilike(f'%{search}%'),
                    Wishlist.category.ilike(f'%{search}%')
                )
            )
        
        # Apply status filter
        if status_filter == 'active':
            query = query.filter_by(is_active=True)
        elif status_filter == 'paused':
            query = query.filter_by(is_active=False)
        
        # Apply search type filter
        if search_type_filter in ['item', 'category']:
            query = query.filter_by(search_type=search_type_filter)
        
        # Apply sorting
        if sort_by == 'name':
            sort_column = db.func.coalesce(Wishlist.item_name, Wishlist.category)
        elif sort_by == 'status':
            sort_column = Wishlist.is_active
        elif sort_by == 'matches':
            # Sort by number of matches (complex, done in Python)
            sort_column = None
        else:  # created_at (default)
            sort_column = Wishlist.created_at
        
        # Apply sort column if exists
        if sort_column is not None:
            query = query.order_by(sort_column.desc() if sort_order == 'desc' else sort_column.asc())
        else:
            query = query.order_by(Wishlist.created_at.desc())
        
        pagination = query.paginate(page=page, per_page=per_page)
        
        wishlists = []
        for wishlist_item in pagination.items:
            match_count = len(wishlist_item.matched_items) if wishlist_item.matched_items else 0
            wishlists.append({
                'id': wishlist_item.id,
                'item_name': wishlist_item.item_name,
                'category': wishlist_item.category,
                'search_type': wishlist_item.search_type,
                'is_active': wishlist_item.is_active,
                'notify_via_email': wishlist_item.notify_via_email,
                'notify_via_app': wishlist_item.notify_via_app,
                'created_at': wishlist_item.created_at.isoformat() if wishlist_item.created_at else None,
                'last_notified_at': wishlist_item.last_notified_at.isoformat() if wishlist_item.last_notified_at else None,
                'notification_count': wishlist_item.notification_count,
                'match_count': match_count
            })
        
        # Sort by matches if needed
        if sort_by == 'matches':
            wishlists.sort(key=lambda x: x['match_count'], reverse=(sort_order == 'desc'))
        
        return jsonify({
            'success': True,
            'wishlists': wishlists,
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': page,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev
        }), 200
        
    except Exception as e:
        logger.error(f'Error fetching wishlist: {str(e)}')
        return jsonify({'error': 'Failed to fetch wishlist'}), 500


@wishlist_bp.route('/manage', methods=['GET'])
@login_required
def manage_wishlists():
    """Wishlist management page showing all user wishlists"""
    from flask import render_template
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 12  # Items per page
        
        # Get user's wishlists with pagination
        pagination = Wishlist.query.filter_by(
            user_id=current_user.id
        ).order_by(Wishlist.created_at.desc()).paginate(page=page, per_page=per_page)
        
        wishlists = []
        for wishlist_item in pagination.items:
            match_count = len(wishlist_item.matched_items) if wishlist_item.matched_items else 0
            wishlists.append({
                'id': wishlist_item.id,
                'item_name': wishlist_item.item_name,
                'category': wishlist_item.category,
                'search_type': wishlist_item.search_type,
                'is_active': wishlist_item.is_active,
                'notify_via_email': wishlist_item.notify_via_email,
                'notify_via_app': wishlist_item.notify_via_app,
                'created_at': wishlist_item.created_at,
                'last_notified_at': wishlist_item.last_notified_at,
                'notification_count': wishlist_item.notification_count or 0,
                'match_count': match_count
            })
        
        logger.info(f'Wishlist manage page accessed - User: {current_user.username}, Wishlists: {len(wishlists)}')
        
        return render_template(
            'wishlist_manage.html',
            wishlists=wishlists,
            pagination=pagination,
            total_wishlists=pagination.total
        )
        
    except Exception as e:
        logger.error(f'Error loading wishlist management page: {str(e)}', exc_info=True)
        from flask import flash, redirect, url_for
        flash('An error occurred while loading your wishlists.', 'danger')
        return redirect(url_for('user.dashboard'))


@wishlist_bp.route('/remove/<int:wishlist_id>', methods=['POST'])
@login_required
def remove_from_wishlist(wishlist_id):
    """Remove item from wishlist"""
    try:
        wishlist_item = Wishlist.query.filter_by(
            id=wishlist_id,
            user_id=current_user.id
        ).first()
        
        if not wishlist_item:
            return jsonify({'error': 'Wishlist item not found'}), 404
        
        # Delete associated matches
        WishlistMatch.query.filter_by(wishlist_id=wishlist_id).delete()
        
        db.session.delete(wishlist_item)
        db.session.commit()
        
        logger.info(f'User {current_user.id} removed wishlist item {wishlist_id}')
        
        return jsonify({'success': True, 'message': 'Item removed from wishlist'}), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error removing from wishlist: {str(e)}')
        return jsonify({'error': 'Failed to remove from wishlist'}), 500


@wishlist_bp.route('/pause/<int:wishlist_id>', methods=['POST'])
@login_required
def pause_wishlist(wishlist_id):
    """Pause notifications for a wishlist item"""
    try:
        wishlist_item = Wishlist.query.filter_by(
            id=wishlist_id,
            user_id=current_user.id
        ).first()
        
        if not wishlist_item:
            return jsonify({'error': 'Wishlist item not found'}), 404
        
        wishlist_item.is_active = False
        db.session.commit()
        
        logger.info(f'User {current_user.id} paused wishlist item {wishlist_id}')
        
        return jsonify({'success': True, 'message': 'Notifications paused'}), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error pausing wishlist: {str(e)}')
        return jsonify({'error': 'Failed to pause'}), 500


@wishlist_bp.route('/resume/<int:wishlist_id>', methods=['POST'])
@login_required
def resume_wishlist(wishlist_id):
    """Resume notifications for a wishlist item"""
    try:
        wishlist_item = Wishlist.query.filter_by(
            id=wishlist_id,
            user_id=current_user.id
        ).first()
        
        if not wishlist_item:
            return jsonify({'error': 'Wishlist item not found'}), 404
        
        wishlist_item.is_active = True
        db.session.commit()
        
        logger.info(f'User {current_user.id} resumed wishlist item {wishlist_id}')
        
        return jsonify({'success': True, 'message': 'Notifications resumed'}), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error resuming wishlist: {str(e)}')
        return jsonify({'error': 'Failed to resume'}), 500


@wishlist_bp.route('/matches/<int:wishlist_id>', methods=['GET'])
@login_required
def get_matches(wishlist_id):
    """Get all items that match a wishlist entry"""
    try:
        wishlist_item = Wishlist.query.filter_by(
            id=wishlist_id,
            user_id=current_user.id
        ).first()
        
        if not wishlist_item:
            return jsonify({'error': 'Wishlist item not found'}), 404
        
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # Get wishlist matches with item and user info
        pagination = WishlistMatch.query.filter_by(
            wishlist_id=wishlist_id
        ).paginate(page=page, per_page=per_page)
        
        matches = []
        for match in pagination.items:
            item = match.item
            if item:
                matches.append({
                    'match_id': match.id,
                    'item_id': item.id,
                    'name': item.name,
                    'username': item.user.username if item.user else 'Unknown',
                    'condition': item.condition,
                    'category': item.category,
                    'is_approved': item.is_approved,
                    'posted_date': item.created_at.isoformat() if hasattr(item, 'created_at') else None,
                    'notification_sent_at': match.notification_sent_at.isoformat() if match.notification_sent_at else None,
                    'email_sent': match.email_sent,
                    'app_notification_sent': match.app_notification_sent,
                    'viewUrl': f'/item/{item.id}'
                })
        
        return jsonify({
            'success': True,
            'wishlist_id': wishlist_id,
            'matches': matches,
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': page
        }), 200
        
    except Exception as e:
        logger.error(f'Error fetching matches: {str(e)}')
        return jsonify({'error': 'Failed to fetch matches'}), 500


@wishlist_bp.route('/bulk-pause', methods=['POST'])
@login_required
def bulk_pause():
    """Pause all active wishlists"""
    try:
        data = request.get_json() or {}
        wishlist_ids = data.get('wishlist_ids')  # Optional: specific IDs, otherwise all
        
        if wishlist_ids:
            # Pause specific wishlists
            Wishlist.query.filter(
                Wishlist.user_id == current_user.id,
                Wishlist.id.in_(wishlist_ids),
                Wishlist.is_active == True
            ).update({'is_active': False}, synchronize_session=False)
            count = len(wishlist_ids)
        else:
            # Pause all active wishlists
            count = Wishlist.query.filter_by(
                user_id=current_user.id,
                is_active=True
            ).update({'is_active': False}, synchronize_session=False)
        
        db.session.commit()
        logger.info(f'User {current_user.id} paused {count} wishlist items')
        
        return jsonify({
            'success': True,
            'message': f'Paused {count} wishlist{"s" if count != 1 else ""}',
            'count': count
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error bulk pausing wishlists: {str(e)}')
        return jsonify({'error': 'Failed to pause wishlists'}), 500


@wishlist_bp.route('/bulk-resume', methods=['POST'])
@login_required
def bulk_resume():
    """Resume all paused wishlists"""
    try:
        data = request.get_json() or {}
        wishlist_ids = data.get('wishlist_ids')  # Optional: specific IDs, otherwise all
        
        if wishlist_ids:
            # Resume specific wishlists
            Wishlist.query.filter(
                Wishlist.user_id == current_user.id,
                Wishlist.id.in_(wishlist_ids),
                Wishlist.is_active == False
            ).update({'is_active': True}, synchronize_session=False)
            count = len(wishlist_ids)
        else:
            # Resume all paused wishlists
            count = Wishlist.query.filter_by(
                user_id=current_user.id,
                is_active=False
            ).update({'is_active': True}, synchronize_session=False)
        
        db.session.commit()
        logger.info(f'User {current_user.id} resumed {count} wishlist items')
        
        return jsonify({
            'success': True,
            'message': f'Resumed {count} wishlist{"s" if count != 1 else ""}',
            'count': count
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error bulk resuming wishlists: {str(e)}')
        return jsonify({'error': 'Failed to resume wishlists'}), 500


@wishlist_bp.route('/bulk-delete', methods=['POST'])
@login_required
def bulk_delete():
    """Delete multiple wishlists"""
    try:
        data = request.get_json()
        wishlist_ids = data.get('wishlist_ids', [])
        
        if not wishlist_ids:
            return jsonify({'error': 'No wishlists specified'}), 400
        
        # Get wishlists to delete
        wishlists_to_delete = Wishlist.query.filter(
            Wishlist.user_id == current_user.id,
            Wishlist.id.in_(wishlist_ids)
        ).all()
        
        if not wishlists_to_delete:
            return jsonify({'error': 'No wishlists found'}), 404
        
        count = len(wishlists_to_delete)
        
        # Delete associated matches first
        for wb in wishlists_to_delete:
            WishlistMatch.query.filter_by(wishlist_id=wb.id).delete()
        
        # Delete wishlists
        for wb in wishlists_to_delete:
            db.session.delete(wb)
        
        db.session.commit()
        logger.info(f'User {current_user.id} deleted {count} wishlist items')
        
        return jsonify({
            'success': True,
            'message': f'Deleted {count} wishlist{"s" if count != 1 else ""}',
            'count': count
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error bulk deleting wishlists: {str(e)}')
        return jsonify({'error': 'Failed to delete wishlists'}), 500


@wishlist_bp.route('/export/csv', methods=['GET'])
@login_required
def export_csv():
    """Export wishlists to CSV file"""
    try:
        # Get all wishlists for the user (with optional filters)
        search = request.args.get('search', '').strip()
        status_filter = request.args.get('status', 'all')
        search_type_filter = request.args.get('search_type', 'all')
        
        query = Wishlist.query.filter_by(user_id=current_user.id)
        
        # Apply filters
        if search:
            query = query.filter(
                or_(
                    Wishlist.item_name.ilike(f'%{search}%'),
                    Wishlist.category.ilike(f'%{search}%')
                )
            )
        
        if status_filter == 'active':
            query = query.filter_by(is_active=True)
        elif status_filter == 'paused':
            query = query.filter_by(is_active=False)
        
        if search_type_filter in ['item', 'category']:
            query = query.filter_by(search_type=search_type_filter)
        
        wishlists = query.all()
        
        if not wishlists:
            return jsonify({'error': 'No wishlists to export'}), 404
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Item/Category Name',
            'Search Type',
            'Status',
            'Email Notifications',
            'In-App Notifications',
            'Matches Found',
            'Notifications Sent',
            'Created Date',
            'Last Notified Date'
        ])
        
        # Write data rows
        for wishlist_item in wishlists:
            match_count = len(wishlist_item.matched_items) if wishlist_item.matched_items else 0
            writer.writerow([
                wishlist_item.item_name or wishlist_item.category,
                wishlist_item.search_type,
                'Active' if wishlist_item.is_active else 'Paused',
                'Yes' if wishlist_item.notify_via_email else 'No',
                'Yes' if wishlist_item.notify_via_app else 'No',
                match_count,
                wishlist_item.notification_count or 0,
                wishlist_item.created_at.strftime('%Y-%m-%d %H:%M:%S') if wishlist_item.created_at else '',
                wishlist_item.last_notified_at.strftime('%Y-%m-%d %H:%M:%S') if wishlist_item.last_notified_at else 'Never'
            ])
        
        # Prepare response
        output.seek(0)
        bytes_output = io.BytesIO()
        bytes_output.write(output.getvalue().encode('utf-8'))
        bytes_output.seek(0)
        
        filename = f'wishlists_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv'
        
        logger.info(f'User {current_user.id} exported {len(wishlists)} wishlists to CSV')
        
        return send_file(
            bytes_output,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        logger.error(f'Error exporting wishlist to CSV: {str(e)}')
        return jsonify({'error': 'Failed to export wishlists'}), 500
