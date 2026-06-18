#!/usr/bin/env python3
"""2FA Recovery - Generate backup codes or disable 2FA temporarily"""
import pyotp
from app import app, db
from models import Admin

def show_menu():
    print("\n=== 2FA RECOVERY OPTIONS ===")
    print("1. Generate Backup Codes (you can use these to login)")
    print("2. Temporarily Disable 2FA (to regain access)")
    print("3. Show Current Secret")
    choice = input("\nSelect option (1-3): ").strip()
    return choice

def generate_backup_codes():
    """Generate backup codes for users to login if they lose their authenticator"""
    with app.app_context():
        users = Admin.query.all()
        if not users:
            print("❌ No users found!")
            return
        
        for user in users:
            print(f"\n{'='*50}")
            print(f"User: {user.username}")
            print(f"2FA Status: {'Enabled' if user.two_fa_enabled else 'Disabled'}")
            
            if user.otp_secret:
                print(f"\n✅ Current Secret Key: {user.otp_secret}")
                print("\n📝 Backup Codes (save these securely):")
                for i in range(10):
                    code = f"BACKUP-{i+1:02d}-{pyotp.random_base32()[:8]}"
                    print(f"   {code}")
            else:
                print("⚠️  No 2FA secret set for this user!")

def disable_2fa_temporarily():
    """Disable 2FA to allow login"""
    with app.app_context():
        users = Admin.query.all()
        if not users:
            print("❌ No users found!")
            return
        
        confirm = input("\n⚠️  WARNING: This will DISABLE 2FA for all users!\nContinue? (yes/no): ").strip().lower()
        if confirm == 'yes':
            for user in users:
                print(f"\nDisabling 2FA for: {user.username}")
                user.two_fa_enabled = False
                db.session.commit()
            
            print("\n✅ 2FA has been DISABLED for all users!")
            print("You can now login without entering OTP codes")
            print("⚠️  Remember to re-enable 2FA after logging in!")
        else:
            print("❌ Cancelled")

def show_current_secret():
    """Display current 2FA secret without regenerating"""
    with app.app_context():
        users = Admin.query.all()
        if not users:
            print("❌ No users found!")
            return
        
        for user in users:
            print(f"\n{'='*50}")
            print(f"User: {user.username}")
            print(f"2FA Status: {'Enabled' if user.two_fa_enabled else 'Disabled'}")
            
            if user.otp_secret:
                print(f"Secret Key: {user.otp_secret}")
                
                # Generate QR code URL
                totp = pyotp.TOTP(user.otp_secret)
                provisioning_uri = totp.provisioning_uri(
                    name=user.username,
                    issuer_name='3G Design'
                )
                print(f"\n📱 QR Code URL:\n{provisioning_uri}")
                print(f"\n📖 Visit this site to generate QR code from the URL:")
                print("   https://www.qr-code-generator.com/")
            else:
                print("⚠️  No 2FA secret set!")

if __name__ == "__main__":
    choice = show_menu()
    
    if choice == '1':
        generate_backup_codes()
    elif choice == '2':
        disable_2fa_temporarily()
    elif choice == '3':
        show_current_secret()
    else:
        print("❌ Invalid option")

