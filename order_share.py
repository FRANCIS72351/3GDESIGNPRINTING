"""
Generate order receipt images and WhatsApp text for in-chat media sharing.
Primary path: one polished composite PNG shared via Web Share (image bubble in chat).
"""
import os
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from brand_mark import paste_brand_header_pil


BRAND_NAVY = '#0B1F3A'
BRAND_NAVY_DEEP = '#061428'
BRAND_GOLD = '#C9A84C'
BRAND_GOLD_SOFT = '#E8D5A3'
BRAND_CREAM = '#FAF8F4'
BRAND_MUTED = '#6B7280'
BRAND_LINE = '#E6E1D8'


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


def _font_candidates(bold=False):
    win = os.environ.get('WINDIR', r'C:\Windows')
    fonts = os.path.join(win, 'Fonts')
    if bold:
        return [
            os.path.join(fonts, 'segoeuib.ttf'),
            os.path.join(fonts, 'arialbd.ttf'),
            os.path.join(fonts, 'calibrib.ttf'),
            'segoeuib.ttf',
            'arialbd.ttf',
            'Arial Bold.ttf',
            'arial.ttf',
            'Arial.ttf',
        ]
    return [
        os.path.join(fonts, 'segoeui.ttf'),
        os.path.join(fonts, 'arial.ttf'),
        os.path.join(fonts, 'calibri.ttf'),
        'segoeui.ttf',
        'arial.ttf',
        'Arial.ttf',
    ]


def _load_font(size, bold=False):
    for name in _font_candidates(bold=bold):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _text_width(draw, text, font):
    try:
        return draw.textlength(text, font=font)
    except Exception:
        box = draw.textbbox((0, 0), text, font=font)
        return box[2] - box[0]


def _paste_brand_header(canvas, draw, app_root, x, y, img_height=22):
    paste_brand_header_pil(canvas, draw, app_root, x, y, variant='gold', img_height=img_height)


