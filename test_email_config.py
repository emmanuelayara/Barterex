#!/usr/bin/env python
"""Test email configuration"""
from app import app

with app.app_context():
    config = app.config
    print("\n=== EMAIL CONFIGURATION ===\n")
    print(f"Mail Server: {config.get('MAIL_SERVER')}")
    print(f"Mail Port: {config.get('MAIL_PORT')}")
    print(f"Use TLS: {config.get('MAIL_USE_TLS')}")
    print(f"Use SSL: {config.get('MAIL_USE_SSL')}")
    print(f"Username: {config.get('MAIL_USERNAME')}")
    print(f"Default Sender: {config.get('MAIL_DEFAULT_SENDER')}")
    print(f"\n✅ Configuration loaded successfully")
    
    # Test sending a test email
    print("\n=== TESTING EMAIL SEND ===\n")
    try:
        from flask_mail import Message, Mail
        mail = Mail(app)
        
        msg = Message(
            subject="Barterex Test Email",
            sender=config.get('MAIL_DEFAULT_SENDER'),
            recipients=['ayaraemmanuel16@gmail.com']
        )
        msg.html = "<h1>Test Email</h1><p>This is a test email from Barterex.</p>"
        
        print("Attempting to send test email...")
        mail.send(msg)
        print("✅ Test email sent successfully!")
        
    except Exception as e:
        print(f"❌ Error sending test email: {e}")
        import traceback
        traceback.print_exc()
