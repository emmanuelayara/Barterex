"""
BarterXpress Valuator client
============================
Connects Barterex to the standalone "barterxpress-valuator" AI service
(a separate Flask app) over HTTP.

What Barterex does with it
--------------------------
1. A user uploads an item  -> the item is saved FIRST, then valuated in
   the background (a valuation takes 35-45 seconds, so the upload page
   must never wait for it). The result fills the AI fields on the Item
   so the admin sees a suggested value in the approvals queue.
2. An admin approves / rejects the item -> we tell the valuator the real
   outcome (POST /api/verify). That closes the loop and, over time,
   gives the valuator real data to learn from.

Barterex's own `User.credits` stays the ONLY source of truth for
balances. The valuator's credit numbers are advice for the admin, never
paid out automatically, so nobody can be credited twice.

Nothing in here can break an upload or an approval: every public
function catches its own errors, logs them, and returns.

Settings (put these in .env — see .env.example):
    VALUATOR_API_URL       Where the valuator lives, e.g.
                           http://127.0.0.1:5001  (unset = feature OFF)
    VALUATOR_API_KEY       The shared secret. Must be identical to the
                           VALUATOR_API_KEY in the valuator's own .env.
    VALUATOR_API_TIMEOUT   Seconds to wait for a valuation. Default 120.
    VALUATOR_ENABLED       Set to false to switch the feature off.
    VALUATOR_MAX_PARALLEL  How many valuations may run at once. Default 2.
"""

import base64
import io
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests

try:  # the project's own logger; fall back to plain logging if unavailable
    from logger_config import setup_logger
    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration (read at call time so tests / .env changes are respected)
# ---------------------------------------------------------------------------

def _base_url() -> str:
    return (os.getenv('VALUATOR_API_URL') or '').strip().rstrip('/')


def _api_key() -> str:
    return (os.getenv('VALUATOR_API_KEY') or '').strip()


def _timeout() -> float:
    try:
        return max(5.0, float(os.getenv('VALUATOR_API_TIMEOUT', '120')))
    except ValueError:
        return 120.0


def is_enabled() -> bool:
    """On only when a URL is configured and it isn't switched off."""
    if os.getenv('VALUATOR_ENABLED', 'true').strip().lower() in ('0', 'false', 'no', 'off'):
        return False
    return bool(_base_url())


MAX_IMAGES_SENT = 3          # photos sent per item (cost + speed)
MAX_IMAGE_SIDE = 1280        # px; bigger photos are shrunk before sending

# ---------------------------------------------------------------------------
# Translating Barterex values into what the valuator understands
# ---------------------------------------------------------------------------

# Barterex label -> valuator condition.
CONDITION_MAP = {
    'brand new': 'brand_new',
    'like new': 'like_new',
    'lightly used': 'good',
    'fairly used': 'good',
    'used': 'fair',
    'for parts': 'poor',
}

# Only categories that are clearly electronics are forced. Everything
# else is left for the valuator to detect from the item's name, because
# e.g. "Fashion Accessories" can hold a Rolex, a gold chain or a cap and
# they price very differently.
CATEGORY_MAP = {
    'phones & gadgets': 'electronics',
    'consumer electronics': 'electronics',
    'gaming & accessories': 'electronics',
}


def map_condition_to_valuator(condition: str) -> str:
    if not condition:
        return 'good'
    return CONDITION_MAP.get(condition.strip().lower(), 'good')


def map_category_to_valuator(category: str):
    """The valuator's category name, or None to let it work it out."""
    if not category:
        return None
    return CATEGORY_MAP.get(category.strip().lower())


_WORD_NUMBERS = {'a': 1, 'an': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4,
                 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9,
                 'ten': 10, 'half': 0.5}
_UNIT_YEARS = {'y': 1.0, 'yr': 1.0, 'yrs': 1.0, 'year': 1.0, 'years': 1.0,
               'm': 1 / 12, 'mo': 1 / 12, 'mos': 1 / 12, 'month': 1 / 12, 'months': 1 / 12,
               'w': 1 / 52, 'wk': 1 / 52, 'wks': 1 / 52, 'week': 1 / 52, 'weeks': 1 / 52,
               'd': 1 / 365, 'day': 1 / 365, 'days': 1 / 365}


