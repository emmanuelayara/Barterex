# Upload Error Handling - Testing Guide

## Quick Start Test

### Test 1: Successful Upload (Baseline)
**Steps:**
1. Navigate to `/upload`
2. Fill in:
   - Item Name: "iPhone 12 Pro"
   - Description: "Excellent condition, barely used, comes with all accessories and original box"
   - Condition: "Brand New"
   - Category: "Electronics"
3. Upload 3 JPG images (< 10MB each, at least 400x300 pixels)
4. Click "Submit Item"

**Expected Result:**
```
✅ Success! Your item has been submitted for approval with 3 image(s). We'll review it shortly.
→ Redirected to marketplace
```

---

## Error Message Tests

### Test 2: No Images
**Steps:**
1. Fill in all form fields correctly
2. Do NOT select any images
3. Click "Submit Item"

**Expected Result:**
```
❌ Please upload at least one image so buyers can see your item.
```

### Test 3: Too Many Images
**Steps:**
1. Fill in all form fields correctly
2. Select 8 images (valid JPG/PNG)
3. Click "Submit Item"

**Expected Result:**
```
❌ You've uploaded 8 images, but the maximum is 6 images. 
Please remove 2 image(s) and try again.
```

### Test 4: Image File Too Large
**Steps:**
1. Fill in all form fields correctly
2. Select image > 10MB (or create test file)
3. Click "Submit Item"

**Expected Result:**
```
❌ 'filename.jpg' is too large (15.2 MB). Maximum allowed image size is 10 MB. 
Try compressing the image using an online tool or your device's built-in compression.
```

### Test 5: Wrong Image Format
**Steps:**
1. Fill in all form fields correctly
2. Select non-image file (PDF, TXT, ZIP, etc.)
3. Click "Submit Item"

**Expected Result:**
```
❌ 'document.pdf' has an unsupported format (.pdf). 
Please use one of these formats: GIF, JPEG, PNG, WEBP
```

### Test 6: Image Too Small (Low Resolution)
**Steps:**
1. Fill in all form fields correctly
2. Create a very small image (200x150 pixels)
3. Upload it
4. Click "Submit Item"

**Expected Result:**
```
⚠️ 'small.jpg' is too small (200x150 pixels). 
Please use images that are at least 400x300 pixels. 
Higher resolution images help buyers see details better.
```

### Test 7: Item Name Too Short
**Steps:**
1. Item Name: "A"
2. Fill in other fields correctly
3. Upload valid images
4. Click "Submit Item"

**Expected Result:**
```
❌ Item Name: Item name is too short (1 character). 
Please use at least 3 characters to describe your item clearly.
```

### Test 8: Item Name Too Long
**Steps:**
1. Item Name: (copy/paste text > 100 characters)
2. Fill in other fields correctly
3. Upload valid images
4. Click "Submit Item"

**Expected Result:**
```
❌ Item Name: Item name must be between 3 and 100 characters.
```

### Test 9: Description Too Short
**Steps:**
1. Item Name: "iPhone"
2. Description: "Good" (4 characters)
3. Fill in other fields correctly
4. Upload valid images
5. Click "Submit Item"

**Expected Result:**
```
❌ Item Description: Description is too short (4 characters). 
Please provide at least 20 characters describing the item, condition, and any important details.
```

### Test 10: Description Too Long
**Steps:**
1. Item Name: "iPhone"
2. Description: (paste text > 2000 characters)
3. Fill in other fields correctly
4. Upload valid images
5. Click "Submit Item"

**Expected Result:**
```
❌ Item Description: Description must be between 20 and 2000 characters.
```

### Test 11: No Condition Selected
**Steps:**
1. Fill in name and description correctly
2. Leave Condition as default (not selected)
3. Fill in other fields
4. Upload valid images
5. Click "Submit Item"

**Expected Result:**
```
❌ Item Condition: Please select the condition of your item.
```

### Test 12: No Category Selected
**Steps:**
1. Fill in name and description correctly
2. Leave Category as default (not selected)
3. Fill in other fields
4. Upload valid images
5. Click "Submit Item"

