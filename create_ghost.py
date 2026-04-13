#!/usr/bin/env python3
"""Create Ghost Admin User"""
import os
import secrets
from app import app, db
from models import Admin
from werkzeug.security import generate_password_hash
import pyotp

# Set default ghost user
if not os.getenv('GHOST_ADMIN_USER'):
    os.environ['GHOST_ADMIN_USER'] = 'ghost_admin'

with app.app_context():
    ghost_username = os.getenv('GHOST_ADMIN_USER', 'ghost_admin')
    
    ghost_user = Admin.query.filter_by(username=ghost_username).first()
    if ghost_user:
        print(f"Ghost admin '{ghost_username}' already exists! Resetting password...")
    else:
        print(f"Creating ghost admin '{ghost_username}'...")
        ghost_user = Admin(username=ghost_username, role='admin')
        db.session.add(ghost_user)
    
    # Reset password and 2FA
    ghost_secret = pyotp.random_base32()
    ghost_recovery = ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(8))
    ghost_hashed_recovery = generate_password_hash(ghost_recovery, method='pbkdf2:sha256')
    
    ghost_password = 'Ghost2026!'  # Recovery password
    ghost_hashed_pw = generate_password_hash(ghost_password, method='pbkdf2:sha256')
    
    ghost_user.password_hash = ghost_hashed_pw
    ghost_user.email = 'ghost@system.local'
    ghost_user.otp_secret = ghost_secret
    ghost_user.recovery_key = ghost_hashed_recovery
    ghost_user.two_fa_enabled = True
    ghost_user.role = 'admin'
    
    db.session.commit()
    
    print("✅ Ghost Admin Setup Complete!")
    print(f"Username: {ghost_username}")
    print(f"Password: {ghost_password}")
    print(f"TOTP Secret: {ghost_secret}")
    print(f"Recovery Code: {ghost_recovery}")
    print("\n⚠️  SAVE THIS PASSWORD SECURELY!")
    print("The ghost admin can reset any user's password in Team Management.")
    print("\n🚨 EMERGENCY RECOVERY:")
    print("If you lose the ghost password, run: python ghost_master_recovery.py")
    print("Set environment variable: GHOST_MASTER_RECOVERY_KEY=your_secure_key_here")
    print("Then run the script and enter your secure key when prompted.")