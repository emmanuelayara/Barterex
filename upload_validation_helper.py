"""
Upload Validation Helper - User-friendly validation for item uploads

Provides clear, natural language error messages for all common upload issues:
- Image size problems
- Description length issues
- Item name issues
- Category/condition validation
"""

from logger_config import setup_logger

logger = setup_logger(__name__)


class UploadValidationError(Exception):
    """Custom exception for upload validation with user-friendly messages"""
    def __init__(self, field, message, suggestion=None):
        self.field = field
        self.message = message
        self.suggestion = suggestion
        super().__init__(message)
    
    def get_user_message(self):
        """Get the full user-facing error message with suggestion"""
        msg = f"{self.message}"
        if self.suggestion:
            msg += f" {self.suggestion}"
        return msg


def validate_item_name(name):
    """
    Validate item name field.
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    if not name or not name.strip():
        return False, "Please enter an item name."
    
    name = name.strip()
    
    if len(name) < 3:
        return False, f"Item name is too short ({len(name)} characters). Please use at least 3 characters to describe your item clearly."
    
    if len(name) > 100:
        return False, f"Item name is too long ({len(name)} characters). Please keep it under 100 characters."
    
    # Check for suspicious patterns
    if name.count('  ') > 0:  # Multiple spaces
        return False, "Item name contains too many spaces. Please clean it up and try again."
    
    return True, None


def validate_item_description(description):
    """
    Validate item description field.
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    if not description or not description.strip():
        return False, "Please provide a description for your item."
    
    description = description.strip()
    
    if len(description) < 20:
        return False, (
            f"Description is too short ({len(description)} characters). "
            f"Please provide at least 20 characters describing the item, condition, and any important details."
        )
    
    if len(description) > 2000:
        return False, (
            f"Description is too long ({len(description)} characters). "
            f"Please keep it under 2000 characters."
        )
    
    # Check for suspicious patterns
    if description.count('\n') > 20:  # Too many line breaks
        return False, "Description contains too many line breaks. Please format it more cleanly."
    
    return True, None


def validate_image_count(image_count):
    """
    Validate number of images uploaded.
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    if image_count == 0:
        return False, (
            "Please upload at least one image. "
            "High-quality images help buyers understand your item better."
        )
    
    if image_count > 6:
        return False, (
            f"You've uploaded {image_count} images, but the maximum is 6 images per item. "
            f"Please remove {image_count - 6} image(s) and try again."
        )
    
    return True, None


def validate_image_size(file_size_bytes, filename, max_size_mb=10):
    """
    Validate individual image file size.
    
    Args:
        file_size_bytes: Size of file in bytes
        filename: Name of the file
        max_size_mb: Maximum allowed size in MB
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    max_size_bytes = max_size_mb * 1024 * 1024
    
    if file_size_bytes == 0:
        return False, f"'{filename}' appears to be empty. Please select a valid image file."
    
    if file_size_bytes > max_size_bytes:
        size_mb = file_size_bytes / (1024 * 1024)
        return False, (
            f"'{filename}' is too large ({size_mb:.1f} MB). "
            f"Maximum allowed image size is {max_size_mb} MB. "
            f"Try compressing the image using an online tool or your device's built-in compression."
        )
    
    return True, None


def validate_image_dimensions(width, height, filename, min_width=400, min_height=300):
    """
    Validate image dimensions.
    
    Args:
        width: Image width in pixels
        height: Image height in pixels
        filename: Name of the file
        min_width: Minimum width required
        min_height: Minimum height required
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    if width is None or height is None:
        return False, f"'{filename}' has invalid dimensions. Please use a valid image file."
    
    if width < min_width or height < min_height:
        return False, (
            f"'{filename}' is too small ({width}x{height} pixels). "
            f"Please use images that are at least {min_width}x{min_height} pixels. "
            f"Higher resolution images help buyers see details better."
        )
    
    # Check for unusually extreme aspect ratios
    aspect_ratio = width / height if height > 0 else 0
    if aspect_ratio > 5 or aspect_ratio < 0.2:
        return False, (
            f"'{filename}' has an unusual shape (aspect ratio: {aspect_ratio:.1f}:1). "
            f"Please use photos that are closer to normal proportions (landscape or portrait)."
        )
    
    return True, None


def validate_image_type(filename, allowed_extensions={'jpg', 'jpeg', 'png', 'gif', 'webp'}):
    """
    Validate image file type/extension.
    
    Args:
        filename: Name of the file
        allowed_extensions: Set of allowed file extensions
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    if '.' not in filename:
        return False, f"'{filename}' has no file extension. Please use a valid image file (.jpg, .png, etc)."
    
    ext = filename.rsplit('.', 1)[1].lower()
    
    if ext not in allowed_extensions:
        ext_list = ', '.join(sorted(allowed_extensions)).upper()
        return False, (
            f"'{filename}' has an unsupported format (.{ext}). "
            f"Please use one of these formats: {ext_list}"
        )
    
    return True, None


