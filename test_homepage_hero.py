"""Navbar shows the logo in front of 3G DESIGN GLOBAL; homepage hero does not."""
import os
import tempfile
import unittest

os.environ.setdefault('GHOST_ADMIN_USER', 'ghost_test_user')

from app import app, db


class NavbarBrandLogoTests(unittest.TestCase):
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

    def _assert_navbar_logo_before_wordmark(self, html):
        brand_start = html.find('class="navbar-brand')
        self.assertGreater(brand_start, -1)
        brand_end = html.find('</a>', brand_start)
        brand = html[brand_start:brand_end]
        logo_pos = brand.find('navbar-brand-mark')
        text_pos = brand.find('brand-wordmark')
        self.assertGreater(logo_pos, -1)
        self.assertGreater(text_pos, logo_pos)
        self.assertIn('img/LOGO.png', brand)
        self.assertIn('3G DESIGN GLOBAL', brand)

    def test_homepage_navbar_has_logo_in_front_of_text(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertNotIn('hero-brand-lockup', html)
        self.assertNotIn('hero-brand-logo', html)
        self.assertNotIn('class="home-page"', html)
        self._assert_navbar_logo_before_wordmark(html)

        hero_start = html.find('hero-content')
        hero_end = html.find('</h1>', hero_start)
        hero = html[hero_start:hero_end]
        self.assertNotIn('LOGO.png', hero)

    def test_about_page_navbar_has_logo_in_front_of_text(self):
        response = self.client.get('/about')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self._assert_navbar_logo_before_wordmark(html)
        self.assertNotIn('hero-brand-lockup', html)

    def test_homepage_promo_uses_advertisement_events_headings(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertNotIn('See What We Do', html)
        self.assertGreaterEqual(html.count('Advertisement / Events'), 2)

        promo_start = html.find('id="homepage-promo"')
        self.assertGreater(promo_start, -1)
        promo = html[promo_start:html.find('id="products"', promo_start)]
        flyer_pos = promo.find('Promotional flyer coming soon')
        first_heading = promo.find('Advertisement / Events')
        second_heading = promo.find('Advertisement / Events', first_heading + 1)
        self.assertGreater(first_heading, -1)
        self.assertGreater(flyer_pos, first_heading)
        self.assertGreater(second_heading, flyer_pos)


if __name__ == '__main__':
    unittest.main()
