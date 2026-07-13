import getpass
from werkzeug.security import generate_password_hash

from app import db, User, Admin


def sync_admin_account(username, password):
    username = username.strip()
    password = password.strip()

    if not username:
        raise ValueError("Username cannot be empty.")
    if not password:
        raise ValueError("Password cannot be empty.")

    admin = Admin.query.filter((Admin.username == username) | (Admin.email == username)).first()
    if admin:
        admin.username = username
        admin.role = 'admin'
        admin.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        admin.two_fa_enabled = False
        admin.otp_secret = None
    else:
        admin = Admin(
            username=username,
            role='admin',
            password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
            two_fa_enabled=False,
            otp_secret=None,
        )
        db.session.add(admin)

    user = User.query.filter_by(username=username).first()
    if user:
        user.role = 'admin'
        user.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    else:
        user = User(username=username, role='admin')
        user.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        db.session.add(user)

    db.session.commit()
    return admin


def promote_to_admin():
    print("--- Advanced Admin Management Tool ---")
    username = input("Enter the username to promote: ").strip()
    password = getpass.getpass(f"Enter new password for {username}: ")

    if not username:
        print("Error: Username cannot be empty.")
        return

    try:
        sync_admin_account(username, password)
        print(f"✅ SUCCESS: Administrator account synchronized for '{username}'.")
    except Exception as e:
        db.session.rollback()
        print(f"❌ DATABASE ERROR: {e}")


if __name__ == "__main__":
    from app import app
    with app.app_context():
        promote_to_admin()