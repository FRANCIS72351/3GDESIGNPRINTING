"""Tests for WhatsApp order flow (finalize, prepare, checkout, share page)."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('PUBLIC_SITE_URL', 'https://example.test')

from app import app, finalize_whatsapp_order, get_public_base_url
from models import db, PendingReceipt
from order_share import (
    build_order_copy_text,
    build_wa_me_fallback_text,
    build_whatsapp_short_message,
    generate_order_image,
)
from site_config import CANONICAL_CLOUD_SITE_URL, _sanitize_public_url, get_public_site_url


class WhatsAppOrderTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.ctx = app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        PendingReceipt.query.delete()
        db.session.commit()
        db.session.remove()
        self.ctx.pop()

    def _sample_item(self, name='Test Mug', image='test-mug.jpg'):
        return {
            'product_id': '1',
            'product_name': name,
            'variant_name': 'Original Design',
            'price': 12.5,
            'currency': 'USD',
            'image': image,
            'quantity': 2,
        }

    def test_flask_app_has_no_get_current_object(self):
        self.assertFalse(hasattr(app, '_get_current_object'))

    def test_sanitize_rejects_bare_pythonanywhere(self):
        self.assertEqual(_sanitize_public_url('https://pythonanywhere.com'), '')
        self.assertEqual(
            _sanitize_public_url('https://3gdesign.pythonanywhere.com'),
            'https://3gdesign.pythonanywhere.com',
        )

    @patch.dict(os.environ, {'PUBLIC_SITE_URL': '', 'WEBHOOK_BASE_URL': '', 'PYTHONANYWHERE_DOMAIN': '3gdesign.pythonanywhere.com'}, clear=False)
    def test_pythonanywhere_domain_resolves_correctly(self):
        url = get_public_site_url()
        self.assertEqual(url, 'https://3gdesign.pythonanywhere.com')

    @patch.dict(
        os.environ,
        {
            'PUBLIC_SITE_URL': '',
            'WEBHOOK_BASE_URL': '',
            'PYTHONANYWHERE_DOMAIN': '',
            'PYTHONANYWHERE_SITE': '',
            'FLASK_ENV': 'production',
        },
        clear=False,
    )
    def test_production_falls_back_to_canonical_cloud_url(self):
        url = get_public_site_url()
        self.assertEqual(url, CANONICAL_CLOUD_SITE_URL)

    @patch('app.run_in_background')
    @patch('app.generate_order_image', return_value='orders/order_test.png')
    def test_finalize_whatsapp_order(self, _mock_image, _mock_bg):
        with app.test_request_context('/'):
            token, message_text, image_rel = finalize_whatsapp_order([self._sample_item()])

        self.assertTrue(token)
        self.assertEqual(image_rel, 'orders/order_test.png')
        self.assertIn('Test Mug', message_text)
        base = get_public_base_url()
        self.assertIn(f'{base}/order/share/{token}', message_text)
        self.assertNotIn('🖼', message_text)
        self.assertNotIn('pythonanywhere.com/static', message_text.replace(base, ''))

        receipt = PendingReceipt.query.filter_by(token=token).first()
        self.assertIsNotNone(receipt)
        data = json.loads(receipt.payload)
        self.assertEqual(data['share_image_url'], f'{base}/static/uploads/orders/order_test.png')
        self.assertIn('image_url', data['items'][0])
        self.assertIn(f'{base}/static/uploads/test-mug.jpg', data['items'][0]['image_url'])

        _mock_bg.assert_called_once()
        self.assertIs(_mock_bg.call_args[0][0], app)
        self.assertEqual(_mock_bg.call_args[0][6], f'{base}/order/share/{token}')

    def test_build_order_copy_text_has_no_url(self):
        text = build_order_copy_text([self._sample_item()])
        self.assertIn('Test Mug', text)
        self.assertIn('NEW ORDER', text)
        self.assertNotIn('http', text)
        self.assertNotIn('order/share', text)
        self.assertNotIn('static/uploads', text)

    def test_build_whatsapp_short_message_uses_share_link(self):
        items = [self._sample_item()]
        url = 'https://example.test/order/share/abc123'
        text = build_whatsapp_short_message(items, share_page_url=url)
        self.assertIn('Test Mug', text)
        self.assertIn(url, text)
        self.assertNotIn('🖼', text)

    def test_wa_me_fallback_has_no_long_url(self):
        hint = build_wa_me_fallback_text()
        self.assertNotIn('http', hint)
        self.assertNotIn('pythonanywhere', hint)
        self.assertNotIn('order/share', hint)

    def test_generate_order_image_creates_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            logo = os.path.join(tmp, 'static', 'img')
            uploads = os.path.join(tmp, 'static', 'uploads')
            os.makedirs(logo, exist_ok=True)
            os.makedirs(uploads, exist_ok=True)
            from PIL import Image
            Image.new('RGB', (10, 10), 'red').save(os.path.join(logo, 'LOGO.png'))
            Image.new('RGB', (80, 80), 'blue').save(os.path.join(uploads, 'shirt.png'))

            items = [{
                'product_name': 'Banner',
                'variant_name': 'Large',
                'price': 25.0,
                'currency': 'USD',
                'quantity': 1,
                'image': '/static/uploads/shirt.png',
            }]
            rel = generate_order_image(items, 'unittesttoken', tmp)
            self.assertEqual(rel, 'orders/order_unittesttoken.png')
            out = os.path.join(tmp, 'static', 'uploads', rel)
            self.assertTrue(os.path.isfile(out))
            self.assertGreater(os.path.getsize(out), 500)

    @patch('app.run_in_background')
    @patch('app.generate_order_image', return_value='orders/order_prep.png')
    def test_prepare_whatsapp_order_route(self, _mock_image, _mock_bg):
        r = self.client.post('/prepare-whatsapp-order', data={
            'product_id': '1',
            'product_name': 'Banner Print',
            'variant_name': 'Large',
            'price': '25',
            'currency': 'USD',
            'image': 'banner.jpg',
            'quantity': '1',
        }, follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn('/order/share/', r.location)
        token = r.location.rstrip('/').split('/')[-1]
        receipt = PendingReceipt.query.filter_by(token=token).first()
        self.assertIsNotNone(receipt)

    @patch('app.run_in_background')
    @patch('app.generate_order_image', return_value='orders/order_cart.png')
    def test_checkout_whatsapp_route(self, _mock_image, _mock_bg):
        with self.client.session_transaction() as sess:
            sess['cart'] = [self._sample_item('T-Shirt', 'shirt.png')]

        r = self.client.get('/checkout-whatsapp', follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn('/order/share/', r.location)

        with self.client.session_transaction() as sess:
            self.assertNotIn('cart', sess)

    @patch('app.run_in_background')
    @patch('app.generate_order_image', return_value='orders/order_page.png')
    def test_order_share_page_shows_images(self, _mock_image, _mock_bg):
        with app.test_request_context('/'):
            token, _, _ = finalize_whatsapp_order([self._sample_item()])

        r = self.client.get(f'/order/share/{token}')
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        base = get_public_base_url()
        self.assertIn(f'{base}/static/uploads/orders/order_page.png', html)
        self.assertIn('/static/uploads/test-mug.jpg', html)
        self.assertIn('Test Mug', html)
        self.assertIn('product-strip', html)
        self.assertIn('receipt-preview', html)

    @patch('app.run_in_background')
    @patch('app.generate_order_image', return_value='orders/order_og.png')
    def test_order_share_page_has_og_tags(self, _mock_image, _mock_bg):
        with app.test_request_context('/'):
            token, _, _ = finalize_whatsapp_order([self._sample_item('Poster', 'poster.jpg')])

        r = self.client.get(f'/order/share/{token}')
        html = r.get_data(as_text=True)
        base = get_public_base_url()
        self.assertIn('property="og:image"', html)
        self.assertIn(f'{base}/static/uploads/orders/order_og.png', html)
        self.assertIn('property="og:title"', html)
        self.assertIn('property="og:description"', html)
        self.assertIn(f'{base}/order/share/{token}', html)
        self.assertIn('Send to WhatsApp with Images', html)
        self.assertIn('sendOrderToWhatsApp', html)
        self.assertIn('shareImageFiles', html)
        self.assertIn('Copy order text', html)
        self.assertIn('wa.me/', html)
        # wa.me must NOT be prefilled with the full multi-line share page URL
        self.assertNotIn('order%2Fshare', html)
        self.assertNotIn('View%20order', html)
        self.assertIn('chat-preview', html)
        self.assertIn('Exact image that will attach', html)

    @patch('app.run_in_background')
    @patch('app.generate_order_image', return_value='orders/order_abs.png')
    def test_order_share_uses_absolute_public_urls(self, _mock_image, _mock_bg):
        with app.test_request_context('/'):
            token, _, _ = finalize_whatsapp_order([self._sample_item()])

        r = self.client.get(f'/order/share/{token}')
        html = r.get_data(as_text=True)
        self.assertIn('https://example.test/static/uploads/orders/order_abs.png', html)
        self.assertIn('https://example.test/order/share/', html)
        self.assertNotIn('https://pythonanywhere.com/', html)

    @patch('app.run_in_background')
    @patch('app.generate_order_image', return_value='orders/order_copy.png')
    def test_order_share_copy_text_has_no_url(self, _mock_image, _mock_bg):
        with app.test_request_context('/'):
            token, _, _ = finalize_whatsapp_order([self._sample_item()])

        r = self.client.get(f'/order/share/{token}')
        html = r.get_data(as_text=True)
        self.assertIn('const copyText =', html)
        self.assertIn('Test Mug', html)
        self.assertIn('shareImageFiles', html)
        self.assertIn('files: files', html)
        # Clipboard / caption must not expose raw static upload URLs
        self.assertNotIn('/static/uploads/test-mug.jpg', html.split('const copyText =')[1].split('const shortMessage')[0])


if __name__ == '__main__':
    unittest.main()
