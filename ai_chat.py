"""
3G DESIGN — AI chat routes (web widget + Twilio WhatsApp gateway).
Meta Cloud API AI replies are handled in whatsapp_service.process_incoming_message.
"""
import os

from flask import Blueprint, request, jsonify, current_app
from xml.sax.saxutils import escape

from ai_agent import handle_customer_message

ai_chat_bp = Blueprint('ai_chat', __name__)


def _ai_enabled():
    return os.getenv('WHATSAPP_AI_REPLY', 'true').lower() in ('1', 'true', 'yes')


@ai_chat_bp.route('/api/web/chat', methods=['POST'])
def web_chat_endpoint():
    """Browser chat widget — session_token from localStorage."""
    data = request.get_json(silent=True) or {}
    session_token = (data.get('session_token') or '').strip()
    user_message = (data.get('message') or '').strip()

    if not session_token or not user_message:
        return jsonify({'error': 'session_token and message are required'}), 400

    if not session_token.startswith('web:'):
        session_token = f'web:{session_token}'

    try:
        ai_reply = handle_customer_message(
            session_token=session_token,
            user_message=user_message,
            channel='web',
        )
        return jsonify({'reply': ai_reply}), 200
    except Exception as e:
        current_app.logger.error(f'Web chat error: {e}')
        return jsonify({'error': 'Could not process message'}), 500


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
            "Thank you for contacting 3G DESIGN! We received your message and will respond shortly."
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
