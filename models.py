from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash
from app import db


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    role = db.Column(db.String(20), default='moderator')
    password_hash = db.Column(db.String(128))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50)) # e.g., 'T-Shirt', 'Frame'
    price = db.Column(db.Float, default=0.0) # Base price
    currency = db.Column(db.String(3), default='USD') # 'USD' or 'LRD'
    stock = db.Column(db.Integer, default=0) # Total stock
    image = db.Column(db.String(100))
    description = db.Column(db.Text)
    stock_quantity = db.Column(db.Integer, default=0)
    # Add this line to define when to alert you
    min_stock_threshold = db.Column(db.Integer, default=5)
    
    variants = db.relationship('ProductVariant', backref='product', lazy=True, cascade="all, delete-orphan")

class ProductVariant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    type_name = db.Column(db.String(50)) # e.g., 'Material', 'Color'
    type_value = db.Column(db.String(50)) # e.g., 'Cotton', 'Red'
    size = db.Column(db.String(20)) # e.g., 'S', 'M', 'L', 'XL'
    price = db.Column(db.Float) # Price for this specific variant
    stock = db.Column(db.Integer, default=0)
    image = db.Column(db.String(100))

class Leaders(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    image = db.Column(db.String(100))
    position = db.Column(db.String(100))
    bio = db.Column(db.Text)
    email = db.Column(db.String(120))
    contact = db.Column(db.String(20))

class CallLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20))
    caller_name = db.Column(db.String(100))
    transcript = db.Column(db.Text)
    audio_url = db.Column(db.String(255))
    notes = db.Column(db.Text)
    source = db.Column(db.String(30), default='local_desktop')  # twilio_cloud, local_desktop, whatsapp_manual
    call_type = db.Column(db.String(20), default='voice')       # voice, whatsapp_call, whatsapp_message
    status = db.Column(db.String(20), default='logged')         # received, processed, missed, logged
    duration_seconds = db.Column(db.Integer)
    call_sid = db.Column(db.String(64))
    logged_by = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password_hash = db.Column(db.String(128))
    email = db.Column(db.String(120))
    role = db.Column(db.String(20), default='admin')  # admin, moderator, staff
    moderator_permissions = db.Column(db.Text)  # JSON list of responsibility keys (moderator only)
    otp_secret = db.Column(db.String(32))
    recovery_key = db.Column(db.String(128))  # Hashed recovery key
    two_fa_enabled = db.Column(db.Boolean, default=False)
    failed_2fa_count = db.Column(db.Integer, default=0)
    last_attempt_time = db.Column(db.Float, default=0.0)
    time_drift = db.Column(db.Integer, default=0) # Seconds to offset from server time
    last_login_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_ip = db.Column(db.String(45))
    public_key = db.Column(db.Text)
    encrypted_private_key = db.Column(db.LargeBinary)

class AboutContent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.Text)  # "About our press" text
    services = db.Column(db.Text)     # List of services (T-shirts, Banners, etc.)
    ad_title = db.Column(db.String(150), default='')
    ad_description = db.Column(db.Text, default='')
    ad_video_file = db.Column(db.String(255), default='')
    # Slider Image Paths
    slider1 = db.Column(db.String(100), default='slider.1.jpg')
    slider2 = db.Column(db.String(100), default='slider.2.jpg')
    slider3 = db.Column(db.String(100), default='slider.3.jpg')

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True)
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    date_joined = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Link to Sales: One customer can have many sales
    sales = db.relationship('Sale', backref='customer', lazy=True)

# Update Sale model to link to a customer
class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='USD') # 'USD' or 'LRD'
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    sms_status = db.Column(db.String(20), default="Pending")

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    status = db.Column(db.String(20), default='Pending')  # Pending, Processing, Delivered, Cancelled
    production_stage = db.Column(db.String(20), default='quote')  # quote → delivered
    promised_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text)
    total_amount = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(3), default='USD')
    order_source = db.Column(db.String(50))
    date_ordered = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy=True)
    customer = db.relationship('Customer', backref='orders', lazy=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    quantity = db.Column(db.Integer, default=1)
    price_at_time = db.Column(db.Float) # Price when ordered
    currency = db.Column(db.String(3), default='USD') # 'USD' or 'LRD'
    
    product = db.relationship('Product', backref='order_items', lazy=True)

class DailyReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('admin.id'))
    report_text = db.Column(db.Text, nullable=False)
    total_sales = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(3), default='USD') # 'USD' or 'LRD'
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    staff_name = db.Column(db.String(50)) # To easily see who wrote it
    report_date = db.Column(db.Date)  # Business date for manual income entry
    payment_method = db.Column(db.String(30))  # cash, mobile_money, bank_transfer, other
    reference = db.Column(db.String(100))  # Receipt or transaction reference

    @property
    def effective_date(self):
        if self.report_date:
            return self.report_date
        if self.date_posted:
            return self.date_posted.date()
        return None

    @property
    def payment_method_label(self):
        labels = {
            'cash': 'Cash',
            'mobile_money': 'Mobile Money',
            'bank_transfer': 'Bank Transfer',
            'other': 'Other',
        }
        return labels.get(self.payment_method or 'other', 'Other')

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('admin.id'))
    staff_name = db.Column(db.String(50))
    check_in = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Active') # Active or Logged Out

class InventoryLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    item_name = db.Column(db.String(200))
    item_sku = db.Column(db.String(100))
    unit = db.Column(db.String(30))
    quantity = db.Column(db.Integer, nullable=False)
    transaction_type = db.Column(db.String(10))  # 'IN' or 'OUT'
    reason = db.Column(db.String(50))  # e.g. purchase, sale, damaged
    reference = db.Column(db.String(100))  # PO #, supplier, customer order
    recorded_by = db.Column(db.Integer, db.ForeignKey('admin.id'))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)

    product = db.relationship('Product', backref='inventory_logs')
    admin = db.relationship('Admin', backref='inventory_logs')

    @property
    def display_name(self):
        if self.item_name:
            return self.item_name
        if self.product:
            return self.product.name
        return '—'

    @property
    def is_manual(self):
        return self.product_id is None
# generate document
class GeneratedDocument(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    doc_type = db.Column(db.String(20))  # 'invoice', 'receipt', 'letterhead'
    doc_number = db.Column(db.String(50), unique=True)
    content = db.Column(db.Text)  # JSON snapshot of line items and customer
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=True)
    customer_name = db.Column(db.String(100))
    total_amount = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(3), default='USD')
    payment_status = db.Column(db.String(20), default='Pending')  # Paid, Pending
    issued_by = db.Column(db.Integer, db.ForeignKey('admin.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    creator = db.relationship('Admin', backref='documents')
    order = db.relationship('Order', backref='documents', lazy=True)

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='USD') # 'USD' or 'LRD'
    description = db.Column(db.String(255), nullable=False)
    recorded_by = db.Column(db.Integer, db.ForeignKey('admin.id'))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    admin = db.relationship('Admin', backref='expenses')
# halidays
class Event(db.Model):
    __tablename__ = 'event'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    event_type = db.Column(db.String(50))
    description = db.Column(db.Text)
class LoginLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    ip_address = db.Column(db.String(45))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20)) # 'success' or 'failed'

class SystemSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    is_active = db.Column(db.Boolean, default=True)  # True = Running, False = Locked
    lock_message = db.Column(db.String(255), default="System Maintenance: Please contact the Architect.")
    last_late_check_date = db.Column(db.Date, nullable=True)


class WhatsAppIntegration(db.Model):
    """Meta WhatsApp Business API credentials (Embedded Signup or manual import)."""
    __tablename__ = 'whatsapp_integration'
    id = db.Column(db.Integer, primary_key=True)
    waba_id = db.Column(db.String(32))
    phone_number_id = db.Column(db.String(32), nullable=False)
    display_phone = db.Column(db.String(20))
    business_name = db.Column(db.String(120))
    access_token_enc = db.Column(db.Text, nullable=False)
    connection_method = db.Column(db.String(30), default='embedded_signup')
    connected_by = db.Column(db.String(50))
    connected_at = db.Column(db.DateTime, default=datetime.utcnow)
    token_expires_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)


class AIChatMessage(db.Model):
    """Per-session AI conversation history (phone or web session token)."""
    __tablename__ = 'ai_chat_message'
    id = db.Column(db.Integer, primary_key=True)
    session_token = db.Column(db.String(80), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)  # user, assistant
    content = db.Column(db.Text, nullable=False)
    channel = db.Column(db.String(30), default='unknown')  # web, whatsapp_api, twilio_whatsapp
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PendingReceipt(db.Model):
    """WhatsApp order receipts awaiting shop intake."""
    __tablename__ = 'pending_receipt'
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(40), unique=True, nullable=False, index=True)
    payload = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, converted
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    order = db.relationship('Order', backref='pending_receipt', lazy=True)
