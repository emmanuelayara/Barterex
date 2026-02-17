#!/usr/bin/env python
"""Quick verification script for Cloudinary configuration"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Find and load the .env file from the current directory or parent directories
env_path = Path(__file__).parent / '.env'
print(f"Looking for .env at: {env_path}")
print(f"File exists: {env_path.exists()}\n")

# Load environment variables from the specific .env file
if env_path.exists():
    load_dotenv(env_path)
else:
    # Fallback to default load_dotenv() which searches standard locations
    load_dotenv()

print("=== Cloudinary Configuration Verification ===\n")

# Check environment variables
use_cloudinary = os.getenv('USE_CLOUDINARY', 'False').lower() in ['true', '1', 'yes']
cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME')
api_key = os.getenv('CLOUDINARY_API_KEY')
api_secret = os.getenv('CLOUDINARY_API_SECRET')

print(f"1. USE_CLOUDINARY: {use_cloudinary}")
print(f"2. CLOUDINARY_CLOUD_NAME: {cloud_name if cloud_name else '❌ NOT SET'}")
print(f"3. CLOUDINARY_API_KEY: {'✅ SET' if api_key else '❌ NOT SET'}")
print(f"4. CLOUDINARY_API_SECRET: {'✅ SET' if api_secret else '❌ NOT SET'}")

# Check if all required fields are present
all_configured = use_cloudinary and cloud_name and api_key and api_secret

print(f"\n{'✅ Cloudinary is FULLY CONFIGURED' if all_configured else '❌ Cloudinary is NOT fully configured'}")

# Test actual connection
if all_configured:
    try:
        import cloudinary
        from cloudinary_handler import cloudinary_handler
        
        print(f"\n📧 Testing Cloudinary Connection:")
        print(f"  - Handler status: {'✅ Configured' if cloudinary_handler.is_configured else '❌ Not configured'}")
        print(f"  - Cloud name: {cloudinary.config().cloud_name}")
        print(f"  - API key present: {'✅ Yes' if cloudinary.config().api_key else '❌ No'}")
        
    except Exception as e:
        print(f"❌ Error testing connection: {e}")
else:
    print("\n⚠️ Missing required environment variables. Please add them to .env file.")

print("\n" + "="*50 + "\n")