**Expected Result:**
```
❌ Item Category: Please select a category for your item.
```

### Test 13: Multiple Errors at Once
**Steps:**
1. Item Name: "X" (too short)
2. Description: "OK" (too short)
3. No images
4. No condition selected
5. Click "Submit Item"

**Expected Result:**
```
❌ Item Name: Item name is too short (1 character)...

❌ Item Description: Description is too short (2 characters)...

❌ Please upload at least one image so buyers can see your item.

❌ Item Condition: Please select the condition of your item.
```
*(All errors shown, user can fix multiple issues)*

---

## Edge Case Tests

### Test 14: Empty File (0 bytes)
**Steps:**
1. Create empty file named "empty.jpg"
2. Fill in form correctly
3. Upload empty file
4. Click "Submit Item"

**Expected Result:**
```
❌ 'empty.jpg' appears to be empty. Please select a valid image file.
```

### Test 15: Corrupted Image File
**Steps:**
1. Take valid JPG, delete part of file content
2. Keep .jpg extension
3. Fill in form correctly
4. Upload corrupted file
5. Click "Submit Item"

**Expected Result:**
```
❌ 'corrupted.jpg' has an invalid dimensions. Please use a valid image file.
```
(or similar error about image integrity)

### Test 16: Mixed Valid and Invalid Images
**Steps:**
1. Select 4 valid images and 1 PDF
2. Fill in form correctly
3. Click "Submit Item"

**Expected Result:**
```
❌ 'document.pdf' has an unsupported format (.pdf)...
```
*(Stops before uploading, user can fix)*

### Test 17: Image with Extreme Aspect Ratio
**Steps:**
1. Create very wide image (5000x100 pixels) or very tall (100x5000)
2. Fill in form correctly
3. Upload image
4. Click "Submit Item"

**Expected Result:**
```
⚠️ 'extreme.jpg' has an unusual shape (aspect ratio: 50.0:1). 
Please use photos that are closer to normal proportions (landscape or portrait).
```

---

## User Journey Tests

### Journey 1: User learns from error
**Steps:**
1. Upload single image 15MB → Get error about size
2. User compresses image to 5MB
3. Upload again
4. Success!

**Expected:** User understands issue and fixes it

### Journey 2: User fixes multiple issues
**Steps:**
1. Submit with short name, short description, no images
2. Get 3 errors
3. User fixes all 3
4. Submit again
5. Success!

**Expected:** User can see all issues and fix at once

### Journey 3: User abandons after understanding issue
**Steps:**
1. User tries to upload 8 images
2. Gets clear message about 6 max
3. User decides 6 images is enough
4. Removes 2 images
5. Success!

**Expected:** User feels supported, not frustrated

---

## Browser Compatibility Tests

### Test 18: Chrome
- [ ] Error messages display correctly
- [ ] Images preview properly
- [ ] Form validation works
- [ ] Success redirect works

### Test 19: Firefox
- [ ] Error messages display correctly
- [ ] Images preview properly
- [ ] Form validation works
- [ ] Success redirect works

### Test 20: Safari
- [ ] Error messages display correctly
- [ ] Images preview properly
- [ ] Form validation works
- [ ] Success redirect works

### Test 21: Mobile (iOS)
- [ ] Can select images from camera roll
- [ ] Error messages readable on small screen
- [ ] Form fields accessible
- [ ] Can retry after error

### Test 22: Mobile (Android)
- [ ] Can select images from gallery
- [ ] Error messages readable on small screen
- [ ] Form fields accessible
- [ ] Can retry after error

---

## Database Tests

### Test 23: Image Metadata Saved
**Steps:**
1. Upload item successfully
2. Check database Item and ItemImage tables

**Expected:**
```
ItemImage table has:
- image_url: "static/uploads/..."
- is_primary: True/False
- order_index: 0,1,2...
- width: correct pixel width
- height: correct pixel height
- file_size: correct size in bytes
- quality_flags: JSON array
```

### Test 24: Rollback on Error
**Steps:**
1. Start upload with 3 valid images + 1 invalid
2. Get error on invalid image
3. Check database

