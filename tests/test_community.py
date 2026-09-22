"""Authentication, consent, shared metrics, and feedback regressions."""
import io
import json
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engagement import Engagement, configure_admin
from newserver import Handler
import server

TEST_CODE = 'test-owner-only-8392'


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        configure_admin(TEST_CODE, self.directory)
        self.api = Engagement(self.directory)

    def tearDown(self):
        self.temp.cleanup()

    def call(self, path, data=None, cookie='', ip='127.0.0.1', origin='https://betterassist.example'):
        method = 'GET' if data is None else 'POST'
        status, headers, body = self.api.dispatch(method, path, {'Origin': origin, 'Content-Type': 'application/json', 'Cookie': cookie}, json.dumps(data).encode(), ip, 'https://betterassist.example')
        return status, headers, json.loads(body)

    def login(self):
        status, headers, _ = self.call('/api/admin/login', {'code': TEST_CODE})
        self.assertEqual(status, 200)
        cookie = next(value for key, value in headers if key == 'Set-Cookie')
        self.assertIn('HttpOnly', cookie)
        self.assertIn('Secure', cookie)
        self.assertIn('SameSite=Strict', cookie)
        return cookie.split(';')[0]

    def test_authentication_expiry_logout_and_private_hash(self):
        self.assertNotIn(TEST_CODE, (self.directory / 'secrets.json').read_text())
        self.assertEqual(self.call('/api/admin/stats')[0], 401)
        self.assertEqual(self.call('/api/admin/stats', cookie='ba_admin=fake')[0], 401)
        self.assertEqual(self.call('/api/admin/login', {'code': 'incorrect'})[0], 401)
        cookie = self.login()
        self.assertEqual(self.call('/api/admin/stats', cookie=cookie)[0], 200)
        self.assertEqual(self.call('/api/admin/logout', {}, cookie=cookie)[0], 200)
        self.assertEqual(self.call('/api/admin/stats', cookie=cookie)[0], 401)
        cookie = self.login()
        with sqlite3.connect(self.directory / 'engagement.sqlite3') as db:
            db.execute('UPDATE sessions SET expires=?', (time.time() - 1,))
        db.close()
        self.assertEqual(self.call('/api/admin/stats', cookie=cookie)[0], 401)

    def test_login_rate_limits_persist_across_restart(self):
        for _ in range(5):
            self.assertEqual(self.call('/api/admin/login', {'code': 'wrong'})[0], 401)
        self.api = Engagement(self.directory)
        self.assertEqual(self.call('/api/admin/login', {'code': TEST_CODE})[0], 429)
        self.assertEqual(self.call('/api/admin/login', {'code': TEST_CODE}, ip='127.0.0.2')[0], 200)

    def test_csrf_bad_requests_and_consent_required(self):
        self.assertEqual(self.call('/api/admin/login', {'code': TEST_CODE}, origin='https://evil.example')[0], 403)
        self.assertEqual(self.call('/api/traffic', {'eventId': str(uuid.uuid4())})[0], 400)
        for body, kind, expected in [(b'not json', 'application/json', 400), (b'[]', 'application/json', 400), (b'{}', 'text/plain', 415), (b'x' * 9000, 'application/json', 413)]:
            status, _, _ = self.api.dispatch('POST', '/api/feedback', {'origin': 'https://betterassist.example', 'content-type': kind}, body, '127.0.0.1', 'https://betterassist.example')
            self.assertEqual(status, expected)

    def test_shared_counts_deduplication_feedback_and_restart(self):
        event = {'eventId': str(uuid.uuid4()), 'consent': True}
        status, headers, _ = self.call('/api/traffic', event)
        self.assertEqual(status, 200)
        visitor = next(value.split(';')[0] for key, value in headers if key == 'Set-Cookie')
        self.call('/api/traffic', event, cookie=visitor)
        self.call('/api/traffic', {'eventId': str(uuid.uuid4()), 'consent': True}, cookie=visitor)
        self.call('/api/traffic', {'eventId': str(uuid.uuid4()), 'consent': True})
        feedback = {'id': str(uuid.uuid4()), 'rating': 4, 'message': '<script>danger()</script>'}
        self.assertEqual(self.call('/api/feedback', feedback)[0], 200)
        self.assertEqual(self.call('/api/feedback', feedback)[0], 200)
        self.api = Engagement(self.directory)
        stats = self.call('/api/admin/stats', cookie=self.login())[2]
        self.assertEqual((stats['views'], stats['visitors'], stats['today']), (3, 2, 3))
        self.assertEqual(len(stats['days']), 30)
        self.assertEqual(stats['feedbackCount'], 1)
        self.assertEqual(stats['ratings'], [{'rating': 4, 'count': 1}])
        self.assertEqual(stats['feedback'][0]['message'], feedback['message'])
        self.assertEqual(self.call('/api/feedback')[0], 404)

    def test_feedback_validation_rate_limits_and_revoke(self):
        for rating in (True, 0, 6, '5'):
            self.assertEqual(self.call('/api/feedback', {'id': str(uuid.uuid4()), 'rating': rating})[0], 400)
        self.assertEqual(self.call('/api/feedback', {'id': str(uuid.uuid4()), 'message': ' '})[0], 400)
        self.assertEqual(self.call('/api/feedback', {'id': str(uuid.uuid4()), 'message': 'x' * 2001})[0], 400)
        for _ in range(6):
            self.assertEqual(self.call('/api/feedback', {'id': str(uuid.uuid4()), 'message': 'Please add a feature'})[0], 200)
        self.assertEqual(self.call('/api/feedback', {'id': str(uuid.uuid4()), 'rating': 5})[0], 429)
        status, headers, _ = self.call('/api/privacy', {})
        self.assertEqual(status, 200)
        self.assertTrue(any('ba_visitor=' in value and 'Max-Age=0' in value for _, value in headers))

    def test_wsgi_serves_only_public_files_and_fails_closed(self):
        for path in ('/engagement.py', '/secrets.json', '/.env', '/.git/config', '/data/../engagement.py', '/data/%2e%2e/engagement.py', '/data', '/README.md', '/data\\..\\engagement.py'):
            self.assertIsNone(server.public_file(path), path)
        self.assertIsNotNone(server.public_file('/admin.html'))
        self.assertIsNotNone(server.public_file('/data/index.json'))
        missing = Engagement(self.directory / 'not-configured')
        self.assertEqual(missing.dispatch('GET', '/api/admin/stats', {}, b'', '127.0.0.1', 'http://127.0.0.1')[0], 503)
        with patch.object(server, 'service', self.api):
            response = []
            body = b''.join(server.application({'PATH_INFO': '/api/admin/stats', 'REQUEST_METHOD': 'GET', 'HTTP_HOST': '127.0.0.1:9999', 'wsgi.input': io.BytesIO(b'')}, lambda status, headers: response.append((status, headers))))
            self.assertTrue(response[0][0].startswith('401'))
            self.assertIn(('Cache-Control', 'no-store'), response[0][1])
            self.assertIn(b'Please log in', body)


