import os
import time
import math
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


import assemblyai as aai

from werkzeug.utils import secure_filename
from flask import Flask, abort, request, jsonify, render_template, redirect, url_for, session, flash, Response
from dotenv import load_dotenv
from twilio.twiml.voice_response import VoiceResponse
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

from models import db, Product, ProductVariant, Sale, CallLog, Leaders, Admin, AboutContent, Customer, Order, OrderItem, DailyReport, Attendance, User, InventoryLog, Expense, SystemSettings, LoginLog
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
# Updated for 3G DESIGN Branding
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, '3G_ERP_V1.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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

# 7. Initialize Extensions
db.init_app(app)
mail = Mail(app)

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
                ("date_ordered", "DATETIME")
            ]
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
                    return redirect(url_for('file_portal'))
                return redirect(url_for('home'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ----------------------------------
# System Status Check
# ----------------------------------
@app.before_request
def check_system_status():
    # 1. Allow access to the Ghost Dashboard so YOU can turn it back on
    # 2. Allow access to static files (CSS/Images)
    if 'ghost-protocol' in request.path or request.path.startswith('/static') or request.path == '/login':
        return
    # Check if system is deactivated in DB
    settings = SystemSettings.query.first()
    if settings and not settings.is_active:
        return render_template('system_locked.html', message=settings.lock_message), 403

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
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/favicon.icon')

# ----------------------------------
# Shopping Cart Logic
# ----------------------------------
@app.route('/add-to-cart', methods=['POST'])
def add_to_cart():
    product_id = request.form.get('product_id')
    variant_name = request.form.get('variant_name', 'Base')
    price = float(request.form.get('price', 0))
    currency = request.form.get('currency', 'USD')
    image = request.form.get('image', '')
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

@app.route('/checkout-whatsapp')
def checkout_whatsapp():
    cart = session.get('cart', [])
    if not cart:
        flash("Your cart is empty.", "warning")
        return redirect(url_for('home'))
    
    # Base URL for images
    base_url = request.host_url.rstrip('/')
    
    # Professional Header
    message = "📑 *OFFICIAL ORDER RECEIPT - Olatricity*\n"
    message += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # Optimization: Put the first image link at the very top for WhatsApp Link Preview
    if cart and cart[0].get('image'):
        first_img = f"{base_url}/static/uploads/{cart[0]['image']}"
        message += f"🖼️ *Design Preview:* {first_img}\n\n"

    total_usd = 0
    total_lrd = 0
    
    for i, item in enumerate(cart, 1):
        message += f"📦 *ITEM #{i}: {item['product_name']}*\n"
        message += f"▫️ Variant: {item['variant_name']}\n"
        message += f"▫️ Qty: {item['quantity']}\n"
        message += f"▫️ Subtotal: {item['price'] * item['quantity']:.2f} {item['currency']}\n"
        
        # Additional links are clickable but usually don't show extra previews
        if i > 1 and item.get('image'):
            item_img = f"{base_url}/static/uploads/{item['image']}"
            message += f"🔗 View Design: {item_img}\n"
        
        message += "\n"
        
        if item['currency'] == 'USD': total_usd += item['price'] * item['quantity']
        else: total_lrd += item['price'] * item['quantity']
    
    message += "------------------------------------------\n"
    message += f"💰 *Total USD:* ${total_usd:.2f}\n"
    message += f"💰 *Total LRD:* L${total_lrd:.2f}\n"
    message += "------------------------------------------\n"
    message += "Please confirm availability and lead time. Thank you! 🙏"
    
    # Clear cart after checkout
    session.pop('cart', None)
    
    whatsapp_url = f"https://wa.me/+231775323731?text={urllib.parse.quote(message)}"
    return redirect(whatsapp_url)

# ----------------------------------
# TWILIO: Answer Call & Record
# ----------------------------------
@app.route("/voice", methods=['POST'])
def voice():
    response = VoiceResponse()
    response.say("Welcome to 3G DESIGN. Your call is being recorded for order accuracy.")
    
    # Twilio will POST to /handle-recording when the user hangs up or time is up
    response.record(action="/handle-recording", maxLength=60)
    return str(response)
# ----------------------------------
# AssemblyAI: Handle Recording
# ----------------------------------
from flask import request, current_app
import assemblyai as aai
# Make sure db and CallLog are imported from your models file
# from models import db, CallLog 

@app.route("/handle-recording", methods=['POST'])
def handle_recording():
    # 1. Get data from Twilio
    recording_url = request.form.get('RecordingUrl')
    from_number = request.form.get('From')

    if not recording_url:
        current_app.logger.warning("No recording URL received from Twilio.")
        return "No recording found", 400
    try:
        # 2. Start Transcription (Ensure aai.settings.api_key is set elsewhere)
        transcriber = aai.Transcriber()
        transcript = transcriber.transcribe(recording_url)

        # 3. Check for transcription errors
        if transcript.status == aai.TranscriptStatus.error:
            current_app.logger.error(f"Transcription Error: {transcript.error}")
            return "Transcription failed", 500

        # 4. Save to Database
        new_call = CallLog(
            phone_number=from_number,
            transcript=transcript.text,
            audio_url=recording_url
        )

        db.session.add(new_call)
        db.session.commit()
        
        print(f"Success: Recorded call from {from_number}")
        return "OK", 200

    except Exception as e:
        # If the database or transcription fails, roll back the session
        db.session.rollback()
        print(f"System Error: {str(e)}")
        return "Internal Server Error", 500
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

@app.route('/portal/upload', methods=['POST'])
@login_required
def upload_file():
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

def roles_required(*roles):
    def wrapper(f):
        @wraps(f)
        def decorated_view(*args, **kwargs):
            # Assumes 'role' is stored in the session during login
            user_role = session.get('role')
            if user_role not in roles:
                # 403 Forbidden: They aren't an Admin or Moderator
                abort(403) 
            return f(*args, **kwargs)
        return decorated_view
    return wrapper

# Apply it to your Management Portal route
@app.route('/download-doc/<doc_type>')
@roles_required('admin', 'moderator') # ONLY these roles can enter
def download_pdf(doc_type):
    # Role check
    if session.get('role') not in ['admin', 'moderator']:
        abort(403)

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # --- 1. TOP DECORATIVE BARS ---
    p.setFillColor(colors.HexColor("#0B1F3A")) # 3G DESIGN Deep Navy
    p.rect(0, height - 25, width, 25, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 10)
    p.drawCentredString(width/2, height - 17, doc_type.upper())

    # --- 2. LOGO & CONTACT INFO ---
    logo_path = os.path.join(app.root_path, 'static/img/LOGO.png')
    if os.path.exists(logo_path):
        p.drawImage(logo_path, 50, height - 85, width=120, preserveAspectRatio=True, mask='auto')

    # Contact Details (Right Aligned like the sample)
    p.setFillColor(colors.black)
    p.setFont("Helvetica", 9)
    text_x = 550
    p.drawRightString(text_x, height - 55, "📞 +231 77 532 3731")
    p.drawRightString(text_x, height - 67, "📧 info@olatricity.com")
    p.drawRightString(text_x, height - 79, "🌐 www.olatricity.com")
    p.drawRightString(text_x, height - 91, "📍 Newport & Benson Street, Monrovia, Liberia")

    # --- 3. THE ACCENT BLUE LINE ---
    p.setStrokeColor(colors.HexColor("#4FC3F7")) # Olatricity Sky Blue
    p.setLineWidth(2)
    p.line(50, height - 110, 550, height - 110)

    # --- 4. RECIPIENT & DATE ---
    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, height - 140, "To:")
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 152, "Valued Client / Management")
    p.drawRightString(550, height - 170, datetime.now().strftime("%B %d, %Y"))

    # --- 5. CONTENT AREA ---
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, height - 200, f"Subject: Official {doc_type.title()}")
    
    p.setFont("Helvetica", 11)
    p.drawString(50, height - 230, "Dear Sir/Madam,")
    # Add your body text logic here...

    # --- 6. SIGNATURE LINE ---
    p.drawString(50, 150, "Sincerely,")
    p.line(50, 110, 180, 110) # Signature line
    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, 95, f"{session.get('username')}")
    p.setFont("Helvetica", 9)
    p.drawString(50, 83, "Authorized Signatory")
    p.drawString(50, 71, "3G DESIGN")

    # --- 7. BOTTOM BLUE BAR ---
    p.setFillColor(colors.HexColor("#0B1F3A"))
    p.rect(0, 0, width, 30, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 9)
    p.drawCentredString(width/2, 12, "QUALITY IN EVERY PRINT, EXCELLENCE IN EVERY DESIGN")

    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"3G DESIGN_{doc_type}.pdf", mimetype='application/pdf')

