from app import app
from models import db, Admin

def disable_2fa():
    with app.app_context():
        admin = Admin.query.filter_by(username='admin').first()
        if admin:
            admin.two_fa_enabled = False
            db.session.commit()
            print("2FA has been disabled for 'admin'.")
        else:
            print("Admin user not found.")

if __name__ == "__main__":
    disable_2fa()
