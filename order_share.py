"""
Generate order images and WhatsApp text for in-chat sharing (no preview links).
"""
import json
import os
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from brand_mark import paste_brand_header_pil


BRAND_NAVY = '#0B1F3A'
BRAND_GOLD = '#C9A84C'
BRAND_CREAM = '#FAF8F4'


def _normalize_local_image(image_file):
    """Strip URL prefixes so relative upload paths resolve on disk."""
    if not image_file:
        return ''
    value = str(image_file).strip()
    if value.startswith('http'):
        return None
    value = value.replace('\\', '/')
    for prefix in ('/static/uploads/', 'static/uploads/', '/uploads/', 'uploads/'):
        if value.startswith(prefix):
            value = value[len(prefix):]
    return value.lstrip('/')


def _resolve_image_path(app_root, image_file):
    normalized = _normalize_local_image(image_file)
    if normalized is None:
        return None
    if not normalized:
        return os.path.join(app_root, 'static', 'img', 'LOGO.png')
    path = os.path.join(app_root, 'static', 'uploads', normalized)
    if os.path.exists(path):
        return path
    return os.path.join(app_root, 'static', 'img', 'LOGO.png')


def _load_font(size, bold=False):
    names = ['arialbd.ttf', 'Arial Bold.ttf', 'arial.ttf', 'Arial.ttf'] if bold else ['arial.ttf', 'Arial.ttf']
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _paste_brand_header(canvas, draw, app_root, x, y, img_height=22):
    paste_brand_header_pil(canvas, draw, app_root, x, y, variant='gold', img_height=img_height)


def _paste_thumbnail(canvas, draw, img_path, box, thumb_size, placeholder_font):
    """Fit product photo inside a rounded gold-bordered tile."""
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=10, outline=BRAND_GOLD, width=2, fill='#FFFFFF')
    if not img_path or not os.path.exists(img_path):
        draw.text((x0 + 28, y0 + 40), '3G', fill=BRAND_NAVY, font=placeholder_font)
        return
    try:
        thumb = Image.open(img_path).convert('RGB')
        inner = thumb_size - 10
        thumb.thumbnail((inner, inner), Image.Resampling.LANCZOS)
        tx = x0 + (thumb_size - thumb.width) // 2
        ty = y0 + (thumb_size - thumb.height) // 2
        canvas.paste(thumb, (tx, ty))
    except Exception:
        draw.text((x0 + 28, y0 + 40), '3G', fill=BRAND_NAVY, font=placeholder_font)


def build_whatsapp_text(cart_items, *, share_page_url=None):
    """
    Professional order text for WhatsApp — concise summary with share page link.
    Raw image URLs in plain text do not render inline in WhatsApp chat.
    """
    return build_whatsapp_short_message(cart_items, share_page_url=share_page_url)


def build_whatsapp_short_message(cart_items, *, share_page_url):
    """
    Concise WhatsApp text for wa.me fallback — share page link triggers og:image preview.
    """
    total_usd = sum(i['price'] * i['quantity'] for i in cart_items if i.get('currency') == 'USD')
    total_lrd = sum(i['price'] * i['quantity'] for i in cart_items if i.get('currency') == 'LRD')

    lines = ['🛒 NEW ORDER — 3G Design', '']
    for item in cart_items:
        sym = '$' if item.get('currency') == 'USD' else 'L$'
        subtotal = item['price'] * item['quantity']
        name = item.get('product_name', 'Product')
        variant = item.get('variant_name', '')
        if variant and variant not in ('Base', 'Original Design'):
            lines.append(f"• {name} ({variant}) x{item['quantity']} — {sym}{subtotal:.2f}")
        else:
            lines.append(f"• {name} x{item['quantity']} — {sym}{subtotal:.2f}")
    lines.append('')
    if total_usd:
        lines.append(f'💰 Total USD: ${total_usd:.2f}')
    if total_lrd:
        lines.append(f'💰 Total LRD: L${total_lrd:.2f}')
    if share_page_url:
        lines.append('')
        lines.append('📋 View order with images:')
        lines.append(share_page_url)
    lines.append('')
    lines.append('Please confirm availability and lead time. Thank you! 🙏')
    return '\n'.join(lines)


