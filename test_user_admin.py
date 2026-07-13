from werkzeug.security import check_password_hash

from app import app, db, Admin
from user_admin import sync_admin_account


def test_sync_admin_account_creates_admin_with_password():
    username = "copilot_test_user"
    password = "CopilotTest123!"

    with app.app_context():
        Admin.query.filter_by(username=username).delete()
        db.session.commit()

        sync_admin_account(username, password)

        admin = Admin.query.filter_by(username=username).first()

        assert admin is not None
        assert admin.role == "admin"
        assert check_password_hash(admin.password_hash, password)

        db.session.delete(admin)
        db.session.commit()
