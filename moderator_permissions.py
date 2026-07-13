"""
Moderator responsibility permissions for 3G Design ERP.

Admins assign granular permissions to moderator accounts. Admins always have full access.
"""
import json
from datetime import date, datetime, timedelta
from functools import wraps

from sqlalchemy import func

# Responsibility keys stored as JSON on Admin.moderator_permissions
ALL_MODERATOR_PERMISSIONS = {
    'files': 'Client Files & Archives',
    'sales': 'Sales History & Ledger',
    'financials': 'Financial Records (Daily/Weekly)',
    'billing': 'Invoices & Receipts',
    'inventory': 'Inventory Management',
    'products': 'Product Listings',
    'operations': 'Production Operations',
    'attendance': 'Time Tracking',
    'communications': 'Communications Center',
    'daily_reports': 'Daily Sales Reports',
}

DEFAULT_MODERATOR_PERMISSIONS = list(ALL_MODERATOR_PERMISSIONS.keys())

INCOME_PAYMENT_METHODS = {
    'cash': 'Cash',
    'mobile_money': 'Mobile Money',
    'bank_transfer': 'Bank Transfer',
    'other': 'Other',
}

MODERATOR_DASHBOARD_ACTIONS = [
    {
        'perm': 'files',
        'label': 'Client File Portal',
        'description': 'Browse, upload, and archive client design files',
        'icon': 'fa-folder-open',
        'endpoint': 'file_portal',
        'color': 'primary',
    },
    {
        'perm': 'sales',
        'label': 'Website Commerce Ledger',
        'description': 'View website and direct sale transaction history',
        'icon': 'fa-globe',
        'endpoint': 'staff_sales_history',
        'color': 'info',
    },
    {
        'perm': 'sales',
        'label': 'Direct Sale History',
        'description': 'WhatsApp and in-shop order records',
        'icon': 'fa-history',
        'endpoint': 'direct_sale_history',
        'color': 'secondary',
    },
    {
        'perm': 'financials',
        'label': 'Financial Management',
        'description': 'Daily and weekly income & expense records',
        'icon': 'fa-chart-pie',
        'endpoint': 'financials',
        'color': 'success',
    },
    {
        'perm': 'billing',
        'label': 'Billing Center',
        'description': 'Issue invoices, receipts, and document history',
        'icon': 'fa-file-invoice-dollar',
        'endpoint': 'billing.billing_portal',
        'color': 'primary',
    },
    {
        'perm': 'operations',
        'label': 'Operations Hub',
        'description': 'Print production pipeline and order inbox',
        'icon': 'fa-industry',
        'endpoint': 'operations.operations_hub',
        'color': 'warning',
    },
    {
        'perm': 'communications',
        'label': 'Communications Center',
        'description': 'Call logs and WhatsApp tracking',
        'icon': 'fa-headset',
        'endpoint': 'communications.communications_portal',
        'color': 'info',
    },
    {
        'perm': 'products',
        'label': 'Post New Product',
        'description': 'Add catalog listings to the storefront',
        'icon': 'fa-plus-circle',
        'endpoint': 'add_product',
        'color': 'primary',
        'btn': True,
    },
    {
        'perm': 'inventory',
        'label': 'Inventory & Stock',
        'description': 'Warehouse stock levels and transaction logs',
        'icon': 'fa-boxes',
        'endpoint': 'inventory',
        'color': 'warning',
        'btn': True,
    },
]

# Routes mapped to permission keys for backend enforcement
ROUTE_PERMISSION_MAP = {
    'file_portal': 'files',
    'staff_sales_history': 'sales',
    'direct_sale_history': 'sales',
    'financials': 'financials',
    'add_expense': 'financials',
    'add_product': 'products',
    'inventory': 'inventory',
    'submit_daily_report': 'daily_reports',
}


def parse_moderator_permissions(admin):
    """Return list of permission keys for an admin account."""
    if not admin:
        return []
    if admin.role == 'admin':
        return list(ALL_MODERATOR_PERMISSIONS.keys())
    if admin.role != 'moderator':
        return []
    raw = getattr(admin, 'moderator_permissions', None)
    if not raw:
        return list(DEFAULT_MODERATOR_PERMISSIONS)
    try:
        perms = json.loads(raw)
        if isinstance(perms, list):
            return [p for p in perms if p in ALL_MODERATOR_PERMISSIONS]
    except (json.JSONDecodeError, TypeError):
        pass
    return list(DEFAULT_MODERATOR_PERMISSIONS)


def moderator_has_permission(admin, perm):
    if not admin or perm not in ALL_MODERATOR_PERMISSIONS:
        return False
    if admin.role == 'admin':
        return True
    if admin.role != 'moderator':
        return False
    return perm in parse_moderator_permissions(admin)


def moderator_has_any_permission(admin, *perms):
    return any(moderator_has_permission(admin, p) for p in perms)


def can_log_manual_income(admin):
    """Admins, staff, and moderators with daily_reports or financials may log income."""
    if not admin:
        return False
    if admin.role in ('admin', 'staff'):
        return True
    if admin.role == 'moderator':
        return moderator_has_any_permission(admin, 'daily_reports', 'financials')
    return False


def daily_report_effective_date():
    """SQL expression: business date for a DailyReport row."""
    from models import DailyReport
    return func.coalesce(DailyReport.report_date, func.date(DailyReport.date_posted))


