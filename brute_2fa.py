import pyotp
import time
from app import app, db
from models import Admin

def find_offset(target_token, secret):
    totp = pyotp.TOTP(secret)
    now = int(time.time())
    # Search +/- 10 days (in 30s intervals)
    search_range = 10 * 24 * 60 * 2 # 10 days * 24 hours * 60 mins / 0.5 mins
    print(f"Searching for token {target_token}...")
    for i in range(-search_range, search_range):
        check_time = now + (i * 30)
        if totp.at(check_time) == target_token:
            offset_seconds = i * 30
            days = offset_seconds / (24 * 3600)
            return offset_seconds, days
    return None, None

with app.app_context():
    # From logs: Francis_Architect, Token: 498227
    secret = "KXBH742NFHCU6QKBYHAPYAYOOFXZ6SDI" # From my diag script
    token = "498227"
    
    offset, days = find_offset(token, secret)
    if offset:
        print(f"FOUND! Offset: {offset} seconds ({days:.2f} days)")
    else:
        print("Not found in 10 day range.")
