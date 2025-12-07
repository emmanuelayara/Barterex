"""
File Upload Validation Utilities
Provides comprehensive file upload validation with magic byte verification,
size limits, and image validation to prevent malware uploads.
"""

import io
import os
from PIL import Image
from werkzeug.utils import secure_filename
from exceptions import FileUploadError
from logger_config import setup_logger

logger = setup_logger(__name__)

# Magic bytes for different file types (file signatures)
MAGIC_BYTES = {
    b'\xFF\xD8\xFF': 'jpg',      # JPG
    b'\x89PNG\r\n\x1a\n': 'png', # PNG
    b'GIF87a': 'gif',             # GIF 87a
    b'GIF89a': 'gif',             # GIF 89a
}


def get_file_type_from_magic_bytes(file_data):
    """
    Detect file type by magic bytes (file signature) using PIL.
    This is the actual file type, not just the extension.
    
    Args:
        file_data: Binary file data
        
    Returns:
        str: Detected file type ('JPEG', 'PNG', 'GIF', etc.) or None
    """
    try:
        # Use PIL to detect image format from bytes
        img = Image.open(io.BytesIO(file_data))
        format_name = img.format
        if format_name:
            return format_name.lower()
    except Exception:
        pass
    
    # Fallback to magic bytes detection
    for magic, file_type in MAGIC_BYTES.items():
        if file_data.startswith(magic):
            return file_type
    
    return None


def validate_file_size(file_size, max_size=10*1024*1024):
    """
    Validate file size before processing.
    
    Args:
        file_size: Size of file in bytes
        max_size: Maximum allowed size (default: 10MB)
        
    Returns:
        tuple: (is_valid: bool, message: str)
    """
    if file_size is None:
        return False, "Unable to determine file size"
    
    if file_size == 0:
        return False, "File is empty"
    
    if file_size > max_size:
        size_mb = file_size / (1024 * 1024)
        max_mb = max_size / (1024 * 1024)
        return False, f"File too large: {size_mb:.1f}MB > {max_mb:.1f}MB"
    
    return True, "Size valid"


def validate_file_extension(filename, allowed_extensions={'png', 'jpg', 'jpeg', 'gif'}):
    """
    Validate file extension.
    
    Args:
        filename: Original filename
        allowed_extensions: Set of allowed extensions
        
    Returns:
        tuple: (is_valid: bool, message: str)
    """
    if not filename or '.' not in filename:
        return False, "Filename has no extension"
    
    ext = filename.rsplit('.', 1)[1].lower()
    
    if ext not in allowed_extensions:
        return False, f"Extension not allowed: .{ext}. Allowed: {', '.join(allowed_extensions)}"
    
    return True, "Extension valid"


def validate_image_integrity(file_data):
    """
    Validate that file is a real, valid image (not corrupted or fake).
    Uses PIL to verify the image can be opened and is not malformed.
    
    Args:
        file_data: Binary file data
        
    Returns:
        tuple: (is_valid: bool, message: str)
    """
    try:
        # Open image from binary data
        img = Image.open(io.BytesIO(file_data))
        
        # Verify it's a valid image
        img.verify()
        
        logger.debug(f"Image validation passed - Type: {img.format}, Size: {img.size}")
        return True, "Image valid"
        
    except Exception as e:
        return False, f"Invalid image file: {str(e)}"


def validate_upload(file_obj, max_size=10*1024*1024, allowed_extensions={'png', 'jpg', 'jpeg', 'gif'}):
    """
    Comprehensive file upload validation with multiple security checks.
    
    Security Layers:
    1. File size check (prevents disk exhaustion attacks)
    2. File extension validation (prevents obvious mislabeled files)
    3. Magic bytes validation (detects actual file type, not just extension)
    4. Image integrity check (ensures it's a real, valid image)
    5. secure_filename (strips dangerous path characters)
    
    Args:
        file_obj: FileStorage object from Flask request.files
        max_size: Maximum file size in bytes (default: 10MB)
        allowed_extensions: Set of allowed file extensions
        
    Returns:
        tuple: (is_valid: bool, message: str, detected_type: str or None)
        
    Raises:
        FileUploadError: If validation fails
    """
    
    # Validation step 1: Check extension first (quick validation)
    ext_valid, ext_msg = validate_file_extension(file_obj.filename, allowed_extensions)
    if not ext_valid:
        logger.warning(f"File upload rejected - Invalid extension: {file_obj.filename}")
        raise FileUploadError(ext_msg)
    
    # Validation step 2: Check file size BEFORE reading entire file into memory
    if file_obj.content_length:
        size_valid, size_msg = validate_file_size(file_obj.content_length, max_size)
        if not size_valid:
            logger.warning(f"File upload rejected - {size_msg}")
            raise FileUploadError(size_msg)
    
    # Read file data once into memory
    file_data = file_obj.read()
    file_obj.seek(0)  # Reset file pointer for actual save operation
    
    # Validation step 3: Check for empty file after reading
    if len(file_data) == 0:
        logger.warning("File upload rejected - Empty file")
        raise FileUploadError("File is empty")
    
    # Validation step 4: Enforce max size after reading (defense in depth)
    if len(file_data) > max_size:
        size_mb = len(file_data) / (1024 * 1024)
        max_mb = max_size / (1024 * 1024)
        msg = f"File too large: {size_mb:.1f}MB > {max_mb:.1f}MB"
        logger.warning(f"File upload rejected - {msg}")
        raise FileUploadError(msg)
    
    # Validation step 5: Check magic bytes (actual file type)
    detected_type = get_file_type_from_magic_bytes(file_data)
    
    if detected_type is None:
        logger.warning(f"File upload rejected - Unknown file type for: {file_obj.filename}")
        raise FileUploadError("Unable to determine file type. File may be corrupted or not an image.")
    
    if detected_type not in allowed_extensions:
        logger.warning(f"File upload rejected - Invalid magic bytes. Detected: {detected_type}, Expected: {allowed_extensions}")
        raise FileUploadError(f"File type mismatch. Detected {detected_type}, expected image format.")
    
    # Validation step 6: Verify it's a valid, uncorrupted image
    img_valid, img_msg = validate_image_integrity(file_data)
    if not img_valid:
        logger.warning(f"File upload rejected - Image integrity failed: {img_msg}")
        raise FileUploadError(img_msg)
    
    logger.info(f"File upload validation passed - File: {file_obj.filename}, Type: {detected_type}, Size: {len(file_data)} bytes")
    return True, "All validations passed", detected_type


def generate_safe_filename(file_obj, user_id, item_id=None, index=None):
    """
    Generate a safe, unique filename for storage.
    
    Format: {user_id}_{timestamp}_{original_filename}
    Or:     {item_id}_{index}_{timestamp}_{original_filename}
    
    Args:
        file_obj: FileStorage object
        user_id: User's ID
        item_id: Item ID (optional)
        index: Index for multiple files (optional)
        
    Returns:
        str: Safe, unique filename
    """
    import time
    
    original_name = secure_filename(file_obj.filename)
    timestamp = int(time.time())
    
    if item_id is not None and index is not None:
        return f"{item_id}_{index}_{timestamp}_{original_name}"
    else:
        return f"{user_id}_{timestamp}_{original_name}"