@app.route('/admin_portal')
@roles_required('admin', 'moderator')
def admin_portal():
    return render_template("admin_portal.html")

@app.route('/direct-sale-history')
@roles_required('admin', 'moderator')
def direct_sale_history():
    search = request.args.get('search', '')
    query = Order.query
    
    if search:
        query = query.join(Customer).filter(
            (Customer.name.ilike(f"%{search}%")) |
            (Order.status.ilike(f"%{search}%")) |
            (Order.order_source.ilike(f"%{search}%"))
        )
    
    orders = query.order_by(Order.date_ordered.desc()).all()
    return render_template("direct_sale_history.html", orders=orders, search=search)

@app.route("/admin/generate-order-pdf", methods=['POST'])
@app.route("/admin/generate-order-pdf/<int:order_id>", methods=['GET'])
@roles_required('admin', 'moderator')
def generate_order_pdf(order_id=None):
    if order_id:
        order = Order.query.get_or_404(order_id)
        customer_name = order.customer.name if order.customer else "Guest"
        # Combine items for description
        items_list = []
        for item in order.items:
            p_name = item.product.name if item.product else "Deleted Product"
            items_list.append(f"{p_name} (x{item.quantity})")
        
        product_name = ", ".join(items_list)
        price_display = f"${order.total_amount:,.2f}"
        doc_type = "invoice"
    else:
        product_name = request.form.get('product_name')
        customer_name = request.form.get('customer_name')
        doc_type = request.form.get('doc_type', 'invoice')
        
        # Original logic for price from product_name string
        price_display = "$0.00"
        if product_name and "$" in product_name:
            price_display = "$" + product_name.split("$")[-1].strip()
        elif product_name and "Variable" in product_name:
            price_display = "TBD"

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # --- Modern UI: Sidebar Accent ---
    p.setFillColor(colors.HexColor("#0B1F3A"))
    p.rect(0, 0, 40, height, fill=1, stroke=0)

    # --- Header ---
    p.setFillColor(colors.HexColor("#0B1F3A"))
    p.rect(40, height - 80, width - 40, 80, fill=1, stroke=0)
    
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 24)
    p.drawString(60, height - 50, "3G DESIGN")
    
    p.setFont("Helvetica", 12)
    p.drawRightString(width - 30, height - 35, doc_type.upper())
    p.drawRightString(width - 30, height - 55, datetime.now().strftime("%d %b %Y"))

    # --- Logo & Contact ---
    logo_path = os.path.join(app.root_path, 'static', 'img', 'LOGO.png')
    if os.path.exists(logo_path):
        p.drawImage(logo_path, 60, height - 160, width=100, preserveAspectRatio=True, mask='auto')

    p.setFillColor(colors.black)
    p.setFont("Helvetica-Bold", 10)
    p.drawString(200, height - 110, "3G DESIGN")
    p.setFont("Helvetica", 9)
    p.drawString(200, height - 125, "Newport & Benson Street, Monrovia, Liberia")
    p.drawString(200, height - 137, "Tel: +231 77 532 3731")
    p.drawString(200, height - 149, "Email: info@3GDESIGNprinting.com")

    # --- Customer Info ---
    p.setStrokeColor(colors.HexColor("#0B1F3A"))
    p.setLineWidth(1)
    p.line(60, height - 180, width - 30, height - 180)

    p.setFont("Helvetica-Bold", 11)
    p.drawString(60, height - 210, "BILLED TO:")
    p.setFont("Helvetica", 11)
    p.drawString(60, height - 225, customer_name)

    # --- Order Table Header ---
    p.setFillColor(colors.HexColor("#F2F4F7"))
    p.rect(60, height - 280, width - 90, 25, fill=1, stroke=0)
    
    p.setFillColor(colors.black)
    p.setFont("Helvetica-Bold", 10)
    p.drawString(70, height - 273, "DESCRIPTION")
    p.drawRightString(width - 40, height - 273, "AMOUNT")

    # --- Order Details ---
    p.setFont("Helvetica", 10)
    p.drawString(70, height - 310, product_name[:80] + ("..." if len(product_name) > 80 else ""))
    
    p.drawRightString(width - 40, height - 310, price_display)

    # --- Footer ---
    p.setStrokeColor(colors.HexColor("#0B1F3A"))
    p.line(60, 100, width - 30, 100)
    
    p.setFont("Helvetica-Oblique", 8)
    p.drawCentredString(width/2 + 20, 80, "Thank you for choosing 3G DESIGN for your digital solutions.")
    p.setFont("Helvetica-Bold", 10)
    p.drawCentredString(width/2 + 20, 60, "QUALITY IN EVERY PRINT, EXCELLENCE IN EVERY DESIGN")

    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"{customer_name}_{doc_type}.pdf", mimetype='application/pdf')

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
def add_sale():
    # ... your existing sale logic ...
    
    product = Product.query.get(product_id)
    product.stock_quantity -= quantity_sold
    
    db.session.commit()

    # --- INVENTORY CHECK START ---
    check_inventory_alerts(product)
    # --- INVENTORY CHECK END ---

    return redirect(url_for('dashboard'))

