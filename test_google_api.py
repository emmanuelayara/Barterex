#!/usr/bin/env python3
"""
Google API Credentials Verification & Testing Script
Tests if your Google API credentials are loaded and working correctly
"""

import os
import sys
import requests
from dotenv import load_dotenv

print("=" * 70)
print("GOOGLE API CREDENTIALS VERIFICATION & TESTING")
print("=" * 70)

# Step 1: Load environment variables
print("\n[STEP 1] Loading environment variables from .env...")
print("-" * 70)

load_dotenv(override=True)

google_api_key = os.getenv('GOOGLE_API_KEY')
google_cx = os.getenv('GOOGLE_SEARCH_ENGINE_ID')

print(f"✓ .env loaded (override=True)")

if google_api_key:
    print(f"✅ GOOGLE_API_KEY found")
    print(f"   Full key: {google_api_key[:30]}...{google_api_key[-10:]}")
    print(f"   Length: {len(google_api_key)} characters")
else:
    print(f"❌ GOOGLE_API_KEY NOT found")

if google_cx:
    print(f"✅ GOOGLE_SEARCH_ENGINE_ID found")
    print(f"   Full CX: {google_cx}")
else:
    print(f"❌ GOOGLE_SEARCH_ENGINE_ID NOT found")

# Step 2: Validate format
print("\n[STEP 2] Validating credential format...")
print("-" * 70)

if not google_api_key or not google_cx:
    print("❌ MISSING CREDENTIALS - Cannot proceed with testing")
    sys.exit(1)

# Check API key format (should start with AIzaSy)
if google_api_key.startswith('AIzaSy'):
    print("✅ API Key format is correct (starts with 'AIzaSy')")
else:
    print("⚠️  API Key format might be wrong (should start with 'AIzaSy')")

# Check CX format (should have format: xxxx:xxxx or similar)
if ':' in google_cx or len(google_cx) > 10:
    print("✅ Search Engine ID format looks correct")
else:
    print("⚠️  Search Engine ID format might be wrong")

# Step 3: Test API connection
print("\n[STEP 3] Testing Google Custom Search API connection...")
print("-" * 70)

test_query = "iPhone 13 price"
url = "https://www.googleapis.com/customsearch/v1"

params = {
    'key': google_api_key,
    'cx': google_cx,
    'q': test_query,
    'num': 5
}

print(f"Testing with query: '{test_query}'")
print(f"API URL: {url}")
print(f"Parameters:")
print(f"  - key: {google_api_key[:20]}...{google_api_key[-5:]}")
print(f"  - cx: {google_cx}")
print(f"  - q: {test_query}")
print(f"  - num: 5")

try:
    print("\n⏳ Sending request to Google API...")
    response = requests.get(url, params=params, timeout=10)
    
    print(f"✓ Response received - Status: {response.status_code}")
    
    if response.status_code == 200:
        print("✅ API request successful (200 OK)")
        data = response.json()
        
        if 'items' in data:
            results = data['items']
            print(f"✅ Got {len(results)} search results")
            
            print("\nTop Results:")
            for i, item in enumerate(results[:3], 1):
                print(f"  {i}. {item['title'][:60]}...")
                print(f"     URL: {item['link']}")
        else:
            print("⚠️  Response has no 'items' - possible API issue")
            print(f"Response keys: {list(data.keys())}")
    
    elif response.status_code == 403:
        print("❌ API Error 403: Forbidden")
        print("   Reasons:")
        print("   - API key is invalid or disabled")
        print("   - Search Engine ID (CX) is wrong")
        print("   - API hasn't been enabled in Google Cloud Console")
        data = response.json()
        if 'error' in data:
            print(f"   Error: {data['error']['message']}")
    
    elif response.status_code == 400:
        print("❌ API Error 400: Bad Request")
        print("   Likely cause: Invalid parameter format")
        data = response.json()
        if 'error' in data:
            print(f"   Error: {data['error']['message']}")
    
    else:
        print(f"❌ Unexpected status code: {response.status_code}")
        print(f"   Response: {response.text[:200]}")
        
except requests.exceptions.Timeout:
    print("❌ Request timeout - API took too long to respond")
except requests.exceptions.ConnectionError:
    print("❌ Connection error - Cannot reach Google API")
except Exception as e:
    print(f"❌ Error during API test: {str(e)}")

# Step 4: Test with your app's estimator
print("\n[STEP 4] Testing with your app's AI Price Estimator...")
print("-" * 70)

try:
    from services.ai_price_estimator import AIPriceEstimator
    
    print("✓ Successfully imported AIPriceEstimator")
    
    estimator = AIPriceEstimator()
    print("✓ Created estimator instance")
    
    # Check if credentials are loaded
    print(f"\nEstimator's credentials:")
    print(f"  - google_api_key: {'✅ Loaded' if estimator.google_api_key else '❌ NOT loaded'}")
    print(f"  - google_cx: {'✅ Loaded' if estimator.google_cx else '❌ NOT loaded'}")
    
    if estimator.google_api_key and estimator.google_cx:
        print("\n✅ CREDENTIALS ARE PROPERLY LOADED IN YOUR APP")
    else:
        print("\n❌ CREDENTIALS NOT LOADED - This is why you get 'not configured' message")
        print("\nSolution: Restart Flask app to reload .env file")
    
except Exception as e:
    print(f"❌ Error importing estimator: {str(e)}")

# Step 5: Summary and recommendations
print("\n[STEP 5] SUMMARY & RECOMMENDATIONS")
print("=" * 70)

print("\n📋 VERIFICATION SUMMARY:\n")

checks = []
checks.append(("API Key in .env", bool(google_api_key)))
checks.append(("Search Engine ID in .env", bool(google_cx)))
checks.append(("API Key format correct", google_api_key.startswith('AIzaSy') if google_api_key else False))
checks.append(("Google API responds", response.status_code == 200 if 'response' in locals() else False))

for check_name, result in checks:
    status = "✅" if result else "❌"
    print(f"{status} {check_name}")

all_good = all(result for _, result in checks)

print("\n" + "=" * 70)
if all_good:
    print("✅ ALL CHECKS PASSED - Your Google API is working!")
    print("\nNext step: If your app still says 'not configured':")
    print("1. Restart Flask (Ctrl+C, then python app.py)")
    print("2. Go to /valuate")
    print("3. Test a valuation")
    print("4. Check logs for 'Found X price references'")
else:
    print("⚠️  SOME CHECKS FAILED - Troubleshooting needed")
    
    if not google_api_key or not google_cx:
        print("\n🔧 FIX: Add credentials to .env:")
        print("   GOOGLE_API_KEY=your_api_key_here")
        print("   GOOGLE_SEARCH_ENGINE_ID=your_cx_here")
    
    if google_api_key and 'response' in locals() and response.status_code != 200:
        print(f"\n🔧 FIX: API returned {response.status_code}")
        print("   Check Google Cloud Console:")
        print("   1. Verify API key is active")
        print("   2. Verify Custom Search API is enabled")
        print("   3. Verify Search Engine ID (CX) is correct")

print("=" * 70)
