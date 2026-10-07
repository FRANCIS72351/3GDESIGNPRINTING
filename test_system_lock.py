"""Ghost recovery must reach 2FA and unlock the site while CORE LOCKED."""
import os
import tempfile
import unittest

import pyotp
from werkzeug.security import generate_password_hash

os.environ.setdefault('GHOST_ADMIN_USER', 'ghost_test_user')

from app import app, db, is_system_lock_exempt_path
from models import Admin, SystemSettings
from server_stability import invalidate_settings_cache


class SystemLockGhostRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{self.db_path}'
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        self.totp_secret = pyotp.random_base32()

        with app.app_context():
            db.create_all()
            ghost = Admin(
                username='ghost_test_user',
                password_hash=generate_password_hash('GhostUnlock!'),
                email='ghost@system.local',
                role='admin',
                otp_secret=self.totp_secret,
                two_fa_enabled=True,
                recovery_key=generate_password_hash('UNLOCK12'),
            )
            db.session.add(ghost)
            db.session.add(SystemSettings(
                is_active=False,
                lock_message='System Maintenance: Please contact the Architect.',
            ))
            db.session.commit()
            invalidate_settings_cache()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()
        os.close(self.db_fd)
        os.unlink(self.db_path)
        invalidate_settings_cache()

    def test_unlock_paths_are_exempt(self):
        self.assertTrue(is_system_lock_exempt_path('/login'))
        self.assertTrue(is_system_lock_exempt_path('/verify-2fa'))
        self.assertTrue(is_system_lock_exempt_path('/verify-2fa-setup'))
        self.assertTrue(is_system_lock_exempt_path('/setup-2fa'))
        self.assertTrue(is_system_lock_exempt_path('/setup-2fa/reset'))
        self.assertTrue(is_system_lock_exempt_path('/login/recovery'))
        self.assertTrue(is_system_lock_exempt_path('/logout'))
        self.assertTrue(is_system_lock_exempt_path('/ghost-protocol/dashboard'))
        self.assertFalse(is_system_lock_exempt_path('/'))
        self.assertFalse(is_system_lock_exempt_path('/dashboard'))

    def test_public_site_shows_lock_screen(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 403)
        self.assertIn(b'Core Locked', resp.data)
        self.assertIn(b'Architect sign-in', resp.data)

    def test_ghost_login_reaches_2fa_while_locked(self):
        login = self.client.post(
            '/login',
            data={'username': 'ghost_test_user', 'password': 'GhostUnlock!'},
            follow_redirects=False,
        )
        self.assertEqual(login.status_code, 302)
        self.assertIn('/verify-2fa', login.location)

        verify_page = self.client.get('/verify-2fa')
        self.assertEqual(verify_page.status_code, 200)
        self.assertNotIn(b'Core Locked', verify_page.data)
        self.assertIn(b'Two-Factor Authentication', verify_page.data)

    def test_ghost_2fa_opens_overwatch_and_can_unlock(self):
        self.client.post(
            '/login',
            data={'username': 'ghost_test_user', 'password': 'GhostUnlock!'},
        )
        token = pyotp.TOTP(self.totp_secret).now()
        verify = self.client.post(
            '/verify-2fa',
            data={'token': token},
            follow_redirects=False,
        )
        self.assertEqual(verify.status_code, 302)
        self.assertIn('/ghost-protocol/', verify.location)

        dashboard = self.client.get('/ghost-protocol/dashboard')
        self.assertEqual(dashboard.status_code, 200)
        self.assertNotIn(b'Core Locked', dashboard.data)

        activate = self.client.post('/ghost-protocol/activate', follow_redirects=True)
        self.assertEqual(activate.status_code, 200)
        home = self.client.get('/')
        self.assertEqual(home.status_code, 200)
        self.assertNotIn(b'Core Locked', home.data)


if __name__ == '__main__':
    unittest.main()
