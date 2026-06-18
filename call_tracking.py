"""
3G Design — Communications & Call Tracking
Supports cloud (Twilio webhooks) and local desktop API logging.
"""
import os
from datetime import datetime
from functools import wraps

from flask import Blueprint, request, jsonify, render_template, session, flash, redirect, url_for, current_app

from models import db, CallLog
from server_stability import run_in_background
from site_config import get_public_site_url, get_whatsapp_webhook_url, whatsapp_env_status
from whatsapp_service import is_configured as whatsapp_is_configured
from whatsapp_credentials import disconnect_integration, get_verify_token

call_bp = Blueprint('communications', __name__)

VALID_SOURCES = {'twilio_cloud', 'local_desktop', 'whatsapp_manual', 'whatsapp_web', 'whatsapp_api'}
VALID_TYPES = {'voice', 'whatsapp_call', 'whatsapp_message', 'recording'}
VALID_STATUSES = {'received', 'processed', 'missed', 'logged', 'in_progress'}


def _api_key_ok():
    key = os.getenv('LOCAL_API_KEY', '').strip()
    if not key:
        return False
    supplied = request.headers.get('X-API-Key') or request.headers.get('Authorization', '').replace('Bearer ', '')
    return supplied == key


def api_or_login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if _api_key_ok():
            return f(*args, **kwargs)
        if session.get('admin_logged_in') and session.get('role') in ('admin', 'moderator', 'staff'):
            return f(*args, **kwargs)
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Unauthorized. Provide X-API-Key header or log in.'}), 401
        return redirect(url_for('login'))
    return wrapper


def create_call_log(data):
    entry = CallLog(
        phone_number=data.get('phone_number', '').strip(),
        caller_name=data.get('caller_name', '').strip() or None,
        transcript=data.get('transcript', '').strip() or None,
        audio_url=data.get('audio_url', '').strip() or None,
        notes=data.get('notes', '').strip() or None,
        source=data.get('source', 'local_desktop'),
        call_type=data.get('call_type', 'voice'),
        status=data.get('status', 'logged'),
        duration_seconds=data.get('duration_seconds'),
        call_sid=data.get('call_sid'),
        logged_by=data.get('logged_by') or session.get('username'),
    )
    db.session.add(entry)
    db.session.commit()
    return entry


@call_bp.route('/admin/communications')
@api_or_login_required
def communications_portal():
    calls = CallLog.query.order_by(CallLog.timestamp.desc()).limit(100).all()
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    stats = {
        'today_total': CallLog.query.filter(CallLog.timestamp >= today_start).count(),
        'today_whatsapp': CallLog.query.filter(
            CallLog.timestamp >= today_start,
            CallLog.call_type.ilike('%whatsapp%'),
        ).count(),
        'today_local': CallLog.query.filter(
            CallLog.timestamp >= today_start,
            CallLog.source == 'local_desktop',
        ).count(),
        'today_cloud': CallLog.query.filter(
            CallLog.timestamp >= today_start,
            CallLog.source == 'twilio_cloud',
        ).count(),
        'all_total': CallLog.query.count(),
    }

    local_api_url = os.getenv('LOCAL_API_URL', f'{get_public_site_url()}/api/communications/log')
    api_key_set = bool(os.getenv('LOCAL_API_KEY', '').strip())
    wa_status = whatsapp_env_status()
    whatsapp_api_configured = wa_status['fully_configured']

    return render_template(
        'communications.html',
        calls=calls,
        stats=stats,
        local_api_url=local_api_url,
        api_key_set=api_key_set,
        whatsapp_api_configured=whatsapp_api_configured,
        whatsapp_webhook_url=get_whatsapp_webhook_url(request.url_root),
        whatsapp_status=wa_status,
        public_site_url=get_public_site_url(request.url_root),
        meta_app_id=os.getenv('META_APP_ID', '').strip(),
        embedded_config_id=os.getenv('WHATSAPP_EMBEDDED_CONFIG_ID', '').strip(),
    )


@call_bp.route('/api/communications/log', methods=['POST'])
def api_log_communication():
    """Log a call/message from local desktop or integrations."""
    if not _api_key_ok():
        if not (session.get('admin_logged_in') and session.get('role') in ('admin', 'moderator', 'staff')):
            return jsonify({'error': 'Invalid or missing API key'}), 401

    payload = request.get_json(silent=True) or request.form.to_dict()

    phone = (payload.get('phone_number') or payload.get('phone') or '').strip()
    if not phone:
        return jsonify({'error': 'phone_number is required'}), 400

    source = payload.get('source', 'local_desktop')
    call_type = payload.get('call_type', 'whatsapp_call')
    status = payload.get('status', 'logged')

    if source not in VALID_SOURCES:
        source = 'local_desktop'
    if call_type not in VALID_TYPES:
        call_type = 'whatsapp_call'
    if status not in VALID_STATUSES:
        status = 'logged'

    try:
        entry = create_call_log({
            'phone_number': phone,
            'caller_name': payload.get('caller_name', ''),
            'notes': payload.get('notes', ''),
            'transcript': payload.get('transcript', ''),
            'source': source,
            'call_type': call_type,
            'status': status,
            'duration_seconds': payload.get('duration_seconds'),
            'logged_by': payload.get('logged_by', 'local_tracker'),
        })
        return jsonify({
            'success': True,
            'id': entry.id,
            'message': 'Communication logged successfully',
            'tracked_at': entry.timestamp.isoformat() if entry.timestamp else None,
        }), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Call log error: {e}')
        return jsonify({'error': 'Failed to save log'}), 500


