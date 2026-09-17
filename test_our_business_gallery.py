"""Our Business gallery page, navbar link, and admin photo uploads."""
import io
import os
import tempfile
import unittest

from PIL import Image
from werkzeug.security import generate_password_hash

os.environ.setdefault('GHOST_ADMIN_USER', 'ghost_test_user')

from app import app, db
from models import Admin, BusinessGalleryImage


class OurBusinessGalleryTests(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{self.db_path}'
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        self.upload_dir = tempfile.mkdtemp()
        app.config['BUSINESS_GALLERY_FOLDER'] = self.upload_dir

        with app.app_context():
            db.session.remove()
            db.engine.dispose()
            db.create_all()
            admin = Admin(
                username='gallery_test_admin',
                password_hash=generate_password_hash('adminpass', method='pbkdf2:sha256'),
                role='admin',
            )
            db.session.add(admin)
            db.session.commit()
            self.admin_id = admin.id

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        os.close(self.db_fd)
        os.unlink(self.db_path)
        for name in os.listdir(self.upload_dir):
            os.unlink(os.path.join(self.upload_dir, name))
        os.rmdir(self.upload_dir)

    def _login(self):
        with self.client.session_transaction() as sess:
            sess['admin_logged_in'] = True
            sess['admin_id'] = self.admin_id
            sess['role'] = 'admin'
            sess['username'] = 'gallery_test_admin'

    def _png_bytes(self, color=(20, 40, 80)):
        buf = io.BytesIO()
        Image.new('RGB', (40, 40), color).save(buf, format='PNG')
        buf.seek(0)
        return buf

    def test_navbar_and_empty_gallery(self):
        home = self.client.get('/')
        self.assertEqual(home.status_code, 200)
        self.assertIn(b'Our Business', home.data)
        self.assertIn(b'/our-business', home.data)

        page = self.client.get('/our-business')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Our Business', page.data)
        self.assertIn(b'Gallery opening soon', page.data)

    def test_admin_can_publish_photo_to_gallery(self):
        self._login()
        resp = self.client.post(
            '/admin/our-business',
            data={
                'action': 'upload',
                'title': 'Storefront',
                'caption': 'Newport Street building',
                'images': [(self._png_bytes(), 'shop.png')],
            },
            content_type='multipart/form-data',
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Storefront', resp.data)

        public = self.client.get('/our-business')
        self.assertEqual(public.status_code, 200)
        self.assertIn(b'Storefront', public.data)
        self.assertIn(b'Newport Street building', public.data)
        self.assertNotIn(b'Gallery opening soon', public.data)
        self.assertIn(b'uploads/business/', public.data)

        with app.app_context():
            self.assertEqual(BusinessGalleryImage.query.count(), 1)


if __name__ == '__main__':
    unittest.main()
