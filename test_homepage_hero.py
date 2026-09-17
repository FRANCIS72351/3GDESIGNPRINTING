"""Homepage hero shows logo inline with brand text, not in the top navbar."""
import os
import tempfile
import unittest

os.environ.setdefault('GHOST_ADMIN_USER', 'ghost_test_user')

from app import app, db


class HomepageHeroLogoTests(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{self.db_path}'
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

        with app.app_context():
            db.engine.dispose()
            db.create_all()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_homepage_hero_puts_logo_in_front_of_text(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertIn('class="home-page"', html)
        self.assertIn('hero-brand-lockup', html)
        self.assertIn('hero-brand-logo', html)
        self.assertIn('img/LOGO.png', html)
        self.assertIn('3G DESIGN GLOBAL', html)

        lockup_start = html.find('hero-brand-lockup')
        lockup_end = html.find('</h1>', lockup_start)
        lockup = html[lockup_start:lockup_end]
        logo_pos = lockup.find('hero-brand-logo')
        text_pos = lockup.find('brand-wordmark')
        self.assertGreater(logo_pos, -1)
        self.assertGreater(text_pos, logo_pos)

    def test_about_page_keeps_navbar_logo(self):
        response = self.client.get('/about')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn('class="home-page"', html)
        self.assertIn('navbar-brand-mark', html)
        self.assertNotIn('hero-brand-lockup', html)


if __name__ == '__main__':
    unittest.main()
