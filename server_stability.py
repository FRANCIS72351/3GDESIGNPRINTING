"""Helpers to keep the app stable under concurrent traffic."""
import gzip
import threading
import time
from datetime import datetime, timedelta
from io import BytesIO

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

_settings_cache = {'data': None, 'expires': None}
_settings_lock = threading.Lock()
SETTINGS_CACHE_SECONDS = 30


def configure_sqlite(app, db):
    """WAL mode + busy timeout so SQLite survives multi-threaded Waitress.

    Keep these pragmas. WAL lets many readers proceed together; writers still
    serialize, so this is capacity for reads, not thousands of concurrent writes.
    """
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


def _settings_snapshot(row):
    if row is None:
        return None
    return {
        'is_active': bool(row.is_active),
        'lock_message': row.lock_message,
    }


ABOUT_CONTENT_COLUMN_MIGRATIONS = [
    ('ad_title', "VARCHAR(150) DEFAULT ''"),
    ('ad_description', "TEXT DEFAULT ''"),
    ('ad_video_file', "VARCHAR(255) DEFAULT ''"),
]


PERFORMANCE_INDEXES = (
    ('ix_daily_report_date_posted', 'daily_report', 'date_posted'),
    ('ix_daily_report_report_date', 'daily_report', 'report_date'),
    ('ix_expense_timestamp', 'expense', 'timestamp'),
    ('ix_call_log_timestamp', 'call_log', 'timestamp'),
)


def ensure_performance_indexes(db):
    """Create high-traffic date indexes on existing SQLite tables (idempotent)."""
    from sqlalchemy import inspect, text

    tables = set(inspect(db.engine).get_table_names())
    with db.engine.begin() as conn:
        for index_name, table_name, column_name in PERFORMANCE_INDEXES:
            if table_name not in tables:
                continue
            conn.execute(text(
                f'CREATE INDEX IF NOT EXISTS {index_name} '
                f'ON "{table_name}" ({column_name})'
            ))


def ensure_table_columns(db, table_name, columns):
    """Add missing columns to an existing SQLite table (idempotent)."""
    from sqlalchemy import inspect, text

    if table_name not in inspect(db.engine).get_table_names():
        return

    with db.engine.begin() as conn:
        existing = {
            row[1]
            for row in conn.execute(text(f'PRAGMA table_info("{table_name}")'))
        }
        for col_name, col_type in columns:
            if col_name in existing:
                continue
            conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN {col_name} {col_type}'))


def ensure_about_content_schema(db, AboutContent):
    """Create about_content and add legacy columns on first use."""
    from sqlalchemy import inspect

    table_name = AboutContent.__tablename__
    if table_name not in inspect(db.engine).get_table_names():
        AboutContent.__table__.create(db.engine, checkfirst=True)
    ensure_table_columns(db, table_name, ABOUT_CONTENT_COLUMN_MIGRATIONS)


def get_about_content(db, AboutContent):
    """Return the singleton About page row, creating schema/row if needed."""
    ensure_about_content_schema(db, AboutContent)
    try:
        content = AboutContent.query.first()
    except OperationalError:
        db.session.rollback()
        ensure_about_content_schema(db, AboutContent)
        content = AboutContent.query.first()

    if content is None:
        content = AboutContent(description='', services='')
        db.session.add(content)
        commit_with_retry(db)
    return content


HOMEPAGE_CONTENT_COLUMN_MIGRATIONS = [
    ('title', "VARCHAR(200) DEFAULT ''"),
    ('video_heading', "VARCHAR(150) DEFAULT 'Advertisement / Events'"),
    ('video_caption', "TEXT DEFAULT ''"),
    ('video_url', "VARCHAR(500) DEFAULT ''"),
    ('banner_image', "VARCHAR(255) DEFAULT ''"),
    ('is_published', 'BOOLEAN DEFAULT 1'),
    ('updated_at', 'DATETIME'),
]


