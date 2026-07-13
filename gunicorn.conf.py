"""Gunicorn configuration for production (EC2, Docker, ECS)."""
import os

bind = os.getenv('GUNICORN_BIND', f"127.0.0.1:{os.getenv('APP_PORT', '8000')}")
workers = int(os.getenv('GUNICORN_WORKERS', '2'))
threads = int(os.getenv('GUNICORN_THREADS', '4'))
worker_class = 'gthread'
timeout = int(os.getenv('GUNICORN_TIMEOUT', '120'))
keepalive = int(os.getenv('GUNICORN_KEEPALIVE', '5'))
graceful_timeout = int(os.getenv('GUNICORN_GRACEFUL_TIMEOUT', '30'))
accesslog = os.getenv('GUNICORN_ACCESS_LOG', '-')
errorlog = os.getenv('GUNICORN_ERROR_LOG', '-')
loglevel = os.getenv('LOG_LEVEL', 'info').lower()
capture_output = True
wsgi_app = 'wsgi:application'
