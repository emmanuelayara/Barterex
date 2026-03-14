#!/usr/bin/env python
import os
import sys

# Test the image_url filter logic
def test_image_url_filter():
    """Test the image_url filter with various inputs"""
    
    # Create upload directory for testing
    upload_dir = 'static/uploads'
    os.makedirs(upload_dir, exist_ok=True)
    
    def format_image_url(url):
        """Mimic the flask filter logic"""
        if not url:
            return '/static/placeholder.png'
        
        url = str(url).strip()
        
        # If URL is already a full Cloudinary URL, return as-is
        if 'res.cloudinary.com' in url:
            return url
        
        # If URL already looks like a full HTTP/HTTPS URL, return as-is
        if url.startswith('http://') or url.startswith('https://'):
            return url
        
        if url.startswith('/static/'):
            return url.replace('//', '/')
        
        # Handle paths with Cloudinary folder structure
        if '/' in url:
            filename = url.split('/')[-1]
        else:
            filename = url
        
        filename = filename.strip('/')
        
        # The database may store filenames like "0_1_0_1771234294_Barter_logo.PNG"
        # But actual files are stored as "1_0_1771234294_Barter_logo.PNG"
        file_path = os.path.join(upload_dir, filename)
        
        if not os.path.exists(file_path) and '_' in filename:
            # Try removing the first component
            parts = filename.split('_', 1)
            if len(parts) > 1:
                alt_filename = parts[1]
                alt_path = os.path.join(upload_dir, alt_filename)
                if os.path.exists(alt_path):
                    filename = alt_filename
        
        return f'/static/uploads/{filename}'
    
    # Test cases
    test_cases = [
        ('barterex/1/1/1/0_1_0_1771234294_Barter_logo.PNG', '/static/uploads/1_0_1771234294_Barter_logo.PNG'),
        ('barterex/1/1/1/1_1_1_1771234294_Capture_for_barter.PNG', '/static/uploads/1_1_1771234294_Capture_for_barter.PNG'),
        ('1_0_1771234294_Barter_logo.PNG', '/static/uploads/1_0_1771234294_Barter_logo.PNG'),
        (None, '/static/placeholder.png'),
        ('', '/static/placeholder.png'),
        ('https://res.cloudinary.com/demo/image/upload/v1/sample.jpg', 'https://res.cloudinary.com/demo/image/upload/v1/sample.jpg'),
    ]
    
    print("Testing image_url filter")
    print("=" * 80)
    
    results = []
    for input_url, expected in test_cases:
        result = format_image_url(input_url)
        status = "✓ PASS" if result == expected else "✗ FAIL"
        results.append((status, input_url, expected, result))
        print(f"\n{status}")
        print(f"  Input:    {input_url}")
        print(f"  Expected: {expected}")
        print(f"  Got:      {result}")
    
    print("\n" + "=" * 80)
    passed = sum(1 for r in results if '✓' in r[0])
    total = len(results)
    print(f"Results: {passed}/{total} passed")
    
    return all('✓' in r[0] for r in results)

if __name__ == '__main__':
    success = test_image_url_filter()
    sys.exit(0 if success else 1)
