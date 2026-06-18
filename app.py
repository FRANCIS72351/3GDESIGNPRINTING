import os
import time
import math
import secrets
import pyotp
import qrcode
import io
import base64
import urllib.parse
from datetime import datetime, timedelta, time as datetime_time
from sqlalchemy import func
from twilio.twiml.voice_response import VoiceResponse
from flask import send_from_directory
# Removed flask_login import as we use a custom decorator
from flask import Flask, render_template, request, redirect, url_for, session

import assemblyai as aai

from werkzeug.utils import secure_filename
from flask import Flask, abort, request, jsonify, render_template, redirect, url_for, session, flash, Response, current_app
from markupsafe import Markup, escape
from dotenv import load_dotenv
from twilio.twiml.voice_response import VoiceResponse
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime

from models import db, Product, ProductVariant, Sale, CallLog, Leaders, Admin, AboutContent, Customer, Order, OrderItem, DailyReport, Attendance, User, InventoryLog, Expense, SystemSettings, LoginLog, GeneratedDocument, PendingReceipt, Event
from flask_mail import Mail, Message

from security_utils import ERPSecurity
security = ERPSecurity()

# ----------------------------------
# # 1. Define the Base Directory (The "Root" of your project)
# This ensures PythonAnywhere always finds your files
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

app = Flask(__name__, template_folder='static/uploads/template')

# 2. Security & Keys
app.secret_key = os.getenv('SECRET_KEY', 'fallback-key-for-dev-only')
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")

# 3. Database Alignment
# This points exactly to /home/FRANCIS72351/3G DESIGNPRINTING/3G_ERP_V1.db
# Updated for 3G Design Branding
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, '3G_ERP_V1.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {'timeout': 30, 'check_same_thread': False},
    'pool_pre_ping': True,
}

# ----------------------------------
# 4. Folder Architecture
# ----------------------------------
PORTAL_FOLDER = os.path.join(basedir, 'static/uploads/portal')
app.config['PORTAL_FOLDER'] = PORTAL_FOLDER
os.makedirs(PORTAL_FOLDER, exist_ok=True)

PRODUCT_FOLDER = os.path.join(basedir, 'static/uploads')
app.config['PRODUCT_FOLDER'] = PRODUCT_FOLDER
os.makedirs(PRODUCT_FOLDER, exist_ok=True)

# File upload settings for large storage capacity
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB limit

# 5. Mail System (Gmail Ghost Protocol)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')

# 6. Ghost Admin Identity
GHOST_USER = os.getenv('GHOST_ADMIN_USER')

# 7. Twilio (cloud voice/SMS) — optional
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
app.config['TWILIO_PHONE_NUMBER'] = os.getenv('TWILIO_PHONE_NUMBER')
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    try:
        from twilio.rest import Client
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    except Exception as e:
        print(f"Twilio init skipped: {e}")

# 8. Webhook base URL for Twilio (cloud) — set to ngrok/production URL
app.config['WEBHOOK_BASE_URL'] = os.getenv('WEBHOOK_BASE_URL', '').rstrip('/')

# 7. Initialize Extensions
db.init_app(app)
mail = Mail(app)

from server_stability import configure_sqlite, get_cached_system_settings, invalidate_settings_cache, run_in_background
configure_sqlite(app, db)

from call_tracking import call_bp
app.register_blueprint(call_bp)

from billing import billing_bp
app.register_blueprint(billing_bp)

from operations import operations_bp
app.register_blueprint(operations_bp)

from ai_chat import ai_chat_bp
app.register_blueprint(ai_chat_bp)

from staff_portal import staff_bp, run_late_staff_check_if_due, post_login_redirect
app.register_blueprint(staff_bp)


def _run_late_staff_check_safe(app_obj):
    run_late_staff_check_if_due(mail, app_obj)


def _static_url(filename):
    from flask import url_for
    return url_for('static', filename=filename)


@app.template_global()
def brand_lockup(variant='navy', extra_class=''):
    from brand_mark import brand_wordmark_markup
    return brand_wordmark_markup(_static_url, variant, extra_class, suffix=True, lockup=True)


@app.template_global()
def brand_wordmark(variant='navy', extra_class='', suffix=True):
    from brand_mark import brand_wordmark_markup
    return brand_wordmark_markup(_static_url, variant, extra_class, suffix)


@app.template_global()
def brand_name(name, variant='navy', extra_class=''):
    from brand_mark import brand_name_markup
    return brand_name_markup(name, _static_url, variant, extra_class)


@app.template_global()
def brand_wordmark_email(base_url, variant='navy', extra_class='', suffix=True):
    from brand_mark import brand_wordmark_email_markup
    return brand_wordmark_email_markup(base_url, variant, extra_class, suffix)


@app.template_filter('brandify')
def brandify_filter(text, variant='navy'):
    """Replace 3G Design with Ethnocentric wordmark markup."""
    from brand_mark import brandify_html
    return brandify_html(text, _static_url, variant=variant)


# ----------------------------------
# Production Configuration for PythonAnywhere
# ----------------------------------
# Force HTTPS in production
# if os.environ.get('PYTHONANYWHERE_DOMAIN'):
#     # Running on PythonAnywhere - force HTTPS
#     from flask_sslify import SSLify
#     sslify = SSLify(app)

# Ensure URLs are generated with correct scheme
app.config['PREFERRED_URL_SCHEME'] = 'https' if os.environ.get('PYTHONANYWHERE_DOMAIN') else 'http'
with app.app_context():
    db.create_all()
    from sqlalchemy import text
    with db.engine.connect() as conn:
        # Tables and their required columns
        migrations = {
            'product': [
                ("currency", "VARCHAR(10) DEFAULT 'USD'")
            ],
            'product_variant': [
                ("image", "VARCHAR(120)"),
                ("currency", "VARCHAR(10) DEFAULT 'USD'"),
                ("type_value", "VARCHAR(50)")
            ],
            'admin': [
                ("last_login_at", "DATETIME"),
                ("last_login_ip", "VARCHAR(100)"),
                ("time_drift", "INTEGER DEFAULT 0")
            ],
            'order': [
                ("order_source", "VARCHAR(50)"),
                ("date_ordered", "DATETIME"),
                ("production_stage", "VARCHAR(20) DEFAULT 'quote'"),
                ("promised_date", "DATE"),
                ("notes", "TEXT"),
            ],
            'call_log': [
                ("caller_name", "VARCHAR(100)"),
                ("notes", "TEXT"),
                ("source", "VARCHAR(30) DEFAULT 'local_desktop'"),
                ("call_type", "VARCHAR(20) DEFAULT 'voice'"),
                ("status", "VARCHAR(20) DEFAULT 'logged'"),
                ("duration_seconds", "INTEGER"),
                ("call_sid", "VARCHAR(64)"),
                ("logged_by", "VARCHAR(50)"),
            ],
            'generated_document': [
                ("order_id", "INTEGER"),
                ("customer_name", "VARCHAR(100)"),
                ("total_amount", "FLOAT DEFAULT 0"),
                ("currency", "VARCHAR(3) DEFAULT 'USD'"),
                ("payment_status", "VARCHAR(20) DEFAULT 'Pending'"),
            ],
            'pending_receipt': [
                ("status", "VARCHAR(20) DEFAULT 'pending'"),
                ("order_id", "INTEGER"),
            ],
            'event': [
                ("event_type", "VARCHAR(50)"),
                ("description", "TEXT"),
            ],
            'system_settings': [
                ("last_late_check_date", "DATE"),
            ],
        }
        
        for table, columns in migrations.items():
            for col_name, col_type in columns:
                try:
                    # Check if column exists
                    conn.execute(text(f'SELECT {col_name} FROM "{table}" LIMIT 1'))
                except Exception:
                    # Column doesn't exist, add it
                    try:
                        conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {col_name} {col_type}'))
                        conn.commit()
                        print(f"Added column {col_name} to {table}")
                    except Exception as e:
                        print(f"Error adding {col_name} to {table}: {e}")
