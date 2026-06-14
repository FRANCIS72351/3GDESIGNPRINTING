"""
3G DESIGN — Billing: professional invoices & receipts
"""
import io
import json
import os
from datetime import datetime
from functools import wraps

from flask import (
    Blueprint, abort, current_app, flash, jsonify, redirect,
    render_template, request, send_file, session, url_for,
)
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from models import db, Product, Customer, Order, OrderItem, GeneratedDocument, Admin

billing_bp = Blueprint('billing', __name__)

BRAND_NAVY = '#0B1F3A'
BRAND_GOLD = '#C9A84C'
COMPANY = {
    'name': '3G DESIGN',
    'tagline': 'Quality in Every Print, Excellence in Every Design',
    'phone': '+231 77 532 3731',
    'email': 'info@3GDESIGNprinting.com',
    'web': 'www.olatricity.com',
    'address': 'Newport & Benson Street, Monrovia, Liberia',
}


def billing_roles_required(*roles):
    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'admin_logged_in' not in session:
                return redirect(url_for('login'))
            if session.get('role') not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return wrapper


def next_doc_number(doc_type):
    prefix = 'INV' if doc_type == 'invoice' else 'RCT'
    year = datetime.utcnow().year
    pattern = f'{prefix}-{year}-%'
    last = (
        GeneratedDocument.query
        .filter(GeneratedDocument.doc_number.like(pattern))
        .order_by(GeneratedDocument.id.desc())
        .first()
    )
    seq = 1
    if last and last.doc_number:
        try:
            seq = int(last.doc_number.split('-')[-1]) + 1
        except ValueError:
            seq = GeneratedDocument.query.filter_by(doc_type=doc_type).count() + 1
    return f'{prefix}-{year}-{seq:05d}'


def format_money(amount, currency='USD'):
    symbol = 'L$' if currency == 'LRD' else '$'
    return f'{symbol}{amount:,.2f}'


def parse_line_items_from_form():
    descriptions = request.form.getlist('description[]') or request.form.getlist('description')
    quantities = request.form.getlist('quantity[]') or request.form.getlist('quantity')
    unit_prices = request.form.getlist('unit_price[]') or request.form.getlist('unit_price')
    product_ids = request.form.getlist('product_id[]') or request.form.getlist('product_id')

    items = []
    for i, desc in enumerate(descriptions):
        desc = (desc or '').strip()
        if not desc:
            continue
        qty = max(1, int(quantities[i] or 1) if i < len(quantities) else 1)
        price = float(unit_prices[i] or 0) if i < len(unit_prices) else 0.0
        pid = int(product_ids[i]) if i < len(product_ids) and product_ids[i] else None
        items.append({
            'description': desc,
            'quantity': qty,
            'unit_price': price,
            'line_total': round(qty * price, 2),
            'product_id': pid,
        })
    return items


def get_or_create_customer(name, phone='', email='', address=''):
    name = (name or '').strip()
    if not name:
        return None
    customer = None
    if phone:
        customer = Customer.query.filter_by(phone=phone.strip()).first()
    if not customer and email:
        customer = Customer.query.filter_by(email=email.strip()).first()
    if not customer:
        customer = Customer.query.filter(Customer.name.ilike(name)).first()
    if not customer:
        customer = Customer(
            name=name,
            phone=phone.strip() or None,
            email=email.strip() or None,
            address=address.strip() or None,
        )
        db.session.add(customer)
        db.session.flush()
    else:
        if phone and not customer.phone:
            customer.phone = phone.strip()
        if email and not customer.email:
            customer.email = email.strip()
        if address and not customer.address:
            customer.address = address.strip()
    return customer


def build_document_payload(doc_type, customer_data, items, currency='USD', payment_status='Pending', notes='', discount=0):
    subtotal = round(sum(i['line_total'] for i in items), 2)
    discount = float(discount or 0)
    total = round(max(subtotal - discount, 0), 2)
    doc_number = next_doc_number(doc_type)
    return {
        'doc_type': doc_type,
        'doc_number': doc_number,
        'customer': customer_data,
        'items': items,
        'currency': currency,
        'subtotal': subtotal,
        'discount': discount,
        'total': total,
        'payment_status': payment_status,
        'notes': notes,
        'issued_at': datetime.utcnow().isoformat(),
        'issued_by_name': session.get('username', 'Staff'),
    }


def persist_document(payload, order_id=None):
    doc = GeneratedDocument(
        doc_type=payload['doc_type'],
        doc_number=payload['doc_number'],
        content=json.dumps(payload),
        order_id=order_id,
        customer_name=payload['customer'].get('name'),
        total_amount=payload['total'],
        currency=payload['currency'],
        payment_status=payload['payment_status'],
        issued_by=session.get('admin_id'),
    )
    db.session.add(doc)
    db.session.commit()
    return doc