def generate_order_image(cart_items, token, app_root):
    """
    Build one PNG with product thumbnails + order details.
    Saved to static/uploads/orders/order_{token}.png
    """
    thumb_size = 112
    row_h = 132
    pad = 28
    header_h = 78
    footer_h = 58
    width = 680
    n = max(len(cart_items), 1)
    height = header_h + (n * row_h) + footer_h + pad

    canvas = Image.new('RGB', (width, height), BRAND_CREAM)
    draw = ImageDraw.Draw(canvas)
    body_font = _load_font(17)
    small_font = _load_font(13)
    gold_font = _load_font(15, bold=True)
    placeholder_font = _load_font(18, bold=True)

    draw.rectangle([0, 0, width, header_h], fill=BRAND_NAVY)
    _paste_brand_header(canvas, draw, app_root, pad, 20, img_height=26)
    draw.text((pad, 52), 'ORDER RECEIPT', fill='#FFFFFF', font=small_font)

    y = header_h + pad // 2
    total_usd = 0.0
    total_lrd = 0.0

    for item in cart_items:
        img_path = _resolve_image_path(app_root, item.get('image', ''))
        box = (pad, y, pad + thumb_size, y + thumb_size)
        _paste_thumbnail(canvas, draw, img_path, box, thumb_size, placeholder_font)

        text_x = pad + thumb_size + 20
        name = (item.get('product_name') or 'Product')[:38]
        draw.text((text_x, y + 10), name, fill=BRAND_NAVY, font=body_font)
        variant = item.get('variant_name', '')
        if variant and variant not in ('Base', 'Original Design'):
            draw.text((text_x, y + 36), f'Design: {variant[:32]}', fill='#555555', font=small_font)

        sym = '$' if item.get('currency') == 'USD' else 'L$'
        subtotal = item['price'] * item['quantity']
        if item.get('currency') == 'USD':
            total_usd += subtotal
        else:
            total_lrd += subtotal
        draw.text(
            (text_x, y + 62),
            f"Qty: {item['quantity']}   {sym}{subtotal:.2f}",
            fill=BRAND_NAVY,
            font=gold_font,
        )
        draw.line([(pad, y + row_h - 6), (width - pad, y + row_h - 6)], fill='#E8E4DC', width=1)
        y += row_h

    footer_y = height - footer_h + 10
    draw.rectangle([0, height - footer_h, width, height], fill=BRAND_NAVY)
    parts = []
    if total_usd:
        parts.append(f'Total USD: ${total_usd:.2f}')
    if total_lrd:
        parts.append(f'Total LRD: L${total_lrd:.2f}')
    total_line = '   ·   '.join(parts) if parts else 'Order total on request'
    draw.text((pad, footer_y), total_line, fill=BRAND_GOLD, font=gold_font)

    out_dir = os.path.join(app_root, 'static', 'uploads', 'orders')
    os.makedirs(out_dir, exist_ok=True)
    filename = f'order_{token}.png'
    out_path = os.path.join(out_dir, filename)
    canvas.save(out_path, 'PNG', optimize=True)
    return f'orders/{filename}'


def try_notify_shop_via_api(cart_items, message_text, image_rel_path, app_root, share_page_url=None):
    """
    Optional: push order image + text to shop WhatsApp via Meta Cloud API.
    Sends composite receipt image and individual product photos as media messages.
    """
    import os
    import requests
    from whatsapp_credentials import get_access_token, get_phone_number_id

    access_token = get_access_token()
    phone_id = get_phone_number_id()
    notify_to = os.getenv('WHATSAPP_NOTIFY_NUMBER', os.getenv('WHATSAPP_NUMBER', '')).strip()
    notify_to = ''.join(c for c in notify_to if c.isdigit())

    if not access_token or not phone_id or not notify_to:
        return False

    base = f'https://graph.facebook.com/v18.0/{phone_id}'
    headers = {'Authorization': f'Bearer {access_token}'}

    image_path = os.path.join(app_root, 'static', 'uploads', image_rel_path)
    media_id = None
    if os.path.exists(image_path):
        try:
            with open(image_path, 'rb') as f:
                resp = requests.post(
                    f'{base}/media',
                    headers=headers,
                    data={'messaging_product': 'whatsapp', 'type': 'image/png'},
                    files={'file': ('order.png', f, 'image/png')},
                    timeout=30,
                )
            if resp.ok:
                media_id = resp.json().get('id')
        except Exception:
            pass

    def send_payload(payload):
        try:
            requests.post(f'{base}/messages', headers={**headers, 'Content-Type': 'application/json'}, json=payload, timeout=30)
        except Exception:
            pass

    caption = message_text[:1024]
    if share_page_url and share_page_url not in caption:
        caption = f"{caption}\n\n🔗 {share_page_url}"[:1024]

    if media_id:
        send_payload({
            'messaging_product': 'whatsapp',
            'to': notify_to,
            'type': 'image',
            'image': {'id': media_id, 'caption': caption},
        })
    else:
        send_payload({
            'messaging_product': 'whatsapp',
            'to': notify_to,
            'type': 'text',
            'text': {'body': message_text[:4096]},
        })

    for item in cart_items:
        img_path = _resolve_image_path(app_root, item.get('image', ''))
        if not img_path or not os.path.exists(img_path):
            continue
        try:
            with open(img_path, 'rb') as f:
                resp = requests.post(
                    f'{base}/media',
                    headers=headers,
                    data={'messaging_product': 'whatsapp', 'type': 'image/jpeg'},
                    files={'file': (os.path.basename(img_path), f, 'image/jpeg')},
                    timeout=30,
                )
            if resp.ok:
                mid = resp.json().get('id')
                cap = f"{item.get('product_name', 'Product')} — {item.get('variant_name', '')} x{item.get('quantity', 1)}"
                send_payload({
                    'messaging_product': 'whatsapp',
                    'to': notify_to,
                    'type': 'image',
                    'image': {'id': mid, 'caption': cap[:1024]},
                })
        except Exception:
            continue
    return True