def validate_condition(condition):
    """
    Validate item condition.
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    valid_conditions = ['Brand New', 'Fairly Used']
    
    if not condition:
        return False, "Please select the condition of your item (Brand New or Fairly Used)."
    
    if condition not in valid_conditions:
        return False, f"'{condition}' is not a valid condition. Please select either 'Brand New' or 'Fairly Used'."
    
    return True, None


def validate_category(category):
    """
    Validate item category.
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    valid_categories = [
        "Electronics", "Fashion / Clothing", "Footwear",
        "Home & Kitchen", "Beauty & Personal Care",
        "Sports & Outdoors", "Groceries", "Furniture",
        "Toys & Games", "Books & Stationery",
        "Health & Wellness", "Automotive", "Phones & Gadgets"
    ]
    
    if not category:
        return False, "Please select a category for your item to help buyers find it easily."
    
    if category not in valid_categories:
        return False, f"'{category}' is not a valid category. Please select from the available options."
    
    return True, None


def validate_upload_request(form_data, images_from_request):
    """
    Comprehensive validation of the entire upload request.
    
    Args:
        form_data: Dictionary with form fields (name, description, condition, category)
        images_from_request: List of file objects from request.files
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None, field: str or None)
    """
    # Validate item name
    is_valid, error = validate_item_name(form_data.get('name', ''))
    if not is_valid:
        return False, error, 'name'
    
    # Validate description
    is_valid, error = validate_item_description(form_data.get('description', ''))
    if not is_valid:
        return False, error, 'description'
    
    # Validate condition
    is_valid, error = validate_condition(form_data.get('condition', ''))
    if not is_valid:
        return False, error, 'condition'
    
    # Validate category
    is_valid, error = validate_category(form_data.get('category', ''))
    if not is_valid:
        return False, error, 'category'
    
    # Validate image count
    image_count = len([f for f in images_from_request if f and f.filename])
    is_valid, error = validate_image_count(image_count)
    if not is_valid:
        return False, error, 'images'
    
    return True, None, None


def get_user_friendly_error_message(error_obj, field=None):
    """
    Convert technical error objects into user-friendly messages.
    
    Args:
        error_obj: Exception or error object
        field: Field name where error occurred (optional)
    
    Returns:
        str: User-friendly error message
    """
    error_str = str(error_obj)
    
    # Map technical error patterns to user-friendly messages
    error_mappings = {
        'No file selected': 'Please select at least one image to upload.',
        'File is empty': 'The image file you uploaded is empty. Please select a valid image file.',
        'unknown file type': 'The image file could not be read. Please try a different image.',
        'corrupted': 'The image file appears to be corrupted. Please try a different image.',
        'polyglot attack': 'The file appears to have a mismatched format. Please use a genuine image file.',
        'MIME type': 'The file format is not supported. Please use JPG, PNG, GIF, or WEBP images.',
        'file size': 'The image is too large. Please use an image smaller than 10MB.',
        'content_length': 'The image is too large. Please use an image smaller than 10MB.',
        'magic bytes': 'The file format does not match the filename. Please ensure you\'re uploading real image files.',
        'dimension': 'The image is too small. Please use images at least 400x300 pixels.',
        'Invalid file type': 'Only image files are allowed. Please use JPG, PNG, GIF, or WEBP format.',
    }
    
    # Find matching error message
    for pattern, user_message in error_mappings.items():
        if pattern.lower() in error_str.lower():
            return user_message
    
    # If field is provided, provide context-specific message
    if field == 'images':
        return (
            "There was a problem with one of your images. "
            "Please ensure all images are valid JPG, PNG, GIF, or WEBP files smaller than 10MB."
        )
    elif field == 'description':
        return "There was a problem with your item description. Please check the length and content."
    elif field == 'name':
        return "There was a problem with your item name. Please check the spelling and length."
    
    # Default fallback
    return (
        "There was a problem uploading your item. "
        "Please check your inputs and try again. If the problem persists, contact support."
    )
