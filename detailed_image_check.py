#!/usr/bin/env python
import sqlite3
import os

db_path = 'instance/barter.db'

with open('detailed_image_check.txt', 'w') as f:
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        # Get first 10 ItemImage records
        rows = cur.execute("SELECT id, item_id, image_url FROM item_image LIMIT 10").fetchall()
        f.write("ItemImage database check:\n")
        f.write("=" * 80 + "\n\n")
        
        uploads_dir = 'static/uploads'
        files = os.listdir(uploads_dir) if os.path.exists(uploads_dir) else []
        
        for id, item_id, stored_url in rows:
            f.write(f"DB Record {id}:\n")
            f.write(f"  Stored URL: {stored_url}\n")
            
            # Extract filename like filter does
            if '/' in stored_url:
                extracted_filename = stored_url.split('/')[-1]
            else:
                extracted_filename = stored_url
            
            f.write(f"  Extracted filename: {extracted_filename}\n")
            
            # Check if file exists
            full_path = os.path.join(uploads_dir, extracted_filename)
            exists = os.path.exists(full_path)
            f.write(f"  File exists at /static/uploads/{extracted_filename}: {exists}\n")
            
            # Look for similar files
            matching = [fname for fname in files if extracted_filename in fname or extracted_filename.split('_')[-1] in fname]
            if matching and not exists:
                f.write(f"  Similar files found:\n")
                for m in matching[:3]:
                    f.write(f"    - {m}\n")
            
            f.write("\n")
        
        conn.close()
        f.write(f"\nTotal files in /static/uploads: {len(files)}\n")
        
    except Exception as e:
        f.write(f"Error: {e}\n")

print("Output written to detailed_image_check.txt")
