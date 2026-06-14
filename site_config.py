"""
3G DESIGN — Site URL & environment detection (local, VS port-forward, cloud).
"""
import os


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
