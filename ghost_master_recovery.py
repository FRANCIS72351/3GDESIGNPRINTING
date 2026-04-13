#!/usr/bin/env python3
"""
Ghost User Master Recovery Script
This script allows recovery of the ghost user's password using a master recovery key.
Only use this in emergency situations when the ghost user loses access.
"""

import os
import secrets
from app import app, db
from models import Admin
from werkzeug.security import generate_password_hash
import pyotp

# Master recovery key - SET THIS AS ENVIRONMENT VARIABLE!
# DO NOT hardcode in production!
MASTER_RECOVERY_KEY = os.getenv('GHOST_MASTER_RECOVERY_KEY', 'GHOST_MASTER_2026_RECOVERY_KEY')

def reset_ghost_password():
    """Reset the ghost user's password using master key"""
    # Check if master key is set
    if not MASTER_RECOVERY_KEY or MASTER_RECOVERY_KEY == 'GHOST_MASTER_2026_RECOVERY_KEY':
        print("❌ Master recovery key not properly configured!")
        print("Set environment variable: export GHOST_MASTER_RECOVERY_KEY=your_secure_key")
        print("⚠️  NEVER use the default key in production!")
        return False
    
    master_key = input("Enter Master Recovery Key: ").strip()
    
    if master_key != MASTER_RECOVERY_KEY:
        print("❌ Invalid master recovery key!")
        return False
    
    ghost_username = os.getenv('GHOST_ADMIN_USER', 'ghost_admin')
    
    with app.app_context():
        ghost_user = Admin.query.filter_by(username=ghost_username).first()
        
        if not ghost_user:
            print(f"❌ Ghost user '{ghost_username}' not found!")
            return False
        
        # Generate new password and 2FA
        new_password = secrets.token_urlsafe(16)
        new_secret = pyotp.random_base32()
        new_recovery = ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(8))
        
        ghost_user.password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
        ghost_user.otp_secret = new_secret
        ghost_user.recovery_key = generate_password_hash(new_recovery, method='pbkdf2:sha256')
        ghost_user.two_fa_enabled = True
        ghost_user.failed_2fa_count = 0
        ghost_user.last_attempt_time = 0.0
        
        db.session.commit()
        
        print("✅ GHOST USER PASSWORD RESET SUCCESSFUL!")
        print("=" * 50)
        print(f"Username: {ghost_username}")
        print(f"NEW Password: {new_password}")
        print(f"NEW TOTP Secret: {new_secret}")
        print(f"NEW Recovery Code: {new_recovery}")
        print("=" * 50)
        print("\n⚠️  CRITICAL: Save this information immediately!")
        print("🔒 Store the master recovery key securely: NEVER share it!")
        print("📧 Consider emailing this to yourself or saving in encrypted storage")
        print("\nNext steps:")
        print("1. Login with the new password")
        print("2. Setup 2FA with the new secret")
        print("3. Change password to something memorable")
        print("4. Update your recovery codes")
        
        return True

if __name__ == "__main__":
    print("🔐 GHOST USER MASTER RECOVERY")
    print("This will reset the ghost user's password and 2FA")
    print("Only use this if the ghost user has lost all access!")
    print()
    
    confirm = input("Are you sure you want to proceed? (type 'YES' to continue): ").strip()
    if confirm == 'YES':
        success = reset_ghost_password()
        if success:
            print("\n✅ Recovery completed successfully!")
        else:
            print("\n❌ Recovery failed!")
    else:
        print("❌ Recovery cancelled.")