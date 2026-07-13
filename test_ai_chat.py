"""Flask test client checks for web chat API."""
import os
import unittest

os.environ.setdefault('WHATSAPP_AI_REPLY', 'false')

from app import app
from models import db, AIChatMessage


class WebChatApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.ctx = app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        AIChatMessage.query.delete()
        db.session.commit()
        db.session.remove()
        self.ctx.pop()

    def test_post_requires_message(self):
        r = self.client.post('/api/web/chat', json={'session_token': 'web_test123'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('type a message', r.get_json()['error'].lower())

    def test_post_rejects_long_message(self):
        r = self.client.post('/api/web/chat', json={
            'session_token': 'web_test123',
            'message': 'x' * 501,
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn('500', r.get_json()['error'])

    def test_post_and_get_history(self):
        token = 'web_hist_test'
        r = self.client.post('/api/web/chat', json={
            'session_token': token,
            'message': 'What are your business hours?',
        })
        self.assertEqual(r.status_code, 200)
        self.assertIn('reply', r.get_json())

        h = self.client.get('/api/web/chat', query_string={'session_token': token})
        self.assertEqual(h.status_code, 200)
        messages = h.get_json()['messages']
        self.assertGreaterEqual(len(messages), 2)
        self.assertEqual(messages[0]['role'], 'user')
        self.assertEqual(messages[-1]['role'], 'assistant')

    def test_order_status_not_hours(self):
        from ai_agent import _rule_based_reply, _normalize_session

        token = _normalize_session('web_order_test')
        reply = _rule_based_reply(token, 'when will my order be ready')
        self.assertIn('order', reply.lower())
        self.assertNotIn('monday', reply.lower())


if __name__ == '__main__':
    unittest.main()