def ensure_homepage_content_schema(db, HomepageContent):
    """Create homepage_content and add missing columns on first use."""
    from sqlalchemy import inspect

    table_name = HomepageContent.__tablename__
    if table_name not in inspect(db.engine).get_table_names():
        HomepageContent.__table__.create(db.engine, checkfirst=True)
    ensure_table_columns(db, table_name, HOMEPAGE_CONTENT_COLUMN_MIGRATIONS)


def get_homepage_content(db, HomepageContent):
    """Return the singleton homepage promo row, creating schema/row if needed."""
    ensure_homepage_content_schema(db, HomepageContent)
    try:
        content = HomepageContent.query.first()
    except OperationalError:
        db.session.rollback()
        ensure_homepage_content_schema(db, HomepageContent)
        content = HomepageContent.query.first()

    if content is None:
        content = HomepageContent(
            title='',
            video_heading='Advertisement / Events',
            video_caption='watch this video',
            video_url='',
            banner_image='',
            is_published=True,
        )
        db.session.add(content)
        commit_with_retry(db)
    else:
        changed = False
        if (content.video_heading or '').strip() in ('', 'See What We Do'):
            content.video_heading = 'Advertisement / Events'
            changed = True
        if content.video_caption == 'Watch this short video to learn more about our services, process, and current offerings.':
            content.video_caption = 'watch this video'
            changed = True
        if changed:
            commit_with_retry(db)
    return content


def ensure_business_gallery_schema(db, BusinessGalleryImage):
    """Create business_gallery_image on first use."""
    from sqlalchemy import inspect

    table_name = BusinessGalleryImage.__tablename__
    if table_name not in inspect(db.engine).get_table_names():
        BusinessGalleryImage.__table__.create(db.engine, checkfirst=True)


def list_business_gallery_images(db, BusinessGalleryImage, published_only=True):
    """Return gallery rows, creating the table if the live database is older."""
    ensure_business_gallery_schema(db, BusinessGalleryImage)
    try:
        query = BusinessGalleryImage.query
        if published_only:
            query = query.filter_by(is_published=True)
        return query.order_by(
            BusinessGalleryImage.sort_order.asc(),
            BusinessGalleryImage.created_at.desc(),
        ).all()
    except OperationalError:
        db.session.rollback()
        ensure_business_gallery_schema(db, BusinessGalleryImage)
        query = BusinessGalleryImage.query
        if published_only:
            query = query.filter_by(is_published=True)
        return query.order_by(
            BusinessGalleryImage.sort_order.asc(),
            BusinessGalleryImage.created_at.desc(),
        ).all()


def ensure_system_settings(db, SystemSettings):
    """Create system_settings if missing and seed a default active row."""
    from sqlalchemy import inspect

    if 'system_settings' not in inspect(db.engine).get_table_names():
        SystemSettings.__table__.create(db.engine, checkfirst=True)

    try:
        row = SystemSettings.query.first()
    except OperationalError:
        db.session.rollback()
        SystemSettings.__table__.create(db.engine, checkfirst=True)
        row = SystemSettings.query.first()

    if row is None:
        row = SystemSettings(is_active=True)
        db.session.add(row)
        commit_with_retry(db)
    return row


def get_cached_system_settings(SystemSettings, ttl=SETTINGS_CACHE_SECONDS):
    now = datetime.utcnow()
    with _settings_lock:
        if _settings_cache['data'] is not None and _settings_cache['expires'] and _settings_cache['expires'] > now:
            return _settings_cache['data']

    from models import db

    try:
        row = SystemSettings.query.first()
    except OperationalError:
        invalidate_settings_cache()
        db.session.rollback()
        row = ensure_system_settings(db, SystemSettings)
    else:
        if row is None:
            row = ensure_system_settings(db, SystemSettings)

    snapshot = _settings_snapshot(row)
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


