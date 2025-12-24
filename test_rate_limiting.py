#!/usr/bin/env python
"""
Rate Limiting Verification Script
Tests that rate limiting works on protected endpoints
"""

import requests
import time
import sys
from datetime import datetime

BASE_URL = "http://localhost:5000"

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")

def test_endpoint(endpoint, limit_per_minute, num_requests=None):
    """Test rate limiting on an endpoint"""
    if num_requests is None:
        num_requests = limit_per_minute + 2
    
    print_header(f"Testing {endpoint} (Limit: {limit_per_minute}/min)")
    
    success_count = 0
    rate_limited_count = 0
    
    for i in range(num_requests):
        try:
            # Make request
            start = time.time()
            response = requests.post(endpoint, timeout=5)
            elapsed = time.time() - start
            
            status = response.status_code
            
            # Get rate limit headers
            limit = response.headers.get('X-RateLimit-Limit', 'N/A')
            remaining = response.headers.get('X-RateLimit-Remaining', 'N/A')
            reset = response.headers.get('X-RateLimit-Reset', 'N/A')
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            if status == 429:
                rate_limited_count += 1
                print(f"[{timestamp}] Request {i+1:2d}: ❌ 429 Rate Limited")
                print(f"              Limit: {limit}, Remaining: {remaining}")
            elif status in [200, 302, 400, 401, 403]:  # Expected statuses
                success_count += 1
                print(f"[{timestamp}] Request {i+1:2d}: ✅ {status} Allowed ({elapsed:.2f}s)")
                print(f"              Limit: {limit}, Remaining: {remaining}")
            else:
                print(f"[{timestamp}] Request {i+1:2d}: ⚠️  {status} Unexpected ({elapsed:.2f}s)")
            
        except requests.exceptions.ConnectionError:
            print(f"Request {i+1:2d}: ❌ Connection Error - Server not running")
            return False
        except requests.exceptions.Timeout:
            print(f"Request {i+1:2d}: ❌ Timeout")
        except Exception as e:
            print(f"Request {i+1:2d}: ❌ Error - {e}")
    
    print(f"\n✅ Successful: {success_count}")
    print(f"❌ Rate Limited: {rate_limited_count}")
    
    # Verify rate limiting worked
    if rate_limited_count > 0:
        print(f"✓ Rate limiting is WORKING! Got {rate_limited_count} rate limit responses")
        return True
    else:
        print(f"⚠️  Warning: No rate limit responses received (might not be configured)")
        return False

def main():
    print("\n" + "="*60)
    print("  RATE LIMITING VERIFICATION TEST")
    print("="*60)
    print(f"\nTarget: {BASE_URL}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Check if server is running
    try:
        response = requests.get(f"{BASE_URL}/", timeout=2)
        print(f"✅ Server is running (Status: {response.status_code})")
    except:
        print(f"❌ Server not running at {BASE_URL}")
        print("Please start the Flask app and try again")
        sys.exit(1)
    
    # Test endpoints
    results = {}
    
    # Test 1: /checkout (10 per minute)
    print_header("Test 1: /checkout Endpoint")
    results['/checkout'] = test_endpoint(f"{BASE_URL}/checkout", 10, num_requests=12)
    
    # Wait before next test
    print("\n⏳ Waiting 5 seconds before next test...")
    time.sleep(5)
    
    # Test 2: /api/estimate-price (5 per minute)
    print_header("Test 2: /api/estimate-price Endpoint")
    results['/api/estimate-price'] = test_endpoint(f"{BASE_URL}/api/estimate-price", 5, num_requests=7)
    
    # Wait before next test
    print("\n⏳ Waiting 5 seconds before next test...")
    time.sleep(5)
    
    # Test 3: /finalize_purchase (10 per minute)
    print_header("Test 3: /finalize_purchase Endpoint")
    results['/finalize_purchase'] = test_endpoint(f"{BASE_URL}/finalize_purchase", 10, num_requests=12)
    
    # Summary
    print_header("TEST SUMMARY")
    
    all_passed = all(results.values())
    
    for endpoint, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {endpoint}")
    
    print(f"\n{'='*60}")
    if all_passed:
        print("  ✅ ALL TESTS PASSED - Rate limiting is working!")
    else:
        print("  ⚠️  Some tests did not show rate limiting")
        print("  Check configuration and server logs")
    print(f"{'='*60}\n")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
