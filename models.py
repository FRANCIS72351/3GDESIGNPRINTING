from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True)
    role = db.Column(db.String(20), default='moderator') # admin, moderator


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50)) # e.g., 'T-Shirt', 'Frame'
    price = db.Column(db.Float, default=0.0) # Base price
    currency = db.Column(db.String(3), default='USD') # 'USD' or 'LRD'
    stock = db.Column(db.Integer, default=0) # Total stock
    image = db.Column(db.String(100))
    description = db.Column(db.Text)
    
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

class CallLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20))
    transcript = db.Column(db.Text)        # Transcription from AssemblyAI
    audio_url = db.Column(db.String(255))  # Twilio recording link
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password_hash = db.Column(db.String(128))
    email = db.Column(db.String(120))
    role = db.Column(db.String(20), default='admin')  # 'admin' or 'staff'
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

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    status = db.Column(db.String(20), default='Pending') # Pending, Processing, Shipped, Delivered, Cancelled
    total_amount = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(3), default='USD') # 'USD' or 'LRD'
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    quantity = db.Column(db.Integer, default=1)
    price_at_time = db.Column(db.Float) # Price when ordered
    currency = db.Column(db.String(3), default='USD') # 'USD' or 'LRD'

class DailyReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('admin.id'))
    report_text = db.Column(db.Text, nullable=False)
    total_sales = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(3), default='USD') # 'USD' or 'LRD'
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    staff_name = db.Column(db.String(50)) # To easily see who wrote it

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('admin.id'))
    staff_name = db.Column(db.String(50))
    check_in = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Active') # Active or Logged Out

class InventoryLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    quantity = db.Column(db.Integer, nullable=False)
    transaction_type = db.Column(db.String(10)) # 'IN' or 'OUT'
    recorded_by = db.Column(db.Integer, db.ForeignKey('admin.id'))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)

    product = db.relationship('Product', backref='inventory_logs')
    admin = db.relationship('Admin', backref='inventory_logs')

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='USD') # 'USD' or 'LRD'
    description = db.Column(db.String(255), nullable=False)
    recorded_by = db.Column(db.Integer, db.ForeignKey('admin.id'))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    admin = db.relationship('Admin', backref='expenses')

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
