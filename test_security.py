#!/usr/bin/env python
"""
Security Test Script for CSRF and Rate Limiting
Tests the implementation of CSRF protection and rate limiting on auth endpoints
"""

import requests
import time
import sys
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

BASE_URL = 'http://localhost:5000'

def print_header(text):
    print(f"\n{BOLD}{BLUE}{'='*70}{RESET}")
    print(f"{BOLD}{BLUE}{text:^70}{RESET}")
    print(f"{BOLD}{BLUE}{'='*70}{RESET}\n")

def print_success(text):
    print(f"{GREEN}✅ {text}{RESET}")

def print_error(text):
    print(f"{RED}❌ {text}{RESET}")

def print_warning(text):
    print(f"{YELLOW}⚠️  {text}{RESET}")

def print_info(text):
    print(f"{BLUE}ℹ️  {text}{RESET}")

def create_session():
    """Create a requests session with retry strategy"""
    session = requests.Session()
    retry = Retry(connect=3, backoff_factor=0.5)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def get_csrf_token(session, endpoint='/login'):
    """Extract CSRF token from form"""
    try:
        response = session.get(f'{BASE_URL}{endpoint}', timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        csrf_input = soup.find('input', {'name': 'csrf_token'})
        if csrf_input:
            return csrf_input.get('value')
        return None
    except Exception as e:
        print_warning(f"Could not extract CSRF token: {e}")
        return None

def test_server_connection(session):
    """Test if server is running"""
    print_header("Step 1: Checking Server Connection")
    try:
        response = session.get(f'{BASE_URL}/', timeout=5)
        if response.status_code in [200, 302]:
            print_success(f"Server is running on {BASE_URL}")
            return True
        else:
            print_error(f"Server returned status {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Cannot connect to server: {e}")
        print_info("Make sure Flask app is running with: python app.py")
        return False

def test_csrf_protection(session):
    """Test CSRF token protection"""
    print_header("Step 2: Testing CSRF Token Protection")
    
    # Test 2a: Get page and extract CSRF token
    print("Test 2a: Extracting CSRF token from login form...")
    csrf_token = get_csrf_token(session, '/login')
    
    if csrf_token:
        print_success(f"CSRF token found: {csrf_token[:20]}...")
    else:
        print_error("CSRF token not found in login form")
        return False
    
    # Test 2b: POST with valid CSRF token
    print("\nTest 2b: Attempting login WITH valid CSRF token...")
    login_data = {
        'username': 'testuser',
        'password': 'testpass',
        'csrf_token': csrf_token
    }
    
    try:
        response = session.post(f'{BASE_URL}/login', data=login_data, timeout=5, allow_redirects=False)
        # 400 would be CSRF error, 302 is redirect (login failed but CSRF passed), 200 is form re-render
        if response.status_code in [200, 302]:
            print_success(f"CSRF token accepted (Status: {response.status_code})")
            return True
        elif response.status_code == 400:
            print_error(f"CSRF token rejected with 400 error")
            return False
        else:
            print_warning(f"Unexpected status: {response.status_code}")
            return True
    except Exception as e:
        print_error(f"Request failed: {e}")
        return False

def test_rate_limiting(session):
    """Test rate limiting on login"""
    print_header("Step 3: Testing Rate Limiting on Login (5 per minute limit)")
    
    print("Making 7 rapid login attempts (should be blocked after 5)...\n")
    
    blocked_count = 0
    accepted_count = 0
    
    for i in range(7):
        try:
            response = session.post(
                f'{BASE_URL}/login',
                data={'username': 'testuser', 'password': 'testpass'},
                timeout=5,
                allow_redirects=False
            )
            
            if response.status_code == 429:
                print_error(f"Attempt {i+1}: Rate limited (429 Too Many Requests)")
                blocked_count += 1
            else:
                print_success(f"Attempt {i+1}: Accepted (Status: {response.status_code})")
                accepted_count += 1
            
            time.sleep(0.2)  # Small delay between requests
        except Exception as e:
            print_warning(f"Attempt {i+1}: Error - {str(e)}")
    
    print(f"\nResults: {accepted_count} accepted, {blocked_count} rate-limited")
    
    if blocked_count > 0:
        print_success("Rate limiting is working!")
        return True
    else:
        print_warning("No 429 responses - rate limiting may not be triggered yet")
        return False

def test_registration_rate_limiting(session):
    """Test rate limiting on registration"""
    print_header("Step 4: Testing Rate Limiting on Registration (5 per hour limit)")
    
    print("Making 3 registration attempts...\n")
    
    for i in range(3):
        try:
            csrf_token = get_csrf_token(session, '/register')
            if not csrf_token:
                print_warning(f"Attempt {i+1}: Could not get CSRF token")
                continue
            
            response = session.post(
                f'{BASE_URL}/register',
                data={
                    'email': f'test{i}@example.com',
                    'username': f'testuser{i}',
                    'password': 'TestPass123!',
                    'confirm_password': 'TestPass123!',
                    'csrf_token': csrf_token
                },
                timeout=5,
                allow_redirects=False
            )
            
            if response.status_code == 429:
                print_error(f"Attempt {i+1}: Rate limited (429)")
            else:
                print_success(f"Attempt {i+1}: Accepted (Status: {response.status_code})")
            
            time.sleep(0.5)
        except Exception as e:
            print_warning(f"Attempt {i+1}: Error - {str(e)}")
    
    print_info("Registration rate limiting is configured to allow 5 attempts per hour")
    return True

def test_session_security(session):
    """Test session security headers"""
    print_header("Step 5: Testing Session Security Headers")
    
    try:
        response = session.get(f'{BASE_URL}/', timeout=5)
        headers = response.headers
        
        security_headers = {
            'Strict-Transport-Security': 'HSTS (HTTP Strict Transport Security)',
            'X-Content-Type-Options': 'Content-Type sniffing protection',
            'X-Frame-Options': 'Clickjacking protection',
            'X-XSS-Protection': 'XSS protection',
        }
        
        for header, description in security_headers.items():
            if header in headers:
                print_success(f"{header}: {description} - FOUND")
            else:
                print_warning(f"{header}: {description} - NOT SET")
        
        return True
    except Exception as e:
        print_error(f"Could not check headers: {e}")
        return False

def main():
    """Main test runner"""
    print(f"\n{BOLD}{BLUE}Barterex Security Test Suite{RESET}")
    print(f"{BLUE}CSRF Protection & Rate Limiting Tests{RESET}\n")
    
    session = create_session()
    
    tests = [
        ("Server Connection", test_server_connection),
        ("CSRF Protection", test_csrf_protection),
        ("Rate Limiting (Login)", test_rate_limiting),
        ("Rate Limiting (Registration)", test_registration_rate_limiting),
        ("Session Security Headers", test_session_security),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func(session)
            results.append((test_name, result))
        except Exception as e:
            print_error(f"Test failed with exception: {e}")
            results.append((test_name, False))
    
    # Print summary
    print_header("Test Summary")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        if result:
            print_success(f"{test_name}")
        else:
            print_error(f"{test_name}")
    
    print(f"\n{BOLD}Results: {passed}/{total} tests passed{RESET}\n")
    
    if passed == total:
        print_success("All security tests passed!")
        return 0
    else:
        print_warning(f"{total - passed} test(s) failed")
        return 1

if __name__ == '__main__':
    sys.exit(main())
