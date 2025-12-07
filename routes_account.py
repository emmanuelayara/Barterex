"""
Account Management Routes
Handles security settings, password changes, 2FA, activity logging, and GDPR compliance
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from flask_login import login_required, current_user, logout_user
from datetime import datetime
import json
import io

from app import db
from models import User, ActivityLog, SecuritySettings
from forms import ChangePasswordForm, SecuritySettingsForm, TwoFactorSetupForm, ExportDataForm, DeleteAccountForm
from account_management import (
    log_activity, get_activity_history, get_client_ip, get_user_agent,
    change_password, validate_password_strength, 
    enable_2fa, disable_2fa,
    request_data_export, export_user_data, export_user_data_csv,
    request_account_deletion, cancel_account_deletion, delete_user_account,
    init_security_settings, update_security_settings, 
    add_trusted_device, add_trusted_ip, get_security_score
)

account_bp = Blueprint('account', __name__, url_prefix='/account')


# ==================== SECURITY SETTINGS ==================== #

@account_bp.route('/security', methods=['GET', 'POST'])
@login_required
def security_settings():
    """User's security settings page"""
    form = SecuritySettingsForm()
    settings = current_user.security_settings or init_security_settings(current_user.id)
    
    if form.validate_on_submit():
        update_security_settings(
            current_user.id,
            alert_on_new_device=form.alert_on_new_device.data,
            alert_on_location_change=form.alert_on_location_change.data,
            password_strength_required=form.password_strength_required.data
        )
        log_activity(current_user.id, 'security_settings_updated', 'User updated security settings')
        flash('Security settings updated successfully', 'success')
        return redirect(url_for('account.security_settings'))
    
    elif request.method == 'GET':
        form.alert_on_new_device.data = settings.alert_on_new_device
        form.alert_on_location_change.data = settings.alert_on_location_change
        form.password_strength_required.data = settings.password_strength_required
    
    security_score = get_security_score(current_user.id)
    
    return render_template('account/security_settings.html', 
                         form=form, 
                         settings=settings,
                         security_score=security_score)


# ==================== PASSWORD MANAGEMENT ==================== #

@account_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password_page():
    """Change password page"""
    form = ChangePasswordForm()
    settings = current_user.security_settings or init_security_settings(current_user.id)
    
    if form.validate_on_submit():
        success, message = change_password(
            current_user.id,
            form.current_password.data,
            form.new_password.data,
            settings.password_strength_required
        )
        
        if success:
            flash(message, 'success')
            return redirect(url_for('account.security_settings'))
        else:
            flash(message, 'danger')
    
    return render_template('account/change_password.html', form=form)


# ==================== TWO-FACTOR AUTHENTICATION ==================== #

@account_bp.route('/2fa/setup', methods=['GET', 'POST'])
@login_required
def setup_2fa():
    """Setup 2FA"""
    if current_user.two_factor_enabled:
        flash('2FA is already enabled. Disable it first if you want to change settings.', 'info')
        return redirect(url_for('account.security_settings'))
    
    # Generate temporary secret for setup
    if '2fa_temp_secret' not in session:
        import secrets
        session['2fa_temp_secret'] = secrets.token_hex(16)
    
    form = TwoFactorSetupForm()
    if form.validate_on_submit():
        # In a real app, verify the code against the secret
        # For now, just enable it
        success, secret = enable_2fa(current_user.id)
        if success:
            flash('2FA enabled successfully!', 'success')
            session.pop('2fa_temp_secret', None)
            return redirect(url_for('account.security_settings'))
    
    return render_template('account/setup_2fa.html', form=form, temp_secret=session.get('2fa_temp_secret'))


@account_bp.route('/2fa/disable', methods=['POST'])
@login_required
def disable_2fa_endpoint():
    """Disable 2FA"""
    if not current_user.two_factor_enabled:
        return jsonify({'success': False, 'message': '2FA not enabled'}), 400
    
    success, message = disable_2fa(current_user.id)
    if success:
        flash('2FA disabled', 'success')
    else:
        flash(message, 'danger')
    
    return redirect(url_for('account.security_settings'))


# ==================== ACTIVITY LOG ==================== #

@account_bp.route('/activity', methods=['GET'])
@login_required
def activity_log():
    """View user's activity log"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Get activity history
    all_activities = get_activity_history(current_user.id, days=90)
    
    # Paginate
    total = len(all_activities)
    start = (page - 1) * per_page
    end = start + per_page
    activities = all_activities[start:end]
    
    total_pages = (total + per_page - 1) // per_page
    
    return render_template('account/activity_log.html',
                         activities=activities,
                         page=page,
                         total_pages=total_pages,
                         total=total)


@account_bp.route('/activity/export', methods=['POST'])
@login_required
def export_activity():
    """Export activity log as CSV"""
    csv_data = export_user_data_csv(current_user.id)
    
    output = io.BytesIO()
    output.write(csv_data.encode('utf-8'))
    output.seek(0)
    
    log_activity(current_user.id, 'activity_export', 'User exported activity log')
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'activity_log_{current_user.username}_{datetime.utcnow().strftime("%Y%m%d")}.csv'
    )


# ==================== GDPR COMPLIANCE ==================== #

@account_bp.route('/data-export', methods=['GET', 'POST'])
@login_required
def data_export():
    """Request data export (GDPR)"""
    form = ExportDataForm()
    
    if form.validate_on_submit():
        success, message = request_data_export(current_user.id)
        if success:
            flash(message, 'success')
            return redirect(url_for('account.security_settings'))
        else:
            flash(message, 'warning')
    
    return render_template('account/data_export.html', form=form)


@account_bp.route('/data-export/download', methods=['GET'])
@login_required
def download_exported_data():
    """Download user's exported data"""
    data = export_user_data(current_user.id)
    
    output = io.BytesIO()
    output.write(json.dumps(data, indent=2, default=str).encode('utf-8'))
    output.seek(0)
    
    log_activity(current_user.id, 'data_downloaded', 'User downloaded exported data')
    
    return send_file(
        output,
        mimetype='application/json',
        as_attachment=True,
        download_name=f'user_data_{current_user.username}_{datetime.utcnow().strftime("%Y%m%d")}.json'
    )


