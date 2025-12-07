from app import app
from models import CartItem

with app.app_context():
    cart_items = CartItem.query.all()
    print(f"Total cart items: {len(cart_items)}")
    for ci in cart_items:
        if ci.item:
            print(f"\nCart Item ID: {ci.id}")
            print(f"  Item ID: {ci.item_id}")
            print(f"  Item Name: {repr(ci.item.name)}")
            print(f"  Item Number: {repr(ci.item.item_number)}")
            print(f"  Item Value: {ci.item.value}")
            print(f"  Item Category: {ci.item.category}")
            print(f"  Item Location: {ci.item.location}")
            print(f"  Item Condition: {ci.item.condition}")