def _rounded_thumb(img_path, size, radius=18):
    """Load, cover-crop, and mask a product photo into a rounded square."""
    thumb = Image.new('RGBA', (size, size), (255, 255, 255, 255))
    if not img_path or not os.path.exists(img_path):
        return thumb.convert('RGB'), False
    try:
        src = Image.open(img_path).convert('RGB')
        # Cover crop to square
        w, h = src.size
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        src = src.crop((left, top, left + side, top + side))
        src = src.resize((size, size), Image.Resampling.LANCZOS)

        mask = Image.new('L', (size, size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
        out = Image.new('RGBA', (size, size), (255, 255, 255, 0))
        out.paste(src, (0, 0))
        out.putalpha(mask)
        return out, True
    except Exception:
        return thumb.convert('RGB'), False


def _paste_thumbnail(canvas, draw, img_path, box, thumb_size, placeholder_font):
    """Fit product photo inside a gold-bordered rounded tile on an RGBA canvas."""
    x0, y0, _, _ = box
    shadow = Image.new('RGBA', (thumb_size + 10, thumb_size + 10), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle([4, 4, thumb_size + 4, thumb_size + 4], radius=18, fill=(0, 0, 0, 45))
    shadow = shadow.filter(ImageFilter.GaussianBlur(3))
    canvas.alpha_composite(shadow, (max(0, x0 - 2), max(0, y0 - 1)))

    photo, ok = _rounded_thumb(img_path, thumb_size, radius=16)
    if photo.mode != 'RGBA':
        photo = photo.convert('RGBA')
    canvas.alpha_composite(photo, (x0, y0))

    draw.rounded_rectangle(box, radius=16, outline=BRAND_GOLD, width=2)
    if not ok:
        draw.text(
            (x0 + thumb_size // 2 - 14, y0 + thumb_size // 2 - 12),
            '3G',
            fill=BRAND_NAVY,
            font=placeholder_font,
        )


def _hex_rgb(hex_color):
    value = hex_color.lstrip('#')
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _format_money(amount, currency='USD'):
    sym = '$' if currency == 'USD' else 'L$'
    if float(amount).is_integer():
        return f'{sym}{int(amount)}'
    return f'{sym}{amount:.2f}'


def build_order_copy_text(cart_items):
    """
    Clean order caption for WhatsApp — image-first, no URLs.
    """
    total_usd = sum(i['price'] * i['quantity'] for i in cart_items if i.get('currency') == 'USD')
    total_lrd = sum(i['price'] * i['quantity'] for i in cart_items if i.get('currency') == 'LRD')

    lines = ['🛒 Order from 3G Design']
    for item in cart_items:
        currency = item.get('currency', 'USD')
        subtotal = item['price'] * item['quantity']
        name = item.get('product_name', 'Product')
        variant = item.get('variant_name', '')
        money = _format_money(subtotal, currency)
        if variant and variant not in ('Base', 'Original Design'):
            lines.append(f"• {name} ({variant}) ×{item['quantity']} — {money}")
        else:
            lines.append(f"• {name} ×{item['quantity']} — {money}")

    totals = []
    if total_usd:
        totals.append(f'{_format_money(total_usd, "USD")} USD')
    if total_lrd:
        totals.append(f'{_format_money(total_lrd, "LRD")} LRD')
    if totals:
        lines.append(f"Total: {' · '.join(totals)}")
    lines.append('Please confirm availability. Thank you!')
    return '\n'.join(lines)


def build_whatsapp_text(cart_items, *, share_page_url=None):
    """Professional order text for WhatsApp — caption only, never raw image URLs."""
    return build_whatsapp_short_message(cart_items)


def build_whatsapp_short_message(cart_items, *, share_page_url=None):
    """
    Order caption for WhatsApp text fields. Never includes share-page or upload URLs.
    share_page_url is accepted for backward compatibility but intentionally ignored.
    """
    del share_page_url  # URLs belong in the receipt image, not chat text
    return build_order_copy_text(cart_items)


def build_wa_me_caption(cart_items):
    """Short wa.me prefill from order summary — no URLs."""
    full = build_order_copy_text(cart_items)
    if len(full) <= 300:
        return full
    n = len(cart_items)
    total_usd = sum(i['price'] * i['quantity'] for i in cart_items if i.get('currency') == 'USD')
    total_lrd = sum(i['price'] * i['quantity'] for i in cart_items if i.get('currency') == 'LRD')
    lines = [f'🛒 Order from 3G Design ({n} item{"s" if n != 1 else ""})']
    if total_usd:
        lines.append(f'Total: {_format_money(total_usd, "USD")} USD')
    if total_lrd:
        lines.append(f'Total: {_format_money(total_lrd, "LRD")} LRD')
    lines.append('Receipt image attached. Please confirm. Thank you!')
    return '\n'.join(lines)


def build_wa_me_fallback_text(cart_items=None):
    """wa.me prefill — order summary when possible, never long URLs."""
    if cart_items:
        return build_wa_me_caption(cart_items)
    return 'New order from 3G Design — receipt image attached. Please confirm.'


def generate_order_image(cart_items, token, app_root):
    """
    Build one high-quality PNG receipt with product thumbnails + order details.
    Designed for WhatsApp media bubbles (wide, crisp, navy/gold brand).
    Saved to static/uploads/orders/order_{token}.png
    """
    width = 900
    thumb_size = 128
    row_h = 156
    pad = 36
    header_h = 118
    meta_h = 44
    footer_h = 96
    n = max(len(cart_items), 1)
    height = header_h + meta_h + (n * row_h) + footer_h + 24

    canvas = Image.new('RGBA', (width, height), (*_hex_rgb(BRAND_CREAM), 255))
    draw = ImageDraw.Draw(canvas)

    title_font = _load_font(15, bold=True)
    body_font = _load_font(22, bold=True)
    meta_font = _load_font(16)
    small_font = _load_font(14)
    price_font = _load_font(18, bold=True)
    total_font = _load_font(20, bold=True)
    placeholder_font = _load_font(22, bold=True)
    caption_font = _load_font(13)

    # ——— Header band ———
    draw.rectangle([0, 0, width, header_h], fill=BRAND_NAVY_DEEP)
    draw.rectangle([0, 0, width, 4], fill=BRAND_GOLD)
    _paste_brand_header(canvas, draw, app_root, pad, 28, img_height=28)
    draw.text((pad, 72), 'ORDER RECEIPT', fill=BRAND_GOLD_SOFT, font=title_font)

    # Order meta row
    order_ref = (token or '')[:8].upper()
    date_str = datetime.now(timezone.utc).strftime('%d %b %Y')
    item_label = f'{n} item{"s" if n != 1 else ""}'
    meta_y = header_h + 12
    draw.text((pad, meta_y), f'#{order_ref}', fill=BRAND_NAVY, font=meta_font)
    right_meta = f'{item_label}  ·  {date_str}'
    rw = _text_width(draw, right_meta, meta_font)
    draw.text((width - pad - rw, meta_y), right_meta, fill=BRAND_MUTED, font=meta_font)
    draw.line([(pad, header_h + meta_h - 2), (width - pad, header_h + meta_h - 2)], fill=BRAND_LINE, width=1)

    y = header_h + meta_h + 10
    total_usd = 0.0
    total_lrd = 0.0

    for idx, item in enumerate(cart_items):
        if idx % 2 == 0:
            draw.rounded_rectangle(
                [pad - 8, y - 6, width - pad + 8, y + thumb_size + 10],
                radius=14,
                fill='#FFFFFF',
            )

        img_path = _resolve_image_path(app_root, item.get('image', ''))
        box = (pad, y, pad + thumb_size, y + thumb_size)
        _paste_thumbnail(canvas, draw, img_path, box, thumb_size, placeholder_font)

        text_x = pad + thumb_size + 24
        name = (item.get('product_name') or 'Product')[:42]
        draw.text((text_x, y + 14), name, fill=BRAND_NAVY, font=body_font)

        variant = item.get('variant_name', '')
        detail_y = y + 48
        if variant and variant not in ('Base', 'Original Design'):
            draw.text((text_x, detail_y), f'Design: {variant[:36]}', fill=BRAND_MUTED, font=small_font)

        qty = item.get('quantity', 1)
        unit = item.get('price', 0)
        sym = '$' if item.get('currency') == 'USD' else 'L$'
        subtotal = unit * qty
        if item.get('currency') == 'USD':
            total_usd += subtotal
        else:
            total_lrd += subtotal

        draw.text(
            (text_x, y + thumb_size - 36),
            f'Qty {qty}  ·  {sym}{unit:.2f} each',
            fill=BRAND_MUTED,
            font=small_font,
        )
        price_label = f'{sym}{subtotal:.2f}'
        pw = _text_width(draw, price_label, price_font)
        draw.text((width - pad - pw, y + thumb_size - 38), price_label, fill=BRAND_NAVY, font=price_font)

        y += row_h

    # ——— Footer totals ———
    draw.rectangle([0, height - footer_h, width, height], fill=BRAND_NAVY)
    draw.rectangle([0, height - footer_h, width, height - footer_h + 3], fill=BRAND_GOLD)

    parts = []
    if total_usd:
        parts.append(f'Total USD  ${total_usd:.2f}')
    if total_lrd:
        parts.append(f'Total LRD  L${total_lrd:.2f}')
    total_line = '   ·   '.join(parts) if parts else 'Order total on request'
    draw.text((pad, height - footer_h + 22), total_line, fill=BRAND_GOLD, font=total_font)
    draw.text(
        (pad, height - footer_h + 56),
        '3G Design  ·  Please confirm availability & lead time',
        fill=BRAND_GOLD_SOFT,
        font=caption_font,
    )

    out_dir = os.path.join(app_root, 'static', 'uploads', 'orders')
    os.makedirs(out_dir, exist_ok=True)
    filename = f'order_{token}.png'
    out_path = os.path.join(out_dir, filename)
    canvas.convert('RGB').save(out_path, 'PNG', optimize=True)
    return f'orders/{filename}'


def try_notify_shop_via_api(cart_items, message_text, image_rel_path, app_root, share_page_url=None):
    """
    Optional: push order image + text to shop WhatsApp via Meta Cloud API.
    Sends composite receipt image and individual product photos as media messages.
    """
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
            requests.post(
                f'{base}/messages',
                headers={**headers, 'Content-Type': 'application/json'},
                json=payload,
                timeout=30,
            )
        except Exception:
            pass

    # Caption: order details only — never raw static upload URLs or share links
    caption = build_order_copy_text(cart_items)[:1024]
    del share_page_url

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
            'text': {'body': (message_text or caption)[:4096]},
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
