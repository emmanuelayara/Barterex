"""Test uploading a single image to Cloudinary"""
import os
from app import app
from models import ItemImage
from cloudinary_handler import cloudinary_handler

with app.app_context():
    # Get the first local image
    local_image = ItemImage.query.filter(~ItemImage.image_url.contains('barterex')).first()
    
    if not local_image:
        print("❌ No local images found")
    else:
        print(f"\n🔍 Testing with image: {local_image.image_url}")
        print(f"   Item ID: {local_image.item_id}")
        print(f"   User ID: {local_image.item.user_id}\n")
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], local_image.image_url)
        print(f"🔍 File path: {file_path}")
        print(f"📁 File exists: {os.path.exists(file_path)}\n")
        
        if os.path.exists(file_path):
            try:
                print("⏳ Testing Cloudinary upload...")
                with open(file_path, 'rb') as f:
                    result = cloudinary_handler.upload_image(
                        f,
                        user_id=local_image.item.user_id,
                        item_id=local_image.item_id,
                        index=local_image.order_index,
                        folder_prefix='barterex'
                    )
                    print(f"✅ Upload successful!")
                    print(f"   Public ID: {result['public_id']}")
                    print(f"   URL: {result.get('secure_url', 'N/A')}\n")
            except Exception as e:
                print(f"❌ Upload failed: {e}\n")
        else:
            print("❌ File not found\n")