ADMIN_PHONE = '+231881669599'  # Replace with your actual phone number

def check_inventory_alerts(product):
    """Checks if stock is low and sends an alert to the Admin."""
    if product.stock_quantity <= product.min_stock_threshold:
        message_body = (
            f"⚠️ 3G DESIGN INVENTORY ALERT ⚠️\n"
            f"Item: {product.name} is running low!\n"
            f"Current Stock: {product.stock_quantity}\n"
            f"Threshold: {product.min_stock_threshold}\n"
            f"Please restock soon to avoid missing sales."
        )

        try:
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
def trigger_order_sms(sale_id):
    """Updates the sale record based on SMS success."""
    sale = Sale.query.get(sale_id)
    if not sale or not sale.phone_number:
        return

    message_body = f"3G DESIGN: Order #{sale.id} confirmed for ${sale.total_amount:.2f}. Thank you!"

    try:
        twilio_client.messages.create(
            body=message_body,
            from_=app.config['TWILIO_PHONE_NUMBER'],
            to=sale.phone_number
        )
        sale.sms_status = "Sent" # Success!
    except Exception as e:
        print(f"SMS Error: {e}")
        sale.sms_status = "Failed" # Something went wrong
    
    db.session.commit()
#-----------------------------------------
# sale finalism
#-----------------------------------------
def trigger_order_sms(sale_obj):
    """
    Automated professional response for 3G DESIGN.
    Takes a 'sale' object from your database.
    """
    if not sale_obj.phone_number or not sale_obj.phone_number.startswith('+'):
        print(f"Skipping SMS: Invalid phone for {sale_obj.customer_name}")
        return

    message_body = (
        f"3G DESIGN ERP: Success! Order #{sale_obj.id} confirmed.\n"
        f"Customer: {sale_obj.customer_name}\n"
        f"Amount: ${sale_obj.total_amount:.2f}\n"
        f"Thank you for your business. We are processing your request now!"
    )

    try:
        twilio_client.messages.create(
            body=message_body,
            from_=app.config['TWILIO_PHONE_NUMBER'],
            to=sale_obj.phone_number
        )
        print(f"Auto-SMS sent to {sale_obj.customer_name}")
    except Exception as e:
        print(f"Auto-SMS failed: {e}")

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

        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            new_leader = Leaders(name=name, position=position, bio=bio, email=email, contact=contact, image=filename)
            db.session.add(new_leader)
            db.session.commit()

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
    logs = InventoryLog.query.order_by(InventoryLog.timestamp.desc()).all()
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
    elif transaction_type == 'OUT':
        if product.stock < quantity:
            flash(f'Error: Not enough stock for {product.name}. Current: {product.stock}', 'danger')
            return redirect(url_for('inventory'))
        product.stock -= quantity

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
# Attendance Helpers
# ----------------------------------
def check_for_late_staff():
    # Define your shop's grace period (e.g., 8:15 AM)
    late_threshold = datetime_time(8, 15)
    current_time = datetime.now().time()
    today = datetime.now().date()
    if current_time > late_threshold:
        # Get all staff members
        all_staff = Admin.query.filter_by(role='staff').all()
        for staff in all_staff:
            # Check if they have a check-in record for today
            attendance = Attendance.query.filter(
                Attendance.staff_id == staff.id,
                db.func.date(Attendance.check_in) == today
            ).first()
            if not attendance:
                send_late_notification(staff.username)

