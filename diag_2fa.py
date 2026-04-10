import pyotp
import time
from datetime import datetime
from app import app, db
from models import Admin

with app.app_context():
    print("--- 2FA DIAGNOSTICS ---")
    print(f"Current Server Time (Local): {datetime.now()}")
    print(f"Current Server Time (UTC):   {datetime.utcnow()}")
    print(f"Timestamp (pyotp base):      {time.time()}")
    
    users = Admin.query.all()
    for user in users:
        print(f"\nUser: {user.username}")
        print(f" - 2FA Enabled: {user.two_fa_enabled}")
        print(f" - OTP Secret:  {user.otp_secret}")
        if user.otp_secret:
            totp = pyotp.TOTP(user.otp_secret)
            print(f" - Current Code: {totp.now()}")
            print(f" - Next Code in: {30 - time.time() % 30:.1f}s")
    print("\n--- END DIAGNOSTICS ---")
