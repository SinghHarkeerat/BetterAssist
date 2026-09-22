"""Browser regressions using real bundled agreements. Run: python -m unittest discover -s tests -v"""
import json
from pathlib import Path
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from newserver import Handler


class QuietHandler(Handler):
    def log_message(self, *_):
        pass


class PlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(channel='chrome', headless=True)
        cls.index = json.loads((ROOT / 'data/index.json').read_text(encoding='utf-8'))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 1440, 'height': 1000})
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda e: self.errors.append(str(e)))

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def open(self):
        self.page.goto(self.url)
        self.page.wait_for_function("!document.getElementById('schoolInput').disabled")

    def select(self, major='Computer Science', code='UCLA'):
        campus = next(c for c in self.index['colleges'][0]['campuses'] if c['code'] == code)
        self.page.select_option('#schoolInput', campus['id'])
        self.page.select_option('#majorSelect', major)

    def load(self):
        self.page.click('#loadBtn')
        self.page.locator('#results').wait_for(state='visible')

    def test_search_never_selects_an_unrequested_major(self):
        self.open()
        self.select()
        self.page.fill('#majorInput', 'nothingmatches123')
        self.assertTrue(self.page.locator('#loadBtn').is_disabled())
        self.assertTrue(self.page.locator('#majorSelect').is_disabled())
        self.page.fill('#majorInput', 'computer science')
        self.assertEqual(self.page.locator('#majorSelect option').count(), 4)
        self.assertEqual(self.page.input_value('#majorSelect'), '')
        self.assertTrue(self.page.locator('#loadBtn').is_disabled())

    def test_honors_sequences_and_full_sets_are_preserved(self):
        self.open()
        self.select()
        self.load()
        self.assertEqual(self.page.locator('#chartBody tr').count(), 14)
        self.assertGreater(self.page.locator('.course-tag').count(), 0)
        row = self.page.locator('#chartBody tr').nth(1)
        self.assertIn('Take all courses in this set', row.inner_text())
        self.assertIn('OR', row.inner_text())
        row.locator('.add-course').first.click()
        self.assertEqual(self.page.locator('#planList li').count(), 2)
        self.assertIn('MATH 1B', self.page.locator('#planList').inner_text())
        self.assertIn('MATH 1C', self.page.locator('#planList').inner_text())
        self.assertIn('University course sequence', self.page.locator('#chartBody').inner_text())
        self.page.locator('#planList input').first.check()
        self.assertEqual(self.page.locator('#progressPercent').inner_text(), '50%')
        self.page.reload()
        self.page.locator('#results').wait_for(state='visible')
        self.assertEqual(self.page.locator('#progressCount').inner_text(), '1 of 2 courses')
        self.page.locator('.remove-course').first.click()
        self.assertEqual(self.page.locator('#planList li').count(), 1)

    def test_plan_isolation_and_reset(self):
        self.open()
        self.select()
        self.load()
        self.page.locator('.add-course').first.click()
        self.page.select_option('#majorSelect', 'Mathematics')
        self.assertTrue(self.page.locator('#results').is_hidden())
        self.assertEqual(self.page.locator('#planList li').count(), 0)
        self.load()
        self.assertEqual(self.page.locator('#planList li').count(), 0)
        self.select()
        self.load()
        self.assertEqual(self.page.locator('#planList li').count(), 1)
        self.page.click('#clearBtn')
        self.assertTrue(self.page.locator('#results').is_hidden())
        self.select()
        self.load()
        self.assertEqual(self.page.locator('#planList li').count(), 1)

    def test_missing_foothill_data_is_not_deanza_data(self):
        self.open()
        self.select()
        self.load()
        self.page.select_option('#collegeInput', 'foothill')
        self.assertTrue(self.page.locator('#collegeNotice').is_visible())
        self.assertTrue(self.page.locator('#results').is_hidden())
        self.assertTrue(self.page.locator('#schoolInput').is_disabled())
        self.assertTrue(self.page.locator('#loadBtn').is_disabled())

    def test_failed_index_and_agreement_can_retry(self):
        self.page.route('**/data/index.json', lambda route: route.fulfill(status=503, body='unavailable'))
        self.page.goto(self.url)
        self.page.locator('#retryBtn').wait_for(state='visible')
        self.page.unroute('**/data/index.json')
        self.page.click('#retryBtn')
        self.page.wait_for_function("!document.getElementById('schoolInput').disabled")
        self.select()
        self.page.route('**/uc_to_deanza/**', lambda route: route.fulfill(status=404, body='missing'))
        self.page.click('#loadBtn')
        self.page.locator('#formError').wait_for(state='visible')
        self.assertIn('404', self.page.locator('#formError').inner_text())
        self.assertTrue(self.page.locator('#loadBtn').is_enabled())
        self.page.unroute('**/uc_to_deanza/**')
        self.load()

    def test_stale_request_does_not_replace_changed_selection(self):
        self.open()
        self.select()
        held = []
        self.page.route('**/uc_to_deanza/**', lambda route: held.append(route))
        self.page.click('#loadBtn')
        self.page.wait_for_timeout(100)
        self.page.select_option('#collegeInput', 'foothill')
        for route in held:
            route.abort()
        self.assertTrue(self.page.locator('#results').is_hidden())
        self.assertTrue(self.page.locator('#formError').is_hidden())

    def test_filters_copy_print_and_mobile(self):
        self.open()
        self.select()
        self.load()
        self.page.fill('#courseSearch', 'not-a-course')
        self.assertEqual(self.page.locator('#chartBody tr').count(), 0)
        self.assertTrue(self.page.locator('#noMatches').is_visible())
        self.page.fill('#courseSearch', '')
        self.page.locator('.add-course').first.click()
        self.context.grant_permissions(['clipboard-read', 'clipboard-write'])
        self.page.click('#copyBtn')
        copied = self.page.evaluate('navigator.clipboard.readText()')
        self.assertIn('MATH 1A', copied)
        self.assertIn('Computer Science', copied)
        self.page.evaluate('window.print = () => window.printCalled = true')
        self.page.click('#printBtn')
        self.assertTrue(self.page.evaluate('window.printCalled'))
        for width in [320, 390, 768, 1024, 1440]:
            self.page.set_viewport_size({'width': width, 'height': 900})
            self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'), f'Overflow at {width}')
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.assertTrue(self.page.locator('#mobilePlanBar').is_visible())
        self.page.emulate_media(media='print')
        self.assertTrue(self.page.locator('#mobilePlanBar').is_hidden())
        self.assertTrue(self.page.locator('#course-plan').is_visible())

    def test_unavailable_storage_does_not_break_planning(self):
        self.page.add_init_script("Storage.prototype.setItem = () => { throw new Error('blocked'); }; Storage.prototype.getItem = () => '{invalid';")
        self.open()
        self.select()
        self.load()
        self.page.locator('.add-course').first.click()
        self.assertEqual(self.page.locator('#planList li').count(), 1)
        self.assertIn('unavailable', self.page.locator('#saveNote').inner_text())

    def test_every_indexed_agreement_and_all_formats_parse(self):
        self.open()
        count = 0
        for college in self.index['colleges']:
            for campus in college['campuses']:
                batch = []
                for entries in campus['yearMap'].values():
                    for major in entries:
                        self.assertNotEqual(major['id'], 'reports')
                        result = json.loads((ROOT / major['path']).read_text(encoding='utf-8'))['result']
                        self.assertEqual(result['type'], 'Major')
                        batch.append(result)
                        count += 1
                self.assertTrue(self.page.evaluate('batch => batch.every(r => normalizeRows(r).length === r.articulations.length)', batch))
        self.assertEqual(count, 2571)

    def test_legacy_api_rejects_path_traversal(self):
        for route, query in [('campus', {'campus': '../..'}), ('major', {'campus': '..', 'year': '..', 'major': 'data/index'})]:
            with self.assertRaises(HTTPError) as raised:
                urlopen(f'{self.url}/api/{route}?{urlencode(query)}')
            self.assertEqual(raised.exception.code, 404)


if __name__ == '__main__':
    unittest.main()
