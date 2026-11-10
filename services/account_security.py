"""Reauthentication and verified changes to the account recovery address."""

import hashlib
import secrets

from flask import current_app, url_for
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import check_password_hash
from sqlalchemy.exc import IntegrityError

from app import db
from models import User


def request_email_change(user, email, password):
    from routes.auth import send_email_async
    from markupsafe import escape

    email = email.strip().lower()
    if email == user.email.lower():
        return False, None
    if user.two_factor_enabled:
        return False, 'Disable email two-step verification using your current inbox before changing your email address. Re-enable it after confirming the new email.'
    if not check_password_hash(user.password_hash, password or ''):
        return False, 'Enter your current password to change your email address.'
    if User.query.filter(db.func.lower(User.email) == email, User.id != user.id).first():
        return False, 'This email address is already in use.'
    token = URLSafeTimedSerializer(current_app.config['SECRET_KEY']).dumps({
        'user_id': user.id, 'email': email, 'old_email': user.email,
        'credential': hashlib.sha256(user.password_hash.encode()).hexdigest(),
        'auth_id': user.get_id(),
    }, salt='change-recovery-email')
    link = url_for('auth.confirm_email_change', token=token, _external=True)
    send_email_async(
        'Confirm your new email address', [email],
        f'<p>Confirm your Barter Express email change within one hour: <a href="{escape(link)}">Confirm email change</a>.</p>',
    )
    send_email_async(
        'Email change requested', [user.email],
        '<p>A change to your recovery email was requested. Your current email has not changed. If this was not you, reset your password and contact support.</p>',
    )
    return True, None


def confirm_email_change(token):
    try:
        data = URLSafeTimedSerializer(current_app.config['SECRET_KEY']).loads(
            token, salt='change-recovery-email', max_age=3600,
        )
    except (BadSignature, SignatureExpired):
        return False
    if not isinstance(data, dict):
        return False
    user = User.query.filter_by(id=data.get('user_id')).with_for_update().first()
    if not user or user.two_factor_enabled or user.get_id() != data.get('auth_id') or user.email != data.get('old_email') or (
        hashlib.sha256(user.password_hash.encode()).hexdigest() != data.get('credential')
    ):
        return False
    if User.query.filter(db.func.lower(User.email) == data['email'], User.id != user.id).first():
        return False
    changed = User.query.filter_by(
        id=user.id, email=data['old_email'], password_hash=user.password_hash, auth_token=user.auth_token,
    ).filter(db.or_(User.two_factor_enabled.is_(False), User.two_factor_enabled.is_(None))).update({
        'email': data['email'], 'email_verified': True,
        'email_verification_token': None, 'email_verification_expires_at': None,
        'auth_token': secrets.token_urlsafe(32),
    }, synchronize_session=False)
    if not changed:
        db.session.rollback()
        return False
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        current_app.logger.warning('Email confirmation conflicted with an existing account.')
        return False
    db.session.refresh(user)
    return True
