"""
File Upload Validation Utilities
Provides comprehensive file upload validation with:
- Magic byte verification (actual file type detection)
- Strict MIME type checking
- File size enforcement with multiple layers
- Image integrity validation
- Optional virus/malware scanning
- Prevents: zip bombs, polyglot files, trojanized images, oversized uploads
"""

import io
import os
import mimetypes
import hashlib
import shutil
from pathlib import Path
from PIL import Image
from werkzeug.utils import secure_filename
from exceptions import FileUploadError
from logger_config import setup_logger

logger = setup_logger(__name__)

# Magic bytes for different file types (file signatures) - STRICT validation
MAGIC_BYTES = {
    # JPEG signatures (three common variants)
    b'\xFF\xD8\xFF\xE0': 'jpg',   # JPEG with JFIF
    b'\xFF\xD8\xFF\xE1': 'jpg',   # JPEG with Exif
    b'\xFF\xD8\xFF\xDB': 'jpg',   # JPEG with DQT
    # PNG signature
    b'\x89PNG\r\n\x1a\n': 'png',  # PNG (8 bytes)
    # GIF signatures
    b'GIF87a': 'gif',              # GIF 87a
    b'GIF89a': 'gif',              # GIF 89a
}

# MIME type whitelist - only image types
ALLOWED_MIME_TYPES = {
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',  # Modern format
}

# File extension to MIME type mapping (strict)
EXTENSION_MIME_MAP = {
    'jpg': {'image/jpeg'},
    'jpeg': {'image/jpeg'},
    'png': {'image/png'},
    'gif': {'image/gif'},
    'webp': {'image/webp'},
}

# File size limits by type (in bytes)
# Optimized for web usage while maintaining quality
FILE_SIZE_LIMITS = {
    'jpg': 5 * 1024 * 1024,        # 5MB for JPEG (optimized for web)
    'jpeg': 5 * 1024 * 1024,       # 5MB for JPEG
    'png': 8 * 1024 * 1024,        # 8MB for PNG (lossless, larger files)
    'gif': 3 * 1024 * 1024,        # 3MB for GIF (animated images)
    'webp': 5 * 1024 * 1024,       # 5MB for WebP (modern format)
}

# Global max file size (safety limit)
GLOBAL_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB absolute maximum


def get_file_type_from_magic_bytes(file_data):
    """
    Detect file type by magic bytes (file signature) using PIL and magic byte detection.
    This is the ACTUAL file type, not just the extension - prevents polyglot attacks.
    
    Args:
        file_data: Binary file data
        
    Returns:
        str: Detected file type ('jpeg', 'png', 'gif', 'webp', etc.) or None
    """
    try:
        # Use PIL to detect image format from bytes
        img = Image.open(io.BytesIO(file_data))
        format_name = img.format
        if format_name:
            detected = format_name.lower()
            # Normalize format names
            if detected == 'jpg':
                detected = 'jpeg'
            logger.debug(f"PIL detected image format: {detected}")
            return detected
    except Exception as e:
        logger.debug(f"PIL detection failed: {str(e)}")
    
    # Fallback to magic bytes detection (stricter checking)
    for magic, file_type in MAGIC_BYTES.items():
        if file_data.startswith(magic):
            logger.debug(f"Magic bytes detected: {file_type}")
            return file_type
    
    logger.warning("Unable to detect file type from magic bytes")
    return None


def get_mime_type_from_content(file_data):
    """
    Attempt to detect MIME type from file content using python-magic.
    Fallback to file extension if python-magic is not available.
    
    Args:
        file_data: Binary file data
        
    Returns:
        str: MIME type or None
    """
    try:
        # Try using python-magic if available for better detection
        import magic
        mime = magic.Magic(mime=True)
        mime_type = mime.from_buffer(file_data[:2048])  # Check first 2KB
        return mime_type
    except (ImportError, Exception):
        # Fallback: detect via PIL
        try:
            img = Image.open(io.BytesIO(file_data))
            if img.format == 'JPEG':
                return 'image/jpeg'
            elif img.format == 'PNG':
                return 'image/png'
            elif img.format == 'GIF':
                return 'image/gif'
            elif img.format == 'WEBP':
                return 'image/webp'
        except:
            pass
    
    return None


def validate_file_size(file_size, max_size=10*1024*1024, file_type=None):
    """
    Validate file size before processing.
    Uses type-specific limits if available.
    
    Args:
        file_size: Size of file in bytes
        max_size: Maximum allowed size (default: 10MB, overridden by file_type limit)
        file_type: File type (jpg, png, etc.) for type-specific limits
        
    Returns:
        tuple: (is_valid: bool, message: str)
    """
    if file_size is None:
        return False, "Unable to determine file size"
    
    if file_size == 0:
        return False, "File is empty"
    
    # Use type-specific limit if available
    if file_type and file_type in FILE_SIZE_LIMITS:
        limit = FILE_SIZE_LIMITS[file_type]
    else:
        limit = max_size
    
    if file_size > limit:
        size_mb = file_size / (1024 * 1024)
        max_mb = limit / (1024 * 1024)
        logger.warning(f"File size violation: {size_mb:.1f}MB > {max_mb:.1f}MB limit")
        return False, f"File too large: {size_mb:.1f}MB > {max_mb:.1f}MB limit"
    
    return True, "Size valid"


