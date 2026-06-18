"""
3G DESIGN — Operations Center
WhatsApp order inbox, print production pipeline, customer intelligence.
"""
import json
from datetime import datetime
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from models import db, Order, OrderItem, Customer, PendingReceipt, CallLog, GeneratedDocument, Product
from site_config import get_public_site_url, get_whatsapp_webhook_url, whatsapp_env_status

operations_bp = Blueprint('operations', __name__)

PRODUCTION_STAGES = [
    ('Quote', 'quote', 'secondary'),
    ('Design', 'design', 'info'),
    ('Pre-Press', 'prepress', 'primary'),
    ('Printing', 'printing', 'warning'),
    ('Quality Check', 'qc', 'dark'),
    ('Ready', 'ready', 'success'),
    ('Delivered', 'delivered', 'success'),
]

STAGE_KEYS = [s[1] for s in PRODUCTION_STAGES]


def ops_roles_required(*roles):
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


def stage_badge(stage):
    for label, key, color in PRODUCTION_STAGES:
        if key == stage:
            return label, color
    return stage or 'Quote', 'secondary'


def convert_receipt_to_order(receipt):
    data = json.loads(receipt.payload)
    items = data.get('items', [])
    if not items:
        return None

    total_usd = data.get('total_usd', 0)
    total_lrd = data.get('total_lrd', 0)
    currency = 'LRD' if total_lrd and not total_usd else 'USD'
    total = total_lrd if currency == 'LRD' else total_usd

    customer = Customer.query.filter_by(name='WhatsApp Customer').first()
    customer_name = data.get('customer_name') or data.get('name')
    customer_phone = data.get('customer_phone') or data.get('phone')
    if customer_phone:
        from whatsapp_service import phone_display, upsert_customer
        customer = upsert_customer(customer_phone, customer_name or '')
    elif customer_name:
        customer = Customer.query.filter(Customer.name.ilike(f'%{customer_name[:40]}%')).first()
        if not customer:
            customer = Customer(name=customer_name, phone=customer_phone)
            db.session.add(customer)
            db.session.flush()
    if not customer:
        customer = Customer(name='WhatsApp Customer', phone=customer_phone)
        db.session.add(customer)
        db.session.flush()

    order = Order(
        customer_id=customer.id,
        status='Pending',
        production_stage='quote',
        total_amount=total,
        currency=currency,
        order_source='Website WhatsApp',
        notes=data.get('message_text', '')[:500],
    )
    db.session.add(order)
    db.session.flush()

    for item in items:
        pid = item.get('product_id')
        try:
            pid = int(pid) if pid else None
        except (TypeError, ValueError):
            pid = None
        db.session.add(OrderItem(
            order_id=order.id,
            product_id=pid,
            quantity=item.get('quantity', 1),
            price_at_time=item.get('price', 0),
            currency=item.get('currency', currency),
        ))

    receipt.status = 'converted'
    receipt.order_id = order.id
    db.session.commit()
    return order


@operations_bp.route('/admin/operations')
@ops_roles_required('admin', 'moderator')
def operations_hub():
    pending = (
        PendingReceipt.query
        .filter((PendingReceipt.status == 'pending') | (PendingReceipt.status.is_(None)))
        .order_by(PendingReceipt.created_at.desc())
        .limit(20)
        .all()
    )
    pending_parsed = []
    for r in pending:
        try:
            data = json.loads(r.payload)
        except Exception:
            data = {}
        pending_parsed.append({
            'receipt': r,
            'line_items': data.get('items', []),
            'total_usd': data.get('total_usd', 0),
            'total_lrd': data.get('total_lrd', 0),
            'share_image': data.get('share_image', ''),
        })

    active_orders = (
        Order.query
        .filter(Order.production_stage != 'delivered')
        .order_by(Order.date_ordered.desc())
        .limit(50)
        .all()
    )

    board = {key: [] for _, key, _ in PRODUCTION_STAGES}
    for order in active_orders:
        stage = order.production_stage or 'quote'
        if stage not in board:
            stage = 'quote'
        board[stage].append(order)

    stats = {
        'pending_inbox': len(pending_parsed),
        'active_jobs': len(active_orders),
        'printing_now': len(board.get('printing', [])),
        'ready_pickup': len(board.get('ready', [])),
    }

    return render_template(
        'operations_hub.html',
        pending_orders=pending_parsed,
        board=board,
        stages=PRODUCTION_STAGES,
        stats=stats,
    )


