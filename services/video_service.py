"""
Temporary video storage for the "Activate for Trade" verification video.

Seller records/selects a video in the browser -> this module mints a short-lived
SIGNED URL so the browser can PUT the file straight into Google Cloud Storage
(the Barterex VPS never receives the video bytes). After an admin approves it
(see routes/admin.py video_review), services/youtube_publisher.py fetches the
object from GCS, publishes it to YouTube, and delete_object() removes the
temp copy.

Settings (.env):
    GCS_BUCKET_NAME             Bucket to hold temp videos (unset = feature OFF)
    GOOGLE_APPLICATION_CREDENTIALS   Path to a service account JSON key, OR unset
                                     if using `gcloud auth application-default login`
                                     (standard Google Cloud env var)
    GCS_SERVICE_ACCOUNT_EMAIL   Set this to impersonate the bucket's service account
                                 (via IAM) instead of a key file - needed when your
                                 org blocks service-account key creation. Requires the
                                 logged-in ADC user to have "Service Account Token
                                 Creator" on that service account.
    GCS_SIGNED_URL_MINUTES      How long upload/preview links stay valid. Default 20.

Nothing here can crash the app if GCS isn't configured yet: every public
function checks is_configured() first and returns a clear error otherwise.
"""
import logging
import os
import uuid

try:
    from logger_config import setup_logger
    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    logger = logging.getLogger(__name__)

ALLOWED_VIDEO_TYPES = {
    'video/mp4': 'mp4',
    'video/quicktime': 'mov',
    'video/webm': 'webm',
    'video/x-m4v': 'm4v',
}
MAX_VIDEO_SIZE_BYTES = 200 * 1024 * 1024  # 200MB


def _bucket_name():
    return (os.getenv('GCS_BUCKET_NAME') or '').strip()


def _service_account_email():
    return (os.getenv('GCS_SERVICE_ACCOUNT_EMAIL') or '').strip()


def _signed_url_minutes():
    try:
        return max(5, int(os.getenv('GCS_SIGNED_URL_MINUTES', '20')))
    except ValueError:
        return 20


def is_configured() -> bool:
    """On only when a bucket is set and the google-cloud-storage client library is installed."""
    if not _bucket_name():
        return False
    try:
        import google.cloud.storage  # noqa: F401
    except ImportError:
        logger.warning("google-cloud-storage is not installed; video uploads are disabled")
        return False
    return True


def _client():
    from google.cloud import storage

    # When service-account KEY FILES are blocked (e.g. by an org policy), set
    # GOOGLE_APPLICATION_CREDENTIALS to your own `gcloud auth application-default
    # login` user credentials and GCS_SERVICE_ACCOUNT_EMAIL to the bucket's
    # service account - this impersonates that service account (via the IAM
    # Credentials API) for every call, including signed URLs, with no key file.
    sa_email = _service_account_email()
    if sa_email:
        import google.auth
        from google.auth import impersonated_credentials

        # An empty GOOGLE_APPLICATION_CREDENTIALS in .env still counts as "set" to
        # google-auth, which skips its normal ADC file discovery - drop it so the
        # gcloud `auth application-default login` credentials are found instead.
        if not os.getenv('GOOGLE_APPLICATION_CREDENTIALS', '').strip():
            os.environ.pop('GOOGLE_APPLICATION_CREDENTIALS', None)

        source_credentials, _ = google.auth.default()
        target_credentials = impersonated_credentials.Credentials(
            source_credentials=source_credentials,
            target_principal=sa_email,
            target_scopes=['https://www.googleapis.com/auth/cloud-platform'],
            lifetime=3600,
        )
        return storage.Client(credentials=target_credentials)

    return storage.Client()


def build_object_name(item_id: int, content_type: str) -> str:
    ext = ALLOWED_VIDEO_TYPES.get(content_type, 'mp4')
    return f"item-videos/{item_id}/{uuid.uuid4().hex}.{ext}"


def generate_upload_url(object_name: str, content_type: str) -> dict:
    """A signed PUT URL the browser can upload the video to directly."""
    if not is_configured():
        return {'success': False, 'error': 'Video storage is not configured yet.'}
    try:
        from datetime import timedelta
        bucket = _client().bucket(_bucket_name())
        blob = bucket.blob(object_name)
        url = blob.generate_signed_url(
            version='v4',
            expiration=timedelta(minutes=_signed_url_minutes()),
            method='PUT',
            content_type=content_type,
        )
        return {'success': True, 'upload_url': url, 'object_name': object_name}
    except Exception as e:
        logger.error(f"Could not create GCS upload URL: {e}", exc_info=True)
        return {'success': False, 'error': 'Could not prepare the upload. Please try again.'}


def generate_read_url(object_name: str) -> str:
    """A short-lived signed URL an admin can view/stream the pending video from."""
    if not object_name or not is_configured():
        return ''
    try:
        from datetime import timedelta
        bucket = _client().bucket(_bucket_name())
        blob = bucket.blob(object_name)
        return blob.generate_signed_url(
            version='v4', expiration=timedelta(minutes=_signed_url_minutes()), method='GET',
        )
    except Exception as e:
        logger.error(f"Could not create GCS read URL for {object_name}: {e}", exc_info=True)
        return ''


def download_bytes(object_name: str):
    """Pulls the temp video into memory so it can be pushed to YouTube. None on failure."""
    if not object_name or not is_configured():
        return None
    try:
        bucket = _client().bucket(_bucket_name())
        blob = bucket.blob(object_name)
        return blob.download_as_bytes()
    except Exception as e:
        logger.error(f"Could not download GCS object {object_name}: {e}", exc_info=True)
        return None


def delete_object(object_name: str) -> bool:
    """Removes the temp copy once it's safely published (or no longer needed). Never raises."""
    if not object_name or not is_configured():
        return False
    try:
        bucket = _client().bucket(_bucket_name())
        bucket.blob(object_name).delete()
        return True
    except Exception as e:
        logger.warning(f"Could not delete GCS object {object_name}: {e}")
        return False
