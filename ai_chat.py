"""
3G Design — AI chat routes (web widget + Twilio WhatsApp gateway).
Meta Cloud API AI replies are handled in whatsapp_service.process_incoming_message.
"""
import os
import time
from collections import defaultdict, deque

from flask import Blueprint, request, jsonify, current_app
from xml.sax.saxutils import escape

from ai_agent import handle_customer_message, get_session_messages

ai_chat_bp = Blueprint('ai_chat', __name__)

MAX_MESSAGE_LENGTH = 500
RATE_LIMIT_WINDOW_SEC = 60
RATE_LIMIT_MAX_REQUESTS = 20
_rate_limit_buckets = defaultdict(deque)


def _ai_enabled():
    return os.getenv('WHATSAPP_AI_REPLY', 'true').lower() in ('1', 'true', 'yes')


def _normalize_web_session(session_token):
    session_token = (session_token or '').strip()
    if not session_token:
        return ''
    if not session_token.startswith('web:'):
        session_token = f'web:{session_token}'
    return session_token


def _rate_limit_key():
    data = request.get_json(silent=True) or {}
    token = _normalize_web_session(data.get('session_token') or '')
    if token:
        return token
    return f"ip:{request.remote_addr or 'unknown'}"


def _check_rate_limit(key):
    now = time.time()
    bucket = _rate_limit_buckets[key]
    while bucket and bucket[0] < now - RATE_LIMIT_WINDOW_SEC:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_MAX_REQUESTS:
        return False
    bucket.append(now)
    return True


@ai_chat_bp.route('/api/web/chat', methods=['GET'])
def web_chat_history():
    """Restore prior messages for a browser session."""
    session_token = _normalize_web_session(request.args.get('session_token'))
    if not session_token:
        return jsonify({'error': 'Your chat session could not be found. Refresh the page to start again.'}), 400

    try:
        messages = get_session_messages(session_token)
        return jsonify({'messages': messages}), 200
    except Exception as e:
        current_app.logger.error(f'Web chat history error: {e}')
        return jsonify({'error': 'Could not load your conversation. Please try again.'}), 500


@ai_chat_bp.route('/api/web/chat', methods=['POST'])
def web_chat_endpoint():
    """Browser chat widget — session_token from localStorage."""
    if not _check_rate_limit(_rate_limit_key()):
        return jsonify({
            'error': "You're sending messages too quickly. Please wait a moment and try again.",
        }), 429

    data = request.get_json(silent=True) or {}
    session_token = _normalize_web_session(data.get('session_token'))
    user_message = (data.get('message') or '').strip()

    if not session_token:
        return jsonify({'error': 'Your chat session expired. Refresh the page to continue.'}), 400
    if not user_message:
        return jsonify({'error': 'Please type a message before sending.'}), 400
    if len(user_message) > MAX_MESSAGE_LENGTH:
        return jsonify({'error': f'Messages are limited to {MAX_MESSAGE_LENGTH} characters.'}), 400

    try:
        ai_reply = handle_customer_message(
            session_token=session_token,
            user_message=user_message,
            channel='web',
        )
        return jsonify({'reply': ai_reply}), 200
    except Exception as e:
        current_app.logger.error(f'Web chat error: {e}')
        return jsonify({'error': 'Something went wrong. Please try again or contact us on WhatsApp.'}), 500


@ai_chat_bp.route('/api/web/chat/session', methods=['POST'])
def web_chat_new_session():
    """Issue a new anonymous browser session ID."""
    import secrets
    return jsonify({'session_token': f'web:{secrets.token_urlsafe(16)}'}), 200


@ai_chat_bp.route('/api/whatsapp/twilio-webhook', methods=['POST'])
def twilio_whatsapp_webhook():
    """
    Twilio WhatsApp inbound webhook (TwiML response).
    Configure Twilio WhatsApp sender URL to: /api/whatsapp/twilio-webhook
    """
    customer_phone = request.values.get('From', '')
    incoming_text = request.values.get('Body', '')

    if not customer_phone or not incoming_text:
        return jsonify({'status': 'ignored', 'reason': 'Missing From or Body'}), 400

    if not _ai_enabled():
        ai_reply = (
            "Thank you for contacting 3G Design! We received your message and will respond shortly."
        )
    else:
        try:
            ai_reply = handle_customer_message(
                session_token=customer_phone,
                user_message=incoming_text,
                channel='twilio_whatsapp',
            )
        except Exception as e:
            current_app.logger.error(f'Twilio AI error: {e}')
            ai_reply = "Thanks for your message — our team will get back to you soon."

    try:
        from twilio.twiml.messaging_response import MessagingResponse
        resp = MessagingResponse()
        resp.message(ai_reply)
        return str(resp), 200, {'Content-Type': 'application/xml'}
    except ImportError:
        safe = escape(ai_reply)
        xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{safe}</Message></Response>'
        return xml, 200, {'Content-Type': 'text/xml'}
