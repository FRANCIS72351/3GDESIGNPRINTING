"""
3G DESIGN — WhatsApp credential store.
Priority: active DB integration (Embedded Signup) → .env fallback (manual deploy).
"""
import os
from datetime import datetime

from itsdangerous import URLSafeSerializer, BadSignature

from models import db, WhatsAppIntegration

SERIALIZER_SALT = '3g-whatsapp-credentials-v1'


def _serializer():
    secret = os.getenv('SECRET_KEY', 'dev-insecure-key-change-me')
    return URLSafeSerializer(secret, salt=SERIALIZER_SALT)


def encrypt_token(token):
    return _serializer().dumps(token)


def decrypt_token(encrypted):
    if not encrypted:
        return ''
    try:
        return _serializer().loads(encrypted)
    except BadSignature:
        return ''


def get_active_integration():
    return WhatsAppIntegration.query.filter_by(is_active=True).order_by(
        WhatsAppIntegration.connected_at.desc()
    ).first()


def get_access_token():
    row = get_active_integration()
    if row and row.access_token_enc:
        token = decrypt_token(row.access_token_enc)
        if token:
            return token
    return os.getenv('WHATSAPP_ACCESS_TOKEN', '').strip()


def get_phone_number_id():
    row = get_active_integration()
    if row and row.phone_number_id:
        return row.phone_number_id.strip()
    return os.getenv('WHATSAPP_PHONE_NUMBER_ID', '').strip()


def get_waba_id():
    row = get_active_integration()
    if row and row.waba_id:
        return row.waba_id.strip()
    return os.getenv('WHATSAPP_BUSINESS_ACCOUNT_ID', '').strip()


def get_display_phone():
    row = get_active_integration()
    if row and row.display_phone:
        return row.display_phone
    from site_config import get_whatsapp_number
    return get_whatsapp_number()


def get_verify_token():
    return os.getenv('WHATSAPP_VERIFY_TOKEN', '').strip()


def save_integration(*, access_token, phone_number_id, waba_id='',
                     display_phone='', business_name='', connected_by='',
                     connection_method='embedded_signup', token_expires_at=None):
    """Persist credentials from Embedded Signup; deactivate prior connections."""
    WhatsAppIntegration.query.filter_by(is_active=True).update({'is_active': False})
    row = WhatsAppIntegration(
        waba_id=waba_id or None,
        phone_number_id=phone_number_id,
        display_phone=display_phone or None,
        business_name=business_name or None,
        access_token_enc=encrypt_token(access_token),
        connection_method=connection_method,
        connected_by=connected_by or None,
        connected_at=datetime.utcnow(),
        token_expires_at=token_expires_at,
        is_active=True,
    )
    db.session.add(row)
    db.session.commit()
    return row


def disconnect_integration():
    WhatsAppIntegration.query.filter_by(is_active=True).update({'is_active': False})
    db.session.commit()


def status():
    """Unified WhatsApp configuration status for admin UI and health checks."""
    row = get_active_integration()
    token = get_access_token()
    phone_id = get_phone_number_id()
    verify = get_verify_token()
    return {
        'access_token': bool(token),
        'phone_number_id': bool(phone_id),
        'verify_token': bool(verify),
        'waba_id': bool(get_waba_id()),
        'fully_configured': bool(token and phone_id and verify),
        'can_send': bool(token and phone_id),
        'connection_method': row.connection_method if row else ('manual_env' if token else None),
        'connected_at': row.connected_at.isoformat() if row and row.connected_at else None,
        'connected_by': row.connected_by if row else None,
        'display_phone': get_display_phone(),
        'business_name': row.business_name if row else None,
        'notify_number': os.getenv('WHATSAPP_NOTIFY_NUMBER', os.getenv('WHATSAPP_NUMBER', '')).strip(),
        'embedded_signup_ready': bool(
            os.getenv('META_APP_ID', '').strip()
            and os.getenv('META_APP_SECRET', '').strip()
            and os.getenv('WHATSAPP_EMBEDDED_CONFIG_ID', '').strip()
        ),
    }
