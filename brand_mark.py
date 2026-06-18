"""Shared 3G Design wordmark — Ethnocentric text (3G + Design)."""
import re

from markupsafe import Markup, escape

BRAND_TEXT = '3G Design'
BRAND_PATTERN = re.compile(r'3G\s*Design', re.IGNORECASE)


def _wordmark_classes(variant='navy', extra_class='', lockup=False):
    classes = f'brand-wordmark brand-wordmark--{variant}'
    if extra_class:
        classes = f'{classes} {extra_class}'
    if lockup:
        classes = f'{classes} brand-wordmark--lockup'
    return classes


def brand_wordmark_markup(static_url_fn=None, variant='navy', extra_class='', suffix=True, lockup=False):
    """Render logo-style wordmark as Ethnocentric text, not PNG images."""
    classes = _wordmark_classes(variant, extra_class, lockup)
    if suffix:
        body = Markup('<span class="brand-3g">3G</span><span class="brand-design"> Design</span>')
    else:
        body = Markup('<span class="brand-3g">3G</span>')
    return Markup(f'<span class="{classes}">{body}</span>')


def _variant_hex(variant):
    r, g, b = _variant_color(variant)
    return f'#{r:02X}{g:02X}{b:02X}'


def brand_wordmark_email_markup(base_url, variant='navy', extra_class='', suffix=True):
    """Email-safe Ethnocentric wordmark (inline styles for clients without @font-face)."""
    classes = _wordmark_classes(variant, extra_class)
    color = _variant_hex(variant)
    font_stack = "'Ethnocentric', 'Arial Black', sans-serif"
    three_g = (
        f'<span class="brand-3g" style="font-family:{font_stack};letter-spacing:0.04em;color:{color};">3G</span>'
    )
    if suffix:
        design = (
            f'<span class="brand-design" style="font-family:{font_stack};'
            f'letter-spacing:0.08em;text-transform:uppercase;color:{color};"> Design</span>'
        )
        body = three_g + design
    else:
        body = three_g
    return Markup(f'<span class="{classes}" style="display:inline-flex;align-items:center;gap:4px;">{body}</span>')


def is_brand_name(name):
    return bool(BRAND_PATTERN.fullmatch(str(name or '').strip()))


def brand_name_markup(name, static_url_fn, variant='navy', extra_class=''):
    if is_brand_name(name):
        return brand_wordmark_markup(static_url_fn, variant, extra_class)
    return escape(name or BRAND_TEXT)


def brandify_html(text, static_url_fn, variant='navy', extra_class='brand-wordmark--inline'):
    if text is None:
        return Markup('')
    text = str(text)
    if not BRAND_PATTERN.search(text):
        return escape(text)
    wordmark = brand_wordmark_markup(static_url_fn, variant=variant, extra_class=extra_class)
    html = Markup('')
    last = 0
    for match in BRAND_PATTERN.finditer(text):
        html += escape(text[last:match.start()])
        html += wordmark
        last = match.end()
    html += escape(text[last:])
    return html


def _variant_color(variant):
    if variant in ('light', 'white', 'gold'):
        return (232, 213, 163)
    return (11, 31, 58)


def draw_brand_wordmark_pdf(canvas, x, y, app_root, variant='navy', img_height=14, suffix_size=10):
    """Draw Ethnocentric 3G Design wordmark on a ReportLab canvas."""
    from io import BytesIO

    from brand_font import brand_font_path, get_reportlab_brand_font

    color = _variant_color(variant)
    font_path = brand_font_path(app_root)
    wordmark_size = suffix_size + 4

    if font_path:
        from PIL import Image, ImageDraw

        from brand_font import load_pil_brand_font

        pil_font_size = int(wordmark_size * 2.5)
        wordmark_font = load_pil_brand_font(app_root, pil_font_size, bold=True)

        measure = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
        w3 = measure.textlength('3G', font=wordmark_font)
        wd = measure.textlength('DESIGN', font=wordmark_font)
        pad = 4
        total_w = int(w3 + pad + wd) + pad
        total_h = int(wordmark_font.size) + pad

        img = Image.new('RGBA', (total_w, total_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.text((0, 0), '3G', fill=(*color, 255), font=wordmark_font)
        draw.text((w3 + pad, 0), 'DESIGN', fill=(*color, 255), font=wordmark_font)

        buf = BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        from reportlab.lib.utils import ImageReader

        display_h = max(img_height, wordmark_size)
        display_w = display_h * (total_w / total_h)
        canvas.drawImage(ImageReader(buf), x, y, width=display_w, height=display_h, mask='auto')
        return x + display_w + 4

    font = get_reportlab_brand_font(app_root)
    canvas.setFillColorRGB(color[0] / 255, color[1] / 255, color[2] / 255)
    canvas.setFont(font, wordmark_size)
    canvas.drawString(x, y, '3G')
    x += canvas.stringWidth('3G', font, wordmark_size) + 3
    canvas.drawString(x, y, 'DESIGN')
    return x + canvas.stringWidth('DESIGN', font, wordmark_size) + 4


def paste_brand_header_pil(canvas, draw, app_root, x, y, variant='gold', img_height=22):
    """Draw Ethnocentric brand header on a PIL image (order PNGs)."""
    from brand_font import load_pil_brand_font

    color = _variant_color(variant if variant != 'gold' else 'gold')
    wordmark_font = load_pil_brand_font(app_root, int(img_height), bold=True)

    draw.text((x, y), '3G', fill=color, font=wordmark_font)
    three_g_w = draw.textlength('3G', font=wordmark_font)
    draw.text((x + three_g_w + 4, y), 'DESIGN', fill=color, font=wordmark_font)
