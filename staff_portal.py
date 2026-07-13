"""
3G Design — Staff portal, attendance clock-in/out, late-staff alerts.
"""
import os
from datetime import datetime, time as datetime_time
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for, current_app
from flask_mail import Message
from sqlalchemy import text

from models import db, Admin, Attendance, DailyReport, Order, SystemSettings
from server_stability import commit_with_retry

staff_bp = Blueprint('staff', __name__)

LATE_THRESHOLD = datetime_time(8, 15)
SHOP_OPENS = datetime_time(8, 0)


def staff_roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if 'admin_logged_in' not in session:
                return redirect(url_for('login'))
            if session.get('role') not in roles:
                flash('This area is for shop staff only.', 'danger')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return wrapper
    return decorator


def post_login_redirect(admin):
    """Route users to the right home after authentication."""
    ghost_user = os.getenv('GHOST_ADMIN_USER', 'ghost_admin')
    if admin.username == ghost_user:
        return url_for('ghost_dashboard')
    if admin.role == 'staff':
        return url_for('staff.staff_portal')
    if admin.role == 'moderator':
        return url_for('moderator_portal')
    return url_for('dashboard')


def today_attendance_for(staff_id):
    today = datetime.now().date()
    return Attendance.query.filter(
        Attendance.staff_id == staff_id,
        db.func.date(Attendance.check_in) == today,
    ).order_by(Attendance.check_in.desc()).first()


def _claim_late_staff_check(today):
    """Only one worker runs the daily late-staff alert."""
    settings = SystemSettings.query.first()
    if not settings:
        settings = SystemSettings(is_active=True)
        db.session.add(settings)
        commit_with_retry(db)

    result = db.session.execute(
        text(
            'UPDATE system_settings '
            'SET last_late_check_date = :today '
            'WHERE id = :sid AND (last_late_check_date IS NULL OR last_late_check_date != :today)'
        ),
        {'today': today, 'sid': settings.id},
    )
    commit_with_retry(db)
    return result.rowcount > 0


def run_late_staff_check_if_due(mail, app):
    """Run at most once per business day after the grace period."""
    now = datetime.now()
    if now.weekday() == 6:
        return
    if now.time() < LATE_THRESHOLD:
        return

    if not _claim_late_staff_check(now.date()):
        return

    try:
        check_for_late_staff(mail, app)
    except Exception as exc:
        current_app.logger.error(f'Late staff check failed: {exc}')


def check_for_late_staff(mail, app):
    today = datetime.now().date()
    team = Admin.query.filter(Admin.role.in_(['staff', 'moderator'])).all()
    for member in team:
        if member.username == os.getenv('GHOST_ADMIN_USER', 'ghost_admin'):
            continue
        record = Attendance.query.filter(
            Attendance.staff_id == member.id,
            db.func.date(Attendance.check_in) == today,
        ).first()
        if not record:
            send_late_notification(member.username, mail, app)


def send_late_notification(username, mail, app):
    msg_body = (
        f"ALERT: {username} has not clocked in at 3G Design as of "
        f"{LATE_THRESHOLD.strftime('%H:%M')}."
    )
    current_app.logger.warning(msg_body)

    admin_email = app.config.get('MAIL_USERNAME')
    if admin_email:
        try:
            mail.send(Message(
                subject='3G Design — Late Staff Alert',
                sender=admin_email,
                recipients=[admin_email],
                body=msg_body,
            ))
        except Exception as e:
            current_app.logger.error(f'Late alert email failed: {e}')

    admin_phone = os.getenv('ADMIN_ALERT_PHONE', '+231881669599')
    try:
        from app import twilio_client
        twilio_number = app.config.get('TWILIO_PHONE_NUMBER')
        if twilio_client and twilio_number and admin_phone:
            twilio_client.messages.create(
                body=msg_body,
                from_=twilio_number,
                to=admin_phone,
            )
    except Exception as e:
        current_app.logger.error(f'Late alert SMS failed: {e}')


@staff_bp.route('/staff')
@staff_roles_required('staff')
def staff_portal():
    admin = Admin.query.get(session.get('admin_id'))
    if not admin:
        flash('Please log in again.', 'warning')
        return redirect(url_for('logout'))

    today_record = today_attendance_for(admin.id)
    recent = (
        Attendance.query.filter_by(staff_id=admin.id)
        .order_by(Attendance.check_in.desc())
        .limit(7)
        .all()
    )
    my_reports = (
        DailyReport.query.filter_by(staff_id=admin.id)
        .order_by(DailyReport.date_posted.desc())
        .limit(5)
        .all()
    )
    active_jobs = Order.query.filter(Order.production_stage != 'delivered').count()

    check_in_time = today_record.check_in.strftime('%I:%M %p') if today_record and today_record.check_in else None
    is_late = False
    if today_record and today_record.check_in:
        is_late = today_record.check_in.time() > LATE_THRESHOLD

    return render_template(
        'staff.html',
        user=admin,
        today_record=today_record,
        check_in_time=check_in_time,
        is_late=is_late,
        is_clocked_in=bool(today_record and today_record.status == 'Active'),
        recent_attendance=recent,
        my_reports=my_reports,
        active_jobs=active_jobs,
        late_threshold=LATE_THRESHOLD.strftime('%H:%M'),
    )


@staff_bp.route('/staff/clock-in', methods=['POST'])
@staff_roles_required('staff', 'moderator')
def clock_in():
    admin = Admin.query.get(session.get('admin_id'))
    existing = today_attendance_for(admin.id)
    if existing and existing.status == 'Active':
        flash('You are already clocked in for today.', 'info')
    else:
        record = Attendance(
            staff_id=admin.id,
            staff_name=admin.username,
            check_in=datetime.utcnow(),
            status='Active',
        )
        db.session.add(record)
        commit_with_retry(db)
        local_time = datetime.now().strftime('%I:%M %p')
        if datetime.now().time() > LATE_THRESHOLD:
            flash(f'Clocked in at {local_time} — marked as late.', 'warning')
        else:
            flash(f'Clocked in at {local_time}. Have a productive shift!', 'success')

    if session.get('role') == 'staff':
        return redirect(url_for('staff.staff_portal'))
    if session.get('role') == 'moderator':
        return redirect(url_for('moderator_portal'))
    return redirect(url_for('dashboard'))


@staff_bp.route('/staff/clock-out', methods=['POST'])
@staff_roles_required('staff', 'moderator')
def clock_out():
    admin = Admin.query.get(session.get('admin_id'))
    record = today_attendance_for(admin.id)
    if not record or record.status != 'Active':
        flash('No active clock-in found for today.', 'warning')
    else:
        record.status = 'Logged Out'
        commit_with_retry(db)
        flash('Clocked out. See you next shift!', 'success')

    if session.get('role') == 'staff':
        return redirect(url_for('staff.staff_portal'))
    if session.get('role') == 'moderator':
        return redirect(url_for('moderator_portal'))
    return redirect(url_for('dashboard'))
