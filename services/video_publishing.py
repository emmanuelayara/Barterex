"""Database-backed video jobs with fenced leases and durable resumable uploads."""
import hashlib
import uuid
from datetime import datetime, timedelta

from sqlalchemy import and_, or_

from app import db
from logger_config import setup_logger
from models import AuditLog, ItemVideo
from services import video_service, youtube_publisher
from services.email_notifications import notify_admins, notify_user
from services.item_activation_service import activate_item

logger = setup_logger(__name__)
LEASE_SECONDS = 300
MAX_FAILURES = 5
ACTIVE_STATUSES = ('queued', 'publishing', 'retry_wait')


class LeaseLost(Exception):
    pass


def _audit(video, action, description, admin_id=None):
    db.session.add(AuditLog(
        admin_id=admin_id if admin_id is not None else video.reviewed_by_admin_id, action_type=action,
        target_type='item', target_id=video.item_id,
        target_name=video.item.name, description=description,
    ))


def video_reference(video):
    return f'Barter Express verification: item {video.item_id}, submission {video.id}.'


def queue_video(video, admin_id):
    """Called under a row lock; the route owns the commit."""
    if video.status != 'pending':
        raise ValueError('This video has already been reviewed.')
    video.item.activation_credit_amount()
    if video.item.status != 'pending_activation' or video.item.provisional_credit_granted_at is not None:
        raise ValueError('This item is not eligible for activation.')
    video.status = 'queued'
    video.publish_phase = 'queued'
    video.reviewed_by_admin_id = admin_id
    video.reviewed_at = datetime.utcnow()
    video.publish_next_attempt_at = datetime.utcnow()
    _audit(video, 'queue_activation_video', 'Video approved for durable unlisted YouTube publishing.')


def retry_video(video, admin_id):
    """Retry saved work, never discard its resumable session or known video ID."""
    if video.status != 'publish_failed':
        raise ValueError('Only failed publishing jobs can be retried.')
    video.status = 'queued'
    video.publish_attempts = 0
    video.publish_error = None
    video.publish_next_attempt_at = datetime.utcnow()
    _audit(video, 'retry_activation_video', 'Publishing retry queued with its saved upload state.', admin_id)


def _claim():
    now = datetime.utcnow()
    lease_free = or_(ItemVideo.publish_lease_until.is_(None), ItemVideo.publish_lease_until < now)
    publishing_due = and_(
        ItemVideo.status.in_(ACTIVE_STATUSES),
        or_(ItemVideo.publish_next_attempt_at.is_(None), ItemVideo.publish_next_attempt_at <= now),
    )
    cleanup_due = and_(
        ItemVideo.status.in_(('approved', 'rejected')),
        ItemVideo.temp_video_url.isnot(None),
        or_(ItemVideo.cleanup_next_attempt_at.is_(None), ItemVideo.cleanup_next_attempt_at <= now),
    )
    # Compare-and-swap also works on SQLite, where SELECT FOR UPDATE is ignored.
    ids = db.session.query(ItemVideo.id).filter(
        lease_free, or_(publishing_due, cleanup_due),
    ).order_by(ItemVideo.submitted_at).limit(20).all()
    for (video_id,) in ids:
        token = uuid.uuid4().hex
        count = ItemVideo.query.filter(
            ItemVideo.id == video_id, lease_free, or_(publishing_due, cleanup_due),
        ).update({
            ItemVideo.publish_lease_token: token,
            ItemVideo.publish_lease_until: now + timedelta(seconds=LEASE_SECONDS),
        }, synchronize_session=False)
        db.session.commit()
        if count:
            return video_id, token
    db.session.rollback()
    return None


def _owned(video_id, token):
    video = ItemVideo.query.filter_by(id=video_id).with_for_update().populate_existing().first()
    if (video is None or video.publish_lease_token != token
            or video.publish_lease_until is None or video.publish_lease_until < datetime.utcnow()):
        db.session.rollback()
        raise LeaseLost('Publishing job lease expired or was claimed by another worker.')
    return video


def _save(video_id, token, **values):
    video = _owned(video_id, token)
    for key, value in values.items():
        setattr(video, key, value)
    video.publish_lease_until = datetime.utcnow() + timedelta(seconds=LEASE_SECONDS)
    db.session.commit()


def _release(video, **values):
    for key, value in values.items():
        setattr(video, key, value)
    video.publish_lease_token = None
    video.publish_lease_until = None


def _is_oauth_rejection(error):
    from google.auth.exceptions import RefreshError
    return isinstance(error, RefreshError) and 'invalid_grant' in str(error)


def _failure(video_id, token, error):
    db.session.rollback()
    video = _owned(video_id, token)
    video.publish_attempts += 1
    permanent = isinstance(error, youtube_publisher.PublishingError) and error.permanent
    failed = permanent or video.publish_attempts >= MAX_FAILURES
    # Exception strings from HTTP libraries can contain signed session URLs.
    if isinstance(error, youtube_publisher.PublishingError):
        message = str(error)
    elif _is_oauth_rejection(error):
        message = (
            'YouTube authorization was rejected (refresh token expired or revoked). '
            'Run get_youtube_refresh_token.py, update YOUTUBE_REFRESH_TOKEN and restart '
            'the worker. The saved upload state has been retained for retry.'
        )
    else:
        message = (
            f'{type(error).__name__} during {video.publish_phase or "publishing"}. '
            'The saved upload state has been retained for retry.'
        )
    logger.error('Video job %s: %s', video_id, message)
    _release(
        video, status='publish_failed' if failed else 'retry_wait',
        publish_error=message,
        publish_next_attempt_at=None if failed else datetime.utcnow() + timedelta(
            seconds=min(3600, 60 * 2 ** (video.publish_attempts - 1)),
        ),
    )
    if failed:
        notify_admins(
            'items.video_review', 'Video publishing needs attention',
            f"Publishing for '{video.item.name}' failed: {message}",
            cta_endpoint='admin.video_review_queue', cta_label='Review Publishing',
        )
        notify_user(
            video.uploaded_by_id,
            f"The video for '{video.item.name}' passed review, but publishing is delayed. "
            'Our team has been notified; you do not need to upload it again.',
            subject='Your item video is awaiting publishing recovery',
            cta_endpoint='user.my_valuations', cta_label='My Valuations',
        )
    db.session.commit()


