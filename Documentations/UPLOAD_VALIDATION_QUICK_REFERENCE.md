# Upload Error Handling - Quick Reference

## How to Use the Validation Helper

### In Routes
```python
from upload_validation_helper import validate_image_type, validate_image_size

# Validate image type
is_valid, error_msg = validate_image_type(filename, allowed_extensions)
if not is_valid:
    flash(error_msg, 'danger')
    return redirect(...)

# Validate image size
is_valid, error_msg = validate_image_size(file_size_bytes, filename, max_size_mb=10)
if not is_valid:
    flash(error_msg, 'danger')
    return redirect(...)
```

### Validating Complete Upload
```python
from upload_validation_helper import validate_upload_request

form_data = {
    'name': request.form.get('name'),
    'description': request.form.get('description'),
    'condition': request.form.get('condition'),
    'category': request.form.get('category')
}
images = request.files.getlist('images')

is_valid, error_msg, field = validate_upload_request(form_data, images)
if not is_valid:
    flash(f"{field.upper()}: {error_msg}", 'danger')
```

### Converting Technical Errors to User Messages
```python
from upload_validation_helper import get_user_friendly_error_message

try:
    validate_upload(file)
except FileUploadError as e:
    user_message = get_user_friendly_error_message(str(e), field='images')
    flash(user_message, 'danger')
```

## Available Validators

### `validate_item_name(name)`
Checks: 3-100 characters, no suspicious patterns
Returns: (is_valid: bool, error_message: str or None)

### `validate_item_description(description)`
Checks: 20-2000 characters, reasonable line breaks
Returns: (is_valid: bool, error_message: str or None)

### `validate_image_count(image_count)`
Checks: 1-6 images
Returns: (is_valid: bool, error_message: str or None)

### `validate_image_type(filename, allowed_extensions)`
Checks: File extension against whitelist
Returns: (is_valid: bool, error_message: str or None)

### `validate_image_size(file_size_bytes, filename, max_size_mb)`
Checks: File size (0 to max_size_mb)
Returns: (is_valid: bool, error_message: str or None)

### `validate_image_dimensions(width, height, filename, min_width, min_height)`
Checks: Resolution >= min_width x min_height, reasonable aspect ratio
Returns: (is_valid: bool, error_message: str or None)

### `validate_condition(condition)`
Checks: Value is 'Brand New' or 'Fairly Used'
Returns: (is_valid: bool, error_message: str or None)

### `validate_category(category)`
Checks: Category is in predefined list
Returns: (is_valid: bool, error_message: str or None)

### `validate_upload_request(form_data, images_from_request)`
Performs complete validation of all upload data
Returns: (is_valid: bool, error_message: str or None, field: str or None)

### `get_user_friendly_error_message(error_obj, field=None)`
Converts technical error to user-friendly message
Returns: str (user message)

## Error Message Patterns

All error messages follow this pattern:
```
[Problem description] [Requirement/Limit] [How to fix]
```

Examples:
```
"File is too large (15MB). Maximum is 10MB. Try compressing the image."

"Item name is too short (2 chars). Use at least 3 characters to describe clearly."

"Description is too long (3000 chars). Keep it under 2000 characters."
```

## Configuration

### Image Limits
- Max file size: 10MB (configurable via `max_size_mb` parameter)
- Min dimensions: 400x300 pixels (configurable via `min_width`, `min_height`)
- Allowed formats: jpg, jpeg, png, gif, webp

### Text Limits
- Item name: 3-100 characters
- Description: 20-2000 characters

### Image Count
- Min images: 1
- Max images: 6

## Error Handling Best Practices

### ✅ DO
- Use `get_user_friendly_error_message()` for technical errors
- Include specific details (filename, file size, dimensions)
- Provide actionable suggestions in error messages
- Validate early, before database operations
- Group related validations (all images together)
- Show field-specific errors for form fields

### ❌ DON'T
- Show technical error messages to users directly
- Use cryptic error codes
- Blame the user without explanation
- Skip validation steps
- Mix technical and user-friendly messages
- Validate in the wrong order (size before format)

## Testing Validators

### Test Image Too Large
```python
from upload_validation_helper import validate_image_size

is_valid, msg = validate_image_size(15_000_000, "test.jpg", max_size_mb=10)
# is_valid = False
# msg = "'test.jpg' is too large (15.0 MB). Maximum allowed image size is 10 MB..."
```

### Test Invalid Format
```python
from upload_validation_helper import validate_image_type

is_valid, msg = validate_image_type("test.txt", {'jpg', 'png', 'gif'})
# is_valid = False
# msg = "'test.txt' has an unsupported format (.txt). Please use one of these formats: GIF, JPG, PNG"
```

### Test Low Resolution
```python
from upload_validation_helper import validate_image_dimensions

is_valid, msg = validate_image_dimensions(200, 150, "small.jpg", min_width=400, min_height=300)
# is_valid = False
# msg = "'small.jpg' is too small (200x150 pixels). Please use images that are at least 400x300 pixels..."
```

## Common Error Scenarios

### Scenario 1: User uploads 3 large PNG files
```
Error 1: "image1.png is too large (12.5 MB). Maximum allowed image size is 10 MB..."
Error 2: "image2.png is too large (11.3 MB). Maximum allowed image size is 10 MB..."
Error 3: "image3.png is too large (10.5 MB). Maximum allowed image size is 10 MB..."
→ User realizes all need compression, retries with smaller files
```

### Scenario 2: User uploads 10 images
```
Error: "You've uploaded 10 images, but the maximum is 6 images per item. Please remove 4 image(s) and try again."
→ User removes 4 images, retries with 6
```

### Scenario 3: User enters short description
```
Error: "Description is too short (15 characters). Please provide at least 20 characters describing the item, condition, and any important details."
→ User adds more detail about the item
```

### Scenario 4: User uploads all images successfully, but form has error
```
Form Error: "Item Name: Item name must be between 3 and 100 characters."
→ User fixes item name
→ Images are preserved (no re-upload needed)
```

## Success Messages

### Single Image
```
✅ Success! Your item has been submitted for approval with 1 image. We'll review it shortly.
```

### Multiple Images
```
✅ Success! Your item has been submitted for approval with 5 image(s). We'll review it shortly.
```

## Future Enhancements

Potential improvements:
- [ ] Image compression suggestions
- [ ] Real-time validation on client side
- [ ] Preview of uploaded images with warnings
- [ ] AI-powered image quality assessment
- [ ] Category suggestions based on image analysis
- [ ] Price estimation from image
