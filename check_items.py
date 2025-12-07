from app import app
from models import Item, CartItem

with app.app_context():
    items = Item.query.limit(5).all()
    print(f"Total items in database: {Item.query.count()}")
    print("\n--- Sample Items ---")
    for item in items:
        print(f"ID: {item.id}")
        print(f"Name: {repr(item.name)}")
        print(f"Name Length: {len(item.name)}")
        print(f"Item Number: {item.item_number}")
        print("---")
    
    # Check cart items
    print("\n--- Cart Items ---")
    cart_items = CartItem.query.limit(3).all()
    for ci in cart_items:
        print(f"Cart Item ID: {ci.id}, Item ID: {ci.item_id}")
        if ci.item:
            print(f"  Item Name: {repr(ci.item.name)}")
        print("---")
