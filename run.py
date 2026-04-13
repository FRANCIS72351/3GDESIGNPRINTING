#!/usr/bin/env python3
"""
Production server runner for the Printing Shop application.
This script starts the application using the Waitress WSGI server.
"""

import os
import secrets
from app import app
from models import db, Admin
from werkzeug.security import generate_password_hash
import pyotp
# Import Waitress
from waitress import serve

if __name__ == '__main__':
    # Set default ghost user if not set
    if not os.getenv('GHOST_ADMIN_USER'):
        os.environ['GHOST_ADMIN_USER'] = 'ghost_admin'
    
    with app.app_context():
        # Ensure database tables exist
        db.create_all()
        
        # Create ghost admin if not exists
        ghost_username = os.getenv('GHOST_ADMIN_USER')
        if not Admin.query.filter_by(username=ghost_username).first():
            ghost_secret = pyotp.random_base32()
            ghost_recovery = ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(8))
            ghost_hashed_recovery = generate_password_hash(ghost_recovery, method='pbkdf2:sha256')
            
            ghost_password = 'Ghost2026!'  # Recovery password
            ghost_hashed_pw = generate_password_hash(ghost_password, method='pbkdf2:sha256')
            
            ghost_admin = Admin(
                username=ghost_username,
                password_hash=ghost_hashed_pw,
                email='ghost@system.local',
                otp_secret=ghost_secret,
                recovery_key=ghost_hashed_recovery,
                two_fa_enabled=True,
                role='admin'
            )
            db.session.add(ghost_admin)
            db.session.commit()
            
            print(f"Ghost Admin created: {ghost_username}")
            print(f"Password: {ghost_password}")
            print(f"TOTP secret: {ghost_secret}")
            print(f"Recovery code: {ghost_recovery}")
        
        # --- START OF YOUR ORIGINAL LOGIC ---
        # Create initial admin if not exists
        if not Admin.query.filter_by(username='admin').first():
            # Generate a unique TOTP secret
            secret = pyotp.random_base32()
            # Generate a recovery key (8-character uppercase alphanumeric)
            recovery_code = ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(8))
            hashed_recovery = generate_password_hash(recovery_code, method='pbkdf2:sha256')
            
            hashed_pw = generate_password_hash('Press2026!', method='pbkdf2:sha256')
            new_admin = Admin(
                username='admin', 
                password_hash=hashed_pw, 
                email='admin@press.com',
                otp_secret=secret,
                recovery_key=hashed_recovery,
                two_fa_enabled=True  # Will be enabled after setup
            )
            db.session.add(new_admin)
            db.session.commit()
            
            print(f"Admin created!")
            print(f"TOTP secret: {secret}")
            print(f"Recovery code: {recovery_code}")
            print("Please set up 2FA using the QR code at /setup-2fa")
            print("Save the recovery code in a safe place!")
        # --- END OF YOUR ORIGINAL LOGIC ---

    # WAITRESS REPLACEMENT FOR app.run()
    # This serves the app professionally on port 5000
    print("Starting Production Server with Waitress...")
    print("Server running on http://localhost:5001")
    
    serve(app, host='127.0.0.1', port=5001, threads=1)
    # app.run(debug=True, host='127.0.0.1', port=5001)