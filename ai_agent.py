"""
3G Design — Customer AI assistant.
Session token = phone number (WhatsApp) or browser localStorage UUID (web chat).
Conversation history persisted in SQLite for continuity across sessions.
"""
import os
import re
import json

import requests

from models import db, AIChatMessage, Product, Customer, Order, AboutContent
from server_stability import get_about_content

MAX_HISTORY = 16
BUSINESS_NAME = '3G Design'
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


def get_session_messages(session_token, limit=MAX_HISTORY):
    """Public API for restoring web chat history."""
    session_token = _normalize_session(session_token)
    if not session_token:
        return []
    return [
        {'role': row.role, 'content': row.content}
        for row in _recent_messages(session_token, limit=limit)
        if row.role in ('user', 'assistant')
    ]


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


def _about_business_context():
    """Admin-managed About page copy — primary business knowledge source."""
    content = get_about_content(db, AboutContent)
    if not content:
        return ''
    parts = []
    if content.description and content.description.strip():
        parts.append(f'About: {content.description.strip()}')
    if content.services and content.services.strip():
        parts.append(f'Services: {content.services.strip()}')
    return '\n'.join(parts)


def _business_knowledge_block():
    """Combined static + DB business facts for prompts and fallbacks."""
    lines = [
        f'Name: {BUSINESS_NAME}',
        f'Address: {BUSINESS_ADDRESS}',
        f'Phone: {BUSINESS_PHONE}',
        f'Hours: {BUSINESS_HOURS}',
    ]
    about = _about_business_context()
    if about:
        lines.append(about)
    catalog = _product_catalog_text()
    if catalog:
        lines.append(f'Product catalog:\n{catalog}')
    return '\n'.join(lines)


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


def _is_order_intent(msg):
    """Order status / tracking — checked before hours to avoid 'when' collisions."""
    if any(w in msg for w in (
        'track my', 'tracking', 'order status', 'delivery status',
        'where is my order', 'when will my order', 'my order be ready',
        'order be ready', 'pick up my order', 'pickup my order',
    )):
        return True
    if 'order' in msg and any(w in msg for w in (
        'status', 'ready', 'track', 'delivery', 'when', 'pick', 'done', 'finish', 'complete',
    )):
        return True
    return False


def _is_hours_intent(msg):
    if _is_order_intent(msg):
        return False
    if any(w in msg for w in (
        'business hour', 'opening hour', 'what time do you', 'what hours',
        'when are you open', 'when do you open', 'when do you close',
        'are you open', 'closed today', 'open today', 'opening time', 'closing time',
    )):
        return True
    if any(w in msg for w in ('hour', 'open', 'close')):
        return True
    if 'when' in msg:
        return True
    return False


def _is_services_intent(msg):
    if _is_order_intent(msg):
        return False
    return any(w in msg for w in (
        'service', 'offer', 'do you do', 'what can you', 'what do you offer', 'what do you print',
    ))


def _is_quote_intent(msg):
    if _is_order_intent(msg) or _is_services_intent(msg):
        return False
    return any(w in msg for w in ('quote', 'price', 'cost', 'how much', 'rate', 'pricing'))


def _is_prices_intent(msg):
    return _is_quote_intent(msg)


