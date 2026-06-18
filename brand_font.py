"""Shared Ethnocentric brand font for web-adjacent outputs (PDF, PNG)."""
import os

BRAND_FONT_FILES = ('Ethnocentric.otf', 'Ethnocentric.ttf', 'Ethnocentric-Regular.otf')
BRAND_FONT_FAMILY = 'Ethnocentric'
_reportlab_registered = False


def brand_font_path(app_root):
    fonts_dir = os.path.join(app_root, 'static', 'fonts')
    for name in BRAND_FONT_FILES:
        path = os.path.join(fonts_dir, name)
        if os.path.isfile(path):
            return path
    for entry in os.listdir(fonts_dir) if os.path.isdir(fonts_dir) else []:
        if 'ethnocentric' in entry.lower() and entry.lower().endswith(('.ttf', '.otf')):
            return os.path.join(fonts_dir, entry)
    return None


def get_reportlab_brand_font(app_root, fallback='Helvetica-Bold'):
    global _reportlab_registered
    path = brand_font_path(app_root)
    if not path:
        return fallback
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if BRAND_FONT_FAMILY not in pdfmetrics.getRegisteredFontNames():
        try:
            pdfmetrics.registerFont(TTFont(BRAND_FONT_FAMILY, path))
            _reportlab_registered = True
        except Exception:
            return fallback
    return BRAND_FONT_FAMILY


def load_pil_brand_font(app_root, size, bold=False):
    from PIL import ImageFont

    path = brand_font_path(app_root)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass

    names = ['arialbd.ttf', 'Arial Bold.ttf', 'arial.ttf', 'Arial.ttf'] if bold else ['arial.ttf', 'Arial.ttf']
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()
