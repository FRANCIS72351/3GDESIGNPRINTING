"""Tests for WhatsApp order flow (finalize, prepare, checkout, share page)."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('PUBLIC_SITE_URL', 'https://example.test')

from app import app, finalize_whatsapp_order, get_public_base_url
from models import db, PendingReceipt
from order_share import build_whatsapp_short_message, generate_order_image


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

    @patch('app.run_in_background')
    @patch('app.generate_order_image', return_value='orders/order_test.png')
    def test_finalize_whatsapp_order(self, _mock_image, _mock_bg):
        with app.test_request_context('/'):
            token, message_text, image_rel = finalize_whatsapp_order([self._sample_item()])

        self.assertTrue(token)
        self.assertEqual(image_rel, 'orders/order_test.png')
        self.assertIn('Test Mug', message_text)
        base = get_public_base_url()
        self.assertIn(f'{base}/static/uploads/test-mug.jpg', message_text)
        self.assertIn(f'{base}/static/uploads/orders/order_test.png', message_text)
        self.assertIn(f'{base}/order/share/{token}', message_text)

        receipt = PendingReceipt.query.filter_by(token=token).first()
        self.assertIsNotNone(receipt)
        data = json.loads(receipt.payload)
        self.assertEqual(data['share_image_url'], f'{base}/static/uploads/orders/order_test.png')
        self.assertIn('image_url', data['items'][0])

        _mock_bg.assert_called_once()
        self.assertIs(_mock_bg.call_args[0][0], app)
        self.assertEqual(_mock_bg.call_args[0][6], f'{base}/order/share/{token}')

    def test_build_whatsapp_short_message_uses_share_link(self):
        items = [self._sample_item()]
        url = 'https://example.test/order/share/abc123'
        text = build_whatsapp_short_message(items, share_page_url=url)
        self.assertIn('Test Mug', text)
        self.assertIn(url, text)
        self.assertNotIn('🖼', text)

    def test_generate_order_image_creates_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            logo = os.path.join(tmp, 'static', 'img')
            os.makedirs(logo, exist_ok=True)
            from PIL import Image
            Image.new('RGB', (10, 10), 'red').save(os.path.join(logo, 'LOGO.png'))

            items = [{
                'product_name': 'Banner',
                'variant_name': 'Large',
                'price': 25.0,
                'currency': 'USD',
                'quantity': 1,
                'image': '',
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
        self.assertIn(f'{base}/static/uploads/test-mug.jpg', html)
        self.assertIn('Test Mug', html)
        self.assertIn('product-thumbs', html)

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
        self.assertIn('Share with Images', html)
        self.assertIn('shareWithImages', html)
        self.assertIn('Open WhatsApp with Link Preview', html)
        self.assertIn('wa.me/', html)

    @patch('app.run_in_background')
    @patch('app.generate_order_image', return_value='orders/order_abs.png')
    def test_order_share_uses_absolute_public_urls(self, _mock_image, _mock_bg):
        with app.test_request_context('/'):
            token, _, _ = finalize_whatsapp_order([self._sample_item()])

        r = self.client.get(f'/order/share/{token}')
        html = r.get_data(as_text=True)
        self.assertIn('https://example.test/static/uploads/orders/order_abs.png', html)
        self.assertIn('https://example.test/order/share/', html)


if __name__ == '__main__':
    unittest.main()
