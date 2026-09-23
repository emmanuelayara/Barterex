#!/usr/bin/env python
"""
CLI tool to create an Admin account (bootstrap / emergency use).

The public /admin/register web page has been removed for security reasons
(it let anyone on the internet create a full admin account). Use this
script from a trusted machine/server shell instead, or use the in-app
"Create Admin" page while already logged in as an existing admin.

Usage:
    python create_admin.py
    python create_admin.py --username jdoe --email jdoe@example.com
"""
import argparse
import getpass
import re
import sys

from app import app, db
from models import Admin
from werkzeug.security import generate_password_hash


def validate_password(password):
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if not re.search(r'[A-Z]', password):
        return "Password must contain an uppercase letter."
    if not re.search(r'[a-z]', password):
        return "Password must contain a lowercase letter."
    if not re.search(r'\d', password):
        return "Password must contain a number."
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>?/\\|`~]', password):
        return "Password must contain a special character."
    return None


def main():
    parser = argparse.ArgumentParser(description="Create a Barterex admin account")
    parser.add_argument('--username')
    parser.add_argument('--email')
    args = parser.parse_args()

    username = args.username or input("Username: ").strip()
    email = args.email or input("Email: ").strip()

    if not username or not email:
        print("Username and email are required.")
        sys.exit(1)

    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.")
        sys.exit(1)

    error = validate_password(password)
    if error:
        print(f"Weak password: {error}")
        sys.exit(1)

    with app.app_context():
        if Admin.query.filter_by(email=email).first():
            print(f"An admin with email {email} already exists.")
            sys.exit(1)
        if Admin.query.filter_by(username=username).first():
            print(f"An admin with username {username} already exists.")
            sys.exit(1)

        admin = Admin(
            username=username,
            email=email,
            password=generate_password_hash(password)
        )
        db.session.add(admin)
        db.session.commit()
        print(f"Admin '{username}' created successfully.")


if __name__ == '__main__':
    main()
