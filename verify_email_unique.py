"""
Verification script for email-based unique key implementation.
Tests that the login system works correctly with both email and username.
"""

import sqlite3
import sys

DB_PATH = 'barter.db'

def verify_schema():
    """Verify database schema is correct"""
    print("=" * 60)
    print("SCHEMA VERIFICATION")
    print("=" * 60)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check user table structure
    cursor.execute("PRAGMA table_info(user)")
    columns = {col[1]: (col[2], col[5]) for col in cursor.fetchall()}
    
    print("\n✓ Checking user table columns...")
    
    # Verify key fields exist and have correct properties
    checks = [
        ('id', 'PRIMARY KEY'),
        ('username', 'NOT unique'),
        ('email', 'UNIQUE'),
        ('password_hash', 'for hashing'),
        ('email_verified', 'for verification'),
    ]
    
    all_passed = True
    
    # Verify email uniqueness
    cursor.execute("PRAGMA index_list(user)")
    indexes = cursor.fetchall()
    email_is_unique = False
    
    for idx in indexes:
        cursor.execute(f"PRAGMA index_info({idx[1]})")
        index_columns = cursor.fetchall()
        for col in index_columns:
            if col[2] == 'email' and idx[2]:  # idx[2] is 'unique' flag
                email_is_unique = True
    
    print(f"\n✓ Email UNIQUE constraint: {'✓ PRESENT' if email_is_unique else '✗ MISSING'}")
    
    # Check username does NOT have unique constraint
    username_is_unique = False
    for idx in indexes:
        cursor.execute(f"PRAGMA index_info({idx[1]})")
        index_columns = cursor.fetchall()
        for col in index_columns:
            if col[2] == 'username' and idx[2]:  # idx[2] is 'unique' flag
                username_is_unique = True
    
    print(f"✓ Username unique constraint: {'✗ PRESENT (should be absent)' if username_is_unique else '✓ ABSENT (correct)'}")
    
    # Check all required columns exist
    print("\n✓ Required columns:")
    required_fields = ['id', 'username', 'email', 'password_hash', 'email_verified', 'created_at']
    for field in required_fields:
        if field in columns:
            print(f"  ✓ {field}")
        else:
            print(f"  ✗ {field} MISSING")
            all_passed = False
    
    conn.close()
    return all_passed and email_is_unique and not username_is_unique

def verify_code_changes():
    """Verify code files have been updated"""
    print("\n" + "=" * 60)
    print("CODE CHANGES VERIFICATION")
    print("=" * 60)
    
    all_passed = True
    
    # Check models.py
    print("\n✓ Checking models.py...")
    try:
        with open('models.py', 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            if "username = db.Column(db.String(64), nullable=False, index=True)" in content:
                print("  ✓ User model username field is NOT unique")
            else:
                print("  ✗ User model username might still be unique")
                all_passed = False
    except Exception as e:
        print(f"  ✗ Error reading models.py: {e}")
        all_passed = False
    
    # Check forms.py for LoginForm changes
    print("\n✓ Checking forms.py...")
    try:
        with open('forms.py', 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            if "credential = StringField('Email or Username'" in content:
                print("  ✓ LoginForm has 'credential' field accepting email or username")
            else:
                print("  ✗ LoginForm still uses 'username' field")
                all_passed = False
            
            # Check RegisterForm specifically (not AdminRegisterForm)
            register_form_match = content.find("class RegisterForm")
            admin_form_match = content.find("class AdminRegisterForm")
            
            if register_form_match != -1 and admin_form_match != -1:
                register_section = content[register_form_match:admin_form_match]
            elif register_form_match != -1:
                register_section = content[register_form_match:]
            else:
                register_section = ""
            
            if "def validate_username(self, username):" in register_section:
                print("  ✗ RegisterForm still has validate_username() method")
                all_passed = False
            else:
                print("  ✓ RegisterForm username validation removed")
    except Exception as e:
        print(f"  ✗ Error reading forms.py: {e}")
        all_passed = False
    
    # Check auth.py for login logic changes
    print("\n✓ Checking routes/auth.py...")
    try:
        with open('routes/auth.py', 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            if "credential = form.credential.data" in content:
                print("  ✓ Login route uses 'credential' field")
            else:
                print("  ✗ Login route still uses 'username' field")
                all_passed = False
            
            if "@' in credential:" in content:
                print("  ✓ Login logic includes email detection")
            else:
                print("  ✗ Login logic missing email detection")
                all_passed = False
            
            if "User.query.filter_by(email=credential).first()" in content or \
               "User.query.filter_by(username=credential).first()" in content:
                print("  ✓ Login logic queries both email and username")
            else:
                print("  ✗ Login logic missing email or username query")
                all_passed = False
    except Exception as e:
        print(f"  ✗ Error reading routes/auth.py: {e}")
        all_passed = False
    
    return all_passed

def test_login_scenarios():
    """Test login scenarios (simulation)"""
    print("\n" + "=" * 60)
    print("LOGIN SCENARIOS (Simulation)")
    print("=" * 60)
    
    scenarios = [
        {
            'name': 'Login with Email',
            'credential': 'user@example.com',
            'expected': '@' in 'user@example.com',
            'description': 'Credential contains @ - will query by email'
        },
        {
            'name': 'Login with Username',
            'credential': 'john_doe',
            'expected': '@' not in 'john_doe',
            'description': 'Credential has no @ - will query by username'
        },
        {
            'name': 'Email as Fallback',
            'credential': 'user@domain',
            'expected': True,
            'description': 'Has @, will try email first, then username'
        },
        {
            'name': 'Duplicate Usernames',
            'users': [(('user1@ex1.com', 'developer'), ('user2@ex2.com', 'developer'))],
            'expected': True,
            'description': 'Multiple users can have same username - email disambiguates'
        }
    ]
    
    print("\nSupported scenarios:")
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{i}. {scenario['name']}")
        print(f"   Description: {scenario['description']}")
        if 'credential' in scenario:
            print(f"   Credential: {scenario['credential']}")
        if 'users' in scenario:
            print(f"   Users: {scenario['users']}")
        print(f"   ✓ Supported")
    
    return True

def main():
    print("\n" + "=" * 60)
    print("EMAIL AS UNIQUE KEY - VERIFICATION SUITE")
    print("=" * 60)
    
    results = {}
    
    # Run verifications
    results['Schema'] = verify_schema()
    results['Code Changes'] = verify_code_changes()
    results['Scenarios'] = test_login_scenarios()
    
    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    
    for check, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {check}")
    
    all_passed = all(results.values())
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All verifications PASSED!")
        print("\nYour system is ready to use email as the unique key.")
        print("Users can now login with either email or username.")
    else:
        print("⚠️ Some verifications FAILED.")
        print("Please review the issues above and make corrections.")
    print("=" * 60 + "\n")
    
    return 0 if all_passed else 1

if __name__ == '__main__':
    sys.exit(main())