def parse_usage_duration(text):
    """
    Turns what the seller typed in "How long have you used it?" into
    years, e.g. "2 years" -> 2.0, "6 months" -> 0.5, "a year" -> 1.0.
    Returns None when it can't tell (the valuator then estimates the age
    itself). Never guesses a made-up number.
    """
    if not text or not isinstance(text, str):
        return None
    t = text.strip().lower()
    match = re.search(r'(\d+(?:\.\d+)?|a|an|one|two|three|four|five|six|seven|eight|nine|ten|half)\s*'
                      r'(?:and a half\s*)?(years?|yrs?|y|months?|mos?|m|weeks?|wks?|w|days?|d)\b', t)
    if not match:
        return None
    raw, unit = match.group(1), match.group(2)
    number = float(raw) if raw[0].isdigit() else float(_WORD_NUMBERS.get(raw, 0))
    years = number * _UNIT_YEARS.get(unit, 0)
    if years <= 0 or years > 50:
        return None
    return round(years, 2)


def account_days_old(user_created_at) -> int:
    """How old a user's account is, in days (used for fraud scoring)."""
    if not user_created_at:
        return 365
    try:
        return max(0, (datetime.utcnow() - user_created_at).days)
    except Exception:
        return 365


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------

def encode_image_file_to_base64(file_path: str) -> str:
    """
    Reads a photo from disk and returns it as base64 for the API.
    Big photos are shrunk to MAX_IMAGE_SIDE px (JPEG) first: the AI
    reads a 1280px photo just as well, and it keeps the request small,
    fast and cheap. If shrinking fails the original bytes are sent.
    """
    with open(file_path, 'rb') as f:
        raw = f.read()
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw))
        img.load()
        if max(img.size) > MAX_IMAGE_SIDE or img.format not in ('JPEG', 'PNG'):
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            out = io.BytesIO()
            img.convert('RGB').save(out, format='JPEG', quality=85)
            raw = out.getvalue()
    except Exception as e:
        logger.warning(f"Valuator: could not shrink {file_path} ({e}); sending original")
    return base64.b64encode(raw).decode('utf-8')


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

