#!/usr/bin/env python3
"""
Production server runner for the Printing Shop application.
This script starts the application using the Waitress WSGI server.
"""

import os
import secrets
from wsgi import app
from models import db, Admin
from werkzeug.security import generate_password_hash
import pyotp
# Import Waitress
from waitress import serve

if __name__ == '__main__':
    with app.app_context():
        # Ensure database tables exist
        db.create_all()
        
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
    
    serve(app, host='0.0.0.0', port=5001, threads=4)