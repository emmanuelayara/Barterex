"""Test URL generation for Cloudinary images"""
from app import app
from models import ItemImage

with app.app_context():
    # Get first image
    image = ItemImage.query.first()
    
    if image:
        raw_url = image.image_url
        filtered_url = app.jinja_env.filters['image_url'](raw_url)
        
        print(f"\nTesting URL generation:")
        print(f"1. Raw from DB:     {raw_url}")
        print(f"2. After filter:    {filtered_url}")
        print(f"\nCloudinary config:")
        print(f"  USE_CLOUDINARY:        {app.config.get('USE_CLOUDINARY')}")
        print(f"  CLOUDINARY_CLOUD_NAME: {app.config.get('CLOUDINARY_CLOUD_NAME')}")
        print(f"  Handler configured:    {app.config.get('USE_CLOUDINARY')}")