def _rule_based_reply(session_token, user_message):
    """Intelligent fallback when no LLM API key is configured."""
    msg = (user_message or '').strip().lower()
    catalog = _product_catalog_text()
    ctx = _customer_context(session_token)

    if any(w in msg for w in ('hello', 'hi', 'hey', 'good morning', 'good afternoon')):
        return (
            "Hello! Welcome to *3G Design Printing* — Monrovia’s premium print and branding studio.\n\n"
            "Here are our featured services:\n"
            "• Graphic Design\n"
            "• Flex / Banner\n"
            "• SAV / Sticker\n"
            "• Engraving\n"
            "• Shirt Printing\n"
            "• DTF Film Print\n"
            "• Vinyl Cutting\n"
            "• Stanley Cup / Tumbler / Sport Cup\n"
            "• UV DTF Print\n"
            "• Mugs, Caps, Keychains, Pens, Flyers, Invitations\n"
            "• Sublimation supplies, Laser Cutting, Custom Branding\n\n"
            "Need a quote? Tell me the item, quantity, and deadline — for example, \"quote for 30 shirts\" or \"price for 50 flyers.\"\n\n"
            "Call/WhatsApp 0775323731 or 0881669599 if you want to confirm availability quickly.\n\n"
            "What can I help you with today?"
        )

    if _is_order_intent(msg):
        if ctx:
            return f"{ctx}\n\nFor detailed tracking, our team will follow up shortly. Call {BUSINESS_PHONE} for urgent orders."
        return (
            "To place or track an order, share what you need (item, quantity, deadline). "
            f"Our team at {BUSINESS_PHONE} will confirm pricing and pickup."
        )

    if _is_hours_intent(msg):
        return f"We're open *{BUSINESS_HOURS}*.\n\n📍 {BUSINESS_ADDRESS}"

    if any(w in msg for w in ('where', 'location', 'address', 'find you')):
        return f"📍 *{BUSINESS_ADDRESS}*\n📞 {BUSINESS_PHONE}"

    if any(w in msg for w in ('about', 'who are you', 'what do you do', 'tell me about', 'your company', 'your business')):
        content = get_about_content(db, AboutContent)
        if content and content.description and content.description.strip():
            body = content.description.strip()
            if content.services and content.services.strip():
                body += f"\n\n*Services:*\n{content.services.strip()}"
            return f"*{BUSINESS_NAME}*\n\n{body}\n\n📍 {BUSINESS_ADDRESS}\n📞 {BUSINESS_PHONE}"
        return (
            f"*{BUSINESS_NAME}* is Monrovia's premier print and design shop.\n\n"
            f"We offer printing, branding, apparel, and design services.\n\n"
            f"📍 {BUSINESS_ADDRESS}\n📞 {BUSINESS_PHONE}\n🕐 {BUSINESS_HOURS}"
        )

    if _is_services_intent(msg):
        content = get_about_content(db, AboutContent)
        if content and content.services and content.services.strip():
            return f"Our services include:\n\n{content.services.strip()}\n\n{catalog}"
        return (
            f"Here are some of our offerings:\n\n{catalog}\n\n"
            "We can print custom shirts, mugs, banners, flyers, stickers, and more. "
            "Tell me the item and quantity for a quote."
        )

    if _is_prices_intent(msg):
        return (
            "I can give you a better quote if you tell me the item and quantity. "
            "For example: \"quote for 30 t-shirts\" or \"price for 50 flyers.\"\n\n"
            f"Here are some common options:\n{catalog}\n\n"
            "If you already have a project in mind, I can start the estimate now."
        )

    if any(w in msg for w in ('thank', 'thanks')):
        return "You're welcome! Quality in every print — excellence in every design. 🙏"

    if any(w in msg for w in ('help', 'menu', 'options')):
        return (
            "I can help with several things right now:\n"
            "• *Quotes* — for shirts, mugs, banners, flyers, and more\n"
            "• *Business hours* — when we're open\n"
            "• *Shop location* — where to find us in Monrovia\n"
            "• *Order help* — place a new order or check an existing one\n\n"
            "Just ask in your own words, for example: \"quote for 20 caps\" or \"can I pick up my order today?\""
        )

    return (
        f"Thanks for your message! A specialist at *{BUSINESS_NAME}* will assist you soon.\n\n"
        f"In the meantime, call/WhatsApp {BUSINESS_PHONE} or ask about *prices*, *hours*, or *orders*."
    )


def _openai_reply(session_token, user_message, history):
    api_key = os.getenv('OPENAI_API_KEY', '').strip()
    if not api_key:
        return None

    ctx = _customer_context(session_token)
    knowledge = _business_knowledge_block()
    system = (
        f"You are the friendly AI assistant for {BUSINESS_NAME}, a premium print and design shop in Monrovia, Liberia. "
        "Answer using ONLY the business facts below. Be concise, professional, and helpful. "
        "Use WhatsApp-friendly formatting (*bold* sparingly). "
        f"If you don't know something, direct the customer to call/WhatsApp {BUSINESS_PHONE}.\n\n"
        f"Business facts:\n{knowledge}\n"
    )
    if ctx:
        system += f"\nCustomer context: {ctx}"

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
