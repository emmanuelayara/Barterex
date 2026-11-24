"""Guest ("check my item's value") valuations.

A visitor gets one free AI estimate without an account. The item details, photos, status and AI result
live in a private GuestValuation record linked to a secret token that only exists in the visitor's
cookie (the database keeps just its hash). When the visitor registers or logs in, the same record is
turned into a private "valuation only" item on their account: no second upload, no second AI call, and
nothing is published or credited.
"""
import hashlib
import json
import math
import os
import secrets
import shutil
import time
from datetime import datetime, timedelta

from flask import current_app, request

from app import app, db
from file_upload_validator import optimize_image_for_storage
from logger_config import setup_logger
from models import GuestValuation, Item, ItemImage

logger = setup_logger(__name__)

GUEST_COOKIE = 'bx_guest_valuation'
RECORD_TTL = timedelta(hours=72)             # unclaimed records are deleted after this
VERIFICATION_WINDOW = timedelta(hours=48)    # kept alive while a registrant verifies their email and signs in
MAX_RECORD_LIFETIME = timedelta(days=7)      # hard cap, however often verification emails are resent
PROCESSING_TIMEOUT = timedelta(minutes=15)   # a job that never reported back (e.g. server restart)
CLAIMED_RETENTION = timedelta(days=7)

GENERIC_FAILURE = 'We could not estimate this item right now. Please try again.'

# Only these columns may be copied from the valuator's answer onto an Item.
AI_ITEM_FIELDS = (
    'ai_estimated_value', 'ai_confidence', 'ai_market_listings', 'ai_value_range_low',
    'ai_value_range_high', 'ai_risk_score', 'ai_risk_level', 'ai_risk_flags', 'ai_sources_used',
    'valuator_valuation_id', 'verification_status', 'verification_notes',
)


def new_token():
    return secrets.token_urlsafe(32)


