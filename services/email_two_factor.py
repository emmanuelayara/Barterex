"""Short-lived, browser-bound email codes with database-backed abuse budgets."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from smtplib import SMTPException

from flask import current_app, render_template, session
from flask_mail import Message
from sqlalchemy.exc import IntegrityError

from app import db, mail
from models import Admin, EmailLoginChallenge, User

CODE_LIFETIME = timedelta(minutes=5)
BUDGET_WINDOW = timedelta(minutes=15)
MAX_ATTEMPTS = 5
MAX_SENDS = 5


def fingerprint(account):
    password = account.password if isinstance(account, Admin) else account.password_hash
    identity = str(account.id) if isinstance(account, Admin) else account.get_id()
    enabled = True if isinstance(account, Admin) else bool(account.two_factor_enabled)
    return hashlib.sha256(f'{identity}|{account.email}|{password}|{enabled}'.encode()).hexdigest()


def digest(value):
    return hmac.new(current_app.config['SECRET_KEY'].encode(), value.encode(), hashlib.sha256).hexdigest()


def challenge_account(challenge):
    kind, identifier = challenge.principal.split(':', 1)
    account = db.session.get(Admin if kind == 'admin' else User, int(identifier))
    if not account or (kind == 'admin' and not account.is_active):
        return None
    if account.account_locked_until and account.account_locked_until > datetime.utcnow():
        return None
    if kind == 'user' and not account.email_verified:
        return None
    return account if hmac.compare_digest(challenge.credential_hash, fingerprint(account)) else None


def pending_challenge():
    pending = session.get('email_2fa_pending', {})
    if not isinstance(pending, dict):
        return None
    challenge = EmailLoginChallenge.query.filter_by(challenge_token=pending.get('token')).first()
    if not challenge or not isinstance(pending.get('binding'), str):
        return None
    if not hmac.compare_digest(challenge.binding_hash, digest(pending['binding'])):
        return None
    if challenge.consumed or not challenge_account(challenge):
        return None
    return challenge


def start_challenge(account, purpose, next_page=None):
    """Issue a code only after password verification by the caller."""
    if current_app.config.get('MAIL_DEBUG') or (
        current_app.config.get('MAIL_SUPPRESS_SEND') and not current_app.testing
    ):
        current_app.logger.error('Email verification requires SMTP debug and production mail suppression to be disabled.')
        return False, 'Email verification is not configured safely. Contact support.'
    now = datetime.utcnow()
    kind = 'admin' if isinstance(account, Admin) else 'user'
    principal = f'{kind}:{account.id}'
    challenge = EmailLoginChallenge.query.filter_by(principal=principal).with_for_update().first()
    if challenge:
        reset_window = now - challenge.window_started_at >= BUDGET_WINDOW
        attempts = 0 if reset_window else challenge.attempts
        sends = 0 if reset_window else challenge.sends
        window_started_at = now if reset_window else challenge.window_started_at
        if attempts >= MAX_ATTEMPTS or sends >= MAX_SENDS:
            return False, 'Too many verification attempts or email requests. Try again in 15 minutes.'
        if now - challenge.last_sent_at < timedelta(seconds=60):
            return False, 'Wait at least 60 seconds before requesting another code.'
    token = secrets.token_urlsafe(32)
    binding = secrets.token_urlsafe(32)
    code = f'{secrets.randbelow(1000000):06d}'
    values = {
        'challenge_token': token, 'binding_hash': digest(binding),
        'code_hash': digest(f'{token}:{code}'), 'credential_hash': fingerprint(account),
        'purpose': purpose, 'expires_at': now + CODE_LIFETIME, 'last_sent_at': now,
        'consumed': False,
    }
    if challenge:
        previous_token = challenge.challenge_token
        values.update(sends=sends + 1, attempts=attempts, window_started_at=window_started_at)
        changed = EmailLoginChallenge.query.filter_by(
            id=challenge.id, challenge_token=previous_token, attempts=challenge.attempts, sends=challenge.sends,
        ).update(
            values, synchronize_session=False,
        )
        if not changed:
            db.session.rollback()
            return False, 'Another verification request is in progress. Please retry.'
    else:
        challenge = EmailLoginChallenge(
            principal=principal, sends=1, attempts=0, window_started_at=now, **values,
        )
        db.session.add(challenge)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        current_app.logger.warning('Concurrent email verification request for %s', principal)
        return False, 'Another verification request is in progress. Please retry.'
    try:
        html = render_template('emails/two_factor_code.html', code=code, purpose=purpose)
        mail.send(Message(
            subject='Your Barter Express verification code',
            recipients=[account.email], html=html,
            body=f'Your Barter Express verification code is {code}. It expires in 5 minutes. Never share this code.',
        ))
    except (SMTPException, OSError):
        current_app.logger.exception('Could not deliver email verification code for %s', principal)
        EmailLoginChallenge.query.filter_by(challenge_token=token).update(
            {'consumed': True, 'code_hash': None}, synchronize_session=False,
        )
        db.session.commit()
        session.pop('email_2fa_pending', None)
        return False, 'The verification email could not be sent. Please wait a minute and retry or contact support.'
    session['email_2fa_pending'] = {'token': token, 'binding': binding, 'next': next_page}
    return True, None


def verify_code(code):
    """Consume valid codes once; invalid attempts share a non-resetting budget."""
    challenge = pending_challenge()
    now = datetime.utcnow()
    if not challenge:
        return None, 'This verification session is invalid. Sign in or start setup again.'
    if challenge.expires_at <= now or challenge.attempts >= MAX_ATTEMPTS:
        return None, 'This code has expired or too many attempts were made. Request a new code or try again later.'
    matches = (
        isinstance(code, str) and len(code) == 6 and code.isascii() and code.isdigit()
        and hmac.compare_digest(challenge.code_hash or '', digest(f'{challenge.challenge_token}:{code}'))
    )
    updates = {'attempts': EmailLoginChallenge.attempts + 1}
    if matches:
        updates.update(consumed=True, code_hash=None)
    changed = EmailLoginChallenge.query.filter(
        EmailLoginChallenge.id == challenge.id,
        EmailLoginChallenge.challenge_token == challenge.challenge_token,
        EmailLoginChallenge.consumed.is_(False),
        EmailLoginChallenge.expires_at > now,
        EmailLoginChallenge.attempts < MAX_ATTEMPTS,
    ).update(updates, synchronize_session=False)
    if not changed:
        db.session.rollback()
        return None, 'This code is expired, already used or locked. Start again.'
    db.session.flush()
    if not matches:
        db.session.commit()
        return None, 'Incorrect verification code.'
    return challenge, None
