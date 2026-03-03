#!/usr/bin/env python
"""Debug script to check image URLs in database"""

import os
import sys
os.chdir(os.path.dirname(__file__))
sys.path.insert(0, os.getcwd())

from flask import Flask
from models import db, ItemImage, Item

# Import app configuration
from app import app

def check_images_for_item(item_id):
    """Check all images for a specific item"""
    with app.app_context():
        item = Item.query.get(item_id)
        if not item:
            print(f"❌ Item {item_id} not found")
            return
        
        print(f"\n📦 Item {item_id}: {item.name}")
        print(f"   Item.image_url: {item.image_url}")
        
        images = ItemImage.query.filter_by(item_id=item_id).order_by(ItemImage.order_index).all()
        print(f"   Total ItemImages: {len(images)}\n")
        
        for idx, img in enumerate(images, 1):
            print(f"   Image {idx}:")
            print(f"      ID: {img.id}")
            print(f"      URL: {img.image_url}")
            
            # Try to apply the filter
            from app import format_image_url
            filtered_url = format_image_url(img.image_url)
            print(f"      Filtered URL: {filtered_url}")
            
            # Check if file exists
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], img.image_url.lstrip('/'))
            exists = os.path.exists(file_path)
            print(f"      Local file: {file_path}")
            print(f"      File exists: {exists}")
            print()

if __name__ == '__main__':
    # Check item 11 (from the screenshot)
    print("=" * 60)
    print("🔍 Debugging Image URLs")
    print("=" * 60)
    check_images_for_item(11)
    check_images_for_item(3)
    check_images_for_item(10)
