#!/usr/bin/env python3
"""Create a clean .env file with UTF-8 encoding"""

env_content = """# ⚠️ DO NOT COMMIT ACTUAL SECRETS TO THIS FILE
# This file is for reference only. Add your actual secrets to your .env file
# and make sure .env is in .gitignore

SECRET_KEY=your_secret_key_here
SQLALCHEMY_DATABASE_URI=sqlite:///barter.db
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_app_password_here
MAIL_DEFAULT_SENDER=Barter Express (Barterex),your_email@gmail.com
FLASK_ENV=development
OPENAI_API_KEY=your_openai_api_key_here
GOOGLE_API_KEY=your_google_api_key_here
GOOGLE_SEARCH_ENGINE_ID=your_search_engine_id_here
"""

# Write with UTF-8 encoding
with open('.env', 'w', encoding='utf-8') as f:
    f.write(env_content)

print("✓ .env file created with UTF-8 encoding")

# Verify it's readable
with open('.env', 'r', encoding='utf-8') as f:
    content = f.read()
    lines = content.strip().split('\n')
    print(f"✓ File has {len(lines)} lines")
    print("\nContent preview:")
    for line in lines[-3:]:
        if '=' in line:
            key, val = line.split('=', 1)
            if len(val) > 20:
                print(f"  {key}={val[:20]}...{val[-5:]}")
            else:
                print(f"  {key}={val}")