def hash_token(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def current_token():
    token = request.cookies.get(GUEST_COOKIE, '')
    return token if 0 < len(token) <= 128 else None


def set_guest_cookie(response, token):
    response.set_cookie(
        GUEST_COOKIE, token, max_age=int(RECORD_TTL.total_seconds()), path='/', httponly=True,
        secure=bool(app.config.get('SESSION_COOKIE_SECURE')), samesite='Lax',
    )
    return response


def clear_guest_cookie(response):
    response.delete_cookie(GUEST_COOKIE, path='/')
    return response


def storage_root():
    """Private folder (outside static/) holding guest photos until they are claimed or expire."""
    return os.path.join(current_app.instance_path, 'guest_valuations')


def record_dir(record_id):
    return os.path.join(storage_root(), str(int(record_id)))


def _remove_dir(record_id):
    shutil.rmtree(record_dir(record_id), ignore_errors=True)


def _is_usable_value(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def find_by_token(token, include_claimed=False):
    """The visitor's unexpired record for this cookie token, or None."""
    if not token:
        return None
    record = GuestValuation.query.filter_by(token_hash=hash_token(token)).first()
    if record is None or record.expires_at <= datetime.utcnow():
        return None
    if record.status == 'claimed' and not include_claimed:
        return None
    _fail_if_stale(record)
    return record


def _fail_if_stale(record):
    if record.status == 'processing' and record.created_at < datetime.utcnow() - PROCESSING_TIMEOUT:
        updated = GuestValuation.query.filter_by(id=record.id, status='processing').update(
            {'status': 'failed', 'error_message': GENERIC_FAILURE}, synchronize_session=False)
        db.session.commit()
        if updated:
            db.session.refresh(record)


def create_record(fields, photos):
    """Saves a new guest record and its photos, then queues the AI valuation.

    `fields` holds already-validated name/description/condition/usage_duration/category and `photos`
    already-validated (filename, bytes) pairs. Returns (record, raw_token).
    """
    purge_expired()
    token = new_token()
    now = datetime.utcnow()
    record = GuestValuation(
        token_hash=hash_token(token), status='processing', created_at=now, expires_at=now + RECORD_TTL,
        name=fields['name'], description=fields['description'], condition=fields['condition'],
        usage_duration=fields.get('usage_duration') or None, category=fields['category'], image_files='[]',
    )
    db.session.add(record)
    db.session.flush()
    folder = record_dir(record.id)
    try:
        os.makedirs(folder, exist_ok=True)
        names = []
        for index, (filename, data) in enumerate(photos):
            extension = filename.rsplit('.', 1)[1].lower()
            extension = 'jpg' if extension == 'jpeg' else extension
            stored = f'{index:02d}.{extension}'
            with open(os.path.join(folder, stored), 'wb') as handle:
                handle.write(data)   # already validated; optimised later, only if the visitor claims it
            names.append(stored)
        record.image_files = json.dumps(names)
        db.session.commit()
    except Exception:
        db.session.rollback()
        _remove_dir(record.id)
        raise

    from valuator_client import queue_valuator_task
    if not queue_valuator_task(run_valuation, record.id):
        _store_result(record.id, None)
    return record, token


def _encode_photos(paths, encode, record_id):
    """Shrink and encode the photos in order, skipping any that cannot be read."""
    images = []
    for path in paths:
        try:
            images.append(encode(path))
        except Exception as error:
            logger.warning('Guest valuation %s: skipped unreadable photo: %s', record_id, error)
    return images


def run_valuation(record_id):
    """Background job: one AI call for the record, stored on the record (never re-run)."""
    from valuator_client import (
        MAX_IMAGES_SENT, client, encode_image_file_to_base64, extract_item_ai_fields,
        map_category_to_valuator, map_condition_to_valuator, parse_usage_duration,
    )
    try:
        with app.app_context():
            record = db.session.get(GuestValuation, record_id)
            if record is None or record.ai_valuated_at is not None or record.status not in ('processing', 'claimed'):
                return
            folder = record_dir(record.id)
            paths = [os.path.join(folder, name) for name in record.image_file_list()]
            usage = (record.usage_duration or '').strip()
            description = f'{record.description}\nUsed for: {usage}'.strip() if usage else record.description
            job = dict(
                title=record.name, description=description,
                condition=map_condition_to_valuator(record.condition),
                sale_type='new' if record.condition.strip().lower() == 'brand new' else 'second_hand',
                age_years=parse_usage_duration(usage), category=map_category_to_valuator(record.category),
            )
        images = _encode_photos(paths[:MAX_IMAGES_SENT], encode_image_file_to_base64, record_id)
        response = client.valuate(image_count=len(paths), images=images, account_days=0, **job)
        _store_result(record_id, extract_item_ai_fields(response) if response.get('success') else None)
    except Exception:
        logger.error('Guest valuation job failed for record %s', record_id, exc_info=True)
        try:
            _store_result(record_id, None)
        except Exception:
            logger.error('Could not record failure for guest valuation %s', record_id, exc_info=True)


def _store_result(record_id, fields):
    """Persist the AI answer. `fields` is None when the valuation failed."""
    with app.app_context():
        record = GuestValuation.query.filter_by(id=record_id).with_for_update().first()
        if record is None or record.ai_valuated_at is not None:
            return
        success = bool(fields) and _is_usable_value(fields.get('ai_estimated_value'))
        if not success:
            fields = {'verification_status': 'valuation_unavailable'}
        now = datetime.utcnow()
        if record.status == 'processing':
            record.status = 'ready' if success else 'failed'
            record.error_message = None if success else GENERIC_FAILURE
        elif record.status != 'claimed':
            return
        record.ai_fields = json.dumps({key: fields.get(key) for key in AI_ITEM_FIELDS if key in fields})
        record.ai_valuated_at = now
        if record.status == 'claimed' and record.claimed_item_id:
            item = db.session.get(Item, record.claimed_item_id)
            if item is not None and item.ai_valuated_at is None:
                _apply_ai_fields(item, record.ai_field_dict(), now)
        # Capture this while the row is locked so completion and claim can safely race.
        remove_private_photos = record.status == 'claimed'
        db.session.commit()
        if remove_private_photos:
            _remove_dir(record_id)


def _apply_ai_fields(item, fields, valuated_at):
    for key in AI_ITEM_FIELDS:
        if key in fields:
            setattr(item, key, fields[key])
    item.ai_valuated_at = valuated_at


def public_result(record):
    """The only AI details shown to a guest."""
    fields = record.ai_field_dict()
    return {
        'estimated_value': fields.get('ai_estimated_value'),
        'low': fields.get('ai_value_range_low'),
        'high': fields.get('ai_value_range_high'),
        'confidence': fields.get('ai_confidence'),
        'market_listings': fields.get('ai_market_listings'),
    }


def photo_path(record, index):
    names = record.image_file_list()
    if record.status == 'claimed' or not 0 <= index < len(names):
        return None
    path = os.path.join(record_dir(record.id), names[index])
    return path if os.path.isfile(path) else None


# ---------------------------------------------------------------------------
# Registration, email verification and sign-in
# ---------------------------------------------------------------------------

def _extend(record, now):
    cap = record.created_at + MAX_RECORD_LIFETIME
    record.expires_at = min(cap, max(record.expires_at, now + VERIFICATION_WINDOW))


def bind_to_new_user(user, token):
    """At registration: reserve the visitor's record for this account so it survives email verification."""
    try:
        record = find_by_token(token)
        if record is None or record.status not in ('ready', 'processing') or record.pending_user_id is not None:
            return False
        record.pending_user_id = user.id
        _extend(record, datetime.utcnow())
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        logger.error('Could not attach guest valuation to new user %s', user.id, exc_info=True)
        return False


def keep_for_pending_user(user):
    """Called when a verification email is (re)sent or verified: give the user time to sign in."""
    try:
        now = datetime.utcnow()
        for record in GuestValuation.query.filter(
            GuestValuation.pending_user_id == user.id, GuestValuation.status.in_(('ready', 'processing')),
            GuestValuation.expires_at > now,
        ).all():
            _extend(record, now)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.error('Could not extend guest valuation for user %s', user.id, exc_info=True)


def claim_for_user(user, token=None):
    """Turn this visitor's record into a private valuation-only item on the user's account.

    Returns the Item (also when this very user already claimed it) or None. Never raises, never
    publishes the item and never grants credits. Exactly one account can claim a record.
    """
    if not getattr(user, 'email_verified', False) or getattr(user, 'is_banned', False):
        return None
    try:
        return _claim(user, token)
    except Exception:
        db.session.rollback()
        logger.error('Guest valuation claim failed for user %s', user.id, exc_info=True)
        return None


def _claim(user, token):
    now = datetime.utcnow()
    candidates = list(GuestValuation.query.filter(
        GuestValuation.pending_user_id == user.id, GuestValuation.expires_at > now,
    ).order_by(GuestValuation.id.desc()).all())
    cookie_record = find_by_token(token, include_claimed=True)
    if cookie_record is not None and cookie_record not in candidates \
            and cookie_record.pending_user_id in (None, user.id):
        candidates.append(cookie_record)

    for record in candidates:
        if record.status == 'claimed':
            if record.claimed_by_user_id == user.id and record.claimed_item_id:
                return db.session.get(Item, record.claimed_item_id)   # repeated sign-in: just reopen it
            continue
        if record.status not in ('ready', 'processing'):
            continue
        item = _claim_record(user, record.id, now)
        if item is not None:
            return item
    return None


def _claim_record(user, record_id, now):
    # The single UPDATE is the duplicate-claim gate: only one transaction can flip the status.
    claimed = GuestValuation.query.filter(
        GuestValuation.id == record_id, GuestValuation.status.in_(('ready', 'processing')),
        GuestValuation.expires_at > now,
        db.or_(GuestValuation.pending_user_id.is_(None), GuestValuation.pending_user_id == user.id),
    ).update({'status': 'claimed', 'claimed_by_user_id': user.id, 'claimed_at': now},
             synchronize_session=False)
    if claimed != 1:
        db.session.rollback()
        return None

    record = db.session.get(GuestValuation, record_id)
    db.session.refresh(record)
    # A queued/running job still reads the private originals, even after an account claims them.
    valuation_finished = record.ai_valuated_at is not None
    copied = []
    try:
        item = Item(
            name=record.name, description=record.description, condition=record.condition,
            usage_duration=record.usage_duration if record.condition == 'Fairly Used' else None,
            category=record.category, user_id=user.id, uploaded_by_id=user.id, location=user.state,
            is_available=False, is_approved=False, status='valuation_only',
        )
        if record.ai_valuated_at is not None:
            _apply_ai_fields(item, record.ai_field_dict(), record.ai_valuated_at)
        else:
            item.verification_status = 'pending_valuation'   # the running job fills this in
        db.session.add(item)
        db.session.flush()
        _copy_photos(record, item, copied)
        record.claimed_item_id = item.id
        record.pending_user_id = user.id
        db.session.commit()
    except Exception:
        db.session.rollback()
        for path in copied:
            if os.path.isfile(path):
                os.remove(path)
        raise
    if valuation_finished:
        _remove_dir(record_id)
    logger.info('Guest valuation %s claimed by user %s as item %s', record.id, user.id, item.id)
    return item


def _copy_photos(record, item, copied):
    from image_analyzer import analyze_image_url
    upload_root = os.path.normpath(os.path.join(app.root_path, app.config['UPLOAD_FOLDER']))
    os.makedirs(upload_root, exist_ok=True)
    stamp = int(time.time())
    for index, name in enumerate(record.image_file_list()):
        source = os.path.join(record_dir(record.id), name)
        extension = name.rsplit('.', 1)[1]
        stored = f'{item.id}_{index}_{stamp}_{secrets.token_hex(4)}.{extension}'
        destination = os.path.join(upload_root, stored)
        # Guest photos are saved untouched so the estimate starts fast; they get the normal
        # storage optimisation here, once, and only for visitors who actually keep them.
        with open(source, 'rb') as original:
            data = original.read()
        try:
            data = optimize_image_for_storage(data, extension.lower())
        except Exception as error:
            logger.warning('Could not optimise guest photo %s, keeping the original: %s', name, error)
        with open(destination, 'wb') as handle:
            handle.write(data)
        copied.append(destination)
        analysis = {}
        try:
            analysis = analyze_image_url(stored) or {}
        except Exception as error:
            logger.warning('Image analysis failed for guest photo %s: %s', stored, error)
        db.session.add(ItemImage(
            item_id=item.id, image_url=stored, is_primary=(index == 0), order_index=index,
            width=analysis.get('width'), height=analysis.get('height'), file_size=analysis.get('file_size'),
            quality_flags=json.dumps(analysis.get('quality_flags', [])),
        ))
        if index == 0:
            item.image_url = stored


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------

def discard(record):
    """Remove a record that produced no usable estimate so the visitor can try again."""
    _remove_dir(record.id)
    db.session.delete(record)
    db.session.commit()


def purge_expired():
    """Delete unclaimed records (and their photos) past their expiry, and old claimed stubs."""
    now = datetime.utcnow()
    removed = 0
    try:
        doomed = GuestValuation.query.filter(db.or_(
            db.and_(GuestValuation.status != 'claimed', GuestValuation.expires_at <= now),
            db.and_(GuestValuation.status == 'claimed', GuestValuation.claimed_at <= now - CLAIMED_RETENTION),
        )).all()
        for record in doomed:
            _remove_dir(record.id)
            db.session.delete(record)
            removed += 1
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.error('Guest valuation expiry sweep failed', exc_info=True)
        return 0
    return removed
