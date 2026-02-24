from app import app, db
from models import ItemImage, Item

with app.app_context():
    items = Item.query.limit(3).all()
    for item in items:
        print(f'\nItem: {item.name} (ID: {item.id})')
        print(f'  Primary image_url: {item.image_url}')
        if item.images:
            for i, img in enumerate(item.images[:2]):
                print(f'  Image {i}: {img.image_url}')