# ----------------------------------
# Auth Decorator
# ----------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ----------------------------------
def role_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'admin_logged_in' not in session:
                return redirect(url_for('login'))
            user_role = session.get('role', 'staff')
            if user_role not in roles:
                flash(f"Unauthorized. Your role ({user_role}) does not have access to this area.", "danger")
                if user_role == 'staff':
                    return redirect(url_for('staff.staff_portal'))
                return redirect(url_for('home'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ----------------------------------
# System Status Check
# ----------------------------------
@app.errorhandler(500)
def handle_internal_error(error):
    db.session.rollback()
    current_app.logger.exception('Unhandled server error')
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error'}), 500
    flash('Something went wrong. Please try again.', 'danger')
    return redirect(request.referrer or url_for('home')), 302


@app.before_request
def check_system_status():
    # 1. Allow access to the Ghost Dashboard so YOU can turn it back on
    # 2. Allow access to static files (CSS/Images)
    if ('ghost-protocol' in request.path or request.path.startswith('/static')
            or request.path == '/login'
            or request.path.startswith('/order/receipt')
            or request.path.startswith('/order/share')
            or request.path in ('/voice', '/handle-recording')
            or request.path.startswith('/api/communications')
            or request.path.startswith('/api/whatsapp')
            or request.path.startswith('/api/web/chat')):
        return
    # Check if system is deactivated in DB (cached to avoid a query on every hit)
    settings = get_cached_system_settings(SystemSettings)
    if settings and not settings.get('is_active', True):
        return render_template('system_locked.html', message=settings.get('lock_message')), 403

    if not request.path.startswith('/static'):
        run_in_background(app, _run_late_staff_check_safe, app)

# ----------------------------------
# Public Routes
# ----------------------------------
@app.route('/')
def home():
    category_filter = request.args.get('category')
    if category_filter:
        products = Product.query.filter(Product.category.ilike(f"%{category_filter}%")).all()
    else:
        products = Product.query.all()
    return render_template('home.html', products=products, current_category=category_filter)

@app.route('/contact')
def contact():
    return render_template('contact.html')

#---------------------------------
# favicon route to prevent 404 error 
#----------------------------------
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon',
    )
#-----------------------------------
# event route for the system
#----------------------------------
@app.route('/events', methods=['GET', 'POST'])
@login_required
def event_portal():
    """
    Business Event Portal: Handles both displaying milestones
    and registering new ones cleanly.
    """
    if request.method == 'POST':
        title = request.form.get('title')
        event_date_str = request.form.get('date')
        event_type = request.form.get('event_type')
        description = request.form.get('description')

        if not title or not event_date_str:
            flash("Missing mandatory fields: Title and Date are required.", "danger")
            return redirect(url_for('event_portal'))

        try:
            # Parse HTML date format to Python Date object
            event_date = datetime.strptime(event_date_str, '%Y-%m-%d').date()
            
            # Construct model mapping
            new_event = Event(
                title=title,
                date=event_date,
                event_type=event_type, # Captures 'Holiday', 'Birthday', or 'Anniversary'
                description=description
            )
            
            db.session.add(new_event)
            db.session.commit()
            flash(f"Success: '{title}' has been registered.", "success")
            return redirect(url_for('event_portal'))
            
        except Exception as e:
            db.session.rollback()
            flash(f"Error compiling operational database log: {str(e)}", "danger")
            return redirect(url_for('event_portal'))

    # GET Request: Fetch milestones sorted by earliest upcoming date first
    try:
        events = Event.query.order_by(Event.date.asc()).all()
    except Exception:
        events = [] # Safe fallback if table structure is empty on initial render

    return render_template("events.html", events=events, today=datetime.today().date())
# ----------------------------------
# Shopping Cart Logic
# ----------------------------------

from order_share import build_whatsapp_text, generate_order_image, try_notify_shop_via_api

WHATSAPP_NUMBER = os.getenv('WHATSAPP_NUMBER', '+231775323731').replace(' ', '')


def get_public_base_url():
    """Public URL for images, webhooks, and share links."""
    from site_config import get_public_site_url
    return get_public_site_url(request.url_root if request else None)


def normalize_image_filename(image_value):
    if not image_value:
        return ''
    value = str(image_value).strip()
    if value.startswith('http'):
        return value
    value = value.replace('\\', '/')
    for prefix in ('/static/uploads/', 'static/uploads/', '/uploads/', 'uploads/'):
        if value.startswith(prefix):
            return value[len(prefix):]
    return value.lstrip('/')


def absolute_product_image_url(image_value):
    normalized = normalize_image_filename(image_value)
    if not normalized:
        return f"{get_public_base_url()}/static/img/LOGO.png"
    if normalized.startswith('http'):
        return normalized
    return f"{get_public_base_url()}/static/uploads/{normalized}"


def enrich_cart_item(item):
    image_file = normalize_image_filename(item.get('image', ''))
    return {
        **item,
        'image': image_file,
        'image_url': absolute_product_image_url(image_file),
    }


def product_stock_level(product):
    """Canonical stock — keeps stock and stock_quantity in sync."""
    if product.stock is not None:
        return product.stock
    return product.stock_quantity or 0


def adjust_product_stock(product, delta):
    level = product_stock_level(product) + delta
    product.stock = level
    product.stock_quantity = level
    return level


def finalize_whatsapp_order(cart_items):
    """Create order image + text, save record, optionally notify shop via API."""
    import json
    enriched = []
    for raw in cart_items:
        image_file = normalize_image_filename(raw.get('image', ''))
        enriched.append({
            **raw,
            'image': image_file,
            'image_url': absolute_product_image_url(image_file),
        })

    token = secrets.token_urlsafe(16)
    message_text = build_whatsapp_text(enriched)
    image_rel = generate_order_image(enriched, token, app.root_path)

    total_usd = sum(i['price'] * i['quantity'] for i in enriched if i.get('currency') == 'USD')
    total_lrd = sum(i['price'] * i['quantity'] for i in enriched if i.get('currency') == 'LRD')
    payload = {
        'items': enriched,
        'total_usd': round(total_usd, 2),
        'total_lrd': round(total_lrd, 2),
        'message_text': message_text,
        'share_image': image_rel,
    }
    receipt = PendingReceipt(token=token, payload=json.dumps(payload))
    db.session.add(receipt)
    db.session.commit()

    app_obj = app._get_current_object()
    run_in_background(app_obj, try_notify_shop_via_api, enriched, message_text, image_rel, app_obj.root_path)
    return token, message_text, image_rel


@app.route('/add-to-cart', methods=['POST'])
def add_to_cart():
    product_id = request.form.get('product_id')
    variant_name = request.form.get('variant_name', 'Base')
    price = float(request.form.get('price', 0))
    currency = request.form.get('currency', 'USD')
    image = normalize_image_filename(request.form.get('image', ''))
    product_name = request.form.get('product_name', '')

    if 'cart' not in session:
        session['cart'] = []
    
    cart = session['cart']
    found = False
    for item in cart:
        if item['product_id'] == product_id and item['variant_name'] == variant_name:
            item['quantity'] += 1
            found = True
            break
    
    if not found:
        cart.append({
            'product_id': product_id,
            'product_name': product_name,
            'variant_name': variant_name,
            'price': price,
            'currency': currency,
            'image': image,
            'quantity': 1
        })
    
    session['cart'] = cart
    session.modified = True
    flash(f"Added {product_name} ({variant_name}) to cart.", "success")
    return redirect(request.referrer or url_for('home'))

@app.route('/cart')
def view_cart():
    cart = session.get('cart', [])
    total_usd = sum(item['price'] * item['quantity'] for item in cart if item['currency'] == 'USD')
    total_lrd = sum(item['price'] * item['quantity'] for item in cart if item['currency'] == 'LRD')
    return render_template('cart.html', cart=cart, total_usd=total_usd, total_lrd=total_lrd)

@app.route('/remove-from-cart/<int:index>')
def remove_from_cart(index):
    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        item = cart.pop(index)
        session['cart'] = cart
        session.modified = True
        flash(f"Removed {item['product_name']} from cart.", "info")
    return redirect(url_for('view_cart'))
# -----------------------------------------------------------------
# WhatsApp checkout with visual receipt page
@app.route('/prepare-whatsapp-order', methods=['POST'])
def prepare_whatsapp_order():
    """Single-product Order Now → visual receipt link in WhatsApp."""
    qty = max(1, int(request.form.get('quantity', 1) or 1))
    item = {
        'product_id': request.form.get('product_id'),
        'product_name': request.form.get('product_name', ''),
        'variant_name': request.form.get('variant_name', 'Original Design'),
        'price': float(request.form.get('price', 0)),
        'currency': request.form.get('currency', 'USD'),
        'image': normalize_image_filename(request.form.get('image', '')),
        'quantity': qty,
    }
    if not item['product_name']:
        flash('Product details missing.', 'warning')
        return redirect(request.referrer or url_for('home'))

    token, message_text, image_rel = finalize_whatsapp_order([item])
    return redirect(url_for('order_share_page', token=token))


@app.route('/order/share/<token>')
def order_share_page(token):
    import json
    receipt = PendingReceipt.query.filter_by(token=token).first_or_404()
    data = json.loads(receipt.payload)
    image_rel = data.get('share_image', '')
    message_text = data.get('message_text', build_whatsapp_text(data.get('items', [])))
    image_url = url_for('static', filename=f'uploads/{image_rel}') if image_rel else url_for('static', filename='img/LOGO.png')
    phone = WHATSAPP_NUMBER.lstrip('+')
    wa_fallback_url = f"https://wa.me/{phone}?text={urllib.parse.quote(message_text)}"
    return render_template(
        'order_share.html',
        token=token,
        message_text=message_text,
        image_url=image_url,
        wa_phone=phone,
        wa_fallback_url=wa_fallback_url,
    )


@app.route('/order/receipt/<token>')
def order_receipt(token):
    import json
    receipt = PendingReceipt.query.filter_by(token=token).first_or_404()
    data = json.loads(receipt.payload)
    items = data.get('items', [])
    preview_image = f"{get_public_base_url()}/static/img/LOGO.png"
    if items:
        first = items[0]
        preview_image = first.get('image_url') or absolute_product_image_url(first.get('image'))
    item_count = len(items)
    title = f"Order — {item_count} item{'s' if item_count != 1 else ''} · 3G Design"
    description = ', '.join(i['product_name'] for i in items[:3])
    if item_count > 3:
        description += f' +{item_count - 3} more'
    return render_template(
        'order_receipt.html',
        receipt=receipt,
        data=data,
        items=items,
        og_title=title,
        og_description=description,
        og_image=preview_image,
        og_url=f"{get_public_base_url()}/order/receipt/{token}",
    )


@app.route('/checkout-whatsapp')
def checkout_whatsapp():
    cart = session.get('cart', [])
    if not cart:
        flash("Your cart is empty.", "warning")
        return redirect(url_for('home'))

    token, _, _ = finalize_whatsapp_order(cart)
    session.pop('cart', None)
    return redirect(url_for('order_share_page', token=token))

# ----------------------------------
# TWILIO: Answer Call & Record (Cloud)
# Requires WEBHOOK_BASE_URL in .env when not on PythonAnywhere
# ----------------------------------
@app.route("/voice", methods=['POST'])
def voice():
    response = VoiceResponse()
    response.say("Welcome to 3G Design. Your call is being recorded for order accuracy.")

    call_sid = request.form.get('CallSid')
    from_number = request.form.get('From', 'Unknown')

    try:
        incoming = CallLog(
            phone_number=from_number,
            call_sid=call_sid,
            source='twilio_cloud',
            call_type='voice',
            status='received',
            notes='Incoming cloud call',
        )
        db.session.add(incoming)
        db.session.commit()
    except Exception:
        db.session.rollback()

    recording_action = url_for('handle_recording', _external=True)
    if app.config.get('WEBHOOK_BASE_URL'):
        recording_action = f"{app.config['WEBHOOK_BASE_URL']}/handle-recording"

    response.record(action=recording_action, maxLength=120, transcribe=False)
    return str(response), 200, {'Content-Type': 'text/xml'}


@app.route("/handle-recording", methods=['POST'])
def handle_recording():
    recording_url = request.form.get('RecordingUrl')
    from_number = request.form.get('From', 'Unknown')
    call_sid = request.form.get('CallSid')
    duration = request.form.get('RecordingDuration')

    if not recording_url:
        current_app.logger.warning("No recording URL received from Twilio.")
        return "No recording found", 400

    run_in_background(app._get_current_object(), _process_call_recording, recording_url, from_number, call_sid, duration)
    return "OK", 200


def _process_call_recording(recording_url, from_number, call_sid, duration):
    transcript_text = None
    if os.getenv("ASSEMBLYAI_API_KEY"):
        try:
            transcriber = aai.Transcriber()
            transcript = transcriber.transcribe(recording_url)
            if transcript.status != aai.TranscriptStatus.error:
                transcript_text = transcript.text
            else:
                current_app.logger.error(f"Transcription Error: {transcript.error}")
        except Exception as e:
            current_app.logger.error(f"Transcription skipped: {e}")

    try:
        existing = CallLog.query.filter_by(call_sid=call_sid).first() if call_sid else None
        if existing:
            existing.transcript = transcript_text
            existing.audio_url = recording_url
            existing.status = 'processed'
            existing.duration_seconds = int(duration) if duration and str(duration).isdigit() else None
            existing.notes = 'Cloud recording processed'
        else:
            new_call = CallLog(
                phone_number=from_number,
                transcript=transcript_text,
                audio_url=recording_url,
                call_sid=call_sid,
                source='twilio_cloud',
                call_type='voice',
                status='processed',
                duration_seconds=int(duration) if duration and str(duration).isdigit() else None,
                notes='Cloud recording via Twilio',
            )
            db.session.add(new_call)

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to save recording log: {e}")

# ----------------------------------
# Exponential Backoff Helper
# ----------------------------------
def calculate_backoff(fail_count):
    return math.pow(2, fail_count) if fail_count > 0 else 0

# ----------------------------------
# File Upload Configuration
# ----------------------------------
UPLOAD_FOLDER = 'static/uploads/leaders'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/admin/file-portal')
@login_required
def file_portal():
    search_query = request.args.get('search', '').lower()
    selected_date = request.args.get('date', '')
    
    # Get all date folders
    try:
        all_items = os.listdir(app.config['PORTAL_FOLDER'])
        date_folders = [item for item in all_items if os.path.isdir(os.path.join(app.config['PORTAL_FOLDER'], item))]
        date_folders.sort(reverse=True)  # Most recent first
    except:
        date_folders = []
    
    files = []
    if selected_date and selected_date in date_folders:
        # List all files and folders in selected date folder recursively
        date_path = os.path.join(app.config['PORTAL_FOLDER'], selected_date)
        try:
            all_files = []
            for root, dirs, filenames in os.walk(date_path):
                for filename in filenames:
                    rel_path = os.path.relpath(os.path.join(root, filename), date_path)
                    all_files.append(rel_path)
            
            if search_query:
                files = [f for f in all_files if search_query in f.lower()]
            else:
                files = all_files
        except:
            files = []
    elif search_query:
        # Search across all date folders
        files = []
        for date_folder in date_folders:
            date_path = os.path.join(app.config['PORTAL_FOLDER'], date_folder)
            try:
                all_files = []
                for root, dirs, filenames in os.walk(date_path):
                    for filename in filenames:
                        rel_path = os.path.relpath(os.path.join(root, filename), date_path)
                        all_files.append(rel_path)
                
                matching_files = [f"{date_folder}/{f}" for f in all_files if search_query in f.lower()]
                files.extend(matching_files)
            except:
                pass
    
    return render_template('file_portal.html', 
                         date_folders=date_folders, 
                         files=files, 
                         search_query=search_query, 
                         selected_date=selected_date)

@app.route('/portal/upload', methods=['GET', 'POST'])
@login_required
def upload_file():
    if request.method == 'GET':
        return redirect(url_for('file_portal'))

    if 'files' not in request.files:
        flash('No files selected', 'error')
        return redirect(url_for('file_portal'))
    
    files = request.files.getlist('files')
    if not files or all(file.filename == '' for file in files):
        flash('No files selected', 'error')
        return redirect(url_for('file_portal'))
    
    # Determine the date folder
    selected_date = request.args.get('date')
    if selected_date:
        date_folder_name = selected_date
    else:
        date_folder_name = datetime.now().strftime('%Y-%m-%d')
    
    date_folder = os.path.join(app.config['PORTAL_FOLDER'], date_folder_name)
    os.makedirs(date_folder, exist_ok=True)
    
    uploaded_count = 0
    for file in files:
        if file and file.filename:
            # Check if it's a folder upload (has webkitRelativePath)
            relative_path = getattr(file, 'webkitRelativePath', file.filename)
            
            # Create subdirectories if needed
            full_path = os.path.join(date_folder, relative_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            file.save(full_path)
            uploaded_count += 1
    
    if uploaded_count > 0:
        flash(f"Successfully uploaded {uploaded_count} file(s) to {date_folder_name} folder!", 'success')
    else:
        flash('No files were uploaded', 'warning')
    
    return redirect(url_for('file_portal', date=selected_date))

# Billing routes are in billing.py (invoices, receipts, admin_portal, PDF generation)

def roles_required(*roles):
    def wrapper(f):
        @wraps(f)
        def decorated_view(*args, **kwargs):
            if session.get('role') not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_view
    return wrapper


@app.route('/direct-sale-history')
@roles_required('admin', 'moderator')
def direct_sale_history():
    search = request.args.get('search', '')
    query = Order.query

    if search:
        query = query.outerjoin(Customer).filter(
            (Customer.name.ilike(f"%{search}%")) |
            (Order.status.ilike(f"%{search}%")) |
            (Order.order_source.ilike(f"%{search}%"))
        )

    orders = query.order_by(Order.date_ordered.desc()).limit(150).all()
    return render_template("direct_sale_history.html", orders=orders, search=search)


@app.route("/admin/leader/edit/<int:leader_id>", methods=['GET', 'POST'])
@login_required
def edit_leader(leader_id):
    current_admin = Admin.query.get(session.get('admin_id'))
    if current_admin.role != 'admin':
        flash('Permission denied. Only Admins can edit team members.', 'danger')
        return redirect(url_for('about'))

    leader = Leaders.query.get_or_404(leader_id)
    if request.method == 'POST':
        leader.name = request.form.get('name')
        leader.position = request.form.get('position')
        leader.bio = request.form.get('bio')
        leader.email = request.form.get('email')
        leader.contact = request.form.get('contact')
        file = request.files.get('image')
        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            leader.image = filename

        db.session.commit()
        flash('Leader updated successfully!', 'success')
        return redirect(url_for('leader_management'))

    return render_template('edit_leader.html', leader=leader)

@app.route("/admin/leader/delete/<int:leader_id>", methods=['POST'])
@login_required
def delete_leader(leader_id):
    current_admin = Admin.query.get(session.get('admin_id'))
    if current_admin.role != 'admin':
        flash('Permission denied. Only Admins can delete team members.', 'danger')
        return redirect(url_for('about'))

    leader = Leaders.query.get_or_404(leader_id)
    db.session.delete(leader)
    db.session.commit()
    flash('Leader removed successfully.', 'success')
    return redirect(url_for('leader_management'))

# ----------------------------------
# Leader Management
# ----------------------------------
@app.route("/admin/leader-management")
@login_required
def leader_management():
    current_admin = Admin.query.get(session.get('admin_id'))
    if current_admin.role != 'admin':
        flash('Permission denied. Only Admins can manage team members.', 'danger')
        return redirect(url_for('dashboard'))
    
    leaders = Leaders.query.all()
    return render_template('leader_management.html', leaders=leaders)
#-----------------------------------
# admin alert: inventory low
#-------------------------------------
@app.route('/add-sale', methods=['POST'])
@login_required
def add_sale():
    product_id = request.form.get('product_id', type=int)
    quantity_sold = request.form.get('quantity', type=int) or request.form.get('quantity_sold', type=int)

    if not product_id or not quantity_sold or quantity_sold <= 0:
        flash('Invalid sale: product and quantity are required.', 'danger')
        return redirect(url_for('dashboard'))

    product = Product.query.get(product_id)
    if not product:
        flash('Product not found.', 'danger')
        return redirect(url_for('dashboard'))

    current_stock = product_stock_level(product)
    if current_stock < quantity_sold:
        flash(f'Insufficient stock for {product.name} (have {current_stock}).', 'danger')
        return redirect(url_for('dashboard'))

    adjust_product_stock(product, -quantity_sold)
    unit_price = product.price or 0
    sale = Sale(
        amount=round(unit_price * quantity_sold, 2),
        currency=product.currency or 'USD',
    )
    db.session.add(sale)
    db.session.commit()

    check_inventory_alerts(product)
    trigger_order_sms(sale)
    flash(f'Sale recorded: {quantity_sold}× {product.name}.', 'success')
    return redirect(url_for('dashboard'))

ADMIN_PHONE = '+231881669599'  # Replace with your actual phone number

def check_inventory_alerts(product):
    """Checks if stock is low and sends an alert to the Admin."""
    level = product_stock_level(product)
    if level <= (product.min_stock_threshold or 0):
        message_body = (
            f"⚠️ 3G Design INVENTORY ALERT ⚠️\n"
            f"Item: {product.name} is running low!\n"
            f"Current Stock: {level}\n"
            f"Threshold: {product.min_stock_threshold}\n"
            f"Please restock soon to avoid missing sales."
        )

        try:
            if twilio_client and app.config.get('TWILIO_PHONE_NUMBER'):
                twilio_client.messages.create(
                    body=message_body,
                    from_=app.config['TWILIO_PHONE_NUMBER'],
                    to=ADMIN_PHONE
                )
                print(f"Low stock alert sent for {product.name}")
        except Exception as e:
            print(f"Failed to send inventory alert: {e}")

#-------------------------------------
#sales status for admin and moderator
#-------------------------------------
def trigger_order_sms(sale):
    """Send order confirmation SMS via Twilio; accepts Sale object or sale id."""
    if isinstance(sale, int):
        sale = Sale.query.get(sale)
    if not sale:
        return

    customer = sale.customer if sale.customer_id else None
    phone = customer.phone if customer else None
    if not phone or not str(phone).startswith('+'):
        return

    name = customer.name if customer else 'Customer'
    amount = sale.amount or 0
    message_body = (
        f"3G Design: Order #{sale.id} confirmed for ${amount:.2f}. "
        f"Thank you, {name}!"
    )

    try:
        if twilio_client and app.config.get('TWILIO_PHONE_NUMBER'):
            twilio_client.messages.create(
                body=message_body,
                from_=app.config['TWILIO_PHONE_NUMBER'],
                to=phone,
            )
        sale.sms_status = "Sent"
    except Exception as e:
        print(f"SMS Error: {e}")
        sale.sms_status = "Failed"

    db.session.commit()

@app.route("/admin/staff-sales")
@login_required
def staff_sales_history():
    # Show personal sales history for the logged-in staff
    staff_id = session.get('admin_id')
    reports = DailyReport.query.filter_by(staff_id=staff_id).order_by(DailyReport.date_posted.desc()).all()
    return render_template('staff_sales.html', reports=reports)

# ----------------------------------
# Admin: Add Leader
# ----------------------------------
@app.route("/admin/add_leader", methods=['GET', 'POST'])
@login_required
def add_leader():
    if request.method == 'POST':
        name = request.form.get('name')
        position = request.form.get('position')
        bio = request.form.get('bio')
        email = request.form.get('email')
        contact = request.form.get('contact')
        file = request.files.get('image')
        filename = None
        if file and file.filename:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        new_leader = Leaders(name=name, position=position, bio=bio, email=email, contact=contact, image=filename)
        db.session.add(new_leader)
        db.session.commit()
        flash('Team member added successfully.', 'success')
        return redirect(url_for('leader_management'))

    return render_template('admin_leader.html')

@app.route("/about")
def about():
    leaders = Leaders.query.all()
    content = AboutContent.query.first()
    return render_template("about.html", leaders=leaders, content=content)

# ----------------------------------
# Admin: About Settings
# ----------------------------------
@app.route("/admin/about-settings", methods=['GET', 'POST'])
@login_required
def about_settings():
    content = AboutContent.query.first()
    if not content:
        content = AboutContent(description="", services="")
        db.session.add(content)
        db.session.commit()

    if request.method == 'POST':
        content.description = request.form.get('description')
        content.services = request.form.get('service')

        for i in range(1, 4):
            file = request.files.get(f'slider{i}')
            if file:
                filename = secure_filename(file.filename)
                file.save(os.path.join('static/img', filename))
                setattr(content, f'slider{i}', filename)

        db.session.commit()
        return redirect(url_for('about'))

    return render_template('admin_about.html', content=content)

@app.route("/admin/financials")
@login_required
def financials():
    # Get filters
    period = request.args.get('period', 'daily') # daily, weekly
    
    from datetime import timedelta
    now = datetime.utcnow()
    
    if period == 'weekly':
        start_date = now - timedelta(days=7)
    else:
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Fetch Sales (Income) and Expenses
    sales_recs = DailyReport.query.filter(DailyReport.date_posted >= start_date).order_by(DailyReport.date_posted.desc()).all()
    expenses = Expense.query.filter(Expense.timestamp >= start_date).order_by(Expense.timestamp.desc()).all()
    
    total_income_usd = sum(s.total_sales for s in sales_recs if s.currency == 'USD')
    total_income_lrd = sum(s.total_sales for s in sales_recs if s.currency == 'LRD')
    total_expense_usd = sum(e.amount for e in expenses if e.currency == 'USD')
    total_expense_lrd = sum(e.amount for e in expenses if e.currency == 'LRD')
    
    admin_user = Admin.query.get(session.get('admin_id'))
    return render_template('financials.html', 
                         sales=sales_recs, 
                         expenses=expenses, 
                         total_income_usd=total_income_usd, 
                         total_income_lrd=total_income_lrd, 
                         total_expense_usd=total_expense_usd, 
                         total_expense_lrd=total_expense_lrd, 
                         period=period,
                         admin=admin_user)

@app.route("/admin/expense/add", methods=['POST'])
@login_required
def add_expense():
    amount = float(request.form.get('amount', 0))
    description = request.form.get('description')
    currency = request.form.get('currency', 'USD')
    
    new_expense = Expense(
        amount=amount,
        description=description,
        currency=currency,
        recorded_by=session.get('admin_id')
    )
    
    db.session.add(new_expense)
    db.session.commit()
    flash('Expense recorded successfully.', 'success')
    return redirect(url_for('financials'))

@app.route("/admin/expense/edit/<int:expense_id>", methods=['GET', 'POST'])
@login_required
def edit_expense(expense_id):
    current_admin = Admin.query.get(session.get('admin_id'))
    if current_admin.role != 'admin':
        flash('Permission denied. Only Admins can edit expenses.', 'danger')
        return redirect(url_for('financials'))

    expense = Expense.query.get_or_404(expense_id)
    if request.method == 'POST':
        expense.amount = float(request.form.get('amount'))
        expense.description = request.form.get('description')
        expense.currency = request.form.get('currency', 'USD')
        db.session.commit()
        flash('Expense updated successfully.', 'success')
        return redirect(url_for('financials'))
    
    return render_template('edit_expense.html', expense=expense)

@app.route("/admin/sale/edit/<int:report_id>", methods=['GET', 'POST'])
@login_required
def edit_sale(report_id):
    current_admin = Admin.query.get(session.get('admin_id'))
    if current_admin.role != 'admin':
        flash('Permission denied. Only Admins can edit sales.', 'danger')
        return redirect(url_for('financials'))

    report = DailyReport.query.get_or_404(report_id)
    if request.method == 'POST':
        report.total_sales = float(request.form.get('total_sales'))
        report.report_text = request.form.get('report_text')
        report.currency = request.form.get('currency', 'USD')
        db.session.commit()
        flash('Sale report updated successfully.', 'success')
        return redirect(url_for('financials'))
    
    return render_template('edit_sale.html', report=report)

@app.route("/admin/user/delete/<int:user_id>", methods=['POST'])
@login_required
def delete_user(user_id):
    current_admin = Admin.query.get(session.get('admin_id'))
    if current_admin.role != 'admin':
        flash('Permission denied. Only Admins can manage users.', 'danger')
        return redirect(url_for('team_management'))

    user_to_delete = Admin.query.get_or_404(user_id)
    
    # Prevent admin from deleting themselves
    if user_to_delete.id == current_admin.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('team_management'))
    
    # Prevent deleting the ghost user
    if user_to_delete.username == GHOST_USER:
        flash('Cannot delete system user.', 'danger')
        return redirect(url_for('team_management'))

    db.session.delete(user_to_delete)
    db.session.commit()
    flash(f'User {user_to_delete.username} deleted successfully.', 'success')
    return redirect(url_for('team_management'))

@app.route("/admin/user/reset-password/<int:user_id>", methods=['POST'])
@login_required
def reset_user_password(user_id):
    current_admin = Admin.query.get(session.get('admin_id'))
    # Only ghost user can reset passwords
    if current_admin.username != GHOST_USER:
        flash('Permission denied. Only the system administrator can reset passwords.', 'danger')
        return redirect(url_for('team_management'))

    user_to_reset = Admin.query.get_or_404(user_id)
    
    # Prevent resetting ghost user's own password
    if user_to_reset.username == GHOST_USER:
        flash('Cannot reset system user password.', 'danger')
        return redirect(url_for('team_management'))

    # Generate a temporary password
    import secrets
    temp_password = secrets.token_urlsafe(12)
    hashed_pw = generate_password_hash(temp_password, method='pbkdf2:sha256')
    user_to_reset.password_hash = hashed_pw
    
    # Disable 2FA to allow login with new password
    user_to_reset.two_fa_enabled = False
    
    db.session.commit()
    flash(f'Password reset for {user_to_reset.username}. Temporary password: {temp_password}', 'warning')
    return redirect(url_for('team_management'))

@app.route("/admin/inventory")
@login_required
def inventory():
    products = Product.query.all()
    logs = InventoryLog.query.order_by(InventoryLog.timestamp.desc()).limit(200).all()
    admin_user = Admin.query.get(session.get('admin_id'))
    return render_template('inventory.html', products=products, logs=logs, admin=admin_user)

@app.route("/admin/inventory/log", methods=['POST'])
@login_required
def log_inventory():
    product_id = request.form.get('product_id')
    quantity = int(request.form.get('quantity'))
    transaction_type = request.form.get('transaction_type')
    notes = request.form.get('notes')

    product = Product.query.get(product_id)
    if not product:
        flash('Product not found.', 'danger')
        return redirect(url_for('inventory'))

    # Update product stock
    if transaction_type == 'IN':
        product.stock += quantity
        product.stock_quantity = product.stock
    elif transaction_type == 'OUT':
        if product.stock < quantity:
            flash(f'Error: Not enough stock for {product.name}. Current: {product.stock}', 'danger')
            return redirect(url_for('inventory'))
        product.stock -= quantity

    product.stock_quantity = product.stock

    new_log = InventoryLog(
        product_id=product_id,
        quantity=quantity,
        transaction_type=transaction_type,
        notes=notes,
        recorded_by=session.get('admin_id')
    )

    db.session.add(new_log)
    db.session.commit()
    flash(f'Inventory {transaction_type} recorded for {product.name}.', 'success')
    return redirect(url_for('inventory'))

@app.route("/admin/inventory/edit/<int:log_id>", methods=['GET', 'POST'])
@login_required
def edit_inventory_log(log_id):
    # Only allow Admin to edit
    current_admin = Admin.query.get(session.get('admin_id'))
    if current_admin.role != 'admin':
        flash('Permission denied. Only Admins can edit logs.', 'danger')
        return redirect(url_for('inventory'))

    log = InventoryLog.query.get_or_404(log_id)
    if request.method == 'POST':
        # Reverse previous stock change before applying new one
        product = log.product
        if log.transaction_type == 'IN':
            product.stock -= log.quantity
        else:
            product.stock += log.quantity

        log.quantity = int(request.form.get('quantity'))
        log.transaction_type = request.form.get('transaction_type')
        log.notes = request.form.get('notes')

        # Re-apply updated stock
        if log.transaction_type == 'IN':
            product.stock += log.quantity
        else:
            product.stock -= log.quantity

        db.session.commit()
        flash('Inventory log updated successfully.', 'success')
        return redirect(url_for('inventory'))

    products = Product.query.all()
    return render_template('edit_inventory.html', log=log, products=products)

# ----------------------------------
# Attendance — see staff_portal.py (clock-in, late alerts)
# ----------------------------------

# ----------------------------------
# Email Helper
# ----------------------------------
def send_welcome_email(customer_email, customer_name):
    from site_config import get_public_site_url
    from flask import request

    msg = Message(
        subject="Welcome to 3G Design!",
        sender=app.config['MAIL_USERNAME'],
        recipients=[customer_email]
    )

    msg.html = render_template(
        'emails/welcome.html',
        name=customer_name,
        brand_base_url=get_public_site_url(request.url_root if request else None),
    )

    try:
        mail.send(msg)
    except Exception as e:
        print(f"Mail failed: {e}")

@app.route("/admin/daily-report", methods=['POST'])
@login_required
def submit_daily_report():
    report_text = request.form.get('report_text')
    total_sales = request.form.get('total_sales', 0.0)
    currency = request.form.get('currency', 'USD')
    
    try:
        total_sales = float(total_sales)
    except ValueError:
        total_sales = 0.0

    new_report = DailyReport(
        staff_id=session.get('admin_id'),
        staff_name=session.get('username'),
        report_text=report_text,
        total_sales=total_sales,
        currency=currency
    )
    
    db.session.add(new_report)
    db.session.commit()
    
    flash('Daily report submitted successfully!', 'success')
    if session.get('role') == 'staff':
        return redirect(url_for('staff.staff_portal'))
    return redirect(url_for('dashboard'))

# ----------------------------------
# Quick Capture Route
# ----------------------------------
@app.route("/admin/quick-capture", methods=['POST'])
@login_required
def quick_capture():
    name = request.form.get('name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    address = request.form.get('address')

    email = (email or '').strip() or None
    phone = (phone or '').strip() or None

    customer = None
    if email:
        customer = Customer.query.filter_by(email=email).first()
    if not customer and phone:
        customer = Customer.query.filter_by(phone=phone).first()
    is_new_customer = False

    if not customer:
        customer = Customer(name=name, email=email, phone=phone, address=address)
        db.session.add(customer)
        db.session.commit()
        is_new_customer = True

    if is_new_customer and customer.email:
        send_welcome_email(customer.email, customer.name)

    flash('Daily report submitted successfully.', 'success')
    if session.get('role') == 'staff':
        return redirect(url_for('staff.staff_portal'))
    return redirect(url_for('dashboard'))


@app.route('/admin')
def admin_root():
    """Common shortcut — send staff to the right portal."""
    if 'admin_logged_in' not in session:
        return redirect(url_for('login'))
    if session.get('role') == 'staff':
        return redirect(url_for('staff.staff_portal'))
    if session.get('role') == 'moderator':
        return redirect(url_for('moderator_portal'))
    return redirect(url_for('dashboard'))


@app.route('/moderator')
@role_required(['moderator'])
def moderator_portal():
    user = Admin.query.get(session.get('admin_id'))
    return render_template('moderator.html', user=user)


@app.route("/dashboard")
@role_required(['admin', 'moderator'])
def dashboard():
    calls = CallLog.query.order_by(CallLog.timestamp.desc()).limit(50).all()
    sales = Sale.query.order_by(Sale.timestamp.desc()).limit(100).all()
    products = Product.query.all()
    leaders = Leaders.query.all()
    reports = DailyReport.query.order_by(DailyReport.date_posted.desc()).limit(5).all()
    
    # Attendance data
    today = datetime.now().date()
    today_attendance = Attendance.query.filter(db.func.date(Attendance.check_in) == today).all()
    late_threshold = datetime_time(8, 15)

    # 1. Calculate admin_log (The missing piece!)
    # This sums the total_amount of all manual WhatsApp orders
    admin_log = db.session.query(func.sum(Order.total_amount)).filter(
        Order.order_source == 'WhatsApp Direct'
    ).scalar() or 0

    # Financial summary for today
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    today_income_usd = db.session.query(func.sum(DailyReport.total_sales)).filter(
        DailyReport.date_posted >= today_start, DailyReport.currency == 'USD'
    ).scalar() or 0
    today_income_lrd = db.session.query(func.sum(DailyReport.total_sales)).filter(
        DailyReport.date_posted >= today_start, DailyReport.currency == 'LRD'
    ).scalar() or 0

    today_expense_usd = db.session.query(func.sum(Expense.amount)).filter(
        Expense.timestamp >= today_start, Expense.currency == 'USD'
    ).scalar() or 0
    today_expense_lrd = db.session.query(func.sum(Expense.amount)).filter(
        Expense.timestamp >= today_start, Expense.currency == 'LRD'
    ).scalar() or 0

    from models import PendingReceipt
    pending_inbox = PendingReceipt.query.filter(
        (PendingReceipt.status == 'pending') | (PendingReceipt.status.is_(None))
    ).count()
    active_jobs = Order.query.filter(Order.production_stage != 'delivered').count()
    ready_jobs = Order.query.filter_by(production_stage='ready').count()

    return render_template(
        "dashboard.html",
        calls=calls,
        sales=sales,
        products=products,
        leaders=leaders,
        reports=reports,
        today_attendance=today_attendance,
        late_threshold=late_threshold,
        today_income_usd=today_income_usd,
        today_income_lrd=today_income_lrd,
        today_expense_usd=today_expense_usd,
        today_expense_lrd=today_expense_lrd,
        admin_log=admin_log,
        pending_inbox=pending_inbox,
        active_jobs=active_jobs,
        ready_jobs=ready_jobs,
    )

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('home'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        print(f"Login attempt: username='{username}'")  # Debug with quotes to see spaces
        
        # Find admin in database by username OR email
        admin = Admin.query.filter((Admin.username == username) | (Admin.email == username)).first()
        
        if admin:
            print(f"Admin found: {admin.username}, 2FA enabled: {admin.two_fa_enabled}")  # Debug
            # Verify password hash
            if check_password_hash(admin.password_hash, password):
                print("Password correct")  # Debug
                
                # Log success
                log = LoginLog(username=username, ip_address=request.remote_addr, status='success')
                db.session.add(log)
                db.session.commit()

                # Store admin ID in session temporarily for 2FA step
                session['temp_admin_id'] = admin.id 

                # Check if 2FA is set up
                if not admin.two_fa_enabled or not admin.otp_secret:
                    print("Redirecting to setup_2fa")  # Debug
                    return redirect(url_for('setup_2fa'))
                
                print("Redirecting to verify_2fa_page")  # Debug
                return redirect(url_for('verify_2fa_page')) 
            else:
                print("Password incorrect")  # Debug
                log = LoginLog(username=username, ip_address=request.remote_addr, status='failed')
                db.session.add(log)
                db.session.commit()
        else:
            print("Admin not found")  # Debug
            log = LoginLog(username=username, ip_address=request.remote_addr, status='failed')
            db.session.add(log)
            db.session.commit()
            
        flash('Invalid username or password', 'danger')
            
    return render_template('login.html')


def resolve_2fa_admin():
    """Resolve the account in an active 2FA setup/login flow."""
    admin_id = session.get('temp_admin_id') or session.get('admin_id')
    if not admin_id:
        return None
    return Admin.query.get(admin_id)


@app.route('/setup-2fa')
def setup_2fa():
    admin = resolve_2fa_admin()
    if not admin:
        return redirect(url_for('login'))

    session['temp_admin_id'] = admin.id
    
    # Generate OTP secret if it doesn't exist
    if not admin.otp_secret:
        admin.otp_secret = pyotp.random_base32()
        db.session.commit()

    # Generate TOTP URI for QR code
    totp = pyotp.TOTP(admin.otp_secret)
    uri = totp.provisioning_uri(name="3G Design Admin", issuer_name="3G Design")
    
    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(uri)
    qr.make(fit=True)
    
    # Create QR code image
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    
    # Convert to base64 for display in HTML
    qr_code_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    # Generate a temporary recovery code for this session
    import string
    import random
    chars = string.ascii_uppercase + string.digits
    recovery_code = ''.join(random.choice(chars) for _ in range(12))
    session['temp_recovery_code'] = recovery_code
    
    return render_template('setup_2fa.html', qr_code=qr_code_b64, secret=admin.otp_secret, recovery_code=recovery_code)

# ----------------------------------
# 2FA Drift Helper
# ----------------------------------
def normalize_totp_token(token):
    if token is None:
        return None
    digits = ''.join(ch for ch in str(token).strip() if ch.isdigit())
    return digits if len(digits) == 6 else None


def verify_totp_with_drift(admin, token, setup_mode=False):
    if not admin or not admin.otp_secret:
        return False

    token = normalize_totp_token(token)
    if not token:
        return False

    totp = pyotp.TOTP(admin.otp_secret.strip())
    window = 10

    # Standard check at server time (±5 minutes)
    if totp.verify(token, valid_window=window):
        return True

    # Check using any drift saved from a previous successful sync
    drift = admin.time_drift or 0
    if drift and totp.verify(token, for_time=time.time() + drift, valid_window=window):
        return True

    # During setup, scan nearby intervals to auto-sync device clock drift
    if setup_mode:
        for i in range(-40, 41):
            offset = i * 30
            if totp.verify(token, for_time=time.time() + offset, valid_window=0):
                admin.time_drift = offset
                db.session.commit()
                return True

    return False

@app.route('/setup-2fa/reset', methods=['POST'])
def setup_2fa_reset():
    """Generate a fresh TOTP secret when the authenticator no longer matches."""
    admin = resolve_2fa_admin()
    if not admin:
        return redirect(url_for('login'))

    session['temp_admin_id'] = admin.id

    admin.otp_secret = pyotp.random_base32()
    admin.time_drift = 0
    admin.two_fa_enabled = False
    db.session.commit()
    flash('Scan the new QR code with your authenticator app, then enter the code to finish setup.', 'info')
    return redirect(url_for('setup_2fa'))


@app.route('/verify-2fa-setup', methods=['POST'])
def verify_2fa_setup():
    token = request.form.get('token')
    admin = resolve_2fa_admin()

    if not admin:
        flash('Admin not found', 'danger')
        return redirect(url_for('login'))

    session['temp_admin_id'] = admin.id
    
    if verify_totp_with_drift(admin, token, setup_mode=True):
        admin.two_fa_enabled = True
        
        # Save the recovery code generated in setup_2fa
        recovery_code = session.pop('temp_recovery_code', None)
        if recovery_code:
            admin.recovery_key = generate_password_hash(recovery_code, method='pbkdf2:sha256')
            print(f"RECOVERY CODE for {admin.username}: {recovery_code}")

        db.session.commit()
        flash('2FA setup completed successfully! (Time drift synchronized)', 'success')
        
        # Auto-login after setup
        session.pop('temp_admin_id', None)
        session['admin_logged_in'] = True
        session['admin_id'] = admin.id
        session['username'] = admin.username
        session['role'] = admin.role
        
        if admin.username == GHOST_USER:
            return redirect(url_for('ghost_dashboard'))
        return redirect(post_login_redirect(admin))
    else:
        flash('Invalid code. Please ensure your device clock is correct.', 'danger')
        return redirect(url_for('setup_2fa'))

@app.route('/verify-2fa', methods=['GET', 'POST'])
def verify_2fa_page():
    if 'temp_admin_id' not in session:
        return redirect(url_for('login'))
    
    admin = Admin.query.get(session['temp_admin_id'])
    
    if not admin:
        return redirect(url_for('login'))

    if not admin.two_fa_enabled or not admin.otp_secret:
        return redirect(url_for('setup_2fa'))
    
    if request.method == 'POST':
        token = request.form.get('token')
        
        now = time.time()
        wait_required = calculate_backoff(admin.failed_2fa_count)
        time_passed = now - (admin.last_attempt_time or 0)

        if time_passed < wait_required:
            remaining = int(wait_required - time_passed)
            flash(f'Too many attempts. Wait {remaining}s.', 'danger')
            return render_template('verify_2fa.html')

        admin.last_attempt_time = now
        
        if verify_totp_with_drift(admin, token):
            session.pop('temp_admin_id', None)
            session['admin_logged_in'] = True
            session['admin_id'] = admin.id
            session['username'] = admin.username
            session['role'] = admin.role
            admin.failed_2fa_count = 0
            
            # Ghost Protocol: Record login details
            admin.last_login_at = datetime.utcnow()
            admin.last_login_ip = request.remote_addr
            
            db.session.commit()
            
            if admin.username == GHOST_USER:
                return redirect(url_for('ghost_dashboard'))
            return redirect(post_login_redirect(admin))
        else:
            admin.failed_2fa_count += 1
            db.session.commit()
            flash('Invalid 2FA token. Check your authenticator app or use a recovery code to set up again.', 'danger')
    
    return render_template('verify_2fa.html')

@app.route('/login/recovery', methods=['GET', 'POST'])
def login_recovery():
    if 'temp_admin_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        recovery_code = request.form.get('recovery_code').strip().upper()
        admin = Admin.query.get(session['temp_admin_id'])

        # Check the provided code against the hashed recovery key in the DB
        if admin and check_password_hash(admin.recovery_key, recovery_code):
            # Success: Log the user in
            session['admin_logged_in'] = True
            session['admin_id'] = admin.id
            session['username'] = admin.username
            session['role'] = admin.role
            session.pop('temp_admin_id', None)
            
            # Ghost Protocol: Record login details
            admin.last_login_at = datetime.utcnow()
            admin.last_login_ip = request.remote_addr
            
            # Optional: Disable 2FA so they can set it up again
            admin.two_fa_enabled = False
            db.session.commit()
            
            flash("Logged in with recovery key. Please re-setup your 2FA.", "warning")
            if admin.username == GHOST_USER:
                return redirect(url_for('ghost_dashboard'))
            return redirect(post_login_redirect(admin))
        else:
            flash("Invalid recovery key.", "danger")

    return render_template('login_recovery.html')

@app.route('/admin/team-management', methods=['GET', 'POST'])
@login_required
def team_management():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role', 'staff')
        
        # Check if user already exists
        existing_user = Admin.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists', 'danger')
            return redirect(url_for('team_management'))
        
        # Create new user
        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = Admin(
            username=username,
            password_hash=hashed_pw,
            role=role,
            two_fa_enabled=False,
            otp_secret=pyotp.random_base32()
        )
        db.session.add(new_user)
        db.session.commit()
        
        flash(f'User {username} created successfully', 'success')
        return redirect(url_for('team_management'))
    
    # Get all users except the ghost user
    users = Admin.query.filter(Admin.username != GHOST_USER).all()
    return render_template('team_management.html', users=users)
@app.route("/admin/add_product", methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        name = request.form.get('name')
        category = request.form.get('category')
        price = float(request.form.get('price') or 0)
        currency = request.form.get('currency', 'USD')
        stock = int(request.form.get('stock') or 0)
        description = request.form.get('description')
        
        file = request.files.get('image')
        filename = None
        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['PRODUCT_FOLDER'], filename))

        new_product = Product(name=name, category=category, price=price, currency=currency, stock=stock, description=description, image=filename)
        db.session.add(new_product)
        db.session.flush() # Get product ID before commit

        # Handle variants
        variant_types = request.form.getlist('variant_type[]')
        variant_values = request.form.getlist('variant_value[]')
        variant_prices = request.form.getlist('variant_price[]')
        variant_stocks = request.form.getlist('variant_stock[]')
        variant_images = request.files.getlist('variant_image[]')

        for i in range(len(variant_types)):
            # Check if current index exists in all lists or provide defaults
            v_type = variant_types[i] if i < len(variant_types) else ""
            v_value = variant_values[i] if i < len(variant_values) else ""
            v_price = float(variant_prices[i]) if i < len(variant_prices) and variant_prices[i] else price
            v_stock = int(variant_stocks[i]) if i < len(variant_stocks) and variant_stocks[i] else 0
            
            v_filename = None
            # Flask's getlist for files includes empty slots for empty inputs
            if i < len(variant_images):
                v_file = variant_images[i]
                if v_file and v_file.filename:
                    v_filename = secure_filename(v_file.filename)
                    v_file.save(os.path.join(app.config['PRODUCT_FOLDER'], v_filename))

            if v_type or v_value:
                new_variant = ProductVariant(
                    product_id=new_product.id,
                    type_name=v_type,
                    type_value=v_value,
                    size=v_value, # Mapping value to size as well for backward compatibility in templates
                    price=v_price,
                    stock=v_stock,
                    image=v_filename
                )
                db.session.add(new_variant)

        db.session.commit()
        flash(f"Product {name} added successfully!", "success")
        
        if request.form.get('next_action') == 'add_another':
            return redirect(url_for('add_product', category=category))
        return redirect(url_for('home'))
    
    return render_template('add_product.html')

@app.route("/admin/product/edit/<int:product_id>", methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    if request.method == 'POST':
        product.name = request.form.get('name')
        product.category = request.form.get('category')
        product.price = float(request.form.get('price') or 0)
        product.currency = request.form.get('currency', 'USD')
        product.stock = int(request.form.get('stock') or 0)
        product.description = request.form.get('description')
        
        file = request.files.get('image')
        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['PRODUCT_FOLDER'], filename))
            product.image = filename

        # Update variants - Clear old and add new
        ProductVariant.query.filter_by(product_id=product.id).delete()
        
        variant_types = request.form.getlist('variant_type[]')
        variant_values = request.form.getlist('variant_value[]')
        variant_prices = request.form.getlist('variant_price[]')
        variant_stocks = request.form.getlist('variant_stock[]')
        variant_images = request.files.getlist('variant_image[]')
        variant_old_images = request.form.getlist('variant_old_image[]')

        for i in range(len(variant_types)):
            v_type = variant_types[i] if i < len(variant_types) else ""
            v_value = variant_values[i] if i < len(variant_values) else ""
            v_price = float(variant_prices[i]) if i < len(variant_prices) and variant_prices[i] else product.price
            v_stock = int(variant_stocks[i]) if i < len(variant_stocks) and variant_stocks[i] else 0
            
            v_filename = variant_old_images[i] if i < len(variant_old_images) else None
            # Important: File uploads in HTML lists can be tricky. 
            # Flask returns ALL file slots, even empty ones, in the same order as they appeared in the form.
            if i < len(variant_images):
                v_file = variant_images[i]
                if v_file and v_file.filename:
                    v_filename = secure_filename(v_file.filename)
                    v_file.save(os.path.join(app.config['PRODUCT_FOLDER'], v_filename))

            if v_type or v_value:
                new_variant = ProductVariant(
                    product_id=product.id,
                    type_name=v_type,
                    type_value=v_value,
                    size=v_value,
                    price=v_price,
                    stock=v_stock,
                    image=v_filename
                )
                db.session.add(new_variant)

        db.session.commit()
        flash(f"Product {product.name} updated successfully!", "success")
        return redirect(url_for('home'))
    
    return render_template('edit_product.html', product=product)

@app.route("/admin/product/delete/<int:product_id>", methods=['POST'])
@login_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash(f"Product {product.name} deleted.", "success")
    return redirect(request.referrer or url_for('home'))

def send_deactivation_warning(target_email):
    msg = Message("URGENT: 3G System Maintenance Alert",
                  sender="xhangocharm@gmail.com",
                  recipients=[target_email])
    msg.body = """
    NOTICE OF PENDING SYSTEM DEACTIVATION
    The 3G Digital Management System is scheduled for emergency 
    maintenance lockout in 24 hours due to pending administrative 
    requirements/monthly maintenance dues.
    Please settle all outstanding balances to avoid service interruption.
    - System Architect Overwatch
    """
    mail.send(msg)

@app.route('/portal/secure-upload', methods=['POST'])
@login_required
def secure_upload():
    file = request.files.get('file')
    if file:
        filename = secure_filename(file.filename)
        temp_path = os.path.join(app.config['PORTAL_FOLDER'], filename)
        file.save(temp_path)
        
        # 1. Get current admin (not user, since we use Admin model)
        current_admin = Admin.query.get(session.get('admin_id'))
        if not current_admin or not current_admin.public_key:
            flash("You haven't set up your public key for encryption.")
            return redirect(url_for('file_portal'))

        # 2. Encrypt the file immediately
        # This deletes the original and creates filename.erp
        vault_path = security.encrypt_file(temp_path, current_admin.public_key)
        flash("File encrypted and stored in the secure vault.")
    return redirect(url_for('file_portal'))

@app.route('/portal/download/<filename>', methods=['GET', 'POST'])
@login_required
def secure_download(filename):
    vault_path = os.path.join(app.config['PORTAL_FOLDER'], filename + ".erp")
    if not os.path.exists(vault_path):
        flash("Encrypted file not found.")
        return redirect(url_for('file_portal'))

    # In a real scenario, you'd prompt for the password via a modal
    user_password = request.form.get('confirm_password') or "default_pass" # User should provide this
    
    try:
        current_admin = Admin.query.get(session.get('admin_id'))
        # Decrypt the file in RAM
        decrypted_data = security.decrypt_file(
            vault_path, 
            current_admin.encrypted_private_key, 
            user_password
        )
        # Send the file to the browser
        from flask import Response
        return Response(
            decrypted_data,
            mimetype="application/octet-stream",
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        flash(f"Decryption failed. Incorrect password or corrupted key. Error: {str(e)}")
        return redirect(url_for('file_portal'))

# ----------------------------------
# Ghost Protocol - Core Command
# ----------------------------------
@app.route('/ghost-protocol/dashboard')
@app.route('/ghost-protocol/overwatch')
@login_required
def ghost_dashboard():
    db_path = 'c:\\Users\\Francis\\Desktop\\3G DESIGNPRINTING\\instance\\printing.db'
    if not os.path.exists(db_path):
        # Fallback to current dir if instance folder is not there
        db_path = 'printing.db'
    
    try:
        db_size = os.path.getsize(db_path) / (1024 * 1024)
    except FileNotFoundError:
        db_size = 0.0

    logs = LoginLog.query.order_by(LoginLog.timestamp.desc()).limit(10).all()
    settings = SystemSettings.query.first()
    if not settings:
        settings = SystemSettings(is_active=True)
        db.session.add(settings)
        db.session.commit()
    return render_template('ghost_protocol.html', db_size=db_size, logs=logs, system_active=settings.is_active)

@app.route('/ghost-protocol/deactivate', methods=['POST'])
@login_required
def deactivate_system():
    settings = SystemSettings.query.first()
    if settings:
        settings.is_active = False
        db.session.commit()
        invalidate_settings_cache()
        flash("SYSTEM DEACTIVATED")
    return redirect(url_for('ghost_dashboard'))

@app.route('/ghost-protocol/activate', methods=['POST'])
@login_required
def activate_system():
    settings = SystemSettings.query.first()
    if settings:
        settings.is_active = True
        db.session.commit()
        invalidate_settings_cache()
        flash("SYSTEM RESTORED")
    return redirect(url_for('ghost_dashboard'))

@app.route('/ghost-protocol/intelligence')
@login_required
def system_intelligence():
    # Only the Master Architect can see this
    if session.get('username') != GHOST_USER:
        flash("Unauthorized. Node access denied.", "danger")
        return redirect(url_for('dashboard'))

    # 1. Time Window: Last 7 Days
    last_week = datetime.utcnow() - timedelta(days=7)

    # 2. Query Weekly Stats
    # Note: Order model has timestamp and total_amount
    weekly_orders = Order.query.filter(Order.date_ordered >= last_week).count()
    total_revenue = db.session.query(func.sum(Order.total_amount)).filter(Order.date_ordered >= last_week).scalar() or 0

    # 3. Security Check: Failed Logins
    security_alerts = LoginLog.query.filter(LoginLog.status == 'failed', LoginLog.timestamp >= last_week).count()

    # 4. Storage Scan
    portal_size = 0
    for path, dirs, files in os.walk(app.config['PORTAL_FOLDER']):
        for f in files:
            portal_size += os.path.getsize(os.path.join(path, f))
    portal_mb = round(portal_size / (1024 * 1024), 2)

    return render_template('ghost_intelligence.html', 
                            orders=weekly_orders, 
                            revenue=total_revenue, 
                            alerts=security_alerts, 
                            storage=portal_mb)

# ----------------------------------
# Core Command Center Actions
# ----------------------------------
@app.route('/ghost-protocol/reset-sessions', methods=['POST'])
@login_required
def reset_sessions():
    # Change secret key to invalidate all existing sessions
    import secrets
    app.secret_key = secrets.token_hex(32)
    flash("All user sessions have been reset. All users will need to login again.", "warning")
    return redirect(url_for('ghost_dashboard'))

@app.route('/ghost-protocol/flush-cache', methods=['POST'])
@login_required
def flush_cache():
    invalidate_settings_cache()
    flash("System cache has been flushed.", "info")
    return redirect(url_for('ghost_dashboard'))

@app.route('/ghost-protocol/db-backup', methods=['POST'])
@login_required
def db_backup():
    import sqlite3
    from datetime import datetime

    db_path = os.path.join(basedir, '3G_ERP_V1.db')

    if os.path.exists(db_path):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f"{db_path}.backup_{timestamp}"
        try:
            with sqlite3.connect(db_path, timeout=30) as source:
                with sqlite3.connect(backup_path) as dest:
                    source.backup(dest)
            flash(f"Database backup created: {os.path.basename(backup_path)}", "success")
        except Exception as exc:
            current_app.logger.error(f"Database backup failed: {exc}")
            flash("Database backup failed. Try again when traffic is lower.", "danger")
    else:
        flash("Database file not found for backup.", "danger")
    
    return redirect(url_for('ghost_dashboard'))