@call_bp.route('/api/communications', methods=['GET'])
@api_or_login_required
def api_list_communications():
    limit = min(int(request.args.get('limit', 50)), 200)
    source = request.args.get('source')
    call_type = request.args.get('call_type')

    query = CallLog.query.order_by(CallLog.timestamp.desc())
    if source:
        query = query.filter_by(source=source)
    if call_type:
        query = query.filter_by(call_type=call_type)

    calls = query.limit(limit).all()
    return jsonify({
        'count': len(calls),
        'calls': [{
            'id': c.id,
            'phone_number': c.phone_number,
            'caller_name': c.caller_name,
            'source': c.source,
            'call_type': c.call_type,
            'status': c.status,
            'notes': c.notes,
            'transcript': c.transcript,
            'duration_seconds': c.duration_seconds,
            'logged_by': c.logged_by,
            'timestamp': c.timestamp.isoformat() if c.timestamp else None,
        } for c in calls],
    })


@call_bp.route('/api/communications/status', methods=['GET'])
def api_communications_status():
    """Health check for local tracker — no auth required."""
    wa = whatsapp_env_status()
    return jsonify({
        'service': '3G Design Communications API',
        'status': 'online',
        'local_tracking': bool(os.getenv('LOCAL_API_KEY', '').strip()),
        'twilio_configured': bool(os.getenv('TWILIO_ACCOUNT_SID') and os.getenv('TWILIO_AUTH_TOKEN')),
        'whatsapp_api_configured': wa['fully_configured'],
        'whatsapp_can_send': wa['can_send'],
        'webhook_url': get_whatsapp_webhook_url(),
        'public_site_url': get_public_site_url(),
        'timestamp': datetime.utcnow().isoformat(),
    })


@call_bp.route('/api/whatsapp/status', methods=['GET'])
def api_whatsapp_status():
    """WhatsApp setup status for admin / deployment checks."""
    wa = whatsapp_env_status()
    return jsonify({
        'configured': wa['fully_configured'],
        'can_send': wa['can_send'],
        'verify_token_set': wa['verify_token'],
        'access_token_set': wa['access_token'],
        'phone_number_id_set': wa['phone_number_id'],
        'webhook_url': get_whatsapp_webhook_url(),
        'public_site_url': get_public_site_url(),
        'auto_reply': os.getenv('WHATSAPP_AUTO_REPLY', 'true'),
        'connection_method': wa.get('connection_method'),
        'display_phone': wa.get('display_phone'),
        'business_name': wa.get('business_name'),
        'connected_at': wa.get('connected_at'),
        'embedded_signup_ready': wa.get('embedded_signup_ready'),
        'setup_steps': [
            'Set WHATSAPP_VERIFY_TOKEN in .env (webhook security)',
            'Connect via Embedded Signup below, or set tokens in .env manually',
            f'Register webhook URL in Meta: {get_whatsapp_webhook_url()}',
            'Subscribe to messages field on WhatsApp webhook',
        ],
    })


@call_bp.route('/api/whatsapp/onboarding/config', methods=['GET'])
@api_or_login_required
def whatsapp_onboarding_config():
    """Public Meta app identifiers for Embedded Signup (no secrets)."""
    app_id = os.getenv('META_APP_ID', '').strip()
    config_id = os.getenv('WHATSAPP_EMBEDDED_CONFIG_ID', '').strip()
    return jsonify({
        'app_id': app_id,
        'config_id': config_id,
        'ready': bool(app_id and config_id),
        'webhook_url': get_whatsapp_webhook_url(),
    })


@call_bp.route('/api/whatsapp/onboarding/callback', methods=['POST'])
@api_or_login_required
def whatsapp_onboarding_callback():
    """
    Exchange Embedded Signup code for long-lived token; store WABA + Phone Number ID.
    Frontend sends code + optional IDs from WA_EMBEDDED_SIGNUP event.
    """
    payload = request.get_json(silent=True) or {}
    code = (payload.get('code') or '').strip()
    if not code:
        return jsonify({'error': 'Authorization code is required'}), 400

    try:
        from whatsapp_onboarding import complete_embedded_signup
        result = complete_embedded_signup(
            code=code,
            connected_by=session.get('username', 'admin'),
            waba_id=payload.get('waba_id', ''),
            phone_number_id=payload.get('phone_number_id', ''),
        )
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f'WhatsApp onboarding error: {e}')
        return jsonify({'error': 'Failed to complete WhatsApp connection'}), 500


