from app import app, db, Admin
from werkzeug.security import check_password_hash
from flask import Flask
import os

# Test the login logic directly
with app.app_context():
    print("Testing login logic...")

    # Test credentials
    test_username = 'admin'
    test_password = 'Press2026!'

    print(f"Testing with username: '{test_username}', password: '{test_password}'")

    # Find admin in database by username OR email (same logic as login route)
    admin = Admin.query.filter((Admin.username == test_username) | (Admin.email == test_username)).first()

    if admin:
        print(f"✓ Admin found: {admin.username}")
        print(f"  Email: {admin.email}")
        print(f"  2FA enabled: {admin.two_fa_enabled}")

        # Verify password hash
        if check_password_hash(admin.password_hash, test_password):
            print("✓ Password verification successful!")
            print("✓ Login should work - the issue might be with the web interface or session")
        else:
            print("✗ Password verification failed!")
    else:
        print("✗ Admin not found!")

    print("\nAvailable admin users:")
    all_admins = Admin.query.all()
    for a in all_admins:
        print(f"  - Username: '{a.username}', Email: '{a.email}'")