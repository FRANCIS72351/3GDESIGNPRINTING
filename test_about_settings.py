"""About settings routes survive legacy about_content schema."""
import os
import tempfile
import unittest

from sqlalchemy import text

from werkzeug.security import generate_password_hash

os.environ.setdefault('GHOST_ADMIN_USER', 'ghost_test_user')

from app import app, db
from models import AboutContent, Admin
from server_stability import get_about_content


class AboutSettingsTests(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{self.db_path}'
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

        with app.app_context():
            db.engine.dispose()
            db.create_all()
            admin = Admin(
                id=1,
                username='test_admin',
                password_hash=generate_password_hash('adminpass', method='pbkdf2:sha256'),
                role='admin',
            )
            db.session.add(admin)
            db.session.commit()

        self.admin_id = 1

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def _login_as_admin(self):
        with self.client.session_transaction() as sess:
            sess['admin_logged_in'] = True
            sess['admin_id'] = self.admin_id
            sess['role'] = 'admin'
            sess['username'] = 'test_admin'

    def _create_legacy_about_table(self):
        with app.app_context():
            db.session.execute(text('DROP TABLE IF EXISTS about_content'))
            db.session.commit()
            db.session.execute(text('''
                CREATE TABLE about_content (
                    id INTEGER PRIMARY KEY,
                    description TEXT,
                    services TEXT,
                    slider1 VARCHAR(100) DEFAULT 'slider.1.jpg',
                    slider2 VARCHAR(100) DEFAULT 'slider.2.jpg',
                    slider3 VARCHAR(100) DEFAULT 'slider.3.jpg'
                )
            '''))
            db.session.commit()

    def test_admin_can_open_about_settings(self):
        self._login_as_admin()
        resp = self.client.get('/admin/about-settings')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'About Page Settings', resp.data)

    def test_missing_about_table_is_created_on_get(self):
        with app.app_context():
            db.session.execute(text('DROP TABLE IF EXISTS about_content'))
            db.session.commit()
        self._login_as_admin()
        resp = self.client.get('/admin/about-settings')
        self.assertEqual(resp.status_code, 200)
        with app.app_context():
            row = db.session.execute(text('PRAGMA table_info(about_content)')).fetchall()
            columns = {item[1] for item in row}
            self.assertIn('ad_title', columns)
            self.assertIn('ad_description', columns)
            self.assertIn('ad_video_file', columns)

    def test_legacy_schema_is_migrated_on_get(self):
        self._create_legacy_about_table()
        self._login_as_admin()
        resp = self.client.get('/admin/about-settings')
        self.assertEqual(resp.status_code, 200)
        with app.app_context():
            row = db.session.execute(text('PRAGMA table_info(about_content)')).fetchall()
            columns = {item[1] for item in row}
            self.assertIn('ad_title', columns)
            self.assertIn('ad_description', columns)
            self.assertIn('ad_video_file', columns)

    def test_admin_can_post_about_settings(self):
        self._login_as_admin()
        resp = self.client.post('/admin/about-settings', data={
            'description': 'Updated about copy',
            'service': 'Banners, shirts, signs',
            'ad_title': 'Spring promo',
            'ad_description': 'Limited offer',
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with app.app_context():
            content = get_about_content(db, AboutContent)
            self.assertEqual(content.description, 'Updated about copy')
            self.assertEqual(content.services, 'Banners, shirts, signs')
            self.assertEqual(content.ad_title, 'Spring promo')
            self.assertEqual(content.ad_description, 'Limited offer')

    def test_public_about_page_survives_legacy_schema(self):
        self._create_legacy_about_table()
        resp = self.client.get('/about')
        self.assertEqual(resp.status_code, 200)


if __name__ == '__main__':
    unittest.main()