@call_bp.route('/api/whatsapp/disconnect', methods=['POST'])
@api_or_login_required
def whatsapp_disconnect():
    """Deactivate DB-stored credentials (falls back to .env if set)."""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    disconnect_integration()
    return jsonify({'status': 'disconnected'}), 200


@call_bp.route('/admin/communications/log', methods=['POST'])
@api_or_login_required
def manual_log_communication():
    phone = request.form.get('phone_number', '').strip()
    if not phone:
        flash('Phone number is required.', 'error')
        return redirect(url_for('communications.communications_portal'))

    create_call_log({
        'phone_number': phone,
        'caller_name': request.form.get('caller_name', ''),
        'notes': request.form.get('notes', ''),
        'call_type': request.form.get('call_type', 'whatsapp_call'),
        'status': request.form.get('status', 'logged'),
        'source': 'whatsapp_manual',
        'duration_seconds': request.form.get('duration_seconds') or None,
    })
    flash('Communication logged successfully.', 'success')
    return redirect(url_for('communications.communications_portal'))


@call_bp.route('/admin/communications/quick')
@api_or_login_required
def communications_quick_log():
    """Desktop-friendly one-click logging page — bookmark on your shop PC."""
    return render_template('communications_quick.html')


@call_bp.route('/admin/communications/quick-log', methods=['POST'])
@api_or_login_required
def quick_log_communication():
    phone = request.form.get('phone_number', '').strip()
    if not phone:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json':
            return jsonify({'error': 'phone_number is required'}), 400
        flash('Phone number is required.', 'error')
        return redirect(url_for('communications.communications_quick_log'))

    entry = create_call_log({
        'phone_number': phone,
        'caller_name': request.form.get('caller_name', ''),
        'notes': request.form.get('notes', ''),
        'call_type': request.form.get('call_type', 'whatsapp_call'),
        'status': 'logged',
        'source': 'local_desktop',
    })

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({
            'success': True,
            'id': entry.id,
            'message': 'Logged successfully',
            'timestamp': entry.timestamp.isoformat() if entry.timestamp else None,
        }), 201

    flash(f'Logged {phone} successfully.', 'success')
    return redirect(url_for('communications.communications_quick_log'))


# --------------------------------------------------------------------------
# WhatsApp Business API (Meta Cloud API) Webhook
# Set in .env: WHATSAPP_VERIFY_TOKEN, WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID
# Webhook URL: https://your-domain.com/api/whatsapp/webhook
# --------------------------------------------------------------------------
@call_bp.route('/api/whatsapp/webhook', methods=['GET', 'POST'])
def whatsapp_webhook():
    verify_token = get_verify_token()

    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if mode == 'subscribe' and token == verify_token and challenge:
            return challenge, 200
        current_app.logger.warning('WhatsApp webhook verification failed')
        return 'Verification failed', 403

    if not verify_token:
        return jsonify({'error': 'WhatsApp API not configured'}), 503

    try:
        payload = request.get_json(silent=True) or {}
        app_obj = current_app._get_current_object()
        run_in_background(app_obj, _process_whatsapp_webhook_payload, payload, app_obj.root_path)
        queued = sum(
            len(change.get('value', {}).get('messages', []))
            for entry in payload.get('entry', [])
            for change in entry.get('changes', [])
        )
        return jsonify({'success': True, 'queued': queued}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'WhatsApp webhook error: {e}')
        return jsonify({'error': 'Webhook processing failed'}), 500


def _process_whatsapp_webhook_payload(payload, app_root):
    from whatsapp_service import phone_display, process_incoming_message

    logged = 0
    for entry in payload.get('entry', []):
        for change in entry.get('changes', []):
            value = change.get('value', {})
            for message in value.get('messages', []):
                process_incoming_message(message, value, app_root)
                logged += 1

            for status in value.get('statuses', []):
                if status.get('status') == 'failed':
                    phone = status.get('recipient_id', '')
                    create_call_log({
                        'phone_number': phone_display(phone),
                        'notes': f"Delivery failed: {status.get('errors', '')}",
                        'call_type': 'whatsapp_message',
                        'status': 'missed',
                        'source': 'whatsapp_api',
                        'call_sid': status.get('id'),
                        'logged_by': 'whatsapp_api',
                    })
                    logged += 1
    current_app.logger.info('WhatsApp webhook processed %s events', logged)
