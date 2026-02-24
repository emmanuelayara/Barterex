from app import app, db
from models import ItemImage

with app.app_context():
    # Check first 5 images
    images = ItemImage.query.limit(5).all()
    print(f"\n📊 CHECKING {len(images)} IMAGES:\n")
    for i, img in enumerate(images, 1):
        is_cloudinary = 'barterex/' in img.image_url
        status = "✅ CLOUDINARY" if is_cloudinary else "❌ LOCAL"
        print(f"{i}. {status}: {img.image_url}")
    print()
