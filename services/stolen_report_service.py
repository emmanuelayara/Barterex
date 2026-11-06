"""Validate private evidence without writing it into public item storage."""
import io

from werkzeug.datastructures import FileStorage

from exceptions import FileUploadError
from file_upload_validator import validate_upload

MAX_EVIDENCE_IMAGES = 5
MAX_EVIDENCE_BYTES = 5 * 1024 * 1024
EVIDENCE_TYPES = {
    'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
    'png': 'image/png', 'webp': 'image/webp',
}


def read_evidence(files):
    files = [file for file in files if file.filename]
    if len(files) > MAX_EVIDENCE_IMAGES:
        raise FileUploadError('Attach no more than five evidence images.')
    attachments = []
    for file in files:
        data = file.stream.read(MAX_EVIDENCE_BYTES + 1)
        if len(data) > MAX_EVIDENCE_BYTES:
            raise FileUploadError('Each evidence image must be 5 MB or smaller.')
        bounded = FileStorage(stream=io.BytesIO(data), filename=file.filename)
        _, _, detected_type = validate_upload(
            bounded, max_size=MAX_EVIDENCE_BYTES, allowed_extensions=set(EVIDENCE_TYPES),
        )
        attachments.append((EVIDENCE_TYPES[detected_type], data))
    return attachments
