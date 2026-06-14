"""
3G DESIGN — Customer AI assistant.
Session token = phone number (WhatsApp) or browser localStorage UUID (web chat).
Conversation history persisted in SQLite for continuity across sessions.
"""
import os
import re
import json

import requests

from models import db, AIChatMessage, Product, Customer, Order

MAX_HISTORY = 16
BUSINESS_NAME = '3G DESIGN'
BUSINESS_PHONE = '+231 775 323 731'
BUSINESS_ADDRESS = 'Newport & Benson Street, Monrovia, Liberia'
BUSINESS_HOURS = 'Monday–Saturday, 8:00 AM – 6:00 PM'


def _normalize_session(session_token):
    if not session_token:
        return ''
    token = str(session_token).strip()
    if token.startswith('whatsapp:'):
        token = token.split(':', 1)[1]
    digits = re.sub(r'\D', '', token)
    if len(digits) >= 9 and not token.startswith('web:'):
        return f'+{digits}'
    return token


def _recent_messages(session_token, limit=MAX_HISTORY):
    rows = (
        AIChatMessage.query
        .filter_by(session_token=session_token)
        .order_by(AIChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    return rows[::-1]


def _save_message(session_token, role, content, channel='unknown'):
    row = AIChatMessage(
        session_token=session_token,
        role=role,
        content=(content or '')[:8000],
        channel=channel,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _product_catalog_text():
    products = Product.query.order_by(Product.category, Product.name).limit(12).all()
    if not products:
        return 'Visit our shop for printing, branding, and design services.'
    lines = []
    for p in products:
        price = f'{p.currency or "USD"} {p.price:.2f}' if p.price else 'Quote on request'
        cat = f' ({p.category})' if p.category else ''
        lines.append(f'• {p.name}{cat} — {price}')
    return '\n'.join(lines)


def _customer_context(session_token):
    customer = Customer.query.filter(
        (Customer.phone == session_token) | (Customer.phone.ilike(f'%{session_token[-9:]}%'))
    ).first()
    if not customer:
        return ''
    orders = Order.query.filter_by(customer_id=customer.id).order_by(Order.date_ordered.desc()).limit(3).all()
    if not orders:
        return f'Returning customer: {customer.name}.'
    bits = [f'{o.status} order #{o.id}' for o in orders]
    return f'Customer {customer.name}. Recent orders: {", ".join(bits)}.'


def _rule_based_reply(session_token, user_message):
    """Intelligent fallback when no LLM API key is configured."""
    msg = (user_message or '').strip().lower()
    catalog = _product_catalog_text()
    ctx = _customer_context(session_token)

    if any(w in msg for w in ('hello', 'hi', 'hey', 'good morning', 'good afternoon')):
        return (
            f"Hello! Welcome to *{BUSINESS_NAME}* — Monrovia's premier print house.\n\n"
            "I can help with:\n"
            "• Product prices & quotes\n"
            "• Business hours & location\n"
            "• Placing an order\n\n"
            "What would you like today?"
        )

    if any(w in msg for w in ('hour', 'open', 'close', 'when')):
        return f"We're open *{BUSINESS_HOURS}*.\n\n📍 {BUSINESS_ADDRESS}"

    if any(w in msg for w in ('where', 'location', 'address', 'find you')):
        return f"📍 *{BUSINESS_ADDRESS}*\n📞 {BUSINESS_PHONE}"

    if any(w in msg for w in ('price', 'cost', 'quote', 'how much', 'rate', 'product', 'service', 'print')):
        return (
            f"Here are some of our offerings:\n\n{catalog}\n\n"
            "Tell me quantity and item for a custom quote, or browse our full catalog on the website."
        )

    if any(w in msg for w in ('order', 'track', 'status', 'delivery')):
        if ctx:
            return f"{ctx}\n\nFor detailed tracking, our team will follow up shortly. Call {BUSINESS_PHONE} for urgent orders."
        return (
            "To place or track an order, share what you need (item, quantity, deadline). "
            f"Our team at {BUSINESS_PHONE} will confirm pricing and pickup."
        )

    if any(w in msg for w in ('thank', 'thanks')):
        return "You're welcome! Quality in every print — excellence in every design. 🙏"

    if any(w in msg for w in ('help', 'menu', 'options')):
        return (
            "Ask me about:\n"
            "• *Prices* — e.g. \"How much for t-shirts?\"\n"
            "• *Hours* — when we're open\n"
            "• *Location* — find our shop\n"
            "• *Orders* — place or check an order"
        )

    return (
        f"Thanks for your message! A specialist at *{BUSINESS_NAME}* will assist you soon.\n\n"
        f"In the meantime, call/WhatsApp {BUSINESS_PHONE} or ask about *prices*, *hours*, or *orders*."
    )


def _openai_reply(session_token, user_message, history):
    api_key = os.getenv('OPENAI_API_KEY', '').strip()
    if not api_key:
        return None

    catalog = _product_catalog_text()
    ctx = _customer_context(session_token)
    system = (
        f"You are the friendly AI assistant for {BUSINESS_NAME}, a premium print and design shop in Monrovia, Liberia. "
        f"Address: {BUSINESS_ADDRESS}. Phone: {BUSINESS_PHONE}. Hours: {BUSINESS_HOURS}. "
        f"Be concise, professional, and helpful. Use WhatsApp-friendly formatting (*bold* sparingly). "
        f"Product catalog:\n{catalog}\n{ctx}"
    )

    messages = [{'role': 'system', 'content': system}]
    for h in history[-10:]:
        if h.role in ('user', 'assistant'):
            messages.append({'role': h.role, 'content': h.content})
    messages.append({'role': 'user', 'content': user_message})

    try:
        resp = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={
                'model': os.getenv('OPENAI_MODEL', 'gpt-4o-mini'),
                'messages': messages,
                'max_tokens': 500,
                'temperature': 0.6,
            },
            timeout=45,
        )
        data = resp.json()
        if resp.ok:
            return data['choices'][0]['message']['content'].strip()
    except Exception:
        pass
    return None


def handle_customer_message(session_token, user_message, channel='unknown'):
    """
    Core entry point — same logic for WhatsApp (phone as session) and web chat (UUID).
    Returns assistant reply text.
    """
    session_token = _normalize_session(session_token)
    user_message = (user_message or '').strip()
    if not session_token or not user_message:
        return "I didn't catch that — please send your message again."

    _save_message(session_token, 'user', user_message, channel=channel)
    history = _recent_messages(session_token)

    reply = _openai_reply(session_token, user_message, history)
    if not reply:
        reply = _rule_based_reply(session_token, user_message)

    _save_message(session_token, 'assistant', reply, channel=channel)
    return reply