class QuietHandler(Handler):
    def log_message(self, *_):
        pass


class CommunityBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.http.server_port}'
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(channel='chrome', headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.http.shutdown()
        cls.http.server_close()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        configure_admin(TEST_CODE, self.temp.name)
        self.service_patch = patch.object(server, 'service', Engagement(self.temp.name))
        self.service_patch.start()
        self.context = self.browser.new_context(viewport={'width': 1440, 'height': 1000})
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))

    def tearDown(self):
        self.context.close()
        self.service_patch.stop()
        self.temp.cleanup()
        self.assertEqual(self.errors, [])

    def test_consent_accept_reload_revoke_and_separate_visitors(self):
        traffic = []
        self.page.on('request', lambda request: traffic.append(request.url) if '/api/traffic' in request.url else None)
        self.page.goto(self.url)
        expect(self.page.locator('#cookieBanner')).to_be_visible()
        self.assertEqual(traffic, [])
        self.assertFalse(any(cookie['name'] == 'ba_visitor' for cookie in self.context.cookies()))
        with self.page.expect_response('**/api/traffic'):
            self.page.click('#acceptCookies')
        expect(self.page.locator('#cookieBanner')).to_be_hidden()
        self.assertTrue(any(cookie['name'] == 'ba_visitor' and cookie['httpOnly'] for cookie in self.context.cookies()))
        with self.page.expect_response('**/api/traffic'):
            self.page.reload()
        db = server.service.connect()
        self.assertEqual(db.execute('SELECT COUNT(*) FROM visits').fetchone()[0], 2)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM visitors').fetchone()[0], 1)
        db.close()
        self.page.click('#cookieSettings')
        with self.page.expect_response('**/api/privacy'):
            self.page.click('#declineCookies')
        self.assertFalse(any(cookie['name'] == 'ba_visitor' for cookie in self.context.cookies()))
        self.page.reload()
        expect(self.page.locator('#cookieBanner')).to_be_hidden()
        self.assertEqual(len(traffic), 2)
        with self.browser.new_context() as other:
            page = other.new_page()
            page.goto(self.url)
            with page.expect_response('**/api/traffic'):
                page.click('#acceptCookies')
        db = server.service.connect()
        self.assertEqual(db.execute('SELECT COUNT(*) FROM visitors').fetchone()[0], 2)
        db.close()

    def test_feedback_without_analytics_is_private_and_visible_after_login(self):
        self.page.goto(self.url)
        self.page.click('#declineCookies')
        self.page.locator('.star-option').nth(3).click()
        self.page.fill('#feedbackMessage', '<img src=x onerror="window.pwned=true"> More Foothill majors please!')
        self.page.click('#feedbackSubmit')
        expect(self.page.locator('#feedbackStatus')).to_contain_text('Thanks!')
        self.assertEqual(self.context.request.get(self.url + '/api/admin/stats').status, 401)
        self.page.goto(self.url + '/admin.html')
        expect(self.page.locator('#adminLogin')).to_be_visible()
        self.page.fill('#adminCode', 'wrong')
        self.page.click('#adminLoginButton')
        expect(self.page.locator('#adminLoginStatus')).to_contain_text('incorrect')
        self.page.fill('#adminCode', TEST_CODE)
        self.page.click('#adminLoginButton')
        expect(self.page.locator('#adminDashboard')).to_be_visible()
        expect(self.page.locator('#metricsLabel')).to_have_text('Demo numbers')
        expect(self.page.locator('#totalViews')).to_have_text('14,286')
        expect(self.page.locator('#totalVisitors')).to_have_text('14,031')
        expect(self.page.locator('#todayViews')).to_have_text('24')
        expect(self.page.locator('#averageRating')).to_have_text('4.8 / 5')
        stats = self.context.request.get(self.url + '/api/admin/stats').json()
        self.assertEqual((stats['views'], stats['visitors'], stats['today']), (0, 0, 0))
        self.assertEqual(stats['ratings'], [{'rating': 4, 'count': 1}])
        self.page.click('#metricsToggle')
        expect(self.page.locator('#metricsLabel')).to_have_text('Actual traffic')
        expect(self.page.locator('#averageRating')).to_have_text('4.0 / 5')
        expect(self.page.locator('#totalViews')).to_have_text('0')
        expect(self.page.locator('#feedbackInbox')).to_contain_text('More Foothill majors please!')
        self.assertEqual(self.page.locator('#feedbackInbox img').count(), 0)
        self.assertIsNone(self.page.evaluate('window.pwned'))
        self.assertEqual(self.page.locator('#trafficChart, #trafficTable').count(), 0)
        self.page.click('#adminRefresh')
        expect(self.page.locator('#averageRating')).to_have_text('4.0 / 5')
        self.page.reload()
        expect(self.page.locator('#adminDashboard')).to_be_visible()
        self.page.click('#adminLogout')
        expect(self.page.locator('#adminLoginStatus')).to_contain_text('signed out')
        self.assertEqual(self.context.request.get(self.url + '/api/admin/stats').status, 401)

    def test_unavailable_feedback_preserves_message_and_can_retry(self):
        self.page.goto(self.url)
        self.page.click('#declineCookies')
        self.page.fill('#feedbackMessage', 'Add more majors')
        self.page.route('**/api/feedback', lambda route: route.fulfill(status=503, json={'error': 'Temporarily unavailable'}))
        self.page.click('#feedbackSubmit')
        expect(self.page.locator('#feedbackStatus')).to_contain_text('Temporarily unavailable')
        expect(self.page.locator('#feedbackMessage')).to_have_value('Add more majors')
        self.page.unroute('**/api/feedback')
        self.page.click('#feedbackSubmit')
        expect(self.page.locator('#feedbackStatus')).to_contain_text('Thanks!')

    def test_dashboard_load_error_is_visible_after_successful_login(self):
        self.page.goto(self.url + '/admin.html')
        expect(self.page.locator('#adminLoginButton')).to_be_enabled()
        self.page.route('**/api/admin/stats', lambda route: route.fulfill(status=503, json={'error': 'Dashboard is temporarily unavailable. Please retry.'}))
        self.page.fill('#adminCode', '  ' + TEST_CODE + '  ')
        self.page.click('#adminLoginButton')
        expect(self.page.locator('#adminLoginStatus')).to_be_visible()
        expect(self.page.locator('#adminLoginStatus')).to_contain_text('Dashboard is temporarily unavailable')
        expect(self.page.locator('#adminLoginButton')).to_be_enabled()
        self.page.unroute('**/api/admin/stats')
        self.page.fill('#adminCode', TEST_CODE)
        self.page.click('#adminLoginButton')
        expect(self.page.locator('#adminDashboard')).to_be_visible()
        expect(self.page.locator('#dashboardHeading')).to_be_focused()

    def test_missing_login_cookie_explains_why_dashboard_did_not_open(self):
        self.page.goto(self.url + '/admin.html')
        expect(self.page.locator('#adminLoginButton')).to_be_enabled()
        self.page.route('**/api/admin/stats', lambda route: route.fulfill(status=401, json={'error': 'Please log in'}))
        self.page.fill('#adminCode', TEST_CODE)
        self.page.click('#adminLoginButton')
        expect(self.page.locator('#adminLoginStatus')).to_contain_text('Allow cookies for this website')
        expect(self.page.locator('#adminDashboard')).to_be_hidden()

    def test_mobile_and_static_host_fallback(self):
        self.page.set_viewport_size({'width': 375, 'height': 812})
        self.page.route('**/api/**', lambda route: route.fulfill(status=404, content_type='text/html', body='Not found'))
        self.page.goto(self.url)
        self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))
        self.page.click('#declineCookies')
        self.page.locator('.star-option').nth(4).click()
        self.page.click('#feedbackSubmit')
        expect(self.page.locator('#feedbackStatus')).to_contain_text('not connected')
        self.assertTrue(self.page.locator('input[name=rating][value="5"]').is_checked())
        self.page.goto(self.url + '/admin.html')
        expect(self.page.locator('#adminLoginStatus')).to_contain_text('not connected')
        self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))


if __name__ == '__main__':
    unittest.main()
