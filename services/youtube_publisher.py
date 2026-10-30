"""
Publishes an approved "Activate for Trade" verification video to the official
Barterex YouTube channel.

Settings (.env):
    YOUTUBE_CLIENT_ID       OAuth client ID (Google Cloud Console -> Credentials)
    YOUTUBE_CLIENT_SECRET   OAuth client secret
    YOUTUBE_REFRESH_TOKEN   One-time-generated refresh token for the channel's
                             Google account - see get_youtube_refresh_token.py
    YOUTUBE_ENABLED         Set to false to switch publishing off (default true)

The worker persists resumable sessions before uploading bytes. API errors raise
PublishingError so the durable queue can retry safely or stop for reconciliation.
The OAuth token must grant upload AND read-only access for processing checks.
"""
import logging
import os
import re
from urllib.parse import urlparse

try:
    from logger_config import setup_logger
    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    logger = logging.getLogger(__name__)

YOUTUBE_UPLOAD_SCOPE = 'https://www.googleapis.com/auth/youtube.upload'
YOUTUBE_READ_SCOPE = 'https://www.googleapis.com/auth/youtube.readonly'
TOKEN_URI = 'https://oauth2.googleapis.com/token'
UPLOAD_ENDPOINT = 'https://www.googleapis.com/upload/youtube/v3/videos'
CHUNK_SIZE = 8 * 1024 * 1024


class PublishingError(Exception):
    def __init__(self, message, permanent=False):
        super().__init__(message)
        self.permanent = permanent


def _creds():
    return {
        'client_id': (os.getenv('YOUTUBE_CLIENT_ID') or '').strip(),
        'client_secret': (os.getenv('YOUTUBE_CLIENT_SECRET') or '').strip(),
        'refresh_token': (os.getenv('YOUTUBE_REFRESH_TOKEN') or '').strip(),
    }


def is_enabled() -> bool:
    if os.getenv('YOUTUBE_ENABLED', 'true').strip().lower() in ('0', 'false', 'no', 'off'):
        return False
    return all(_creds().values())


def is_configured() -> bool:
    """On only when credentials are set AND the Google API client libraries are installed."""
    if not is_enabled():
        return False
    try:
        import googleapiclient.discovery  # noqa: F401
        import google.oauth2.credentials  # noqa: F401
    except ImportError:
        logger.warning("google-api-python-client is not installed; YouTube publishing is disabled")
        return False
    return True


def _credentials():
    from google.oauth2.credentials import Credentials

    creds_info = _creds()
    return Credentials(
        token=None,
        refresh_token=creds_info['refresh_token'],
        token_uri=TOKEN_URI,
        client_id=creds_info['client_id'],
        client_secret=creds_info['client_secret'],
        scopes=[YOUTUBE_UPLOAD_SCOPE, YOUTUBE_READ_SCOPE],
    )


def _authorized_session():
    from google.auth.transport.requests import AuthorizedSession
    if not is_configured():
        raise PublishingError('YouTube publishing is not configured.')
    return AuthorizedSession(_credentials())


def _check_response(response, allowed):
    if response.status_code in allowed:
        return
    # Do not include response URLs/bodies: resumable URLs contain bearer capabilities.
    raise PublishingError(
        f'YouTube API returned HTTP {response.status_code}. Check API access, quota and OAuth authorization.',
        permanent=response.status_code == 400,
    )


def _validate_session_uri(uri):
    parsed = urlparse(uri)
    if parsed.scheme != 'https' or parsed.hostname not in ('www.googleapis.com', 'youtube.googleapis.com'):
        raise PublishingError('YouTube returned an invalid resumable upload location.', permanent=True)


def _authorized_channel_ids(client):
    response = client.get(
        'https://www.googleapis.com/youtube/v3/channels',
        params={'part': 'id', 'mine': 'true'}, timeout=60,
    )
    _check_response(response, (200,))
    channel_ids = {channel['id'] for channel in response.json().get('items', [])}
    if not channel_ids:
        raise PublishingError(
            'The authorized Google account has no accessible YouTube channel. '
            'Run get_youtube_refresh_token.py and select the official Barter Express '
            'YouTube channel (including its Brand Account, if applicable), update '
            'YOUTUBE_REFRESH_TOKEN, restart the worker and retry this job.',
            permanent=True,
        )
    expected = (os.getenv('YOUTUBE_CHANNEL_ID') or '').strip()
    if expected and expected not in channel_ids:
        raise PublishingError(
            'The authorized YouTube channel does not match YOUTUBE_CHANNEL_ID. '
            'Reauthorize the official channel, update YOUTUBE_REFRESH_TOKEN, '
            'restart the worker and retry this job.',
            permanent=True,
        )
    return channel_ids


