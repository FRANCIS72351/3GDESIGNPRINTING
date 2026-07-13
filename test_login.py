"""Login flow tests for admin and ghost recovery accounts."""
import os
import unittest

os.environ.setdefault('GHOST_ADMIN_USER', 'Francis_Architect')

from app import app, db, Admin  # noqa: E402


class LoginFlowTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.client.testing = True
        app.config['WTF_CSRF_ENABLED'] = False

    def test_admin_login_success_redirects_to_2fa_setup(self):
        with app.app_context():
            admin = Admin.query.filter_by(username='admin').first()
            if not admin:
                self.skipTest('admin account not present in database')

        response = self.client.post(
            '/login',
            data={'username': 'admin', 'password': 'Press2026!'},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/setup-2fa', response.location)

    def test_admin_wrong_password_uses_generic_error(self):
        response = self.client.post(
            '/login',
            data={'username': 'admin', 'password': 'definitely-wrong-password'},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid username or password', response.data)
        self.assertNotIn(b'ghost recovery account', response.data)

    def test_ghost_username_missing_uses_ghost_specific_error(self):
        ghost_username = os.getenv('GHOST_ADMIN_USER', 'ghost_admin')
        with app.app_context():
            if Admin.query.filter_by(username=ghost_username).first():
                self.skipTest('ghost account already exists')

        response = self.client.post(
            '/login',
            data={'username': ghost_username, 'password': 'wrong-password'},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Ghost recovery account not found', response.data)


if __name__ == '__main__':
    unittest.main()