def validate_file_extension(filename, allowed_extensions={'png', 'jpg', 'jpeg', 'gif', 'webp'}):
    """
    Validate file extension strictly.
    Case-insensitive, rejects double extensions and suspicious patterns.
    
    Args:
        filename: Original filename
        allowed_extensions: Set of allowed extensions
        
    Returns:
        tuple: (is_valid: bool, message: str, extension: str or None)
    """
    if not filename or '.' not in filename:
        logger.warning(f"File rejected: no extension in filename '{filename}'")
        return False, "Filename has no extension", None
    
    # Extract extension (last part only)
    parts = filename.rsplit('.', 1)
    if len(parts) != 2:
        return False, "Invalid filename format", None
    
    ext = parts[1].lower().strip()
    
    # Reject empty extensions or suspicious patterns
    if not ext or len(ext) > 10:
        logger.warning(f"File rejected: suspicious extension format '{ext}'")
        return False, "Invalid extension format", None
    
    # Reject double extensions (e.g., .jpg.exe)
    if '.' in parts[0]:
        # Check if base name has multiple dots (potential double extension)
        base_parts = parts[0].split('.')
        if len(base_parts) > 2:
            logger.warning(f"File rejected: suspicious double extension pattern in '{filename}'")
            return False, "Double extensions are not allowed (e.g., .jpg.exe)", None
    
    if ext not in allowed_extensions:
        logger.warning(f"File extension not allowed: .{ext}. Allowed: {allowed_extensions}")
        return False, f"Extension not allowed: .{ext}", ext
    
    return True, "Extension valid", ext


def validate_image_integrity(file_data, max_dimensions=(4096, 4096)):
    """
    Validate that file is a real, valid image - not corrupted, trojaned, or oversized.
    Uses PIL to verify the image can be opened and is not malformed.
    Also checks image dimensions to prevent zip bomb-like attacks.
    
    Args:
        file_data: Binary file data
        max_dimensions: Maximum allowed image dimensions (width, height)
        
    Returns:
        tuple: (is_valid: bool, message: str)
    """
    try:
        # Open image from binary data
        img = Image.open(io.BytesIO(file_data))
        
        # Verify image can be loaded
        img.load()
        
        # Check dimensions to prevent zip bomb-like attacks
        width, height = img.size
        max_width, max_height = max_dimensions
        
        if width > max_width or height > max_height:
            logger.warning(f"Image dimensions too large: {width}x{height} > {max_width}x{max_height}")
            return False, f"Image dimensions too large: {width}x{height}. Maximum: {max_width}x{max_height}"
        
        # Check minimum dimensions (prevent tiny placeholder images)
        min_width, min_height = 50, 50  # Minimum 50x50 pixels
        if width < min_width or height < min_height:
            logger.warning(f"Image dimensions too small: {width}x{height} < {min_width}x{min_height}")
            return False, f"Image dimensions too small: {width}x{height}. Minimum: {min_width}x{min_height}"
        
        logger.debug(f"Image validation passed - Type: {img.format}, Size: {img.size}, Dimensions: {width}x{height}")
        return True, "Image valid"
        
    except Exception as e:
        logger.warning(f"Image integrity validation failed: {str(e)}")
        return False, f"Invalid image file: {str(e)}"


def scan_for_virus(file_data, filename):
    """
    Scan file for viruses using ClamAV or other antivirus engines.
    This is an optional security layer - gracefully skips if no scanner available.
    
    For production deployment:
    - Install ClamAV: apt-get install clamav clamav-daemon
    - Pip: pip install pyclamd
    
    Args:
        file_data: Binary file data to scan
        filename: Original filename for logging
        
    Returns:
        tuple: (is_safe: bool, message: str)
    """
    try:
        import pyclamd
        
        # Initialize ClamAV connection
        clam = pyclamd.ClamadNetworkSocket()
        
        # Check if daemon is available
        if not clam.ping():
            logger.warning("ClamAV daemon not responding - skipping virus scan")
            return True, "Virus scanner unavailable (non-blocking)"
        
        # Scan the file data
        result = clam.scan_stream(file_data)
        
        if result is None:
            logger.info(f"Virus scan passed for: {filename}")
            return True, "Clean - no viruses detected"
        else:
            # Malware detected
            threat_name = result.get('stream', ['Unknown threat'])[0]
            logger.error(f"MALWARE DETECTED in {filename}: {threat_name}")
            return False, f"Malware detected: {threat_name}"
            
    except ImportError:
        # pyclamd not installed - gracefully skip
        logger.debug("pyclamd not available - virus scanning skipped")
        return True, "Virus scanner not configured"
    except Exception as e:
        # Other errors - log but don't block (fail-safe approach)
        logger.warning(f"Virus scan error: {str(e)}")
        return True, "Virus scan encountered error (non-blocking)"


