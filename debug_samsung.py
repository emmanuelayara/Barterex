from app import app, db
from models import Item, ItemImage

app.app_context().push()

item = db.session.query(Item).filter(Item.name.ilike('%Samsung%')).first()
if item:
    print(f"Item: {item.name} (ID: {item.id})")
    imgs = db.session.query(ItemImage).filter_by(item_id=item.id).all()
    print(f"Images ({len(imgs)}):")
    for img in imgs:
        print(f"  - {img.image_url}")
else:
    print("No Samsung item found")
