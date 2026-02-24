"""
Migration script to upload local images to Cloudinary and update database
Handles all ItemImage records with local filenames
"""
import os
import sys
from app import app, db
from models import Item, ItemImage
from cloudinary_handler import cloudinary_handler
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def migrate_images():
    """Migrate all local images to Cloudinary"""
    
    with app.app_context():
        print("\n" + "="*70)
        print("🚀 IMAGE MIGRATION TO CLOUDINARY")
        print("="*70 + "\n")
        
        # Check Cloudinary config
        if not cloudinary_handler.is_configured:
            print("❌ ERROR: Cloudinary is NOT configured!")
            print("   Check environment variables:\n")
            print(f"   CLOUDINARY_CLOUD_NAME: {app.config.get('CLOUDINARY_CLOUD_NAME')}")
            print(f"   CLOUDINARY_API_KEY: {app.config.get('CLOUDINARY_API_KEY')}")
            print(f"   USE_CLOUDINARY: {app.config.get('USE_CLOUDINARY')}\n")
            return False
        
        print("✅ Cloudinary is configured\n")
        
        # Get all ItemImage records
        all_images = ItemImage.query.all()
        total = len(all_images)
        print(f"📊 Total images in database: {total}\n")
        
        migrated = 0
        failed = 0
        skipped = 0
        
        for idx, image_record in enumerate(all_images, 1):
            image_url = image_record.image_url
            
            # Skip if already a Cloudinary URL
            if 'barterex/' in image_url or 'res.cloudinary.com' in image_url:
                skipped += 1
                continue
            
            # Try to find the file
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], image_url)
            
            print(f"[{idx}/{total}] Processing: {image_url}")
            
            if not os.path.exists(file_path):
                print(f"          ❌ File not found: {file_path}")
                failed += 1
                continue
            
            try:
                # Upload file directly by path to Cloudinary
                user_id = image_record.item.user_id
                item_id = image_record.item_id
                order_index = image_record.order_index
                
                print(f"          ⏳ Uploading to Cloudinary...")
                
                # Upload to Cloudinary by file path
                result = cloudinary_handler.upload_image(
                    file_path,  # Pass file path directly
                    user_id=user_id,
                    item_id=item_id,
                    index=order_index,
                    folder_prefix='barterex'
                )
                
                # Update database with new Cloudinary public_id
                public_id = result['public_id']
                image_record.image_url = public_id
                print(f"          ✅ Uploaded: {public_id}")
                
                migrated += 1
                    
            except Exception as e:
                print(f"          ❌ Error: {str(e)[:100]}")
                failed += 1
        
        # Commit changes to database
        print(f"\n{'='*70}\n")
        try:
            db.session.commit()
            print("✅ Database updated successfully\n")
            print(f"📈 RESULTS:")
            print(f"   ✅ Migrated: {migrated}")
            print(f"   ⏭️  Skipped:  {skipped} (already Cloudinary)")
            print(f"   ❌ Failed:   {failed}\n")
            print("="*70 + "\n")
            return True
        except Exception as e:
            db.session.rollback()
            print(f"❌ Database commit failed: {str(e)}\n")
            return False

if __name__ == '__main__':
    try:
        success = migrate_images()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {str(e)}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