# ==================== ACCOUNT DELETION ==================== #

@account_bp.route('/delete-account', methods=['GET', 'POST'])
@login_required
def delete_account():
    """Request account deletion"""
    form = DeleteAccountForm()
    
    if form.validate_on_submit():
        if form.confirm_username.data != current_user.username:
            flash('Username does not match. Please try again.', 'danger')
            return redirect(url_for('account.delete_account'))
        
        success, message = request_account_deletion(current_user.id)
        if success:
            flash(f'Account deletion scheduled. {message}', 'warning')
            return redirect(url_for('dashboard'))
        else:
            flash(message, 'danger')
    
    return render_template('account/delete_account.html', form=form)


@account_bp.route('/delete-account/cancel', methods=['POST'])
@login_required
def cancel_deletion():
    """Cancel account deletion request"""
    success, message = cancel_account_deletion(current_user.id)
    flash(message, 'success' if success else 'danger')
    return redirect(url_for('account.security_settings'))


# ==================== TRUSTED DEVICES ==================== #

@account_bp.route('/trusted-devices', methods=['GET'])
@login_required
def trusted_devices():
    """View and manage trusted devices"""
    settings = current_user.security_settings or init_security_settings(current_user.id)
    devices = settings.trusted_devices or []
    
    return render_template('account/trusted_devices.html', devices=devices)


@account_bp.route('/trusted-devices/add', methods=['POST'])
@login_required
def add_device():
    """Add current device as trusted"""
    device_fingerprint = request.form.get('fingerprint', '')
    device_name = request.form.get('name', 'Device')
    
    success = add_trusted_device(current_user.id, device_fingerprint, device_name)
    if success:
        flash('Device added to trusted list', 'success')
        log_activity(current_user.id, 'device_trusted', f'Added trusted device: {device_name}')
    else:
        flash('Error adding device', 'danger')
    
    return redirect(url_for('account.trusted_devices'))


@account_bp.route('/trusted-devices/remove/<int:index>', methods=['POST'])
@login_required
def remove_device(index):
    """Remove a trusted device"""
    settings = current_user.security_settings
    if settings and 0 <= index < len(settings.trusted_devices or []):
        devices = settings.trusted_devices
        device_name = devices[index].get('name', 'Device')
        devices.pop(index)
        settings.trusted_devices = devices
        db.session.commit()
        
        flash(f'Removed {device_name} from trusted devices', 'success')
        log_activity(current_user.id, 'device_untrusted', f'Removed trusted device: {device_name}')
    
    return redirect(url_for('account.trusted_devices'))


# ==================== IP WHITELIST ==================== #

@account_bp.route('/ip-whitelist', methods=['GET'])
@login_required
def ip_whitelist():
    """View and manage IP whitelist"""
    settings = current_user.security_settings or init_security_settings(current_user.id)
    ips = settings.ip_whitelist or []
    current_ip = get_client_ip()
    
    return render_template('account/ip_whitelist.html', ips=ips, current_ip=current_ip)


@account_bp.route('/ip-whitelist/add', methods=['POST'])
@login_required
def add_ip_whitelist():
    """Add current IP to whitelist"""
    current_ip = get_client_ip()
    
    success = add_trusted_ip(current_user.id, current_ip)
    if success:
        flash(f'Added {current_ip} to IP whitelist', 'success')
        log_activity(current_user.id, 'ip_whitelisted', f'Added IP to whitelist: {current_ip}')
    else:
        flash('Error adding IP', 'danger')
    
    return redirect(url_for('account.ip_whitelist'))


@account_bp.route('/ip-whitelist/remove/<ip_address>', methods=['POST'])
@login_required
def remove_ip_whitelist(ip_address):
    """Remove IP from whitelist"""
    settings = current_user.security_settings
    if settings and settings.ip_whitelist:
        ips = settings.ip_whitelist
        ips = [ip for ip in ips if ip.get('address') != ip_address]
        settings.ip_whitelist = ips
        db.session.commit()
        
        flash(f'Removed {ip_address} from IP whitelist', 'success')
        log_activity(current_user.id, 'ip_removed', f'Removed IP from whitelist: {ip_address}')
    
    return redirect(url_for('account.ip_whitelist'))


# ==================== API ENDPOINTS ==================== #

@account_bp.route('/api/security-score', methods=['GET'])
@login_required
def api_security_score():
    """Get user's security score"""
    score = get_security_score(current_user.id)
    
    if score >= 80:
        status = 'excellent'
        color = 'success'
    elif score >= 60:
        status = 'good'
        color = 'info'
    elif score >= 40:
        status = 'fair'
        color = 'warning'
    else:
        status = 'poor'
        color = 'danger'
    
    return jsonify({
        'score': score,
        'status': status,
        'color': color
    })
