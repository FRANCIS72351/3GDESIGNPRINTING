"""
3G DESIGN — Site URL & environment detection (local, VS port-forward, cloud).
"""
import os
import urllib.parse

# Public social / click-to-chat (footer, contact page — not WhatsApp Business API)
FACEBOOK_PAGE_URL = 'https://web.facebook.com/3gdesignprinting'
WHATSAPP_DEFAULT_CHAT_TEXT = (
    'Hello! I would like to inquire about your printing services.'
)


def get_whatsapp_number():
    """E.164 number for click-to-chat links (from WHATSAPP_NUMBER env)."""
    return os.getenv('WHATSAPP_NUMBER', '+231775323731').replace(' ', '')


def get_whatsapp_wa_me_digits():
    return get_whatsapp_number().lstrip('+')


def get_whatsapp_chat_url(text=None):
    """wa.me link for opening WhatsApp chat (separate from Business API webhooks)."""
    base = f'https://wa.me/{get_whatsapp_wa_me_digits()}'
    if text:
        return f'{base}?text={urllib.parse.quote(text)}'
    return base


def get_public_site_url(request_root=None):
    """
    Canonical public URL for webhooks, WhatsApp, and share links.
    Priority: PUBLIC_SITE_URL → WEBHOOK_BASE_URL → PythonAnywhere → request → localhost.
    """
    explicit = os.getenv('PUBLIC_SITE_URL', '').strip()
    if explicit:
        return explicit.rstrip('/')

    webhook = os.getenv('WEBHOOK_BASE_URL', '').strip()
    if webhook:
        return webhook.rstrip('/')

    pa_domain = os.environ.get('PYTHONANYWHERE_DOMAIN', '').strip()
    if pa_domain:
        return f'https://{pa_domain}'

    custom_domain = os.getenv('SITE_DOMAIN', '').strip()
    if custom_domain:
        scheme = 'https' if not custom_domain.startswith('http') else ''
        if custom_domain.startswith('http'):
            return custom_domain.rstrip('/')
        return f'https://{custom_domain.rstrip("/")}'

    if request_root:
        root = request_root.rstrip('/')
        if root and not root.startswith('http://127.') and not root.startswith('http://localhost'):
            return root

    port = os.getenv('APP_PORT', '5001')
    return f'http://127.0.0.1:{port}'


def get_whatsapp_webhook_url(request_root=None):
    return f"{get_public_site_url(request_root)}/api/whatsapp/webhook"


def is_production():
    return bool(
        os.environ.get('PYTHONANYWHERE_DOMAIN')
        or os.getenv('PUBLIC_SITE_URL', '').strip()
        or os.getenv('WEBHOOK_BASE_URL', '').strip()
    )


def whatsapp_env_status():
    from whatsapp_credentials import status
    return status()