def upload_video(video_bytes, title, description='', *, session_uri=None,
                 on_session, on_progress, on_result):
    """Persist the session BEFORE sending bytes; always probe it on resume.

    A missing/expired session is never replaced automatically: a lost final
    acknowledgement could mean a video already exists on the channel.
    """
    total = len(video_bytes)
    with _authorized_session() as client:
        if not session_uri:
            _authorized_channel_ids(client)
            response = client.post(
                UPLOAD_ENDPOINT,
                params={'uploadType': 'resumable', 'part': 'snippet,status'},
                headers={'X-Upload-Content-Length': str(total), 'X-Upload-Content-Type': 'video/*'},
                json={
                    'snippet': {
                        'title': title.replace('<', '').replace('>', '').strip()[:100] or 'Barter Express item video',
                        'description': description.replace('<', '').replace('>', '')[:5000],
                    },
                    'status': {'privacyStatus': 'unlisted'},
                },
                timeout=60,
            )
            _check_response(response, (200, 201))
            session_uri = response.headers.get('Location')
            if not session_uri:
                raise PublishingError('YouTube did not return an upload session.')
            _validate_session_uri(session_uri)
            on_session(session_uri)

        _validate_session_uri(session_uri)
        response = client.put(
            session_uri,
            headers={'Content-Length': '0', 'Content-Range': f'bytes */{total}'},
            data=b'', timeout=60,
        )
        previous_offset = None
        while True:
            if response.status_code in (404, 410):
                raise PublishingError(
                    'The saved upload session is unavailable. Check the official channel for this video '
                    'and link its video ID below. Do not upload it again without reconciliation.',
                    permanent=True,
                )
            _check_response(response, (200, 201, 308))
            if response.status_code in (200, 201):
                video_id = response.json().get('id')
                if not video_id or not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
                    raise PublishingError('YouTube returned an invalid video ID.', permanent=True)
                on_result(video_id)
                return video_id
            acknowledged = response.headers.get('Range')
            if acknowledged:
                match = re.fullmatch(r'bytes=0-(\d+)', acknowledged)
                if not match:
                    raise PublishingError('YouTube returned an invalid upload offset.', permanent=True)
                offset = int(match.group(1)) + 1
            else:
                offset = 0
            if previous_offset is not None and offset <= previous_offset:
                raise PublishingError('YouTube upload made no progress. Retry the saved session.')
            if offset >= total:
                raise PublishingError('YouTube has not acknowledged upload completion. Retry the saved session.')
            previous_offset = offset
            on_progress(int(offset * 100 / total))
            end = min(offset + CHUNK_SIZE, total)
            response = client.put(
                session_uri, data=video_bytes[offset:end],
                headers={
                    'Content-Type': 'video/*',
                    'Content-Length': str(end - offset),
                    'Content-Range': f'bytes {offset}-{end - 1}/{total}',
                }, timeout=60,
            )


def get_video_status(video_id, expected_reference=None):
    """Verify channel ownership, unlisted visibility and playback processing."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
        raise PublishingError('Enter the 11-character YouTube video ID.', permanent=True)
    with _authorized_session() as client:
        channel_ids = _authorized_channel_ids(client)
        response = client.get(
            'https://www.googleapis.com/youtube/v3/videos',
            params={'part': 'snippet,status,processingDetails', 'id': video_id}, timeout=60,
        )
        _check_response(response, (200,))
        items = response.json().get('items', [])
        if not items:
            raise PublishingError('The video was not found on the authorized channel.', permanent=True)
        video = items[0]
        channel_id = video.get('snippet', {}).get('channelId')
        expected = (os.getenv('YOUTUBE_CHANNEL_ID') or '').strip()
        if channel_id not in channel_ids or (expected and expected != channel_id):
            raise PublishingError('The video does not belong to the configured official channel.', permanent=True)
        if expected_reference and not video.get('snippet', {}).get('description', '').startswith(expected_reference):
            raise PublishingError('This video does not match the item submission reference.', permanent=True)
        status = video.get('status', {})
        if status.get('privacyStatus') != 'unlisted':
            raise PublishingError('The YouTube video must be unlisted before activation.', permanent=True)
        processing = video.get('processingDetails', {}).get('processingStatus')
        if processing in ('failed', 'terminated') or status.get('uploadStatus') in ('failed', 'rejected', 'deleted'):
            raise PublishingError('YouTube processing failed or the video was rejected/deleted.', permanent=True)
        return processing == 'succeeded' or status.get('uploadStatus') == 'processed'
