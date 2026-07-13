"""Verify system_settings survives missing table at request time."""
import os
import unittest

os.environ.setdefault('GHOST_ADMIN_USER', 'ghost_test_user')

from sqlalchemy import text

from app import app
from models import db, SystemSettings
from server_stability import ensure_system_settings, get_cached_system_settings


class SystemSettingsBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.ctx = app.app_context()
        self.ctx.push()
        db.create_all()
        ensure_system_settings(db, SystemSettings)

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def test_ensure_seeds_default_active_row(self):
        SystemSettings.query.delete()
        db.session.commit()
        row = ensure_system_settings(db, SystemSettings)
        self.assertTrue(row.is_active)
        self.assertEqual(SystemSettings.query.count(), 1)

    def test_get_cached_recreates_missing_table(self):
        from server_stability import invalidate_settings_cache
        invalidate_settings_cache()
        db.session.execute(text('DROP TABLE IF EXISTS system_settings'))
        db.session.commit()
        settings = get_cached_system_settings(SystemSettings)
        self.assertIsNotNone(settings)
        self.assertTrue(settings['is_active'])
        self.assertEqual(SystemSettings.query.count(), 1)

    def test_home_route_without_system_settings_table(self):
        from server_stability import invalidate_settings_cache
        invalidate_settings_cache()
        db.session.execute(text('DROP TABLE IF EXISTS system_settings'))
        db.session.commit()
        with app.test_client() as client:
            response = client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SystemSettings.query.count(), 1)


if __name__ == '__main__':
    unittest.main()
