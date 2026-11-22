"""Public "check my item's value" flow for visitors without an account.

Nothing here lists an item or issues BXC. See services/guest_valuation_service.py.
"""
import mimetypes

from flask import (
    Blueprint, abort, flash, jsonify, redirect, render_template, request, send_file, url_for,
)
from flask_login import current_user, login_required

from app import limiter
from error_handlers import handle_api_errors, handle_errors
from exceptions import FileUploadError
from file_upload_validator import validate_upload
from forms import UploadItemForm
from logger_config import setup_logger
from services import guest_valuation_service as guests
from upload_validation_helper import (
    get_user_friendly_error_message, validate_image_count, validate_image_size, validate_image_type,
)
from valuator_client import is_enabled as valuator_enabled

logger = setup_logger(__name__)

guest_valuation_bp = Blueprint('guest_valuation', __name__, url_prefix='/value')

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}


def _rate_limit(limit):
    return limiter.limit(limit) if limiter is not None else (lambda view: view)


def opened_item_url(item):
    return url_for('user.my_valuations', _anchor=f'item-{item.id}')


def open_claimed_item_response(item):
    """Redirect that opens the just-attached valuation and retires the guest cookie."""
    flash('Your free estimate is saved to your account. It is private: nothing was listed '
          'and no BXC was added.', 'success')
    return guests.clear_guest_cookie(redirect(opened_item_url(item)))


@guest_valuation_bp.route('/start')
@handle_errors
def start():
    if current_user.is_authenticated:
        return redirect(url_for('items.upload_item'))
    record = guests.find_by_token(guests.current_token())
    if record is not None and record.status != 'failed':
        return redirect(url_for('guest_valuation.result'))
    form = UploadItemForm()
    requested = request.args.get('category')
    if requested in dict(form.category.choices):
        form.category.data = requested
    return render_template(
        'guest_value.html', form=form, valuator_ready=valuator_enabled(),
        previous_failed=record is not None,
    )


@guest_valuation_bp.route('/start', methods=['POST'])
@_rate_limit('20 per hour')   # flood protection only; the one-estimate rule is enforced by the guest token
@handle_api_errors
def submit():
    if current_user.is_authenticated:
        return jsonify({'success': False, 'error': 'Use the upload page while signed in.',
                        'redirect_url': url_for('items.upload_item')}), 409
    if not valuator_enabled():
        return jsonify({'success': False, 'error': 'AI valuation is not available right now. Please try again later.'}), 503

    existing = guests.find_by_token(guests.current_token())
    if existing is not None and existing.status != 'failed':
        return jsonify({'success': False, 'redirect_url': url_for('guest_valuation.result'),
                        'error': 'You have already used your free estimate. Create an account to value more items.'}), 409

    form = UploadItemForm()
    if not form.validate_on_submit():
        message = next((errors[0] for errors in form.errors.values() if errors), 'Please check your details and try again.')
        return jsonify({'success': False, 'error': message}), 400

    files = [f for f in request.files.getlist('images') if f and f.filename]
    if not files:
        return jsonify({'success': False, 'error': 'Please take at least 6 photos of your item.'}), 400
    ok, message = validate_image_count(len(files))
    if not ok:
        return jsonify({'success': False, 'error': message}), 400

    photos = []
    for file in files:
        ok, message = validate_image_type(file.filename, ALLOWED_EXTENSIONS)
        if ok:
            file.seek(0, 2)
            size = file.tell()
            file.seek(0)
            ok, message = validate_image_size(size, file.filename, max_size_mb=10)
        if not ok:
            return jsonify({'success': False, 'error': f'{file.filename}: {message}'}), 400
        try:
            validate_upload(file, max_size=10 * 1024 * 1024, allowed_extensions=ALLOWED_EXTENSIONS,
                            enable_virus_scan=False)
        except FileUploadError as error:
            return jsonify({'success': False,
                            'error': f'{file.filename}: {get_user_friendly_error_message(str(error), "images")}'}), 400
        file.seek(0)
        photos.append((file.filename, file.read()))

    if existing is not None:
        guests.discard(existing)   # an earlier attempt failed; let the visitor retry
    condition = form.condition.data
    record, token = guests.create_record({
        'name': form.name.data.strip(),
        'description': form.description.data.strip(),
        'condition': condition,
        'usage_duration': (form.usage_duration.data or '').strip() if condition == 'Fairly Used' else None,
        'category': form.category.data,
    }, photos)
    logger.info('Guest valuation %s started with %s photos', record.id, len(photos))
    response = jsonify({'success': True, 'redirect_url': url_for('guest_valuation.result')})
    return guests.set_guest_cookie(response, token)


def _own_record(include_claimed=False):
    return guests.find_by_token(guests.current_token(), include_claimed=include_claimed)


@guest_valuation_bp.route('/result')
@handle_errors
def result():
    record = _own_record(include_claimed=True)
    if record is None:
        flash('Your estimate has expired or was not found. Start a new one.', 'warning')
        return guests.clear_guest_cookie(redirect(url_for('guest_valuation.start')))
    if record.status == 'claimed':
        if current_user.is_authenticated and record.claimed_by_user_id == current_user.id and record.claimed_item_id:
            return guests.clear_guest_cookie(redirect(url_for('user.my_valuations', _anchor=f'item-{record.claimed_item_id}')))
        return guests.clear_guest_cookie(redirect(url_for('guest_valuation.start')))
    return render_template(
        'guest_value_result.html', record=record, result=guests.public_result(record),
        photo_count=len(record.image_file_list()),
    )


@guest_valuation_bp.route('/status')
def status():
    record = _own_record()
    if record is None:
        return jsonify({'status': 'missing'}), 404
    payload = {'status': record.status}
    if record.status == 'ready':
        payload['result'] = guests.public_result(record)
    elif record.status == 'failed':
        payload['error'] = record.error_message or guests.GENERIC_FAILURE
    return jsonify(payload)


@guest_valuation_bp.route('/photo/<int:index>')
def photo(index):
    record = _own_record()
    path = guests.photo_path(record, index) if record is not None else None
    if path is None:
        abort(404)
    response = send_file(path, mimetype=mimetypes.guess_type(path)[0] or 'application/octet-stream')
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@guest_valuation_bp.route('/claim', methods=['POST'])
@login_required
def claim():
    item = guests.claim_for_user(current_user, guests.current_token())
    if item is None:
        flash('We could not save that estimate to your account. It may have expired or already been saved.', 'warning')
        return guests.clear_guest_cookie(redirect(url_for('guest_valuation.start')))
    return open_claimed_item_response(item)
