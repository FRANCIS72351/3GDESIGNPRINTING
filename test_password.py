from app import app, db, Admin
from werkzeug.security import check_password_hash

with app.app_context():
    admin = Admin.query.filter_by(username='admin').first()
    if admin:
        print(f'Username: {admin.username}')
        print(f'Email: {admin.email}')
        print(f'2FA Enabled: {admin.two_fa_enabled}')
        print(f'OTP Secret exists: {bool(admin.otp_secret)}')

        # Test the default password
        test_password = 'Press2026!'
        is_correct = check_password_hash(admin.password_hash, test_password)
        print(f'Default password "Press2026!" is correct: {is_correct}')

        # Test common passwords
        common_passwords = ['admin', 'password', '123456', 'admin123', 'Francis2026']
        for pwd in common_passwords:
            if check_password_hash(admin.password_hash, pwd):
                print(f'Password "{pwd}" is correct!')
                break
        else:
            print('None of the common passwords worked')
    else:
        print('Admin user not found!')