# ---------------------------------------------------------------------------
# HTTP payload tuning (slow/mobile networks + many concurrent readers)
# ---------------------------------------------------------------------------
_COMPRESSIBLE_TYPES = frozenset((
    'text/html',
    'text/css',
    'text/javascript',
    'text/plain',
    'text/xml',
    'application/javascript',
    'application/json',
    'application/xml',
    'application/xhtml+xml',
    'image/svg+xml',
))
_MIN_GZIP_BYTES = 500
_MAX_GZIP_BYTES = 2 * 1024 * 1024
_PRIVATE_PREFIXES = (
    '/admin',
    '/dashboard',
    '/moderator',
    '/staff',
    '/login',
    '/verify',
    '/setup-2fa',
    '/ghost',
    '/billing',
    '/operations',
    '/api/',
)
_late_check_lock = threading.Lock()
_late_check_next = 0.0
LATE_CHECK_SPAWN_SECONDS = 60


def schedule_late_staff_check(app, func, *args, interval=LATE_CHECK_SPAWN_SECONDS):
    """Spawn the daily late-staff job at most once per minute (not per request)."""
    global _late_check_next
    now = time.monotonic()
    with _late_check_lock:
        if now < _late_check_next:
            return False
        _late_check_next = now + interval
    run_in_background(app, func, *args)
    return True


def _response_mimetype(response):
    return (response.mimetype or '').split(';')[0].strip().lower()


def _apply_cache_headers(request, response):
    path = request.path or ''
    mime = _response_mimetype(response)

    if path == '/health' or path == '/media/homepage-video':
        response.headers['Cache-Control'] = 'no-store'
        return response

    if mime == 'text/html' or response.headers.get('Set-Cookie'):
        response.headers['Cache-Control'] = 'private, no-store'
        return response

    if any(path.startswith(prefix) for prefix in _PRIVATE_PREFIXES):
        response.headers['Cache-Control'] = 'private, no-store'
        return response

    if path.startswith('/static/uploads/'):
        response.headers['Cache-Control'] = 'public, max-age=86400'
        return response

    if path.endswith('/style.css') or path == '/static/style.css':
        response.headers['Cache-Control'] = 'no-store'
        return response

    if path.startswith('/static/img/') or path.startswith('/static/fonts/') or path == '/favicon.ico':
        response.headers['Cache-Control'] = 'public, max-age=604800'
        return response

    if path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=604800'
        return response

    if path.startswith('/media/'):
        response.headers['Cache-Control'] = 'public, max-age=86400'
        return response

    return response


def _maybe_gzip(request, response):
    """Compress text HTML/CSS/JS/JSON. Never buffer video/images or Range streams."""
    if response.status_code not in (200, 201):
        return response
    if request.method == 'HEAD':
        return response
    if request.headers.get('Range') or response.status_code == 206:
        return response
    if response.headers.get('Content-Encoding'):
        return response
    if 'gzip' not in (request.headers.get('Accept-Encoding') or '').lower():
        return response

    mime = _response_mimetype(response)
    if mime.startswith(('video/', 'image/', 'audio/')) or mime not in _COMPRESSIBLE_TYPES:
        return response

    length = response.calculate_content_length()
    if length is not None and (length < _MIN_GZIP_BYTES or length > _MAX_GZIP_BYTES):
        return response

    if getattr(response, 'direct_passthrough', False):
        # Flask send_file often has no Content-Length yet; only buffer
        # compressible text (CSS/JS), never unknown binary streams.
        if length is not None and length > _MAX_GZIP_BYTES:
            return response
        response.direct_passthrough = False

    data = response.get_data()
    if not data or len(data) < _MIN_GZIP_BYTES or len(data) > _MAX_GZIP_BYTES:
        return response

    buf = BytesIO()
    with gzip.GzipFile(mode='wb', fileobj=buf, compresslevel=5) as gz:
        gz.write(data)
    compressed = buf.getvalue()
    if len(compressed) >= len(data):
        return response

    response.set_data(compressed)
    response.headers['Content-Encoding'] = 'gzip'
    response.headers['Content-Length'] = str(len(compressed))
    vary = response.headers.get('Vary', '')
    if 'Accept-Encoding' not in vary:
        response.headers['Vary'] = (vary + ', Accept-Encoding').lstrip(', ')
    return response


def configure_http_performance(app):
    """Browser cache for static files + gzip for text. HTML/admin stay uncached."""
    from flask import request

    @app.after_request
    def _cache_and_compress(response):
        _apply_cache_headers(request, response)
        return _maybe_gzip(request, response)