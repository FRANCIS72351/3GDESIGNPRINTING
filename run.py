#!/usr/bin/env python3
"""
Production server runner for the Printing Shop application.
This script starts the application using the Waitress WSGI server.
"""

import os
import secrets
from app import app
from models import db, Admin, AboutContent, SystemSettings
from server_stability import ensure_system_settings, get_about_content
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
        ensure_system_settings(db, SystemSettings)
        get_about_content(db, AboutContent)

        ghost_username = os.getenv('GHOST_ADMIN_USER', 'ghost_admin').strip() or 'ghost_admin'
        ghost_by_email = Admin.query.filter_by(email='ghost@system.local').first()
        if ghost_by_email and ghost_by_email.username != ghost_username:
            ghost_by_email.username = ghost_username
            db.session.commit()
            print(f"Aligned ghost account username to {ghost_username}")
        
        # Seed default accounts only when the admin table is completely empty.
        if Admin.query.count() == 0:
            ghost_username = os.getenv('GHOST_ADMIN_USER')
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

            secret = pyotp.random_base32()
            recovery_code = ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(8))
            hashed_recovery = generate_password_hash(recovery_code, method='pbkdf2:sha256')
            hashed_pw = generate_password_hash('Press2026!', method='pbkdf2:sha256')
            new_admin = Admin(
                username='admin',
                password_hash=hashed_pw,
                email='admin@press.com',
                otp_secret=secret,
                recovery_key=hashed_recovery,
                two_fa_enabled=False  # Enabled only after /setup-2fa is completed
            )
            db.session.add(new_admin)
            db.session.commit()

            print(f"Ghost Admin created: {ghost_username}")
            print(f"Password: {ghost_password}")
            print(f"TOTP secret: {ghost_secret}")
            print(f"Recovery code: {ghost_recovery}")
            print("Admin created!")
            print(f"TOTP secret: {secret}")
            print(f"Recovery code: {recovery_code}")
            print("Please set up 2FA using the QR code at /setup-2fa")
            print("Save the recovery code in a safe place!")

    port = int(os.getenv('APP_PORT', '5001'))
    threads = int(os.getenv('WAITRESS_THREADS', '16'))
    connection_limit = int(os.getenv('WAITRESS_CONNECTION_LIMIT', '200'))
    channel_timeout = int(os.getenv('WAITRESS_CHANNEL_TIMEOUT', '120'))
    print("Starting Production Server with Waitress...")
    print(f"Bind address: 0.0.0.0:{port} (all interfaces, threads={threads})")
    print(f"Do not use http://0.0.0.0:{port}/ in your browser.")
    print(f"Open in browser: http://127.0.0.1:{port}/")
    print(f"Open in browser: http://localhost:{port}/")
    serve(
        app,
        host='0.0.0.0',
        port=port,
        threads=threads,
        channel_timeout=channel_timeout,
        connection_limit=connection_limit,
    )