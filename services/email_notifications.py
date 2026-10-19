"""
Shared in-app notification + email helpers.

Emails are rendered when queued but only sent once the surrounding database
transaction commits (and are dropped on rollback), so users are never emailed
about something that did not actually happen. Always queue before the commit
that persists the change.
"""
from contextlib import ExitStack

from flask import current_app, has_request_context, render_template, url_for
from sqlalchemy import event
from sqlalchemy.orm import Session

from app import db
from logger_config import setup_logger

logger = setup_logger(__name__)

PENDING_EMAILS_KEY = 'pending_emails'
NOTIFICATION_MESSAGE_LIMIT = 255


def _truncate(message, limit=NOTIFICATION_MESSAGE_LIMIT):
    message = message or ''
    return message if len(message) <= limit else message[:limit - 1].rstrip() + '…'


def queue_email(
    recipient,
    subject,
    heading,
    message,
    username=None,
    details=None,
    cta_endpoint=None,
    cta_label=None,
    **cta_values,
):
    """Render a branded email now and send it after the current transaction commits."""
    if not recipient:
        return
    session_info = db.session.info
    with ExitStack() as stack:
        if not has_request_context():
            # Context processors need a request; use an isolated app context so the
            # caller's cached login state in `g` is left untouched.
            stack.enter_context(current_app.app_context())
            stack.enter_context(current_app.test_request_context())
        cta_url = url_for(cta_endpoint, _external=True, **cta_values) if cta_endpoint else None
        html_body = render_template(
            'emails/notification.html',
            heading=heading,
            message=message,
            username=username,
            details=details,
            cta_url=cta_url,
            cta_label=cta_label,
        )
    session_info.setdefault(PENDING_EMAILS_KEY, []).append((subject, [recipient], html_body))


def notify_user(
    user,
    message,
    subject=None,
    heading=None,
    details=None,
    email=True,
    cta_endpoint='user.notifications',
    cta_label='View Notifications',
    notification_type='system',
    category='status_update',
    **cta_values,
):
    """Add an in-app notification for `user` (a User or user id) and email them the same news."""
    from models import Notification, User

    if user is None:
        return None
    if not isinstance(user, User):
        user = db.session.get(User, user)
        if user is None:
            return None
    notification = Notification(
        user_id=user.id,
        message=_truncate(message),
        notification_type=notification_type,
        category=category,
    )
    db.session.add(notification)
    if email and user.email:
        try:
            queue_email(
                user.email,
                subject or heading or 'Update from Barter Express',
                heading or subject or 'Update from Barter Express',
                message,
                username=user.username,
                details=details,
                cta_endpoint=cta_endpoint,
                cta_label=cta_label,
                **cta_values,
            )
            notification.is_email_sent = True
        except Exception as e:
            logger.error(f"Could not queue notification email for user {user.id}: {e}", exc_info=True)
    return notification


def notify_admins(
    permission,
    subject,
    message,
    heading=None,
    cta_endpoint='admin.admin_dashboard',
    cta_label='Open Admin Dashboard',
    **cta_values,
):
    """Email every active admin who holds `permission` about new work waiting for them."""
    from models import Admin

    admins = Admin.query.filter(Admin.is_active.is_(True), Admin.deleted_at.is_(None)).all()
    for admin in admins:
        if not admin.email or not admin.has_permission(permission):
            continue
        try:
            queue_email(
                admin.email,
                subject,
                heading or subject,
                message,
                username=admin.username,
                cta_endpoint=cta_endpoint,
                cta_label=cta_label,
                **cta_values,
            )
        except Exception as e:
            logger.error(f"Could not queue admin alert for admin {admin.id}: {e}", exc_info=True)


@event.listens_for(Session, 'after_commit')
def _send_queued_emails(session):
    emails = session.info.pop(PENDING_EMAILS_KEY, None)
    if not emails:
        return
    from routes.auth import send_email_async

    for subject, recipients, html_body in emails:
        try:
            send_email_async(subject=subject, recipients=recipients, html_body=html_body)
        except Exception as e:
            logger.error(f"Failed to send queued email to {recipients}: {e}", exc_info=True)


@event.listens_for(Session, 'after_rollback')
def _drop_queued_emails(session):
    session.info.pop(PENDING_EMAILS_KEY, None)