def create_order_from_items(customer, items, currency, payment_status, source='In-Store'):
    total = round(sum(i['line_total'] for i in items), 2)
    order = Order(
        customer_id=customer.id if customer else None,
        status='Paid' if payment_status == 'Paid' else 'Pending',
        production_stage='quote',
        total_amount=total,
        currency=currency,
        order_source=source,
    )
    db.session.add(order)
    db.session.flush()
    for item in items:
        db.session.add(OrderItem(
            order_id=order.id,
            product_id=item.get('product_id'),
            quantity=item['quantity'],
            price_at_time=item['unit_price'],
            currency=currency,
        ))
    db.session.commit()
    return order


def render_pdf(payload):
    buffer = io.BytesIO()
    width, height = letter
    p = canvas.Canvas(buffer, pagesize=letter)
    doc_type = payload['doc_type']
    is_receipt = doc_type == 'receipt'
    accent = colors.HexColor(BRAND_GOLD if is_receipt else BRAND_NAVY)
    navy = colors.HexColor(BRAND_NAVY)

    # Top bar
    p.setFillColor(navy)
    p.rect(0, height - 32, width, 32, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont('Helvetica-Bold', 11)
    p.drawString(50, height - 22, COMPANY['name'])
    p.drawRightString(width - 50, height - 22, doc_type.upper())

    # Logo
    logo_path = os.path.join(current_app.root_path, 'static', 'img', 'LOGO.png')
    y_top = height - 100
    if os.path.exists(logo_path):
        p.drawImage(logo_path, 50, y_top - 10, width=90, height=50, preserveAspectRatio=True, mask='auto')

    p.setFillColor(colors.black)
    p.setFont('Helvetica-Bold', 14)
    p.drawString(160, y_top + 25, COMPANY['name'])
    p.setFont('Helvetica', 9)
    p.drawString(160, y_top + 10, COMPANY['address'])
    p.drawString(160, y_top - 2, f"Tel: {COMPANY['phone']}  |  {COMPANY['email']}")
    p.drawString(160, y_top - 14, COMPANY['web'])

    # Doc meta box
    box_y = height - 175
    p.setStrokeColor(accent)
    p.setLineWidth(1.5)
    p.rect(width - 230, box_y, 180, 70, fill=0, stroke=1)
    p.setFont('Helvetica-Bold', 10)
    p.drawString(width - 220, box_y + 52, f"{'RECEIPT' if is_receipt else 'INVOICE'} NO.")
    p.setFont('Helvetica-Bold', 12)
    p.drawString(width - 220, box_y + 36, payload['doc_number'])
    p.setFont('Helvetica', 9)
    p.drawString(width - 220, box_y + 20, f"Date: {datetime.utcnow().strftime('%d %b %Y')}")
    p.drawString(width - 220, box_y + 6, f"Status: {payload['payment_status']}")

    # Customer
    cust = payload['customer']
    p.setFont('Helvetica-Bold', 10)
    p.drawString(50, box_y + 52, 'BILL TO')
    p.setFont('Helvetica', 10)
    p.drawString(50, box_y + 36, cust.get('name', 'Valued Customer'))
    line_y = box_y + 22
    for field in ('phone', 'email', 'address'):
        val = cust.get(field)
        if val:
            p.setFont('Helvetica', 9)
            p.drawString(50, line_y, val)
            line_y -= 12

    # Table header
    table_top = box_y - 30
    p.setFillColor(colors.HexColor('#F2F4F7'))
    p.rect(50, table_top - 22, width - 100, 22, fill=1, stroke=0)
    p.setFillColor(colors.black)
    p.setFont('Helvetica-Bold', 9)
    p.drawString(55, table_top - 15, '#')
    p.drawString(75, table_top - 15, 'DESCRIPTION')
    p.drawRightString(width - 200, table_top - 15, 'QTY')
    p.drawRightString(width - 130, table_top - 15, 'UNIT')
    p.drawRightString(width - 55, table_top - 15, 'AMOUNT')

    # Line items
    y = table_top - 40
    currency = payload['currency']
    for idx, item in enumerate(payload['items'], 1):
        if y < 140:
            p.showPage()
            y = height - 80
        p.setFont('Helvetica', 9)
        p.drawString(55, y, str(idx))
        desc = item['description'][:55] + ('...' if len(item['description']) > 55 else '')
        p.drawString(75, y, desc)
        p.drawRightString(width - 200, y, str(item['quantity']))
        p.drawRightString(width - 130, y, format_money(item['unit_price'], currency))
        p.drawRightString(width - 55, y, format_money(item['line_total'], currency))
        y -= 18

    # Totals
    y -= 10
    p.setStrokeColor(navy)
    p.line(width - 250, y + 8, width - 50, y + 8)
    y -= 8
    p.setFont('Helvetica', 10)
    p.drawRightString(width - 130, y, 'Subtotal:')
    p.drawRightString(width - 55, y, format_money(payload['subtotal'], currency))
    y -= 16
    if payload.get('discount', 0) > 0:
        p.drawRightString(width - 130, y, 'Discount:')
        p.drawRightString(width - 55, y, f"-{format_money(payload['discount'], currency)}")
        y -= 16
    p.setFont('Helvetica-Bold', 11)
    p.setFillColor(navy)
    p.drawRightString(width - 130, y, 'TOTAL:')
    p.drawRightString(width - 55, y, format_money(payload['total'], currency))
    p.setFillColor(colors.black)

    # Notes
    if payload.get('notes'):
        y -= 30
        p.setFont('Helvetica-Bold', 9)
        p.drawString(50, y, 'Notes / Terms')
        p.setFont('Helvetica', 8)
        notes = payload['notes'][:200]
        p.drawString(50, y - 12, notes)

    # Signature
    p.setFont('Helvetica', 10)
    p.drawString(50, 95, 'Authorized by:')
    p.line(50, 75, 200, 75)
    p.setFont('Helvetica-Bold', 9)
    p.drawString(50, 62, payload.get('issued_by_name', 'Staff'))
    p.setFont('Helvetica', 8)
    p.drawString(50, 50, COMPANY['name'])

    # Footer
    p.setFillColor(navy)
    p.rect(0, 0, width, 28, fill=1, stroke=0)
    p.setFillColor(colors.HexColor(BRAND_GOLD))
    p.setFont('Helvetica-Bold', 8)
    p.drawCentredString(width / 2, 10, COMPANY['tagline'].upper())

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer


def issue_document_from_form(doc_type, save_order=False, order_source='In-Store'):
    customer_name = request.form.get('customer_name', '').strip()
    if not customer_name:
        flash('Customer name is required.', 'error')
        return None, redirect(url_for('billing.billing_portal'))

    items = parse_line_items_from_form()
    if not items:
        flash('Add at least one line item.', 'error')
        return None, redirect(url_for('billing.billing_portal'))

    currency = request.form.get('currency', 'USD')
    payment_status = request.form.get('payment_status', 'Pending')
    if doc_type == 'receipt':
        payment_status = 'Paid'
    notes = request.form.get('notes', '').strip()

    customer = get_or_create_customer(
        customer_name,
        request.form.get('customer_phone', ''),
        request.form.get('customer_email', ''),
        request.form.get('customer_address', ''),
    )

    payload = build_document_payload(
        doc_type, {
            'name': customer_name,
            'phone': request.form.get('customer_phone', ''),
            'email': request.form.get('customer_email', ''),
            'address': request.form.get('customer_address', ''),
        },
        items, currency, payment_status, notes,
        discount=request.form.get('discount', 0),
    )

    order_id = None
    if save_order:
        order = create_order_from_items(customer, items, currency, payment_status, order_source)
        order_id = order.id

    doc = persist_document(payload, order_id=order_id)
    return doc, payload


def document_from_order(order, doc_type):
    existing = (
        GeneratedDocument.query
        .filter_by(order_id=order.id, doc_type=doc_type)
        .order_by(GeneratedDocument.id.desc())
        .first()
    )
    if existing and not request.args.get('regenerate'):
        return existing, json.loads(existing.content)

    items = []
    for oi in order.items:
        pname = oi.product.name if oi.product else 'Custom Item'
        items.append({
            'description': pname,
            'quantity': oi.quantity,
            'unit_price': oi.price_at_time or 0,
            'line_total': round((oi.price_at_time or 0) * oi.quantity, 2),
            'product_id': oi.product_id,
        })
    if not items:
        items = [{'description': 'Order services', 'quantity': 1, 'unit_price': order.total_amount, 'line_total': order.total_amount, 'product_id': None}]

    cust = order.customer
    payment_status = 'Paid' if doc_type == 'receipt' or order.status == 'Paid' else 'Pending'
    payload = build_document_payload(
        doc_type,
        {
            'name': cust.name if cust else 'Valued Customer',
            'phone': cust.phone if cust else '',
            'email': cust.email if cust else '',
            'address': cust.address if cust else '',
        },
        items,
        order.currency or 'USD',
        payment_status,
        '',
    )
    doc = persist_document(payload, order_id=order.id)
    return doc, payload


@billing_bp.route('/admin/billing')
@billing_bp.route('/admin_portal')
@billing_roles_required('admin', 'moderator')
def billing_portal():
    products = Product.query.order_by(Product.name).all()
    recent_docs = GeneratedDocument.query.order_by(GeneratedDocument.created_at.desc()).limit(8).all()
    prefill = {
        'customer_name': request.args.get('name', ''),
        'customer_phone': request.args.get('phone', ''),
        'notes': request.args.get('notes', ''),
    }
    return render_template('billing_portal.html', products=products, recent_docs=recent_docs, prefill=prefill)


@billing_bp.route('/admin/billing/issue', methods=['POST'])
@billing_roles_required('admin', 'moderator')
def issue_document():
    doc_type = request.form.get('doc_type', 'invoice')
    if doc_type not in ('invoice', 'receipt'):
        doc_type = 'invoice'
    save_order = request.form.get('save_order') == '1'
    doc, payload = issue_document_from_form(doc_type, save_order=save_order)
    if doc is None:
        return payload  # redirect from error

    action = request.form.get('action', 'download')
    if action == 'preview':
        return redirect(url_for('billing.document_preview', doc_id=doc.id))
    buffer = render_pdf(payload)
    filename = f"{payload['doc_number']}_{payload['customer']['name'].replace(' ', '_')}.pdf"
    flash(f"{'Receipt' if doc_type == 'receipt' else 'Invoice'} {payload['doc_number']} issued successfully.", 'success')
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')


@billing_bp.route('/admin/billing/log-order', methods=['POST'])
@billing_roles_required('admin', 'moderator')
def log_manual_order():
    """WhatsApp / walk-in order: save to system and issue invoice or receipt."""
    doc_type = 'receipt' if request.form.get('payment_status') == 'Paid' else 'invoice'
    doc, payload = issue_document_from_form(doc_type, save_order=True, order_source='WhatsApp Direct')
    if doc is None:
        return payload
    buffer = render_pdf(payload)
    flash(f"Order saved and {doc_type} {payload['doc_number']} generated.", 'success')
    return send_file(buffer, as_attachment=True, download_name=f"{payload['doc_number']}.pdf", mimetype='application/pdf')


@billing_bp.route('/admin/billing/document/<int:doc_id>')
@billing_roles_required('admin', 'moderator')
def document_preview(doc_id):
    doc = GeneratedDocument.query.get_or_404(doc_id)
    payload = json.loads(doc.content) if doc.content else {}
    return render_template('document_print.html', doc=doc, payload=payload, company=COMPANY)


@billing_bp.route('/admin/billing/document/<int:doc_id>/pdf')
@billing_roles_required('admin', 'moderator')
def document_pdf(doc_id):
    doc = GeneratedDocument.query.get_or_404(doc_id)
    payload = json.loads(doc.content) if doc.content else {}
    buffer = render_pdf(payload)
    filename = f"{doc.doc_number}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')


@billing_bp.route('/admin/billing/history')
@billing_roles_required('admin', 'moderator')
def billing_history():
    search = request.args.get('search', '').strip()
    doc_type = request.args.get('type', '')
    query = GeneratedDocument.query
    if search:
        query = query.filter(
            (GeneratedDocument.doc_number.ilike(f'%{search}%')) |
            (GeneratedDocument.customer_name.ilike(f'%{search}%'))
        )
    if doc_type in ('invoice', 'receipt'):
        query = query.filter_by(doc_type=doc_type)
    docs = query.order_by(GeneratedDocument.created_at.desc()).limit(200).all()
    return render_template('billing_history.html', docs=docs, search=search, doc_type=doc_type)


@billing_bp.route('/admin/billing/order/<int:order_id>/<doc_type>')
@billing_roles_required('admin', 'moderator')
def order_document(order_id, doc_type):
    if doc_type not in ('invoice', 'receipt'):
        abort(404)
    order = Order.query.get_or_404(order_id)
    doc, payload = document_from_order(order, doc_type)
    action = request.args.get('action', 'download')
    if action == 'preview':
        return redirect(url_for('billing.document_preview', doc_id=doc.id))
    buffer = render_pdf(payload)
    return send_file(buffer, as_attachment=True, download_name=f"{payload['doc_number']}.pdf", mimetype='application/pdf')


# Backward-compatible redirects for old routes
@billing_bp.route('/admin/generate-order-pdf', methods=['POST'])
@billing_bp.route('/admin/generate-order-pdf/<int:order_id>', methods=['GET'])
@billing_roles_required('admin', 'moderator')
def legacy_generate_order_pdf(order_id=None):
    if order_id:
        order = Order.query.get_or_404(order_id)
        doc_type = 'receipt' if order.status == 'Paid' else 'invoice'
        return redirect(url_for('billing.order_document', order_id=order_id, doc_type=doc_type))
    return redirect(url_for('billing.billing_portal'))


@billing_bp.route('/download-doc/<doc_type>')
@billing_roles_required('admin', 'moderator')
def legacy_download_doc(doc_type):
    if doc_type == 'letterhead':
        return redirect(url_for('billing.billing_portal'))
    return redirect(url_for('billing.billing_portal'))