def _cleanup(video_id, token):
    video = _owned(video_id, token)
    object_name = video.temp_video_url
    db.session.commit()
    success = video_service.delete_object(object_name)
    video = _owned(video_id, token)
    if success:
        _release(video, temp_video_url=None, temp_copy_deleted_at=datetime.utcnow(),
                 cleanup_error=None, cleanup_next_attempt_at=None)
        logger.info('Temporary video copy deleted for publishing job %s.', video_id)
    else:
        video.cleanup_attempts += 1
        _release(
            video, cleanup_error='Temporary cloud copy could not be deleted; cleanup will retry.',
            cleanup_next_attempt_at=datetime.utcnow() + timedelta(
                seconds=min(21600, 60 * 2 ** min(video.cleanup_attempts, 10)),
            ),
        )
        logger.warning('Temporary video cleanup failed for job %s (attempt %s)', video_id, video.cleanup_attempts)
    db.session.commit()


def _publish(video_id, token):
    video = _owned(video_id, token)
    video.status = 'publishing'
    if video.publish_started_at is None:
        video.publish_started_at = datetime.utcnow()
    video.item.activation_credit_amount()
    if video.item.status != 'pending_activation' or video.item.provisional_credit_granted_at is not None:
        raise youtube_publisher.PublishingError('The item is no longer eligible for activation.', permanent=True)
    db.session.commit()

    if not video.youtube_video_id:
        _save(video_id, token, publish_phase='uploading')
        video_bytes = video_service.download_bytes(video.temp_video_url)
        if not video_bytes:
            raise youtube_publisher.PublishingError('Could not read the temporary cloud video.')
        digest = hashlib.sha256(video_bytes).hexdigest()
        video = _owned(video_id, token)
        if video.upload_source_sha256 and video.upload_source_sha256 != digest:
            raise youtube_publisher.PublishingError('The source video changed after publishing began.', permanent=True)
        session_uri = video.upload_session_uri
        title = video.item.name
        description = video_reference(video) + '\n\n' + (video.item.description or '')
        _save(video_id, token, upload_source_sha256=digest)
        youtube_publisher.upload_video(
            video_bytes, title, description, session_uri=session_uri,
            on_session=lambda uri: _save(video_id, token, upload_session_uri=uri),
            on_progress=lambda percent: _save(video_id, token, publish_progress=percent),
            on_result=lambda youtube_id: _save(
                video_id, token, youtube_video_id=youtube_id,
                youtube_url=f'https://youtu.be/{youtube_id}', publish_progress=100,
                publish_phase='processing',
            ),
        )
    video = _owned(video_id, token)
    youtube_id = video.youtube_video_id
    db.session.commit()
    ready = youtube_publisher.get_video_status(youtube_id, expected_reference=video_reference(video))
    video = _owned(video_id, token)
    if not ready:
        if datetime.utcnow() - video.publish_started_at > timedelta(hours=24):
            raise youtube_publisher.PublishingError('YouTube processing has not finished after 24 hours.', permanent=True)
        _release(video, status='retry_wait', publish_phase='processing', publish_error=None,
                 publish_next_attempt_at=datetime.utcnow() + timedelta(seconds=30))
        db.session.commit()
        return

    # Activation, credits, final status, audit and notifications commit together.
    # The published ID was already committed; rollback here never uploads again.
    video.publish_phase = 'activation'
    amount = activate_item(video.item_id, video.youtube_url)
    _release(video, status='approved', publish_phase='complete',
             publish_error=None, publish_next_attempt_at=None)
    _audit(video, 'approve_activation_video', f'Unlisted video published: {video.youtube_url}')
    notify_user(
        video.item.user_id,
        f"'{video.item.name}' is now live. {amount:,} provisional BXC was added to your account. "
        f'Watch the item video: {video.youtube_url}',
        subject=f"'{video.item.name}' is now live on the marketplace",
        cta_endpoint='user.user_items', cta_label='View My Items', notification_type='listing',
    )
    db.session.commit()
    # Deletion is a separate durable cleanup job, eligible only AFTER this commit.
    logger.info('Video job %s activated its item with unlisted video %s.', video_id, youtube_id)


def run_next_job():
    claim = _claim()
    if claim is None:
        return False
    video_id, token = claim
    cleanup = False
    try:
        video = _owned(video_id, token)
        cleanup = video.status in ('approved', 'rejected')
        db.session.commit()
        if cleanup:
            _cleanup(video_id, token)
        else:
            _publish(video_id, token)
    except LeaseLost:
        db.session.rollback()
        logger.warning('Stopped video job %s after losing its lease.', video_id)
    except Exception as error:
        db.session.rollback()
        try:
            if cleanup:
                # Leave cleanup eligible for lease recovery; never re-publish.
                logger.exception('Video cleanup job %s failed.', video_id)
            else:
                _failure(video_id, token, error)
        except LeaseLost:
            logger.warning('Cannot record failure for video %s: lease was replaced.', video_id)
    finally:
        db.session.remove()
    return True