def daily_report_period_filter(period='daily'):
    """Return a SQLAlchemy filter for DailyReport rows in the given period window."""
    from models import DailyReport
    effective = daily_report_effective_date()
    now = datetime.utcnow()
    if period == 'weekly':
        start = (now - timedelta(days=7)).date()
        return effective >= start
    if period == 'annual':
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0).date()
        return effective >= start
    return effective == now.date()


def parse_manual_income_form(form, *, require_notes=False):
    """Validate manual income fields from a request form. Returns (data, error)."""
    amount_raw = (form.get('total_sales') or '').strip()
    try:
        amount = float(amount_raw)
        if amount <= 0:
            return None, 'Income amount must be greater than zero.'
    except (ValueError, TypeError):
        return None, 'Enter a valid income amount.'

    currency = (form.get('currency') or 'USD').strip().upper()
    if currency not in ('USD', 'LRD'):
        return None, 'Select a valid currency (USD or LRD).'

    payment_method = (form.get('payment_method') or 'other').strip()
    if payment_method not in INCOME_PAYMENT_METHODS:
        return None, 'Select a valid payment source.'

    report_text = (form.get('report_text') or '').strip()
    if require_notes and not report_text:
        return None, 'Activity notes are required for this report.'

    reference = (form.get('reference') or '').strip() or None

    report_date_raw = (form.get('report_date') or '').strip()
    if report_date_raw:
        try:
            report_date = datetime.strptime(report_date_raw, '%Y-%m-%d').date()
        except ValueError:
            return None, 'Invalid income date. Use YYYY-MM-DD.'
    else:
        report_date = date.today()

    if not report_text:
        report_text = f'Manual income — {INCOME_PAYMENT_METHODS[payment_method]}'

    return {
        'total_sales': amount,
        'currency': currency,
        'payment_method': payment_method,
        'report_text': report_text,
        'reference': reference,
        'report_date': report_date,
    }, None


def income_log_permission_required(f):
    """Admins/staff pass; moderators need daily_reports or financials."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import redirect, session, url_for
        from models import Admin

        if 'admin_logged_in' not in session:
            return redirect(url_for('login'))
        role = session.get('role')
        if role in ('admin', 'staff'):
            return f(*args, **kwargs)
        if role == 'moderator':
            admin = Admin.query.get(session.get('admin_id'))
            if can_log_manual_income(admin):
                return f(*args, **kwargs)
            from flask import flash
            flash('You do not have permission to log daily income.', 'danger')
            return redirect(url_for('moderator_portal'))
        from flask import flash
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))
    return decorated_function


def permissions_from_form(form):
    """Extract checked permission keys from a request form."""
    return [key for key in ALL_MODERATOR_PERMISSIONS if form.get(f'perm_{key}')]


def serialize_permissions(perms):
    return json.dumps([p for p in perms if p in ALL_MODERATOR_PERMISSIONS])


def visible_dashboard_actions(admin):
    """Action cards the moderator is allowed to see."""
    allowed = set(parse_moderator_permissions(admin))
    seen = set()
    actions = []
    for action in MODERATOR_DASHBOARD_ACTIONS:
        key = (action['perm'], action.get('endpoint'))
        if action['perm'] in allowed and key not in seen:
            actions.append(action)
            seen.add(key)
    return actions


def compute_period_stats(db, DailyReport, Expense, period='daily'):
    """Aggregate income/expense for daily, weekly, or annual windows."""
    now = datetime.utcnow()
    if period == 'weekly':
        start = now - timedelta(days=7)
        label = 'This Week'
    elif period == 'annual':
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        label = 'Year to Date'
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        label = 'Today'

    period_filter = daily_report_period_filter(period)
    income_usd = db.session.query(func.sum(DailyReport.total_sales)).filter(
        period_filter, DailyReport.currency == 'USD'
    ).scalar() or 0
    income_lrd = db.session.query(func.sum(DailyReport.total_sales)).filter(
        period_filter, DailyReport.currency == 'LRD'
    ).scalar() or 0
    expense_usd = db.session.query(func.sum(Expense.amount)).filter(
        Expense.timestamp >= start, Expense.currency == 'USD'
    ).scalar() or 0
    expense_lrd = db.session.query(func.sum(Expense.amount)).filter(
        Expense.timestamp >= start, Expense.currency == 'LRD'
    ).scalar() or 0
    report_count = DailyReport.query.filter(period_filter).count()

    return {
        'label': label,
        'period': period,
        'income_usd': float(income_usd),
        'income_lrd': float(income_lrd),
        'expense_usd': float(expense_usd),
        'expense_lrd': float(expense_lrd),
        'net_usd': float(income_usd) - float(expense_usd),
        'net_lrd': float(income_lrd) - float(expense_lrd),
        'report_count': report_count,
    }


def check_moderator_route_access(permission):
    """Return a Flask redirect if the current moderator lacks permission, else None."""
    from flask import flash, redirect, session, url_for
    from models import Admin

    if session.get('role') != 'moderator':
        return None
    admin = Admin.query.get(session.get('admin_id'))
    if moderator_has_permission(admin, permission):
        return None
    flash('You do not have permission for this responsibility.', 'danger')
    return redirect(url_for('moderator_portal'))
