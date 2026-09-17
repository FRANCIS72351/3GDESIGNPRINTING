"""
3G DESIGN GLOBAL — Site URL & environment detection (local, VS port-forward, cloud).
"""
import os
import urllib.parse

# Public social / click-to-chat (footer, contact page — not WhatsApp Business API)
FACEBOOK_PAGE_URL = 'https://web.facebook.com/3gdesignprinting'
WHATSAPP_DEFAULT_CHAT_TEXT = (
    'Hello! I would like to inquire about your printing services.'
)

_BARE_PYTHONANYWHERE_HOSTS = frozenset({
    'pythonanywhere.com',
    'www.pythonanywhere.com',
})

# Canonical cloud host when env is missing/misconfigured
CANONICAL_CLOUD_SITE_URL = 'https://3gdesignglobal.com'


def _read_env_url(key):
    """Read an env var and normalize it as a public URL (strip whitespace, trailing slashes)."""
    raw = os.getenv(key)
    if not raw:
        return ''
    return _sanitize_public_url(str(raw).strip())


def _sanitize_public_url(url):
    """Reject malformed hosts (e.g. bare pythonanywhere.com without username subdomain)."""
    if not url:
        return ''
    raw = str(url).strip().rstrip('/')
    if not raw:
        return ''
    if '://' not in raw:
        raw = f'https://{raw}'
    parsed = urllib.parse.urlparse(raw)
    host = (parsed.hostname or '').lower()
    if host in _BARE_PYTHONANYWHERE_HOSTS:
        return ''
    if not host:
        return ''
    scheme = parsed.scheme or 'https'
    port = f':{parsed.port}' if parsed.port else ''
    path = parsed.path.rstrip('/') if parsed.path and parsed.path != '/' else ''
    return f'{scheme}://{host}{port}{path}'


def _pythonanywhere_site_url():
    """Build canonical PA URL from env vars PA sets or you configure explicitly."""
    for key in ('PYTHONANYWHERE_DOMAIN', 'PYTHONANYWHERE_SITE'):
        domain = os.environ.get(key, '').strip()
        if not domain:
            continue
        domain = domain.replace('https://', '').replace('http://', '').strip('/')
        if domain in _BARE_PYTHONANYWHERE_HOSTS:
            continue
        if '.' not in domain:
            continue
        return _sanitize_public_url(f'https://{domain}')
    return ''


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
    Priority: PUBLIC_SITE_URL → WEBHOOK_BASE_URL → PythonAnywhere → SITE_DOMAIN → request → cloud default → localhost.
    Never returns bare pythonanywhere.com (rejected by _sanitize_public_url).
    """
    for env_key in ('PUBLIC_SITE_URL', 'WEBHOOK_BASE_URL'):
        explicit = _read_env_url(env_key)
        if explicit:
            return explicit

    pa_url = _pythonanywhere_site_url()
    if pa_url:
        return pa_url

    sanitized = _read_env_url('SITE_DOMAIN')
    if sanitized:
        return sanitized

    if request_root:
        root = _sanitize_public_url(request_root.rstrip('/'))
        if root and not root.startswith('http://127.') and not root.startswith('http://localhost'):
            return root

    # Production / PA with empty env — never invent a bare host; use known shop URL
    if (
        os.environ.get('PYTHONANYWHERE_DOMAIN')
        or os.environ.get('PYTHONANYWHERE_SITE')
        or os.getenv('FLASK_ENV', '').lower() == 'production'
    ):
        return CANONICAL_CLOUD_SITE_URL

    port = os.getenv('APP_PORT', '5001')
    return f'http://127.0.0.1:{port}'


def get_whatsapp_webhook_url(request_root=None):
    return f"{get_public_site_url(request_root)}/api/whatsapp/webhook"


def get_twilio_webhook_url(path, request_root=None):
    """Build a canonical HTTPS Twilio callback URL from the public site URL."""
    normalized_path = '/' + str(path or '').lstrip('/')
    return f"{get_public_site_url(request_root)}{normalized_path}"


def validate_twilio_request(request):
    """Validate a Twilio signature against the canonical public callback URL."""
    if os.getenv('TWILIO_VALIDATE_SIGNATURE', 'true').lower() not in ('1', 'true', 'yes'):
        return True

    auth_token = os.getenv('TWILIO_AUTH_TOKEN', '').strip()
    signature = request.headers.get('X-Twilio-Signature', '').strip()
    if not auth_token or not signature:
        return False

    from twilio.request_validator import RequestValidator

    callback_url = get_twilio_webhook_url(
        request.path,
        request_root=request.url_root,
    )
    if request.query_string:
        callback_url = f'{callback_url}?{request.query_string.decode("utf-8")}'

    return RequestValidator(auth_token).validate(
        callback_url,
        request.form.to_dict(flat=True),
        signature,
    )


def is_production():
    return bool(
        os.environ.get('PYTHONANYWHERE_DOMAIN')
        or os.environ.get('PYTHONANYWHERE_SITE')
        or _read_env_url('PUBLIC_SITE_URL')
        or _read_env_url('WEBHOOK_BASE_URL')
    )


def whatsapp_env_status():
    from whatsapp_credentials import status
    return status()
