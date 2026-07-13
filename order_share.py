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


def _resolve_image_path(app_root, image_file):
    if not image_file:
        return os.path.join(app_root, 'static', 'img', 'LOGO.png')
    if image_file.startswith('http'):
        return None
    path = os.path.join(app_root, 'static', 'uploads', image_file)
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


def build_whatsapp_text(cart_items, *, share_image_url=None, share_page_url=None):
    """Professional order text for WhatsApp — includes product image URLs when available."""
    total_usd = sum(i['price'] * i['quantity'] for i in cart_items if i.get('currency') == 'USD')
    total_lrd = sum(i['price'] * i['quantity'] for i in cart_items if i.get('currency') == 'LRD')

    lines = [
        '🛒 NEW ORDER — 3G Design',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
    ]
    for item in cart_items:
        sym = '$' if item.get('currency') == 'USD' else 'L$'
        subtotal = item['price'] * item['quantity']
        lines.append(f"📦 {item['product_name']}")
        variant = item.get('variant_name', '')
        if variant and variant not in ('Base', 'Original Design'):
            lines.append(f"   Design: {variant}")
        lines.append(f"   Qty: {item['quantity']}  ·  {sym}{subtotal:.2f}")
        img_url = item.get('image_url')
        if img_url:
            lines.append(f"   🖼 {img_url}")
        lines.append('')
    lines.append('━━━━━━━━━━━━━━━━━━━━')
    if total_usd:
        lines.append(f'💰 Total USD: ${total_usd:.2f}')
    if total_lrd:
        lines.append(f'💰 Total LRD: L${total_lrd:.2f}')
    if share_image_url:
        lines.append('')
        lines.append('📋 Order summary image:')
        lines.append(share_image_url)
    if share_page_url:
        lines.append('')
        lines.append('🔗 View order:')
        lines.append(share_page_url)
    lines.append('')
    lines.append('Please confirm availability and lead time. Thank you! 🙏')
    return '\n'.join(lines)


def generate_order_image(cart_items, token, app_root):
    """
    Build one PNG with product thumbnails + order details.
    Saved to static/uploads/orders/order_{token}.png
    """
    thumb_size = 110
    row_h = 130
    pad = 24
    header_h = 72
    footer_h = 56
    width = 640
    n = max(len(cart_items), 1)
    height = header_h + (n * row_h) + footer_h + pad

    canvas = Image.new('RGB', (width, height), BRAND_CREAM)
    draw = ImageDraw.Draw(canvas)
    body_font = _load_font(16)
    small_font = _load_font(13)
    gold_font = _load_font(14, bold=True)

    draw.rectangle([0, 0, width, header_h], fill=BRAND_NAVY)
    _paste_brand_header(canvas, draw, app_root, pad, 18, img_height=24)
    draw.text((pad, 48), 'ORDER RECEIPT', fill='#FFFFFF', font=small_font)

    y = header_h + pad // 2
    total_usd = 0.0
    total_lrd = 0.0

    for item in cart_items:
        img_path = _resolve_image_path(app_root, item.get('image', ''))
        box = (pad, y, pad + thumb_size, y + thumb_size)
        draw.rounded_rectangle(box, radius=10, outline=BRAND_GOLD, width=2, fill='#FFFFFF')
        if img_path and os.path.exists(img_path):
            try:
                thumb = Image.open(img_path).convert('RGB')
                thumb.thumbnail((thumb_size - 8, thumb_size - 8))
                tx = pad + (thumb_size - thumb.width) // 2
                ty = y + (thumb_size - thumb.height) // 2
                canvas.paste(thumb, (tx, ty))
            except Exception:
                draw.text((pad + 20, y + 40), '3G', fill=BRAND_NAVY, font=body_font)

        text_x = pad + thumb_size + 18
        name = (item.get('product_name') or 'Product')[:36]
        draw.text((text_x, y + 8), name, fill=BRAND_NAVY, font=body_font)
        variant = item.get('variant_name', '')
        if variant and variant not in ('Base', 'Original Design'):
            draw.text((text_x, y + 32), f'Design: {variant[:30]}', fill='#555555', font=small_font)

        sym = '$' if item.get('currency') == 'USD' else 'L$'
        subtotal = item['price'] * item['quantity']
        if item.get('currency') == 'USD':
            total_usd += subtotal
        else:
            total_lrd += subtotal
        draw.text(
            (text_x, y + 54),
            f"Qty: {item['quantity']}   {sym}{subtotal:.2f}",
            fill=BRAND_NAVY,
            font=gold_font,
        )
        draw.line([(pad, y + row_h - 8), (width - pad, y + row_h - 8)], fill='#E8E4DC', width=1)
        y += row_h

    footer_y = height - footer_h + 8
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


def try_notify_shop_via_api(cart_items, message_text, image_rel_path, app_root):
    """
    Optional: push order image + text to shop WhatsApp via Meta Cloud API.
    Works locally — uploads image from disk, no public URL needed.
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

    if media_id:
        send_payload({
            'messaging_product': 'whatsapp',
            'to': notify_to,
            'type': 'image',
            'image': {'id': media_id, 'caption': message_text[:1024]},
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
