#!/usr/bin/env python3
"""
Ghost User Master Recovery Script
This script allows recovery of the ghost user's password and username using a master recovery key.
Only use this in emergency situations when the ghost user loses access.
"""

import os
import secrets
import getpass
from difflib import get_close_matches
from app import app, db
from models import Admin
from werkzeug.security import generate_password_hash
import pyotp

# Master recovery key - SET THIS AS ENVIRONMENT VARIABLE!
# DO NOT hardcode in production!
MASTER_RECOVERY_KEY = os.getenv('GHOST_MASTER_RECOVERY_KEY', 'GHOST_MASTER_2026_RECOVERY_KEY')


def resolve_target_account(requested_username, available_usernames, default_username='ghost_admin'):
    """Resolve the requested username to the closest existing admin account."""
    if not requested_username:
        return default_username

    exact_match = next((name for name in available_usernames if name == requested_username), None)
    if exact_match:
        return exact_match

    normalized_requested = requested_username.strip().lower()
    normalized_available = [name.lower() for name in available_usernames]

    if normalized_requested in normalized_available:
        return available_usernames[normalized_available.index(normalized_requested)]

    close_matches = get_close_matches(normalized_requested, normalized_available, n=1, cutoff=0.6)
    if close_matches:
        return available_usernames[normalized_available.index(close_matches[0])]

    return None


def reset_ghost_account():
    """Reset the ghost user's username, password, and 2FA credentials using a master key"""
    
    # Check if master key is configured
    if not MASTER_RECOVERY_KEY:
        print("❌ Error: GHOST_MASTER_RECOVERY_KEY environment variable is not configured.")
        print("Please export the environment variable and rerun the utility.")
        return False

    using_default_key = MASTER_RECOVERY_KEY == 'GHOST_MASTER_2026_RECOVERY_KEY'
    if using_default_key:
        print("⚠️  Warning: Operating with the built-in fallback recovery key.")
        print("⚠️  This configuration is strictly intended for local debugging or emergency rescue.")
        print("⚠️  Do not use the default fallback key in an active production environment.")
        print()

    # Mask input for the security key
    master_key = getpass.getpass("Enter master recovery key: ").strip()
    if master_key != MASTER_RECOVERY_KEY:
        print("❌ Authentication failed: Invalid master recovery key.")
        return False

    # Collect targeting information
    default_username = os.getenv('GHOST_ADMIN_USER', 'ghost_admin')
    ghost_username = input(f"Target ghost account to reset [{default_username}]: ").strip() or default_username

    with app.app_context():
        existing_usernames = [admin.username for admin in Admin.query.all() if admin.username]
        resolved_username = resolve_target_account(ghost_username, existing_usernames, default_username)

        if not resolved_username:
            print(f"❌ Error: Target account '{ghost_username}' was not found in the database directory.")
            print("Available accounts: " + (", ".join(existing_usernames) if existing_usernames else "<none>"))
            return False

        if resolved_username != ghost_username:
            print(f"⚠️  Resolved target '{ghost_username}' to existing account '{resolved_username}'.")
            ghost_username = resolved_username

    new_username = input(f"Enter new username (Leave blank to preserve '{ghost_username}'): ").strip() or ghost_username

    # Handle credential generation
    new_password = None
    while True:
        new_password = getpass.getpass("New password (Leave blank to auto-generate): ").strip()
        if not new_password:
            new_password = secrets.token_urlsafe(16)
            print("🎲 Generated secure, randomized password.")
            break

        confirm_password = getpass.getpass("Confirm new password: ").strip()
        if confirm_password == new_password:
            break

        print("❌ Input mismatch: Passwords do not match. Please re-enter.")

    with app.app_context():
        ghost_user = Admin.query.filter_by(username=ghost_username).first()
        if not ghost_user:
            print(f"❌ Error: Target account '{ghost_username}' was not found in the database directory.")
            return False

        # Generate fresh independent security keys
        new_secret = pyotp.random_base32()
        new_recovery = ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(8))

        try:
            # Commit mutations securely to the target model instance
            ghost_user.username = new_username
            ghost_user.password_hash = generate_password_hash(new_password)
            ghost_user.otp_secret = new_secret
            ghost_user.recovery_key = generate_password_hash(new_recovery)
            ghost_user.two_fa_enabled = True
            ghost_user.failed_2fa_count = 0
            ghost_user.last_attempt_time = 0.0

            db.session.commit()

            print("\n" + "=" * 50)
            print("   ✅ GHOST ACCOUNT SECURITY AUDIT RECOVERY SUCCESSFUL")
            print("=" * 50)
            print(f"Target Identifier: {ghost_username}")
            print(f"Updated Username : {new_username}")
            print(f"New Clear Password: {new_password}")
            print(f"New TOTP Secret Key: {new_secret}")
            print(f"New Recovery Seed  : {new_recovery}")
            print("=" * 50)
            print("\n⚠️  CRITICAL INFRASTRUCTURE WARNING:")
            print("• Extract and record these credentials immediately.")
            print("• Store secrets inside an encrypted vault or password manager.")
            print("• This terminal buffer should be cleared once documented.")
            return True

        except Exception as e:
            db.session.rollback()
            print(f"❌ Critical Database Error: Committing changes failed. {str(e)}")
            return False

if __name__ == "__main__":
    print("🛡️  GHOST ACCOUNT IDENTITY & ACCESS ACCESS MANAGEMENT UTILITY")
    print("This administrative utility forcefully resets core application keys, usernames, and MFA profiles.")
    print()
    
    confirm = input("Are you sure you want to proceed? Type 'YES' to confirm execution: ").strip()
    if confirm.upper() == 'YES':
        success = reset_ghost_account()
        if success:
            print("\n✅ Task lifecycle finished successfully.")
        else:
            print("\n❌ Task terminated prematurely with errors.")
    else:
        print("❌ Process aborted by operator.")