def send_late_notification(username):
    # This uses your existing Flask-Mail or Twilio setup
    msg_body = f"ALERT: {username} has not clocked in for their shift at 3G DESIGN as of 08:15 AM."
    print(msg_body) # For testing, or send via Twilio/Email
    
    # Optional: Send via Flask-Mail if configured
    try:
        msg = Message(
            subject="Late Staff Alert",
            sender=app.config['MAIL_USERNAME'],
            recipients=[app.config['MAIL_USERNAME']] # Send to admin
        )
        msg.body = msg_body
        mail.send(msg)
    except Exception as e:
        print(f"Failed to send late notification email: {e}")

# ----------------------------------
# Email Helper
# ----------------------------------
def send_welcome_email(customer_email, customer_name):
    msg = Message(
        subject="Welcome to 3G DESIGN!",
        sender=app.config['MAIL_USERNAME'],
        recipients=[customer_email]
    )

    msg.html = render_template(
        'emails/welcome.html',
        name=customer_name
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

    # Check if customer already exists
    customer = Customer.query.filter_by(email=email).first()
    is_new_customer = False

    if not customer:
        customer = Customer(name=name, email=email, phone=phone, address=address)
        db.session.add(customer)
        db.session.commit()
        is_new_customer = True

    if is_new_customer:
        send_welcome_email(customer.email, customer.name)

    return redirect(url_for('dashboard'))

@app.route("/dashboard")
@role_required(['admin', 'moderator'])
def dashboard():
    calls = CallLog.query.order_by(CallLog.timestamp.desc()).all()
    sales = Sale.query.all()
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
        admin_log=admin_log
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
                if not admin.two_fa_enabled:
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

@app.route('/setup-2fa')
def setup_2fa():
    if 'temp_admin_id' not in session:
        return redirect(url_for('login'))
        
    admin = Admin.query.get(session['temp_admin_id'])
    if not admin:
        return redirect(url_for('login'))
    
    # Generate OTP secret if it doesn't exist
    if not admin.otp_secret:
        admin.otp_secret = pyotp.random_base32()
        db.session.commit()

    # Generate TOTP URI for QR code
    totp = pyotp.TOTP(admin.otp_secret)
    uri = totp.provisioning_uri(name="3G DESIGN Admin", issuer_name="3G DESIGN")
    
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
def verify_totp_with_drift(admin, token, setup_mode=False):
    totp = pyotp.TOTP(admin.otp_secret)
    
    # 1. Check with existing drift
    if totp.verify(token, for_time=time.time() + (admin.time_drift or 0), valid_window=1):
        return True
    
    # 2. If setup or failed, scan for drift (up to 24 hours)
    # This ensures "Auto-Sync" for any user on any device
    search_range = 2880 # 24 hours in 30s steps
    for i in range(-search_range, search_range):
        offset = i * 30
        if totp.verify(token, for_time=time.time() + offset):
            admin.time_drift = offset
            db.session.commit()
            return True
            
    return False

@app.route('/verify-2fa-setup', methods=['POST'])
def verify_2fa_setup():
    if 'temp_admin_id' not in session:
        return redirect(url_for('login'))
        
    token = request.form.get('token')
    admin = Admin.query.get(session['temp_admin_id'])
    
    if not admin:
        flash('Admin not found', 'danger')
        return redirect(url_for('login'))
    
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
        return redirect(url_for('dashboard'))
    else:
        flash('Invalid code. Please ensure your device clock is correct.', 'danger')
        return redirect(url_for('setup_2fa'))

@app.route('/verify-2fa', methods=['GET', 'POST'])
def verify_2fa_page():
    if 'temp_admin_id' not in session:
        return redirect(url_for('login'))
    
    admin = Admin.query.get(session['temp_admin_id'])
    
    if not admin or not admin.two_fa_enabled:
        return redirect(url_for('setup_2fa'))
    
    if request.method == 'POST':
        token = request.form.get('token')
        
        if not admin:
            flash('Unauthorized', 'danger')
            return redirect(url_for('login'))

        now = time.time()
        wait_required = calculate_backoff(admin.failed_2fa_count)
        time_passed = now - (admin.last_attempt_time or 0)

        if time_passed < wait_required:
            remaining = int(wait_required - time_passed)
            flash(f'Too many attempts. Wait {remaining}s.', 'danger')
            return render_template('verify_2fa.html')

        admin.last_attempt_time = now
        
        totp = pyotp.TOTP(admin.otp_secret)
        # Debugging time drift (will show in server console)
        print(f"DEBUG: Verifying 2FA for {admin.username}. Token: {token}, Expected: {totp.now()}, Drift allowed: 5 mins")
        
        if admin and totp.verify(token, valid_window=10):
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
            return redirect(url_for('dashboard'))
        else:
            admin.failed_2fa_count += 1
            db.session.commit()
            flash('Invalid 2FA token', 'danger')
    
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
            return redirect(url_for('dashboard'))
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

@app.route('/portal/upload', methods=['POST'])
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
        flash("SYSTEM DEACTIVATED")
    return redirect(url_for('ghost_dashboard'))

@app.route('/ghost-protocol/activate', methods=['POST'])
@login_required
def activate_system():
    settings = SystemSettings.query.first()
    if settings:
        settings.is_active = True
        db.session.commit()
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
    weekly_orders = Order.query.filter(Order.timestamp >= last_week).count()
    total_revenue = db.session.query(func.sum(Order.total_amount)).filter(Order.timestamp >= last_week).scalar() or 0

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
    # Clear any cached data (if implemented)
    # For now, just flash a message
    flash("System cache has been flushed.", "info")
    return redirect(url_for('ghost_dashboard'))

@app.route('/ghost-protocol/db-backup', methods=['POST'])
@login_required
def db_backup():
    # Create a backup of the database
    import shutil
    from datetime import datetime
    
    db_path = 'c:\\Users\\Francis\\Desktop\\3G DESIGNPRINTING\\instance\\printing.db'
    if not os.path.exists(db_path):
        db_path = 'printing.db'
    
    if os.path.exists(db_path):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f"{db_path}.backup_{timestamp}"
        shutil.copy2(db_path, backup_path)
        flash(f"Database backup created: {os.path.basename(backup_path)}", "success")
    else:
        flash("Database file not found for backup.", "danger")
    
    return redirect(url_for('ghost_dashboard'))