"""Helpers to keep the app stable under concurrent traffic."""
import threading
import time
from datetime import datetime, timedelta

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

_settings_cache = {'data': None, 'expires': None}
_settings_lock = threading.Lock()
SETTINGS_CACHE_SECONDS = 30


def configure_sqlite(app, db):
    """WAL mode + busy timeout so SQLite survives multi-threaded Waitress."""
    app.config.setdefault(
        'SQLALCHEMY_ENGINE_OPTIONS',
        {
            'connect_args': {'timeout': 30, 'check_same_thread': False},
            'pool_pre_ping': True,
        },
    )

    @event.listens_for(Engine, 'connect')
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        import sqlite3
        if not isinstance(dbapi_connection, sqlite3.Connection):
            return
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA synchronous=NORMAL')
        cursor.execute('PRAGMA busy_timeout=30000')
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()

    @app.teardown_appcontext
    def _shutdown_session(exception=None):
        if exception is not None:
            db.session.rollback()
        db.session.remove()


def invalidate_settings_cache():
    with _settings_lock:
        _settings_cache['data'] = None
        _settings_cache['expires'] = None


def get_cached_system_settings(SystemSettings, ttl=SETTINGS_CACHE_SECONDS):
    now = datetime.utcnow()
    with _settings_lock:
        if _settings_cache['data'] is not None and _settings_cache['expires'] and _settings_cache['expires'] > now:
            return _settings_cache['data']

    row = SystemSettings.query.first()
    snapshot = None
    if row is not None:
        snapshot = {
            'is_active': bool(row.is_active),
            'lock_message': row.lock_message,
        }
    with _settings_lock:
        _settings_cache['data'] = snapshot
        _settings_cache['expires'] = now + timedelta(seconds=ttl)
    return snapshot


def run_in_background(app, func, *args, **kwargs):
    """Run slow I/O off the request thread (webhooks, transcription, alerts)."""
    from models import db

    def _wrapper():
        with app.app_context():
            try:
                func(*args, **kwargs)
            except Exception:
                app.logger.exception('Background task failed')
            finally:
                db.session.remove()

    thread = threading.Thread(target=_wrapper, daemon=True, name=f'bg-{func.__name__}')
    thread.start()
    return thread


def commit_with_retry(db, retries=5, base_delay=0.05):
    """Retry commits when SQLite reports database is locked."""
    for attempt in range(retries):
        try:
            db.session.commit()
            return
        except OperationalError as exc:
            db.session.rollback()
            if 'locked' not in str(exc).lower() or attempt >= retries - 1:
                raise
            time.sleep(base_delay * (attempt + 1))
