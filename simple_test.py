#!/usr/bin/env python3
"""
Simple test to check if .env loads at all
"""
import os
print("Testing if .env can be parsed...")

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
    print("✓ dotenv.load_dotenv() succeeded")
    
    api_key = os.getenv('GOOGLE_API_KEY')
    cx = os.getenv('GOOGLE_SEARCH_ENGINE_ID')
    
    print(f"GOOGLE_API_KEY: {api_key}")
    print(f"GOOGLE_SEARCH_ENGINE_ID: {cx}")
    
except ValueError as e:
    print(f"❌ ValueError: {e}")
    print("\nThe .env file has invalid characters.")
    print("Let me check the file manually...")
    
    with open('.env', 'rb') as f:
        content = f.read()
        print(f"File size: {len(content)} bytes")
        # Look for null bytes
        if b'\x00' in content:
            print("⚠️  Found NULL bytes in .env file!")
            pos = content.find(b'\x00')
            print(f"First null byte at position {pos}")
            print(f"Context: {content[max(0,pos-20):pos+20]}")
except Exception as e:
    print(f"❌ Error: {type(e).__name__}: {e}")
