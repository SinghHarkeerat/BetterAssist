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
        self.page.fill('#schoolSearch', code)
        self.page.locator('#schoolOptions [role=option]').filter(has_text=campus['pretty']).first.click()
        entry = next(m for m in campus['yearMap'][campus['latestYear']] if m['id'] == major)
        self.page.fill('#majorInput', entry['pretty'])
        self.page.locator('#majorOptions [role=option]').get_by_text(entry['pretty'], exact=True).first.click()

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

    def test_new_page_accepts_a_cached_legacy_index(self):
        legacy = {'campuses': self.index['colleges'][0]['campuses']}
        self.page.route('**/data/index.json', lambda route: route.fulfill(json=legacy))
        self.open()
        self.select()
        self.load()
        self.assertEqual(self.page.locator('#chartBody tr').count(), 14)

    def test_new_index_still_supports_cached_legacy_pages(self):
        self.open()
        old_page_campuses = self.page.evaluate("async () => { const r = await fetch('./data/index.json'); return (await r.json()).campuses; }")
        deanza = next(c for c in self.index['colleges'] if c['id'] == 'deanza')
        self.assertEqual(old_page_campuses, deanza['campuses'])
        self.assertEqual(len(old_page_campuses), 26)

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
        self.page.click('#completedView')
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
        self.select('Mathematics')
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

    def test_live_suggestions_keyboard_and_no_stale_major(self):
        self.open()
        self.page.fill('#schoolSearch', 'ucla')
        self.assertEqual(self.page.locator('#schoolOptions [role=option]').count(), 1)
        self.page.press('#schoolSearch', 'ArrowDown')
        self.page.press('#schoolSearch', 'Enter')
        self.assertEqual(self.page.locator('#schoolSearch').get_attribute('aria-expanded'), 'false')
        self.page.fill('#majorInput', 'computer science')
        self.assertEqual(self.page.locator('#majorOptions [role=option]').count(), 3)
        self.page.press('#majorInput', 'ArrowDown')
        self.page.press('#majorInput', 'Enter')
        self.assertTrue(self.page.locator('#loadBtn').is_enabled())
        self.page.fill('#majorInput', 'nomatch123')
        self.assertEqual(self.page.locator('#majorOptions [role=option]').count(), 0)
        self.assertTrue(self.page.locator('#loadBtn').is_disabled())
        self.page.press('#majorInput', 'Escape')
        self.assertTrue(self.page.locator('#majorOptions').is_hidden())

    def test_honors_switch_and_planned_percentage(self):
        self.open()
        self.select()
        self.load()
        row = self.page.locator('#chartBody tr').first
        row.locator('.add-course').first.click()
        self.assertEqual(self.page.locator('#progressPercent').inner_text(), '7%')
        self.assertEqual(self.page.locator('#planList li').count(), 1)
        self.page.locator('#planList input').check()
        row.locator('.add-course').nth(1).click()
        self.assertEqual(self.page.locator('#planList li').count(), 1)
        self.assertEqual(self.page.locator('#planList strong').inner_text(), 'MATH 1AH')
        self.assertFalse(self.page.locator('#planList input').is_checked())
        self.assertEqual(self.page.locator('#progressPercent').inner_text(), '7%')
        row.locator('.add-course').first.click()
        self.assertEqual(self.page.locator('#planList strong').inner_text(), 'MATH 1A')
        self.page.locator('.remove-course').click()
        self.assertEqual(self.page.locator('#progressPercent').inner_text(), '0%')

    def test_sequence_alternatives_replace_entire_sets(self):
        self.open()
        self.select()
        self.load()
        row = self.page.locator('#chartBody tr').nth(1)
        row.locator('.add-course').first.click()
        self.assertEqual(self.page.locator('#planList li').count(), 2)
        row.locator('.add-course').nth(1).click()
        self.assertEqual(self.page.locator('#planList li').count(), 2)
        codes = self.page.locator('#planList strong').all_text_contents()
        self.assertIn('MATH 1B', codes)
        self.assertIn('MATH 1CH', codes)
        self.assertNotIn('MATH 1C', codes)

    def test_calgetc_saved_independently_for_each_college(self):
        self.open()
        self.page.locator('.ge-area summary').first.click()
        self.page.fill('#ge-course-1A', 'ENGL C1000')
        self.page.check('#ge-1A')
        self.assertEqual(self.page.locator('#gePercent').inner_text(), '8%')
        self.page.reload()
        self.page.wait_for_function("!document.getElementById('schoolInput').disabled")
        self.page.locator('.ge-area summary').first.click()
        self.assertTrue(self.page.locator('#ge-1A').is_checked())
        self.assertEqual(self.page.input_value('#ge-course-1A'), 'ENGL C1000')
        self.page.select_option('#collegeInput', 'foothill')
        self.assertEqual(self.page.locator('#gePercent').inner_text(), '0%')
        self.assertIn('foothill.edu', self.page.locator('#geSource').get_attribute('href'))
        self.page.reload()
        self.page.wait_for_function("document.getElementById('geContext').textContent.includes('Foothill')")
        self.assertEqual(self.page.locator('#gePercent').inner_text(), '0%')
        self.page.select_option('#collegeInput', 'deanza')
        self.assertEqual(self.page.locator('#gePercent').inner_text(), '8%')
        self.page.locator('.ge-area').first.evaluate('node => node.open = true')
        self.page.uncheck('#ge-1A')
        self.assertEqual(self.page.locator('#gePercent').inner_text(), '0%')
        self.page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
        self.assertEqual(self.page.locator('.ge-area[open]').count(), 6)
        for checkbox in self.page.locator('.ge-item input[type=checkbox]').all():
            checkbox.check()
        self.assertEqual(self.page.locator('#gePercent').inner_text(), '100%')
        self.page.evaluate("window.dispatchEvent(new Event('afterprint'))")
        self.assertEqual(self.page.locator('.ge-area[open]').count(), 1)

    def ge_open(self, index):
        self.page.locator('.ge-area').nth(index).evaluate('node => node.open = true')

    def ge_choose(self, area, code):
        self.page.fill(f'#ge-course-{area}', code)
        self.page.locator(f'#ge-options-{area} [role=option]').get_by_text(code, exact=True).click()

    def test_ge_course_suggestions_are_area_specific_and_saved(self):
        self.open()
        self.ge_open(0)
        self.page.fill('#ge-course-1A', 'engl')
        options = self.page.locator('#ge-options-1A [role=option] strong').all_text_contents()
        self.assertEqual(options, ['ENGL C1000', 'ENGL C1000H'])
        self.page.fill('#ge-course-1A', 'calculus')
        self.assertEqual(self.page.locator('#ge-options-1A [role=option]').count(), 0)
        self.page.fill('#ge-course-1A', 'academic reading')
        self.page.press('#ge-course-1A', 'ArrowDown')
        self.page.press('#ge-course-1A', 'Enter')
        self.assertEqual(self.page.input_value('#ge-course-1A'), 'ENGL C1000')
        self.assertIn('1/12 planned', self.page.locator('#geCount').inner_text())
        self.page.check('#ge-1A')
        self.page.reload()
        self.ge_open(0)
        self.page.locator('#ge-hint-1A.ge-selected').wait_for()
        self.assertTrue(self.page.locator('#ge-1A').is_checked())
        self.ge_choose('1A', 'ENGL C1000H')
        self.assertFalse(self.page.locator('#ge-1A').is_checked())
        self.page.select_option('#collegeInput', 'foothill')
        self.ge_open(0)
        self.page.fill('#ge-course-1A', 'esl')
        self.assertEqual(self.page.locator('#ge-options-1A [role=option] strong').all_text_contents(), ['ESLL 26'])

    def test_ge_blocks_double_counting_and_same_discipline(self):
        self.open()
        self.ge_open(2)
        self.ge_choose('3A', 'HUMI 1')
        self.page.fill('#ge-course-3B', 'HUMI 1')
        option = self.page.locator('#ge-options-3B [role=option]').filter(has=self.page.get_by_text('HUMI 1', exact=True))
        self.assertEqual(option.get_attribute('aria-disabled'), 'true')
        self.ge_open(3)
        self.ge_choose('4A', 'ECON 1')
        self.page.fill('#ge-course-4B', 'ECON 2')
        self.assertIn('different discipline', self.page.locator('#ge-options-4B').inner_text())
        self.assertEqual(self.page.locator('#ge-options-4B [aria-disabled=true]').count(), 2)
        self.ge_choose('4B', 'PSYC C1000')
        self.assertIn('Listed for Area 4', self.page.locator('#ge-hint-4B').inner_text())

    def test_ge_labs_only_show_approved_lab_options(self):
        self.open()
        self.ge_open(4)
        self.page.fill('#ge-course-5C', 'ASTR')
        self.assertEqual(self.page.locator('#ge-options-5C [role=option] strong').all_text_contents(), ['ASTR 4 + ASTR 15L', 'ASTR 10 + ASTR 15L'])
        self.ge_choose('5A', 'CHEM 1A')
        self.ge_choose('5C', 'CHEM 1A')
        self.assertIn('Listed for Area 5C', self.page.locator('#ge-hint-5C').inner_text())
        self.page.select_option('#collegeInput', 'foothill')
        self.ge_open(4)
        self.page.fill('#ge-course-5C', 'ASTR')
        self.assertEqual(self.page.locator('#ge-options-5C [role=option] strong').all_text_contents(), ['ASTR 10L'])

    def test_ge_course_load_failure_can_retry(self):
        self.page.route('**/calgetc-2025-2026.json', lambda route: route.fulfill(status=503, body='offline'))
        self.open()
        self.page.locator('#geRetry').wait_for(state='visible')
        self.ge_open(0)
        self.assertTrue(self.page.locator('#ge-course-1A').is_disabled())
        self.page.unroute('**/calgetc-2025-2026.json')
        self.page.click('#geRetry')
        self.page.fill('#ge-course-1A', 'engl')
        self.assertEqual(self.page.locator('#ge-options-1A [role=option]').count(), 2)

    def test_ge_catalog_has_complete_areas_and_valid_common_numbers(self):
        data = json.loads((ROOT / 'data/calgetc-2025-2026.json').read_text(encoding='utf-8'))
        self.assertEqual(data['year'], '2025-2026')
        for name, source in data['colleges'].items():
            self.assertEqual(set(a for c in source['courses'] for a in c['areas']), {'1A','1B','1C','2','3A','3B','4','5A','5B','5C','6'})
            self.assertEqual(len({c['code'] for c in source['courses']}), len(source['courses']))
            self.assertTrue(all(c['prefix'] != 'C' for c in source['courses']))
            course = next(c for c in source['courses'] if c['code'] == 'ENGL C1000H')
            self.assertEqual(course['areas'], ['1A'])
            self.assertTrue(course['honors'])

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
