from app import app, db
from models import ItemImage

with app.app_context():
    # Check first 5 images
    images = ItemImage.query.limit(5).all()
    print(f"\n📊 CHECKING {len(images)} IMAGES:\n")
    for i, img in enumerate(images, 1):
        image_url = str(img.image_url)
        is_remote = image_url.startswith(('http://', 'https://'))
        status = "✅ REMOTE" if is_remote else "❌ LOCAL"
        print(f"{i}. {status}: {image_url}")
    print()
