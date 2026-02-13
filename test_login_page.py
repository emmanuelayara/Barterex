"""
Quick test to verify login template renders without errors
"""
import sys
sys.path.insert(0, '.')

from app import app

with app.app_context():
    with app.test_client() as client:
        print("Testing login page...")
        try:
            response = client.get('/login')
            
            if response.status_code == 200:
                print(f"✅ Login page loaded successfully (HTTP {response.status_code})")
                
                # Check if the credential field is in the response
                if b'credential' in response.data:
                    print("✅ Credential field found in login form")
                else:
                    print("⚠️  Credential field NOT found in login form")
                
                if b'email' in response.data or b'username' in response.data:
                    print("✅ Email/username field found in form")
                else:
                    print("⚠️  Email/username field NOT found")
                    
            else:
                print(f"❌ Login page returned HTTP {response.status_code}")
                print(response.data.decode('utf-8', errors='ignore')[:500])
                
        except Exception as e:
            print(f"❌ Error testing login: {e}")
            import traceback
            traceback.print_exc()

print("\n✅ Test complete!")