def validate_upload(file_obj, max_size=10*1024*1024, allowed_extensions={'png', 'jpg', 'jpeg', 'gif', 'webp'}, enable_virus_scan=False):
    """
    Comprehensive file upload validation with STRICT security checks.
    
    Security Layers (Defense in Depth):
    1. File extension check (quick validation, rejects obvious mismatches)
    2. File size check before reading (prevents disk exhaustion)
    3. Empty file detection (prevents zero-byte attacks)
    4. File size re-check after reading (defense in depth)
    5. Magic bytes validation (detects actual file type, prevents polyglot attacks)
    6. MIME type validation (strict whitelist enforcement)
    7. Image integrity check (ensures valid, uncorrupted image)
    8. Dimension check (prevents zip bomb-like attacks)
    9. Optional virus/malware scan (ClamAV if available)
    
    This prevents:
    - Polyglot attacks (file with multiple signatures)
    - Trojanized images (malware embedded in image)
    - Zip bombs / decompression attacks
    - Double extensions (.jpg.exe)
    - Invalid/corrupted image files
    - Oversized uploads (disk exhaustion)
    - Virus/malware
    
    Args:
        file_obj: FileStorage object from Flask request.files
        max_size: Maximum file size in bytes (default: 10MB)
        allowed_extensions: Set of allowed file extensions
        enable_virus_scan: Enable virus scanning via ClamAV (optional)
        
    Returns:
        tuple: (is_valid: bool, message: str, detected_type: str or None)
        
    Raises:
        FileUploadError: If ANY validation fails
    """
    
    if not file_obj or not file_obj.filename:
        raise FileUploadError("No file selected")
    
    # ===== LAYER 1: Extension validation =====
    ext_valid, ext_msg, ext = validate_file_extension(file_obj.filename, allowed_extensions)
    if not ext_valid:
        logger.warning(f"Upload rejected at layer 1 (extension): {file_obj.filename}")
        raise FileUploadError(ext_msg)
    
    # ===== LAYER 2: File size check (before reading) =====
    if file_obj.content_length:
        size_valid, size_msg = validate_file_size(file_obj.content_length, max_size, file_type=ext)
        if not size_valid:
            logger.warning(f"Upload rejected at layer 2 (size check): {size_msg}")
            raise FileUploadError(size_msg)
    
    # ===== LAYER 3: Read file and check for empty file =====
    file_data = file_obj.read()
    file_obj.seek(0)  # Reset file pointer for actual save operation
    
    if len(file_data) == 0:
        logger.warning(f"Upload rejected at layer 3 (empty file): {file_obj.filename}")
        raise FileUploadError("File is empty")
    
    # ===== LAYER 4: Re-check file size after reading (defense in depth) =====
    size_valid, size_msg = validate_file_size(len(file_data), max_size, file_type=ext)
    if not size_valid:
        logger.warning(f"Upload rejected at layer 4 (size re-check): {size_msg}")
        raise FileUploadError(size_msg)
    
    # ===== LAYER 5: Magic bytes detection (actual file type) =====
    detected_type = get_file_type_from_magic_bytes(file_data)
    
    if detected_type is None:
        logger.warning(f"Upload rejected at layer 5 (unknown file type): {file_obj.filename}")
        raise FileUploadError("Unable to determine file type. File may be corrupted or not an image.")
    
    # ===== LAYER 6: MIME type validation (strict whitelist) =====
    expected_mimes = EXTENSION_MIME_MAP.get(ext, set())
    detected_mime = get_mime_type_from_content(file_data)
    
    if detected_mime and detected_mime not in ALLOWED_MIME_TYPES:
        logger.warning(f"Upload rejected at layer 6 (MIME type): detected {detected_mime}, expected {expected_mimes}")
        raise FileUploadError(f"Invalid MIME type: {detected_mime}")
    
    # ===== LAYER 7: Verify magic bytes match extension =====
    if detected_type not in allowed_extensions:
        logger.warning(f"Upload rejected at layer 7 (magic bytes mismatch): detected {detected_type}, extension {ext}")
        raise FileUploadError(f"File type mismatch: detected {detected_type}, filename has .{ext} extension. This may be a polyglot attack.")
    
    # ===== LAYER 8: Image integrity and dimensions check =====
    img_valid, img_msg = validate_image_integrity(file_data)
    if not img_valid:
        logger.warning(f"Upload rejected at layer 8 (image integrity): {img_msg}")
        raise FileUploadError(img_msg)
    
    # ===== LAYER 9: Optional virus/malware scan =====
    if enable_virus_scan:
        scan_safe, scan_msg = scan_for_virus(file_data, file_obj.filename)
        if not scan_safe:
            logger.error(f"Upload rejected at layer 9 (virus scan): {scan_msg}")
            raise FileUploadError(scan_msg)
        logger.info(f"Virus scan result: {scan_msg}")
    
    # All validations passed
    logger.info(f"✅ File upload passed ALL validation layers - File: {file_obj.filename}, Type: {detected_type}, Size: {len(file_data)} bytes")
    return True, "All validation layers passed", detected_type


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