@operations_bp.route('/admin/operations/convert/<token>', methods=['POST'])
@ops_roles_required('admin', 'moderator')
def convert_pending_order(token):
    receipt = PendingReceipt.query.filter_by(token=token).first_or_404()
    if receipt.status == 'converted' and receipt.order_id:
        flash('Order already converted.', 'info')
        return redirect(url_for('billing.order_document', order_id=receipt.order_id, doc_type='invoice'))

    order = convert_receipt_to_order(receipt)
    if not order:
        flash('Could not convert — no items in receipt.', 'error')
        return redirect(url_for('operations.operations_hub'))

    flash(f'WhatsApp order #{order.id} added to production pipeline.', 'success')
    return redirect(url_for('billing.order_document', order_id=order.id, doc_type='invoice'))


@operations_bp.route('/admin/operations/stage/<int:order_id>', methods=['POST'])
@ops_roles_required('admin', 'moderator')
def update_production_stage(order_id):
    order = Order.query.get_or_404(order_id)
    stage = request.form.get('production_stage', 'quote')
    if stage not in STAGE_KEYS:
        flash('Invalid production stage.', 'error')
        return redirect(request.referrer or url_for('operations.operations_hub'))

    order.production_stage = stage
    if stage == 'delivered':
        order.status = 'Delivered'
    elif stage in ('printing', 'prepress', 'qc'):
        order.status = 'Processing'
    promised = request.form.get('promised_date', '').strip()
    if promised:
        try:
            order.promised_date = datetime.strptime(promised, '%Y-%m-%d').date()
        except ValueError:
            pass
    db.session.commit()
    flash(f'Job #{order.id} moved to {stage_badge(stage)[0]}.', 'success')
    return redirect(request.referrer or url_for('operations.operations_hub'))


@operations_bp.route('/admin/customer')
@ops_roles_required('admin', 'moderator')
def customer_lookup():
    phone = request.args.get('phone', '').strip()
    q = request.args.get('q', '').strip()
    customer = None
    calls = []
    orders = []
    documents = []
    recent_whatsapp = []

    wa_status = whatsapp_env_status()

    if phone:
        customer = Customer.query.filter(Customer.phone.ilike(f'%{phone}%')).first()
        calls = CallLog.query.filter(CallLog.phone_number.ilike(f'%{phone}%')).order_by(CallLog.timestamp.desc()).limit(30).all()
        if customer:
            orders = Order.query.filter_by(customer_id=customer.id).order_by(Order.date_ordered.desc()).limit(50).all()
            documents = GeneratedDocument.query.filter_by(customer_name=customer.name).order_by(GeneratedDocument.created_at.desc()).limit(20).all()
    elif q:
        customer = Customer.query.filter(
            (Customer.name.ilike(f'%{q}%')) | (Customer.phone.ilike(f'%{q}%')) | (Customer.email.ilike(f'%{q}%'))
        ).first()
        if customer:
            phone = customer.phone or ''
            calls = CallLog.query.filter(CallLog.phone_number.ilike(f'%{phone}%')).order_by(CallLog.timestamp.desc()).limit(30).all() if phone else []
            orders = Order.query.filter_by(customer_id=customer.id).order_by(Order.date_ordered.desc()).limit(50).all()
            documents = GeneratedDocument.query.filter_by(customer_name=customer.name).order_by(GeneratedDocument.created_at.desc()).limit(20).all()
    else:
        recent_whatsapp = (
            CallLog.query
            .filter_by(source='whatsapp_api')
            .order_by(CallLog.timestamp.desc())
            .limit(15)
            .all()
        )

    return render_template(
        'customer_360.html',
        customer=customer,
        phone=phone,
        q=q,
        calls=calls,
        orders=orders,
        documents=documents,
        recent_whatsapp=recent_whatsapp,
        wa_status=wa_status,
        webhook_url=get_whatsapp_webhook_url(request.url_root),
        public_site_url=get_public_site_url(request.url_root),
        stages=PRODUCTION_STAGES,
    )


@operations_bp.route('/admin/operations/quote-from-call/<int:call_id>')
@ops_roles_required('admin', 'moderator')
def quote_from_call(call_id):
    call = CallLog.query.get_or_404(call_id)
    return redirect(url_for(
        'billing.billing_portal',
        phone=call.phone_number or '',
        name=call.caller_name or '',
        notes=call.notes or call.transcript or '',
    ))