**Expected:**
- Item was NOT created (transaction rolled back)
- No partial uploads in database
- No orphaned images

---

## Performance Tests

### Test 25: Upload Speed (Single Image)
- Upload 1 valid image (5MB)
- Measure time from submit to success
- Expected: < 5 seconds

### Test 26: Upload Speed (Multiple Images)
- Upload 6 valid images (6MB each)
- Measure time from submit to success
- Expected: < 15 seconds

### Test 27: Error Response Speed
- Submit with invalid data
- Measure time to error display
- Expected: < 1 second

---

## Accessibility Tests

### Test 28: Screen Reader
- Navigate to upload form with screen reader
- Hear field labels and error messages
- Understand what's required

### Test 29: High Contrast
- Enable high contrast mode
- Error messages visible
- Form fields distinguishable

### Test 30: Keyboard Navigation
- Tab through form fields
- Navigate to upload button
- Submit form
- See error messages highlighted

---

## Security Tests

### Test 31: XSS Prevention
**Steps:**
1. Fill in name with: `<script>alert('xss')</script>`
2. Fill in description with image tags
3. Submit with valid images
4. Check that script doesn't execute

**Expected:** HTML is sanitized/escaped, no script execution

### Test 32: File Upload Security
**Steps:**
1. Try to upload file with double extension: `virus.jpg.exe`
2. Try to upload file with null bytes: `virus.jpg\x00.exe`
3. Try to upload executable as image

**Expected:** All rejected with appropriate error messages

---

## Stress Tests

### Test 33: Rapid Resubmission
**Steps:**
1. Fill form incorrectly
2. Get error
3. Immediately resubmit (3 times rapidly)
4. Each time fix one issue
5. Eventually succeed

**Expected:**
- No database errors
- No orphaned records
- Clear error each time
- Success on valid attempt

---

## Regression Tests

### Test 34: Items Uploaded Before Changes
**Steps:**
1. View items uploaded before error handling update
2. Check images still display
3. Check item details page works

**Expected:**
- Old images still visible
- No errors with old items
- Backwards compatible

---

## Test Data

### Valid Images for Testing
```
# High quality (should pass)
- 1920x1080, 2MB, JPEG
- 1024x768, 500KB, PNG
- 2560x1440, 3MB, JPG

# Low quality (should warn or fail)
- 200x150, 50KB, JPG
- 100x100, 10KB, PNG
- 5000x50, 1MB, JPG (extreme aspect ratio)

# Edge cases
- 400x300, 0 bytes (empty)
- 400x300, 10.5MB (just over limit)
- 400x300, 10MB (exactly at limit)
```

---

## Test Reporting

### Pass Criteria ✅
- Error message is clear and specific
- Error includes filename/size when relevant
- Error suggests how to fix the problem
- User can retry after fixing issue
- No database errors or orphaned data
- Page loads properly after error
- All form data preserved except error field

### Fail Criteria ❌
- Error is cryptic or technical
- User doesn't know how to fix issue
- Error prevents retry without page reload
- Database has inconsistent state
- Page errors or crashes
- Form data is lost after error

---

## Checklist for QA

- [ ] All 34 tests completed
- [ ] All tests passed
- [ ] No unexpected errors in logs
- [ ] Database integrity maintained
- [ ] Mobile testing passed
- [ ] Accessibility testing passed
- [ ] Security testing passed
- [ ] Performance acceptable
- [ ] Backwards compatibility verified
- [ ] Documentation reviewed

---

## Test Environment Setup

### Requirements
- Python 3.8+
- Flask with all dependencies
- Database (SQLite for dev)
- Test images (various sizes/formats)

### Sample Test Images
Create these for testing:
```bash
# Valid image (5MB, valid format)
convert -size 1920x1440 xc:blue valid_large.jpg

# Too large (15MB)
convert -size 4000x3000 xc:red too_large.jpg

# Too small (200x100)
convert -size 200x100 xc:green too_small.jpg

# Wrong format
touch invalid.txt
```

---

**Status:** Ready for QA Testing
**Estimated Time:** 2-3 hours for full test suite
**Priority:** High (affects user experience)