class ValuatorClient:
    """Small wrapper around the valuator's HTTP API. Never raises."""

    def __init__(self, base_url=None, api_key=None, timeout=None):
        self._base_url = base_url
        self._api_key = api_key
        self._timeout = timeout

    @property
    def base_url(self):
        return (self._base_url or _base_url()).rstrip('/')

    @property
    def timeout(self):
        return self._timeout or _timeout()

    def _headers(self):
        key = self._api_key if self._api_key is not None else _api_key()
        return {'Authorization': f'Bearer {key}'} if key else {}

    def _call(self, method: str, path: str, payload=None, timeout=None) -> dict:
        if not self.base_url:
            return {'success': False, 'error': 'Valuator is not configured (VALUATOR_API_URL is empty)'}
        url = f"{self.base_url}{path}"
        try:
            response = requests.request(
                method, url, json=payload, headers=self._headers(),
                timeout=timeout or self.timeout,
            )
            try:
                data = response.json()
            except ValueError:
                data = {}
            if not isinstance(data, dict):
                data = {}

            if response.status_code == 401:
                logger.error("Valuator rejected our API key (401) — VALUATOR_API_KEY differs "
                             "between Barterex and the valuator")
                return {'success': False, 'error': 'Valuator rejected the API key', 'status_code': 401}
            if response.status_code >= 400:
                message = data.get('error') or f'HTTP {response.status_code}'
                logger.warning(f"Valuator error on {path}: {message}")
                return {'success': False, 'error': message, 'status_code': response.status_code}
            return data or {'success': False, 'error': 'Empty response from valuator'}

        except requests.exceptions.Timeout:
            logger.warning(f"Valuator timed out on {path} after {timeout or self.timeout}s")
            return {'success': False, 'error': 'Valuator timed out'}
        except requests.exceptions.ConnectionError:
            logger.warning(f"Valuator unreachable on {path} at {self.base_url}")
            return {'success': False, 'error': 'Valuator unreachable'}
        except Exception as e:  # never let this escape
            logger.error(f"Valuator call to {path} failed: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def health_check(self) -> dict:
        result = self._call('GET', '/health', timeout=5)
        return result if result.get('status') else {'status': 'unreachable', **result}

    def is_available(self) -> bool:
        return self.health_check().get('status') not in (None, 'error', 'unreachable')

    def valuate(self, title, description='', condition='good', sale_type='second_hand',
                age_years=None, submitted_price=0, image_count=0, images=None,
                account_days=365, category=None, country='NG') -> dict:
        """POST /api/valuate. age_years=None means "don't know" (NOT zero)."""
        payload = {
            'title': title,
            'description': description or '',
            'condition': condition,
            'sale_type': sale_type,
            'submitted_price': submitted_price or 0,
            'image_count': image_count,
            'images': images or [],
            'account_days_old': account_days,
            'country': country,
        }
        if age_years is not None:
            payload['age_years'] = age_years
        if category:
            payload['category'] = category
        return self._call('POST', '/api/valuate', payload)

    def verify(self, valuation_id, status, verifier_id, verified_value=None,
               verified_condition=None, notes=None) -> dict:
        """POST /api/verify — tells the valuator what really happened."""
        payload = {
            'valuation_id': valuation_id,
            'status': status,
            'verifier_id': verifier_id,
        }
        if verified_value is not None:
            payload['verified_value'] = verified_value
        if verified_condition:
            payload['verified_condition'] = verified_condition
        if notes:
            payload['verifier_notes'] = notes
        return self._call('POST', '/api/verify', payload, timeout=30)


client = ValuatorClient()


def valuate_item(**kwargs) -> dict:
    return client.valuate(**kwargs)


def is_valuator_available() -> bool:
    return client.is_available()


# ---------------------------------------------------------------------------
# Turning the valuator's answer into Item columns
# ---------------------------------------------------------------------------

_CREDIT_STATUS_TO_VERIFICATION = {
    'APPROVED': 'ai_approved',
    'PENDING_REVIEW': 'flagged_for_review',
    'REJECTED': 'ai_rejected',
}


def _confidence_label(score) -> str:
    score = score or 0
    if score >= 85:
        return 'high'
    if score >= 70:
        return 'medium'
    if score >= 55:
        return 'low'
    return 'very_low'


def extract_item_ai_fields(api_response: dict) -> dict:
    """Flattens a /api/valuate answer into the Item's ai_* columns."""
    if not api_response or not api_response.get('success'):
        error = (api_response or {}).get('error') or 'unknown error'
        return {
            'ai_estimated_value': None,
            'ai_confidence': None,
            'ai_market_listings': None,
            'ai_value_range_low': None,
            'ai_value_range_high': None,
            'ai_risk_score': None,
            'ai_risk_level': None,
            'ai_risk_flags': None,
            'ai_sources_used': None,
            'valuator_valuation_id': None,
            'verification_status': 'valuation_unavailable',
            'verification_notes': str(error)[:1000],
        }

    credits = api_response.get('credits') or {}
    risk = api_response.get('risk_assessment') or {}
    value_range = api_response.get('value_range') or {}
    database = api_response.get('database') or {}

    notes = []
    if credits.get('reason'):
        notes.append(str(credits['reason']))
    if risk.get('flags'):
        notes.append('Flags: ' + ', '.join(str(f) for f in risk['flags']))

    return {
        'ai_estimated_value': api_response.get('fair_value'),
        'ai_confidence': _confidence_label(api_response.get('confidence_score')),
        'ai_market_listings': api_response.get('total_comparables'),
        'ai_value_range_low': value_range.get('min'),
        'ai_value_range_high': value_range.get('max'),
        'ai_risk_score': risk.get('score'),
        'ai_risk_level': risk.get('level'),
        'ai_risk_flags': json.dumps(risk.get('flags') or []),
        'ai_sources_used': json.dumps(api_response.get('sources_used') or []),
        'valuator_valuation_id': database.get('valuation_id') if database.get('saved') else None,
        'verification_status': _CREDIT_STATUS_TO_VERIFICATION.get(
            credits.get('status'), 'flagged_for_review'),
        'verification_notes': ' | '.join(notes)[:1000] if notes else None,
    }


# ---------------------------------------------------------------------------
# Background jobs (so uploads and approvals never wait on the valuator)
# ---------------------------------------------------------------------------

try:
    _max_parallel = max(1, int(os.getenv('VALUATOR_MAX_PARALLEL', '2')))
except ValueError:
    _max_parallel = 2

# A small fixed pool: a burst of uploads queues up instead of launching
# dozens of 40-second valuations (each one opens a browser on the valuator).
_executor = ThreadPoolExecutor(max_workers=_max_parallel, thread_name_prefix='valuator')


def build_valuation_job(item, user, upload_root: str) -> dict:
    """
    Collects everything the background job needs as plain values (the job
    runs on another thread and must not touch this request's DB objects).
    """
    images = sorted(getattr(item, 'images', []) or [], key=lambda i: (i.order_index or 0))
    image_paths = [os.path.join(upload_root, i.image_url) for i in images if i.image_url]

    description = (item.description or '').strip()
    usage = (getattr(item, 'usage_duration', None) or '').strip()
    if usage:
        description = f"{description}\nUsed for: {usage}".strip()

    return {
        'item_id': item.id,
        'title': item.name,
        'description': description,
        'condition': map_condition_to_valuator(item.condition),
        'sale_type': 'new' if (item.condition or '').strip().lower() == 'brand new' else 'second_hand',
        'age_years': parse_usage_duration(usage),
        'category': map_category_to_valuator(item.category),
        'image_paths': image_paths,
        'account_days': account_days_old(getattr(user, 'created_at', None)),
    }


def _run_valuation_job(job: dict):
    from app import app, db          # imported here to avoid a circular import
    from models import Item

    started = time.time()
    try:
        images = []
        for path in job['image_paths'][:MAX_IMAGES_SENT]:
            try:
                images.append(encode_image_file_to_base64(path))
            except Exception as e:
                logger.warning(f"Valuator: skipped unreadable photo {path}: {e}")

        response = client.valuate(
            title=job['title'],
            description=job['description'],
            condition=job['condition'],
            sale_type=job['sale_type'],
            age_years=job['age_years'],
            image_count=len(job['image_paths']),
            images=images,
            account_days=job['account_days'],
            category=job['category'],
        )
        fields = extract_item_ai_fields(response)

        with app.app_context():
            item = db.session.get(Item, job['item_id'])
            if item is None:
                logger.info(f"Valuator: item {job['item_id']} no longer exists; dropping result")
                return
            for name, value in fields.items():
                setattr(item, name, value)
            item.ai_valuated_at = datetime.utcnow()
            db.session.commit()

        if response.get('success'):
            logger.info(f"AI valuation done - item {job['item_id']}: fair value "
                        f"{response.get('fair_value')} in {time.time() - started:.0f}s")
        else:
            logger.warning(f"AI valuation unavailable for item {job['item_id']}: "
                           f"{response.get('error')}")
    except Exception as e:
        logger.error(f"AI valuation job failed for item {job['item_id']}: {e}", exc_info=True)
        try:
            with app.app_context():
                db.session.rollback()
        except Exception:
            pass


def start_ai_valuation(item, user, upload_root: str) -> bool:
    """
    Queues the AI valuation of a just-saved item. Call it AFTER the item
    has been committed. Returns True if queued; never raises.
    """
    if not is_enabled():
        return False
    try:
        job = build_valuation_job(item, user, upload_root)
        _executor.submit(_run_valuation_job, job)
        return True
    except Exception as e:
        logger.error(f"Could not queue AI valuation for item {getattr(item, 'id', '?')}: {e}",
                     exc_info=True)
        return False


def _run_verification_job(item_id: int, outcome: str, verifier_id: str, delay: float):
    from app import app, db
    from models import Item

    time.sleep(delay)   # let the approve/reject request finish committing
    try:
        with app.app_context():
            item = db.session.get(Item, item_id)
            if item is None or not item.valuator_valuation_id:
                logger.info(f"Valuator verify skipped for item {item_id}: no AI valuation on record")
                return

            # Only report what really happened in Barterex's database.
            if outcome == 'passed' and item.status != 'approved':
                return
            if outcome == 'failed' and item.status != 'rejected':
                return

            result = client.verify(
                valuation_id=item.valuator_valuation_id,
                status=outcome,
                verifier_id=verifier_id,
                verified_value=item.value if outcome == 'passed' else None,
                verified_condition=map_condition_to_valuator(item.condition),
                notes=(item.rejection_reason if outcome == 'failed' else None),
            )
            if result.get('success'):
                logger.info(f"Valuator verify recorded - item {item_id}, outcome {outcome}")
            else:
                logger.warning(f"Valuator verify failed for item {item_id}: {result.get('error')}")
    except Exception as e:
        logger.error(f"Valuator verify job failed for item {item_id}: {e}", exc_info=True)


def report_verification(item_id: int, outcome: str, admin_id) -> bool:
    """
    Tells the valuator an admin approved ('passed') or rejected ('failed')
    an item. Runs in the background; never raises, never blocks approval.
    """
    if not is_enabled():
        return False
    try:
        verifier_id = f"admin-{admin_id}" if admin_id else "admin"
        _executor.submit(_run_verification_job, item_id, outcome, verifier_id, 2.0)
        return True
    except Exception as e:
        logger.error(f"Could not queue valuator verify for item {item_id}: {e}", exc_info=True)
        return False
