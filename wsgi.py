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
    application.config['PUBLIC_SITE_URL'] = os.getenv('PUBLIC_SITE_URL', '').strip()

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
