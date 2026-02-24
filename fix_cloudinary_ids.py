"""Fix Cloudinary public_ids that have duplicate folder structure"""
from app import app, db
from models import ItemImage

with app.app_context():
    # Find images with doubled folder structure
    wrong_images = ItemImage.query.filter(
        ItemImage.image_url.contains('barterex/') &
        (ItemImage.image_url.like('%barterex/%%/barterex/%'))
    ).all()
    
    if not wrong_images:
        # Try alternative check - look for pattern
        all_images = ItemImage.query.all()
        wrong_images = []
        for img in all_images:
            parts = img.image_url.split('/')
            if len(parts) > 5 and parts[0] == 'barterex':  # Should be barterex/uid/iid/filename
                wrong_images.append(img)
    
    print(f"Found {len(wrong_images)} images with wrong structure")
    
    fixed = 0
    for img in wrong_images:
        old_id = img.image_url
        # Extract: barterex/1/barterex/1/1/... -> extract last 3 parts
        parts = old_id.split('/')
        
        # If structure is barterex/user/barterex/user/item/index_file
        # We want: barterex/user/item/index_file
        if len(parts) >= 5 and parts[0] == 'barterex' and parts[2] == 'barterex':
            # It's the doubled structure
            new_id = f"barterex/{parts[1]}/{parts[3]}/{'/'.join(parts[4:])}"
        else:
            continue
        
        print(f"Fixing: {old_id[:50]}...")
        print(f"   To:  {new_id[:50]}...")
        img.image_url = new_id
        fixed += 1
    
    if fixed > 0:
        db.session.commit()
        print(f"\nFixed {fixed} images")
    else:
        print("No images needed fixing")
