"""
3G DESIGN — WhatsApp Business Cloud API service.
Works locally (with port-forward URL) and on cloud (PythonAnywhere, custom domain).
Credentials: DB (Embedded Signup) with .env fallback.
"""
import os
import re
import requests

from models import db, Customer, CallLog
from whatsapp_credentials import (
    get_access_token,
    get_phone_number_id,
    status as credential_status,
)

GRAPH_API = 'https://graph.facebook.com/v21.0'


def _headers():
    token = get_access_token()
    return {'Authorization': f'Bearer {token}'}


def is_configured():
    s = credential_status()
    return s['fully_configured']


def can_send():
    s = credential_status()
    return s['can_send']


def normalize_phone(phone):
    if not phone:
        return ''
    digits = re.sub(r'\D', '', str(phone))
    return digits


def phone_display(phone):
    digits = normalize_phone(phone)
    if not digits:
        return phone or ''
    return f'+{digits}' if not str(phone).startswith('+') else str(phone)


def upsert_customer(phone, name=''):
    digits = normalize_phone(phone)
    if not digits:
        return None
    display = phone_display(phone)
    customer = Customer.query.filter(
        (Customer.phone == display) |
        (Customer.phone == digits) |
        (Customer.phone.ilike(f'%{digits[-9:]}%'))
    ).first()
    if not customer:
        customer = Customer(name=name or f'WhatsApp {digits[-4:]}', phone=display)
        db.session.add(customer)
        db.session.flush()
    elif name and (not customer.name or customer.name.startswith('WhatsApp ')):
        customer.name = name
    return customer


def send_text(to_phone, body):
    if not can_send():
        return False, 'WhatsApp API not configured for sending'
    phone_id = get_phone_number_id()
    to_digits = normalize_phone(to_phone)
    if not to_digits or not body:
        return False, 'Missing phone or message'
    try:
        resp = requests.post(
            f'{GRAPH_API}/{phone_id}/messages',
            headers={**_headers(), 'Content-Type': 'application/json'},
            json={
                'messaging_product': 'whatsapp',
                'to': to_digits,
                'type': 'text',
                'text': {'body': body[:4096]},
            },
            timeout=30,
        )
        if resp.ok:
            return True, resp.json()
        return False, resp.text
    except Exception as e:
        return False, str(e)


def send_auto_reply(to_phone, customer_name=''):
    name_bit = f' {customer_name}' if customer_name else ''
    body = (
        f"Thank you{name_bit} for contacting *3G DESIGN*!\n\n"
        "We received your message and logged it in our system. "
        "Our team will respond shortly.\n\n"
        "Quality in Every Print — Excellence in Every Design."
    )
    return send_text(to_phone, body)


def download_media(media_id, app_root):
    if not can_send():
        return None
    try:
        meta = requests.get(f'{GRAPH_API}/{media_id}', headers=_headers(), timeout=30)
        if not meta.ok:
            return None
        media_url = meta.json().get('url')
        if not media_url:
            return None
        file_resp = requests.get(media_url, headers=_headers(), timeout=60)
        if not file_resp.ok:
            return None
        ext = 'jpg'
        ctype = file_resp.headers.get('Content-Type', '')
        if 'png' in ctype:
            ext = 'png'
        elif 'webp' in ctype:
            ext = 'webp'
        folder = os.path.join(app_root, 'static', 'uploads', 'whatsapp')
        os.makedirs(folder, exist_ok=True)
        filename = f'{media_id}.{ext}'
        path = os.path.join(folder, filename)
        with open(path, 'wb') as f:
            f.write(file_resp.content)
        return f'whatsapp/{filename}'
    except Exception:
        return None


def process_incoming_message(message, value, app_root):
    """Process one WhatsApp webhook message → CallLog + Customer."""
    phone = message.get('from', '')
    msg_type = message.get('type', 'text')
    body = ''
    image_path = None

    if msg_type == 'text':
        body = message.get('text', {}).get('body', '')
    elif msg_type in ('image', 'document', 'audio', 'video', 'sticker'):
        body = f'[{msg_type} message received]'
        if msg_type == 'image':
            media_id = message.get('image', {}).get('id')
            if media_id:
                image_path = download_media(media_id, app_root)
                if image_path:
                    body = '[Image attached — saved to system]'

    caller = ''
    contacts = value.get('contacts', [])
    if contacts:
        caller = contacts[0].get('profile', {}).get('name', '')

    customer = upsert_customer(phone, caller)
    display_phone = phone_display(phone)

    entry = CallLog(
        phone_number=display_phone,
        caller_name=caller or (customer.name if customer else None),
        notes=body,
        transcript=body,
        audio_url=image_path,
        call_type='whatsapp_message',
        status='received',
        source='whatsapp_api',
        call_sid=message.get('id'),
        logged_by='whatsapp_api',
    )
    db.session.add(entry)
    db.session.commit()

    auto = os.getenv('WHATSAPP_AUTO_REPLY', 'true').lower() in ('1', 'true', 'yes')
    ai_on = os.getenv('WHATSAPP_AI_REPLY', 'true').lower() in ('1', 'true', 'yes')

    if auto and body and msg_type == 'text':
        if ai_on:
            from ai_agent import handle_customer_message
            ai_reply = handle_customer_message(
                session_token=display_phone,
                user_message=body,
                channel='whatsapp_api',
            )
            send_text(phone, ai_reply)
        else:
            send_auto_reply(phone, caller)
    elif auto:
        send_auto_reply(phone, caller)

    return entry
