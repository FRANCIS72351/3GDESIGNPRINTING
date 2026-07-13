"""Tests for moderator dashboard permissions and record visibility."""
import json
import os
import tempfile
import unittest

from werkzeug.security import generate_password_hash

os.environ.setdefault('GHOST_ADMIN_USER', 'ghost_test_user')

from app import app, db
from models import Admin, DailyReport, Expense


class ModeratorDashboardTests(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{self.db_path}'
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

        with app.app_context():
            db.create_all()
            admin = Admin(
                username='test_admin',
                password_hash=generate_password_hash('adminpass'),
                role='admin',
                two_fa_enabled=True,
            )
            mod_full = Admin(
                username='mod_full',
                password_hash=generate_password_hash('modpass'),
                role='moderator',
                two_fa_enabled=True,
            )
            mod_limited = Admin(
                username='mod_limited',
                password_hash=generate_password_hash('modpass'),
                role='moderator',
                two_fa_enabled=True,
                moderator_permissions=json.dumps(['attendance', 'daily_reports']),
            )
            mod_financials = Admin(
                username='mod_fin',
                password_hash=generate_password_hash('modpass'),
                role='moderator',
                two_fa_enabled=True,
                moderator_permissions=json.dumps(['financials']),
            )
            db.session.add_all([admin, mod_full, mod_limited, mod_financials])
            db.session.commit()
            self.admin_id = admin.id
            self.mod_full_id = mod_full.id
            self.mod_limited_id = mod_limited.id
            self.mod_fin_id = mod_financials.id

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def _login_as(self, admin_id, role, username):
        with self.client.session_transaction() as sess:
            sess['admin_logged_in'] = True
            sess['admin_id'] = admin_id
            sess['role'] = role
            sess['username'] = username

    def test_admin_can_access_dashboard(self):
        self._login_as(self.admin_id, 'admin', 'test_admin')
        resp = self.client.get('/dashboard')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Command Center', resp.data)
        self.assertIn(b'Annual Performance', resp.data)
        self.assertIn(b'Manual Daily Income', resp.data)
        self.assertIn(b'Daily Summary Report', resp.data)

    def test_admin_can_log_manual_income(self):
        self._login_as(self.admin_id, 'admin', 'test_admin')
        resp = self.client.post('/admin/daily-report', data={
            'income_entry_mode': 'manual',
            'report_date': '2026-06-30',
            'total_sales': '320.00',
            'currency': 'USD',
            'payment_method': 'mobile_money',
            'reference': 'ADM-RCPT-99',
        }, follow_redirects=True)
        self.assertIn(b'Manual daily income logged successfully', resp.data)
        with app.app_context():
            report = DailyReport.query.filter_by(reference='ADM-RCPT-99').first()
            self.assertIsNotNone(report)
            self.assertEqual(report.total_sales, 320.00)
            self.assertEqual(report.payment_method, 'mobile_money')
            self.assertEqual(report.staff_name, 'test_admin')

    def test_admin_manual_income_updates_dashboard_stats(self):
        self._login_as(self.admin_id, 'admin', 'test_admin')
        self.client.post('/admin/daily-report', data={
            'income_entry_mode': 'manual',
            'total_sales': '500',
            'currency': 'USD',
            'payment_method': 'cash',
        })
        resp = self.client.get('/dashboard')
        self.assertIn(b'$500.00', resp.data)

    def test_admin_summary_report_still_requires_notes(self):
        self._login_as(self.admin_id, 'admin', 'test_admin')
        resp = self.client.post('/admin/daily-report', data={
            'income_entry_mode': 'summary',
            'total_sales': '100',
            'currency': 'USD',
            'payment_method': 'other',
            'report_text': '',
        }, follow_redirects=True)
        self.assertIn(b'Activity notes are required', resp.data)

    def test_admin_multiple_manual_entries_per_day(self):
        self._login_as(self.admin_id, 'admin', 'test_admin')
        for method, amount in [('cash', '50'), ('bank_transfer', '75'), ('mobile_money', '25')]:
            self.client.post('/admin/daily-report', data={
                'income_entry_mode': 'manual',
                'total_sales': amount,
                'currency': 'USD',
                'payment_method': method,
            })
        resp = self.client.get('/dashboard')
        self.assertIn(b'$150.00', resp.data)
        with app.app_context():
            self.assertEqual(DailyReport.query.count(), 3)

    def test_moderator_cannot_access_admin_dashboard(self):
        self._login_as(self.mod_full_id, 'moderator', 'mod_full')
        resp = self.client.get('/dashboard', follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_moderator_portal_shows_daily_weekly_not_annual(self):
        self._login_as(self.mod_full_id, 'moderator', 'mod_full')
        resp = self.client.get('/moderator')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Moderator Dashboard', resp.data)
        self.assertIn(b'Daily', resp.data)
        self.assertIn(b'weekly records only', resp.data)
        self.assertNotIn(b'Annual Performance', resp.data)
        self.assertNotIn(b'Year to Date', resp.data)

    def test_limited_moderator_sees_only_assigned_actions(self):
        self._login_as(self.mod_limited_id, 'moderator', 'mod_limited')
        resp = self.client.get('/moderator')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Time Tracking', resp.data)
        self.assertIn(b'Manual Daily Income', resp.data)
        self.assertNotIn(b'Billing Center', resp.data)
        self.assertNotIn(b'Inventory &amp; Stock', resp.data)

    def test_limited_moderator_blocked_from_inventory_route(self):
        self._login_as(self.mod_limited_id, 'moderator', 'mod_limited')
        resp = self.client.get('/admin/inventory', follow_redirects=True)
        self.assertIn(b'Moderator Dashboard', resp.data)
        self.assertIn(b'do not have permission', resp.data)

    def test_full_moderator_can_access_inventory(self):
        self._login_as(self.mod_full_id, 'moderator', 'mod_full')
        resp = self.client.get('/admin/inventory')
        self.assertEqual(resp.status_code, 200)

    def test_moderator_blocked_from_annual_financials(self):
        self._login_as(self.mod_full_id, 'moderator', 'mod_full')
        resp = self.client.get('/admin/financials?period=annual', follow_redirects=True)
        self.assertIn(b'weekly', resp.data.lower())
        self.assertIn(b'restricted to administrators', resp.data)

    def test_admin_can_access_annual_financials(self):
        self._login_as(self.admin_id, 'admin', 'test_admin')
        resp = self.client.get('/admin/financials?period=annual')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Annual', resp.data)

    def test_moderator_can_log_manual_income(self):
        self._login_as(self.mod_limited_id, 'moderator', 'mod_limited')
        resp = self.client.post('/admin/daily-report', data={
            'report_date': '2026-06-30',
            'total_sales': '150.50',
            'currency': 'USD',
            'payment_method': 'cash',
            'reference': 'RCPT-001',
            'report_text': 'Banner printing payment',
        }, follow_redirects=True)
        self.assertIn(b'Manual daily income logged successfully', resp.data)
        with app.app_context():
            report = DailyReport.query.filter_by(reference='RCPT-001').first()
            self.assertIsNotNone(report)
            self.assertEqual(report.total_sales, 150.50)
            self.assertEqual(report.payment_method, 'cash')
            self.assertEqual(report.staff_name, 'mod_limited')

    def test_financials_moderator_can_log_manual_income(self):
        self._login_as(self.mod_fin_id, 'moderator', 'mod_fin')
        resp = self.client.get('/moderator')
        self.assertIn(b'Manual Daily Income', resp.data)
        post = self.client.post('/admin/daily-report', data={
            'total_sales': '75',
            'currency': 'LRD',
            'payment_method': 'mobile_money',
        }, follow_redirects=True)
        self.assertIn(b'Manual daily income logged successfully', post.data)

    def test_manual_income_updates_daily_stats(self):
        self._login_as(self.mod_limited_id, 'moderator', 'mod_limited')
        self.client.post('/admin/daily-report', data={
            'total_sales': '200',
            'currency': 'USD',
            'payment_method': 'bank_transfer',
        })
        resp = self.client.get('/moderator')
        self.assertIn(b'$200.00', resp.data)

    def test_invalid_income_amount_rejected(self):
        self._login_as(self.mod_limited_id, 'moderator', 'mod_limited')
        resp = self.client.post('/admin/daily-report', data={
            'total_sales': '0',
            'currency': 'USD',
            'payment_method': 'cash',
        }, follow_redirects=True)
        self.assertIn(b'greater than zero', resp.data)


if __name__ == '__main__':
    unittest.main()
