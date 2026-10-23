"""Browser contracts using synthetic data only. Requires playwright and Chrome.

Run: python -m unittest discover -s tests -p test_react_dashboard.py
"""
import copy
import socket
import time
import shutil
import uvicorn
import json
import os
from pathlib import Path
import sys
import threading
import tempfile
from unittest.mock import patch
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import dashboard_server as api_server
from dashboard_server import create_app


def capture():
    today = dict(strategy='Close now', days=0, mean=2100, p10=2100, p90=2100,
                 cash_flows=dict(stock_sale=2200, option_purchase=-100, option_sale=0), sale_floor_pass_rate=1)
    funding = dict(net_debit_usd=20, net_credit_usd=0, held_buyback_usd=100,
                   replacement_premium_usd=80, note='Synthetic funding.')
    roll = dict(strategy='Roll', expiry='2026-12-18', strike=26, days=30, mean=2300,
                p10=1900, p90=2600, cash_flows=dict(stock_sale=2320, option_purchase=-100, option_sale=80),
                sale_floor_pass_rate=.8, roll_funding=funding)
    roll['expire_worthless'] = dict(roll, exit_mode='expire', mean=-20, option_profit_usd=180,
        stock_retained=100, held_buyback_usd=100, replacement_buyback_usd=0,
        assumption='Assume worthless expiry.', cash_flows=dict(stock_sale=0, option_purchase=-100, option_sale=80))
    rolls = [roll]
    for strike in (27, 28):
        candidate = copy.deepcopy(roll)
        candidate['strike'] = strike
        candidate['expire_worthless']['strike'] = strike
        rolls.append(candidate)
    return dict(inputs=dict(account='RRSP', symbol='TEST', captured_at='2026-10-21T12:00:00Z',
        stock=dict(bidPrice=22, askPrice=24, bidSize=500, askSize=400),
        held=dict(bidPrice=.9, askPrice=1, bidSize=4, askSize=5), candidates=[{}], sources={},
        opening_reference=dict(stock_total_usd=2000, stock_price_usd=20, option_total_usd=200, option_price_usd=2)),
        result=dict(rows=[today, *rolls], top_choices=rolls, baseline=2100,
            minimum_stock_sale_price_usd=22, initial_purchase_price_usd=20,
            history_count=60, history_start='2026-07-20', history_end='2026-10-20', excluded=0))


class ReactDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise unittest.SkipTest('Install playwright to run browser contracts.')
        cls.socket = socket.socket()
        cls.socket.bind(('127.0.0.1', 0))
        cls.port = cls.socket.getsockname()[1]
        cls.server = uvicorn.Server(uvicorn.Config(create_app(refresh_macro=False), log_level='error'))
        cls.worker = threading.Thread(target=lambda: cls.server.run(sockets=[cls.socket]), daemon=True)
        cls.worker.start()
        deadline = time.monotonic() + 10
        while not cls.server.started:
            if time.monotonic() > deadline:
                raise RuntimeError('FastAPI test server did not start')
            time.sleep(.01)
        cls.playwright = sync_playwright().start()
        chrome = os.environ.get('CHROME_PATH') or shutil.which('chromium') or shutil.which('google-chrome')
        cls.browser = cls.playwright.chromium.launch(**({'executable_path':chrome} if chrome else {}), headless=True)
        cls.base = f'http://127.0.0.1:{cls.port}'

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.should_exit = True
        cls.worker.join(timeout=10)
        cls.socket.close()

    def setUp(self):
        self.context = self.browser.new_context(viewport=dict(width=1440, height=1100))
        self.page = self.context.new_page()
        self.page.set_default_timeout(10000)
        self.errors, self.posts, self.requests = [], [], []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('request', lambda request: self.requests.append(request.url))
        self.context.route('**/api/**', self.api)

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.assertTrue(all(url.startswith(self.base) for url in self.requests), 'Runtime must use local assets only.')
        self.context.close()

    def api(self, route):
        path = route.request.url.split('/api/', 1)[1].split('?', 1)[0]
        if path == 'exit-optimizer/capture':
            route.fulfill(json=capture()); return
        if route.request.method == 'POST':
            body = route.request.post_data_json
            self.posts.append((path, body))
            if path.startswith('exit-optimizer/'):
                data = capture()
                if path.endswith('scenario'):
                    data['scenario'] = dict(stock_price=body['stock_price'], note='Synthetic scenario.')
                    # A changed model baseline must never replace the captured one.
                    data['result']['rows'][0]['mean'] = 9999
                    data['result']['rows'][0]['cash_flows']['stock_sale'] = 9999
                route.fulfill(json=data)
            elif path == 'optimizer-recommendations':
                route.fulfill(json=dict(id=1, model='test-model', created_at='now', assessment='Synthetic assessment.'))
            else:
                route.fulfill(json={'bases': [], 'premiums': []})
            return
        holding = dict(account='RRSP', symbol='TEST', call_strike_native_currency=25, call_expiry='2026-11-20', call_contracts=1)
        values = {
            'auth/session': {'enabled': False},
            'exit-optimizer/holdings': {'holdings': [holding]},
            'profile/holdings': {'accounts': [dict(account='RRSP', currency='USD', positions=[dict(symbol='TEST', shares=100, contracts=1, cost=2000, strike=25, expiry='2026-11-20', entryFx=1)])]},
            'stock-cost-basis': {'bases': []}, 'option-premiums': {'premiums': []},
            'option-premiums/usd': {'premiums': []},
            'optimizer-recommendations/status': {'configured': True, 'model': 'test-model'},
            'optimizer-recommendations/history': {'runs': []},
        }
        route.fulfill(json=values[path])

    def open_dashboard(self):
        self.page.goto(self.base + '/covered-call-optimizer')
        self.page.get_by_text('Saved quotes loaded. Refresh for current prices.').wait_for()

    def test_react_uses_real_fastapi_capture_and_scenario(self):
        self.context.unroute('**/api/**')
        holding = dict(account='RRSP', symbol='TEST', call_strike_native_currency=25, call_expiry='2026-11-20', call_contracts=1)
        result = capture()
        result['scenario'] = dict(stock_price=25, note='Real FastAPI round trip.')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'frontend').symlink_to(ROOT/'frontend', target_is_directory=True)
            (root/'profile_settings.js').symlink_to(ROOT/'profile_settings.js')
            (root/'reports').mkdir()
            (root/'reports/exit-optimizer-rrsp-test.json').write_text(json.dumps(capture()))
            with patch.object(api_server, 'ROOT', root), \
                 patch.object(api_server.exit_optimizer, 'holdings', return_value=[holding]), \
                 patch.object(api_server.exit_optimizer, 'run') as refresh, \
                 patch.object(api_server.exit_optimizer, 'scenario', return_value=result) as scenario:
                self.open_dashboard()
                refresh.assert_not_called()
                self.page.get_by_role('slider').fill('25')
                self.page.get_by_text('Close today remains fixed at captured quotes. Real FastAPI round trip.').wait_for()
                scenario.assert_called_once_with(dict(account='RRSP', symbol='TEST', stock_price=25))
                self.assertIn('Net cash US$2,100.00', self.page.locator('#chart g[role="img"]').first.get_attribute('aria-label'))

    def test_local_render_scenario_baseline_expire_and_explicit_actions(self):
        self.open_dashboard()
        self.assertEqual(self.posts, [])
        baseline = self.page.locator('#chart g[role="img"]').first
        self.assertIn('Net cash US$2,100.00', baseline.get_attribute('aria-label'))
        slider = self.page.get_by_role('slider')
        slider.fill('25')
        self.page.get_by_text('Close today remains fixed at captured quotes. Synthetic scenario.').wait_for()
        self.assertIn('Net cash US$2,100.00', baseline.get_attribute('aria-label'))
        self.page.get_by_role('radio', name='Expire', exact=True).first.check()
        self.assertIn('Option-only P&L US$180.00', self.page.locator('#chart g[role="img"]').nth(1).get_attribute('aria-label'))
        self.page.get_by_role('button', name='Recommendation', exact=True).click()
        self.page.get_by_role('button', name='Generate recommendation').click()
        self.page.get_by_text('Synthetic assessment.', exact=True).wait_for()
        request = next(body for path, body in self.posts if path == 'optimizer-recommendations')
        self.assertEqual(request['stock_price'], 25)
        self.assertEqual(request['modes']['RRSP|TEST|2026-12-18|26'], 'expire')
        self.page.get_by_role('button', name='Reset to current quote').click()
        self.assertEqual(slider.input_value(), '23')
        self.page.get_by_role('button', name='Refresh data & analyze').click()
        self.page.get_by_text('Quotes refreshed. Chart updated.').wait_for()
        self.assertEqual(sum(path == 'exit-optimizer/run' for path, _ in self.posts), 1)

    def test_settings_database_payload_and_usd_premium(self):
        self.open_dashboard()
        self.page.get_by_role('button', name='My profile').click()
        self.page.get_by_role('button', name='Settings', exact=True).click()
        self.page.get_by_text('Stock cost basis is shared in the database.', exact=False).wait_for()
        self.page.get_by_label('Profile name', exact=True).fill('Test trader')
        self.page.get_by_label('RRSP TEST Purchase shares', exact=True).fill('100')
        self.page.get_by_label('RRSP TEST USD price / share', exact=True).fill('21')
        self.page.get_by_role('button', name='Save settings', exact=True).click()
        self.page.get_by_text('Stock basis saved in the database. Profile and thresholds saved in this browser.').wait_for()
        basis = next(body for path, body in self.posts if path == 'stock-cost-basis')['bases'][0]
        self.assertEqual(basis['totalCost'], 2100)
        self.assertEqual(basis['priceUsd'], 21)
        self.page.get_by_text('Record original option premium sale (USD)', exact=True).click()
        form = self.page.locator('section details').filter(has=self.page.get_by_text('Record original option premium sale (USD)', exact=True))
        form.get_by_label('Settlement date', exact=True).fill('2026-10-20')
        form.get_by_label('Premium sold (USD/share)', exact=True).fill('2.5')
        form.get_by_role('checkbox').check()
        form.get_by_role('button', name='Save opening premium').click()
        form.get_by_text('Opening sale saved in the database. Refresh the optimizer analysis to apply it.').wait_for()
        premium = next(body for path, body in self.posts if path == 'option-premiums/usd')
        self.assertEqual(premium['contracts'], 1)
        self.assertEqual(premium['price_usd'], 2.5)
        self.assertTrue(premium['reviewed'])
        self.page.get_by_text('Opening option sale · CAD conversion details (optional)', exact=True).click()
        converted = self.page.locator('section details').filter(has=self.page.get_by_text('Opening option sale · CAD conversion details (optional)', exact=True))
        for label, value in [('Ticker', 'TEST'), ('Call expiry', '2026-11-20'), ('Strike (USD)', '25'), ('Contracts (100 shares)', '1'), ('Settlement date', '2026-10-20'), ('Sale premium (USD/share)', '2.5'), ('Total fees (USD)', '1'), ('Applied CAD per USD', '1.35'), ('Net premium received (CAD)', '336.15')]:
            converted.get_by_label(label, exact=True).fill(value)
        converted.get_by_role('checkbox').check()
        converted.get_by_role('button', name='Save opening premium').click()
        converted.get_by_text('Opening sale saved in the database. Refresh the optimizer analysis to apply it.').wait_for()
        converted_payload = next(body for path, body in self.posts if path == 'option-premiums')
        self.assertEqual(converted_payload['fees_usd'], 1)
        self.assertEqual(converted_payload['net_cad'], 336.15)
        self.assertTrue(converted_payload['reviewed'])
        self.page.get_by_role('button', name='Close settings').click()
        self.page.get_by_role('button', name='Test trader').wait_for()

    def test_home_legacy_redirect_and_mobile(self):
        self.page.goto(self.base + '/')
        self.page.get_by_role('link', name='Open covered-call optimizer').click()
        self.page.get_by_text('Saved quotes loaded. Refresh for current prices.').wait_for()
        self.page.goto(self.base + '/equity-chart.html')
        self.page.wait_for_url('**/covered-call-optimizer')
        self.page.get_by_text('Saved quotes loaded. Refresh for current prices.').wait_for()

    def test_failed_refresh_retains_chart_and_blocks_mismatched_assessment(self):
        self.open_dashboard()
        self.context.route('**/api/exit-optimizer/run', lambda route: route.fulfill(status=502, json={'error': 'Synthetic market failure.'}))
        self.page.get_by_role('button', name='Refresh data & analyze').click()
        self.page.get_by_text('Synthetic market failure. Previous results retained.').wait_for()
        self.assertIn('Net cash US$2,100.00', self.page.locator('#chart g[role="img"]').first.get_attribute('aria-label'))
        self.context.route('**/api/exit-optimizer/scenario', lambda route: route.fulfill(status=502, json={'error': 'Synthetic scenario failure.'}))
        self.page.get_by_role('slider').fill('25')
        self.page.get_by_text('Chart retains its previous result: Synthetic scenario failure.').wait_for()
        self.page.get_by_role('button', name='Recommendation', exact=True).click()
        self.assertFalse(self.page.get_by_role('button', name='Generate recommendation').is_enabled())
        self.page.get_by_role('button', name='Reset to current quote').click()
        self.assertTrue(self.page.get_by_role('button', name='Generate recommendation').is_enabled())

    def test_latest_scenario_wins_and_capture_stays_fixed(self):
        self.open_dashboard()
        deferred = []
        self.context.route('**/api/exit-optimizer/scenario', lambda route: deferred.append(route))
        self.page.get_by_role('slider').fill('25')
        # Allow the UI's 180ms debounce to dispatch, with both responses held.
        self.page.wait_for_timeout(250)
        self.assertEqual(len(deferred), 1)
        self.page.get_by_role('slider').fill('26')
        self.page.wait_for_timeout(250)
        self.assertEqual(len(deferred), 2)
        newest = capture()
        newest['scenario'] = dict(stock_price=26, note='Latest scenario.')
        deferred[1].fulfill(json=newest)
        self.page.get_by_text('Close today remains fixed at captured quotes. Latest scenario.').wait_for()
        old = capture()
        old['scenario'] = dict(stock_price=25, note='Obsolete scenario.')
        deferred[0].fulfill(json=old)
        self.page.wait_for_timeout(50)
        self.assertEqual(self.page.get_by_role('slider').input_value(), '26')
        self.assertIn('Latest scenario.', self.page.locator('#stock-scenario').inner_text())
        self.assertIn('Net cash US$2,100.00', self.page.locator('#chart g[role="img"]').first.get_attribute('aria-label'))
        (ROOT/'reports').mkdir(exist_ok=True)
        self.page.screenshot(path=str(ROOT/'reports/react-dashboard-desktop.png'), full_page=True)
        self.page.set_viewport_size(dict(width=390, height=844))
        self.assertTrue(self.page.get_by_role('button', name='Refresh data & analyze').is_visible())
        self.page.screenshot(path=str(ROOT/'reports/react-dashboard-mobile.png'), full_page=True)


if __name__ == '__main__':
    unittest.main()
