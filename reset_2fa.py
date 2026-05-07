#!/usr/bin/env python3
"""Reset 2FA - keeps 2FA enabled but generates new secret"""
import pyotp
from app import app, db
from models import Admin

with app.app_context():
    print("=== 2FA RESET ===\n")
    
    users = Admin.query.all()
    if not users:
        print("❌ No users found!")
    else:
        for user in users:
            print(f"User: {user.username}")
            print(f"Current 2FA Status: {'Enabled' if user.two_fa_enabled else 'Disabled'}")
            
            # Generate new secret
            new_secret = pyotp.random_base32()
            user.otp_secret = new_secret
            user.two_fa_enabled = True  # Keep 2FA enabled
            
            db.session.commit()
            
            # Show QR code provisioning URI
            totp = pyotp.TOTP(new_secret)
            provisioning_uri = totp.provisioning_uri(
                name=user.username,
                issuer_name='3G DESIGN'
            )
            
            print(f"\n✅ 2FA Reset Complete!")
            print(f"New Secret: {new_secret}")
            print(f"\n📱 Setup URL (for QR code): {provisioning_uri}")
            print(f"\n⚠️  Manual Entry Key: {new_secret}")
            print(f"\nNow visit: http://localhost:5001/setup-2fa to scan the QR code or enter the key manually")
            print("=" * 50)


