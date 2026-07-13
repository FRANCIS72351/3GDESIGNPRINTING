"""WSGI entry point for Gunicorn / production servers."""
import logging
import os
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

project_folder = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(project_folder, '.env'))

from app import app as application  # noqa: E402

_is_production = os.getenv('FLASK_ENV', '').lower() == 'production'

if _is_production:
    application.config['DEBUG'] = False
    application.config['PREFERRED_URL_SCHEME'] = 'https'
    from site_config import _read_env_url, _sanitize_public_url, CANONICAL_CLOUD_SITE_URL

    _public = _read_env_url('PUBLIC_SITE_URL')
    _pa = os.environ.get('PYTHONANYWHERE_DOMAIN', '').strip() or os.environ.get('PYTHONANYWHERE_SITE', '').strip()
    if _public:
        application.config['PUBLIC_SITE_URL'] = _public
    elif _pa:
        cleaned = _sanitize_public_url(
            f'https://{_pa.lstrip("https://").lstrip("http://").strip("/")}'
        )
        application.config['PUBLIC_SITE_URL'] = cleaned or CANONICAL_CLOUD_SITE_URL
    else:
        application.config['PUBLIC_SITE_URL'] = ''

    log_dir = os.getenv('LOG_DIR', os.path.join(project_folder, 'logs'))
    os.makedirs(log_dir, exist_ok=True)
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    handler = RotatingFileHandler(
        os.path.join(log_dir, 'olatricity.log'),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
    )
    handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s [%(name)s] %(message)s'
    ))
    application.logger.addHandler(handler)
    application.logger.setLevel(getattr(logging, log_level, logging.INFO))
else:
    application.config['DEBUG'] = True
