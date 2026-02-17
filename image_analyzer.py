"""
Image analysis utility for detecting metadata, dimensions, file size, and suspicious patterns
"""
import requests
from io import BytesIO
from PIL import Image
import json
import logging
import os

logger = logging.getLogger(__name__)

def analyze_image_url(image_url):
    """
    Analyze an image from a URL or file path and extract metadata
    
    Args:
        image_url: Full URL to the image OR local file path OR just filename
        
    Returns:
        dict with keys:
        - width: Image width in pixels
        - height: Image height in pixels
        - file_size: File size in bytes
        - quality_flags: List of quality issues detected
        - has_issues: Boolean indicating if any issues found
    """
    result = {
        'width': None,
        'height': None,
        'file_size': None,
        'quality_flags': [],
        'has_issues': False
    }
    
    try:
        # Check if it's a remote URL
        if image_url.startswith('http://') or image_url.startswith('https://'):
            # Remote URL - download it
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
            
            # Get file size
            file_size = len(response.content)
            result['file_size'] = file_size
            
            # Open image with PIL
            img = Image.open(BytesIO(response.content))
        else:
            # Local file path - could be absolute, relative, or just filename
            import sys
            if 'app' in sys.modules:
                from app import app
                
                # Determine the file path
                if image_url.startswith('/'):
                    # Absolute path relative to app root
                    file_path = os.path.join(app.root_path, image_url.lstrip('/'))
                elif image_url.startswith('static'):
                    # Static folder
                    file_path = os.path.join(app.root_path, image_url)
                else:
                    # Just a filename - construct path using upload folder
                    upload_folder = app.config.get('UPLOAD_FOLDER', 'static/uploads')
                    file_path = os.path.join(app.root_path, upload_folder, image_url)
            else:
                # Fallback if app not available
                upload_folder = 'static/uploads'
                file_path = os.path.join(os.getcwd(), upload_folder, image_url)
            
            # Normalize path
            file_path = os.path.normpath(file_path)
            
            # Check if file exists
            if not os.path.exists(file_path):
                logger.error(f"Image file not found: {file_path}")
                result['quality_flags'].append({
                    'type': 'file_not_found',
                    'message': f'Image file not found: {image_url}',
                    'severity': 'error'
                })
                result['has_issues'] = True
                return result
            
            # Read local file
            with open(file_path, 'rb') as f:
                file_content = f.read()
            file_size = len(file_content)
            result['file_size'] = file_size
            
            # Open image with PIL
            img = Image.open(BytesIO(file_content))
        
        # Get dimensions
        width, height = img.size
        result['width'] = width
        result['height'] = height
        
        # Analyze for suspicious patterns
        quality_flags = []
        
        # Check for unusually low resolution (less than 400x300)
        if width < 400 or height < 300:
            quality_flags.append({
                'type': 'low_resolution',
                'message': f'Low resolution: {width}x{height}px (recommend 400x300 minimum)',
                'severity': 'warning'
            })
        
        # Check for unusually high resolution (over 5000px)
        if width > 5000 or height > 5000:
            quality_flags.append({
                'type': 'excessive_resolution',
                'message': f'Excessive resolution: {width}x{height}px',
                'severity': 'info'
            })
        
        # Check for unusual aspect ratios (very wide or very tall)
        aspect_ratio = width / height if height > 0 else 0
        if aspect_ratio > 4 or aspect_ratio < 0.25:
            quality_flags.append({
                'type': 'unusual_aspect_ratio',
                'message': f'Unusual aspect ratio: {aspect_ratio:.2f}:1',
                'severity': 'warning'
            })
        
        # Check file size (alert if very large > 10MB)
        if file_size > 10 * 1024 * 1024:  # 10MB
            quality_flags.append({
                'type': 'large_file',
                'message': f'Large file size: {file_size / (1024*1024):.1f}MB',
                'severity': 'info'
            })
        
        # Check file size (alert if very small < 5KB, might be corrupt)
        if file_size < 5 * 1024:  # 5KB
            quality_flags.append({
                'type': 'small_file',
                'message': f'Very small file size: {file_size / 1024:.1f}KB (possibly corrupt)',
                'severity': 'warning'
            })
        
        # Check for EXIF data (possible watermark or metadata)
        has_exif = False
        try:
            exif_data = img._getexif()
            if exif_data:
                has_exif = True
                quality_flags.append({
                    'type': 'has_metadata',
                    'message': 'Image contains EXIF metadata (camera/location info)',
                    'severity': 'info'
                })
        except:
            pass
        
        # Check for potential watermarks by analyzing image format and mode
        # GIF with animation might indicate a watermark video
        if img.format == 'GIF':
            try:
                img.seek(1)  # Try to get second frame
                quality_flags.append({
                    'type': 'animated_image',
                    'message': 'Animated GIF detected',
                    'severity': 'info'
                })
                img.seek(0)
            except EOFError:
                pass  # Not animated
        
        # Check color mode (grayscale images might indicate watermarks)
        if img.mode in ['L', '1']:
            quality_flags.append({
                'type': 'grayscale_image',
                'message': f'Grayscale image ({img.mode} mode) - consider using color photos',
                'severity': 'warning'
            })
        
        # Analyze color histogram for potential watermark patterns
        # Sample: Check if image has very uniform colors (blank/placeholder)
        try:
            if img.mode == 'RGB' or img.mode == 'RGBA':
                img_small = img.resize((20, 20))  # Small sample
                colors = list(img_small.getdata())
                unique_colors = len(set(colors))
                
                # If very few unique colors, might be placeholder or watermarked
                if unique_colors < 10:
                    quality_flags.append({
                        'type': 'limited_colors',
                        'message': f'Image has very limited color palette ({unique_colors} unique colors)',
                        'severity': 'warning'
                    })
        except Exception as e:
            logger.warning(f"Could not analyze color histogram: {e}")
        
        result['quality_flags'] = quality_flags
        result['has_issues'] = len(quality_flags) > 0
        
    except requests.RequestException as e:
        logger.error(f"Error downloading image from {image_url}: {e}")
        result['quality_flags'].append({
            'type': 'download_error',
            'message': f'Could not download image for analysis',
            'severity': 'error'
        })
        result['has_issues'] = True
    except Exception as e:
        logger.error(f"Error analyzing image {image_url}: {e}")
        result['quality_flags'].append({
            'type': 'analysis_error',
            'message': f'Error analyzing image: {str(e)}',
            'severity': 'error'
        })
        result['has_issues'] = True
    
    return result


def get_formatted_file_size(bytes_size):
    """Convert bytes to human-readable format"""
    if bytes_size is None:
        return 'Unknown'
    
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024:
            return f'{bytes_size:.1f} {unit}'
        bytes_size /= 1024
    
    return f'{bytes_size:.1f} TB'


def get_formatted_dimensions(width, height):
    """Format dimensions as string"""
    if width is None or height is None:
        return 'Unknown'
    return f'{width}x{height} px'
