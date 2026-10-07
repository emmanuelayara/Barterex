"""
Publishes an approved "Activate for Trade" verification video to the official
Barterex YouTube channel.

Settings (.env):
    YOUTUBE_CLIENT_ID       OAuth client ID (Google Cloud Console -> Credentials)
    YOUTUBE_CLIENT_SECRET   OAuth client secret
    YOUTUBE_REFRESH_TOKEN   One-time-generated refresh token for the channel's
                             Google account - see get_youtube_refresh_token.py
    YOUTUBE_ENABLED         Set to false to switch publishing off (default true)

Unset/incomplete credentials simply mean is_configured() is False - nothing
here raises, so an admin approving a video before this is set up gets a clear
"not configured" error instead of a crash, and can retry once .env is filled in.
"""
import logging
import os

try:
    from logger_config import setup_logger
    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    logger = logging.getLogger(__name__)

YOUTUBE_UPLOAD_SCOPE = 'https://www.googleapis.com/auth/youtube.upload'
TOKEN_URI = 'https://oauth2.googleapis.com/token'


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


def _build_client():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds_info = _creds()
    credentials = Credentials(
        token=None,
        refresh_token=creds_info['refresh_token'],
        token_uri=TOKEN_URI,
        client_id=creds_info['client_id'],
        client_secret=creds_info['client_secret'],
        scopes=[YOUTUBE_UPLOAD_SCOPE],
    )
    return build('youtube', 'v3', credentials=credentials, cache_discovery=False)


def upload_video(video_bytes: bytes, title: str, description: str = '',
                  privacy_status: str = 'unlisted') -> dict:
    """
    Uploads a video to the official channel. Returns:
        {'success': True, 'video_id': ..., 'url': 'https://youtu.be/...'}
        {'success': False, 'error': '...'}
    Never raises.
    """
    if not is_configured():
        return {'success': False, 'error': 'YouTube publishing is not configured yet.'}

    try:
        import io
        from googleapiclient.http import MediaIoBaseUpload

        youtube = _build_client()
        media = MediaIoBaseUpload(io.BytesIO(video_bytes), mimetype='video/*', resumable=True)
        request = youtube.videos().insert(
            part='snippet,status',
            body={
                'snippet': {
                    'title': title[:100],
                    'description': description[:5000],
                },
                'status': {'privacyStatus': privacy_status},
            },
            media_body=media,
        )
        response = None
        while response is None:
            status, response = request.next_chunk()
        video_id = response.get('id')
        if not video_id:
            return {'success': False, 'error': 'YouTube did not return a video id.'}
        return {'success': True, 'video_id': video_id, 'url': f'https://youtu.be/{video_id}'}
    except Exception as e:
        logger.error(f"YouTube upload failed: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}
