"""Gunicorn configuration for production (EC2, Docker, ECS).

gthread workers (default 3 x 8 threads) cover a few thousand light reads.
SQLite still serializes writers — extra workers help static/HTML, not write QPS.
Override: GUNICORN_WORKERS, GUNICORN_THREADS, GUNICORN_TIMEOUT, GUNICORN_KEEPALIVE.
"""
import os

bind = os.getenv('GUNICORN_BIND', f"127.0.0.1:{os.getenv('APP_PORT', '8000')}")
workers = int(os.getenv('GUNICORN_WORKERS', '3'))
threads = int(os.getenv('GUNICORN_THREADS', '8'))
worker_class = 'gthread'
timeout = int(os.getenv('GUNICORN_TIMEOUT', '120'))
keepalive = int(os.getenv('GUNICORN_KEEPALIVE', '15'))
graceful_timeout = int(os.getenv('GUNICORN_GRACEFUL_TIMEOUT', '30'))
accesslog = os.getenv('GUNICORN_ACCESS_LOG', '-')
errorlog = os.getenv('GUNICORN_ERROR_LOG', '-')
loglevel = os.getenv('LOG_LEVEL', 'info').lower()
capture_output = True
wsgi_app = 'wsgi:application'
