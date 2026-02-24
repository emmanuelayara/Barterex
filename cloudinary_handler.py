"""Cloudinary image upload and management handler for Barterex"""
import cloudinary
import cloudinary.uploader
import cloudinary.api
from flask import current_app
import os
from werkzeug.utils import secure_filename
import logging

logger = logging.getLogger(__name__)


class CloudinaryHandler:
    """Centralized handler for all Cloudinary operations"""
    
    def __init__(self):
        self.is_configured = False
        self.configure()
    
    def configure(self):
        """Configure Cloudinary with credentials from environment"""
        try:
            cloudinary.config(
                cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
                api_key=os.getenv('CLOUDINARY_API_KEY'),
                api_secret=os.getenv('CLOUDINARY_API_SECRET')
            )
            # Verify configuration
            if cloudinary.config().cloud_name:
                self.is_configured = True
                logger.info(f"✅ Cloudinary configured for cloud: {cloudinary.config().cloud_name}")
            else:
                logger.warning("⚠️ Cloudinary not configured - missing credentials")
        except Exception as e:
            logger.error(f"❌ Cloudinary configuration error: {e}")
    
    def upload_image(self, file_obj, user_id, item_id, index=0, folder_prefix='barterex'):
        """
        Upload image to Cloudinary
        
        Args:
            file_obj: Flask FileStorage object or file path string
            user_id: User ID for organizing uploads
            item_id: Item ID this image belongs to
            index: Image index (for ordering)
            folder_prefix: Cloudinary folder prefix
        
        Returns:
            dict: Upload response with URL and other metadata
        """
        if not self.is_configured:
            raise Exception("Cloudinary is not configured")
        
        try:
            # Get filename
            if isinstance(file_obj, str):
                # If it's a file path string
                filename = os.path.basename(file_obj)
                file_to_upload = file_obj
            else:
                # If it's a file-like object
                filename = getattr(file_obj, 'filename', f'image_{item_id}_{index}.jpg')
                file_to_upload = file_obj
            
            # Create organized folder structure
            public_id = f"{folder_prefix}/{user_id}/{item_id}/{index}_{secure_filename(filename)}"
            
            # Upload to Cloudinary
            result = cloudinary.uploader.upload(
                file_to_upload,
                public_id=public_id,
                folder=f"{folder_prefix}/{user_id}",
                resource_type='auto',
                overwrite=False,
                quality='auto',  # Auto-optimize quality
                width=1200,  # Max width
                crop='limit',  # Don't upscale
                tags=[str(user_id), str(item_id)],  # Tag for organization
            )
            
            logger.info(f"✅ Image uploaded to Cloudinary: {result['public_id']}")
            return result
        
        except Exception as e:
            logger.error(f"❌ Cloudinary upload error: {e}")
            raise Exception(f"Failed to upload image to Cloudinary: {str(e)}")
    
    def delete_image(self, public_id):
        """
        Delete image from Cloudinary
        
        Args:
            public_id: Cloudinary public ID of the image
        
        Returns:
            bool: Success status
        """
        if not self.is_configured:
            logger.warning("Cloudinary not configured, skipping delete")
            return False
        
        try:
            cloudinary.uploader.destroy(public_id)
            logger.info(f"✅ Image deleted from Cloudinary: {public_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Cloudinary delete error: {e}")
            return False
    
    def get_optimized_url(self, public_id, width=None, height=None, quality='auto', format='auto'):
        """
        Get optimized Cloudinary URL for image
        
        Args:
            public_id: Cloudinary public ID
            width: Optional width for resizing
            height: Optional height for resizing
            quality: Quality setting (auto, best, good, eco, low)
            format: Image format (auto, webp, jpg, png, etc)
        
        Returns:
            str: Optimized image URL
        """
        if not self.is_configured:
            return None
        
        try:
            url = cloudinary.CloudinaryImage(public_id).build_url(
                width=width,
                height=height,
                crop='limit' if (width or height) else None,
                quality=quality,
                format=format,
                secure=True  # Use HTTPS
            )
            return url
        except Exception as e:
            logger.error(f"❌ Error building Cloudinary URL: {e}")
            return None
    
    def get_asset_info(self, public_id):
        """
        Get detailed information about an image from Cloudinary
        
        Args:
            public_id: Cloudinary public ID
        
        Returns:
            dict: Image metadata
        """
        if not self.is_configured:
            return {}
        
        try:
            resource = cloudinary.api.resource(public_id)
            return {
                'width': resource.get('width'),
                'height': resource.get('height'),
                'format': resource.get('format'),
                'size': resource.get('bytes'),
                'url': resource.get('url'),
                'secure_url': resource.get('secure_url')
            }
        except Exception as e:
            logger.error(f"❌ Error getting asset info: {e}")
            return {}


# Global instance
cloudinary_handler = CloudinaryHandler()
