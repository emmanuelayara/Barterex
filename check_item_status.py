from app import app, db
from models import Item

with app.app_context():
    item = Item.query.get(15)
    if item:
        print(f"Item ID: {item.id}")
        print(f"Item Name: {item.name}")
        print(f"Available: {item.is_available}")
        print(f"Status: {getattr(item, 'status', 'N/A')}")
    else:
        print("Item not found")
