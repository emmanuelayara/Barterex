"""Restricted verification flow; pending challenges never grant a login session."""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user

from app import db
from models import Admin
from services.email_two_factor import (
    challenge_account, pending_challenge, start_challenge, verify_code,
    complete_admin_login, remember_admin_device,
)

two_factor_bp = Blueprint('two_factor', __name__, url_prefix='/two-factor')


@two_factor_bp.route('/verify', methods=['GET', 'POST'])
def verify():
    challenge = pending_challenge()
    if not challenge:
        flash('Start a new sign-in or verification request.', 'warning')
        return redirect(url_for('auth.login'))
    account = challenge_account(challenge)
    if challenge.purpose in ('enable', 'disable') and (
        not current_user.is_authenticated or current_user.id != account.id
    ):
        session.pop('email_2fa_pending', None)
        flash('Sign in before changing two-step verification.', 'danger')
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        action = request.form.get('action', 'verify')
        if action == 'cancel':
            challenge.consumed = True
            challenge.code_hash = None
            db.session.commit()
            session.pop('email_2fa_pending', None)
            return redirect(url_for('admin.admin_login' if isinstance(account, Admin) else 'account.security_settings'
                                    if challenge.purpose in ('enable', 'disable') else 'auth.login'))
        if action == 'resend':
            success, error = start_challenge(
                account, challenge.purpose, session.get('email_2fa_pending', {}).get('next'),
            )
            flash('A new verification code was emailed. Earlier codes no longer work.' if success else error,
                  'success' if success else 'danger')
            return redirect(url_for('two_factor.verify'))
        verified, error = verify_code((request.form.get('code') or '').strip())
        if error:
            flash(error, 'danger')
        else:
            purpose = verified.purpose
            target = session.get('email_2fa_pending', {}).get('next')
            session.pop('email_2fa_pending', None)
            if purpose in ('enable', 'disable'):
                account.two_factor_enabled = purpose == 'enable'
                account.two_factor_secret = None
                account.revoke_authentication()
                db.session.commit()
                from account_management import log_activity
                log_activity(account.id, 'two_factor_' + ('enabled' if purpose == 'enable' else 'disabled'),
                             'Email two-step verification setting changed after password and email verification.')
                logout_user()
                flash('Email two-step verification updated. Please sign in again. Wait 60 seconds between verification email requests.', 'success')
                return redirect(url_for('auth.login'))
            if isinstance(account, Admin):
                complete_admin_login(account, verified_by_email=True)
                flash('Administrator email verification complete.', 'success')
                return remember_admin_device(redirect(url_for('admin.admin_dashboard')), account)
            from datetime import datetime
            account.failed_login_attempts = 0
            account.account_locked_until = None
            first_login = account.first_login
            if not account.is_banned:
                account.last_login = datetime.utcnow()
                account.first_login = False
            db.session.commit()
            login_user(account, remember=False)
            flash("Welcome to Barter Express! You've received 1,000 starter BXC. Let's get trading!"
                  if first_login and not account.is_banned else 'Sign-in verified.', 'success')
            if account.is_banned:
                return redirect(url_for('auth.banned'))
            # Only relative, same-site paths may survive the password/code round trip.
            if target and target.startswith('/') and not target.startswith('//') and '\\' not in target:
                return redirect(target)
            return redirect(url_for('user.dashboard'))
    email = account.email
    local, domain = email.rsplit('@', 1)
    return render_template('account/email_two_factor.html', masked_email=local[:1] + '***@' + domain,
                           purpose=challenge.purpose, admin=isinstance(account, Admin))
