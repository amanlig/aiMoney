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
    today = dict(strategy='Close now', net_profit_usd=300, days=0, mean=2100, p10=2100, p90=2100,
                 cash_flows=dict(stock_sale=2200, option_purchase=-100, option_sale=0), sale_floor_pass_rate=1)
    funding = dict(net_debit_usd=20, net_credit_usd=0, held_buyback_usd=100,
                   replacement_premium_usd=80, note='Synthetic funding.')
    roll = dict(strategy='Roll', net_profit_usd=500, expiry='2026-12-18', strike=26, days=30, mean=2300,
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
        interest_rate=dict(rate=.04,annual_percent=4.040268,selection={'mode':'treasury'},source='U.S. Treasury Daily Par Yield Curve',observed_on='2026-10-29'),
        opening_reference=dict(stock_total_usd=2000, stock_price_usd=20, option_total_usd=200, option_price_usd=2)),
        result=dict(rate=.04,rows=[today, *rolls], top_choices=rolls, baseline=2100,
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
        self.closed_records = []
        self.rollover_records = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('request', lambda request: self.requests.append(request.url))
        self.context.route('**/api/**', self.api)

    def test_date_keyboard_year_month_day_and_calendar(self):
        from playwright.sync_api import expect
        self.open_dashboard()
        self.page.get_by_role('button', name='Transactions', exact=True).click()
        field=self.page.get_by_label('RRSP TEST Purchase date',exact=True)
        field.fill('')
        field.focus()
        self.page.keyboard.type('2026')
        self.page.keyboard.press('Tab')
        self.assertEqual(field.evaluate('(el) => el.selectionStart'),5)
        self.page.keyboard.type('10')
        self.page.keyboard.press('Tab')
        self.assertEqual(field.evaluate('(el) => el.selectionStart'),8)
        self.page.keyboard.type('29')
        expect(field).to_have_value('2026-10-29')
        self.assertTrue(field.evaluate('(el) => el.checkValidity()'))
        self.page.keyboard.press('Shift+Tab')
        self.assertEqual(field.evaluate('(el) => el.selectionStart'),5)
        self.page.keyboard.type('11')
        expect(field).to_have_value('2026-11-29')
        self.page.keyboard.press('Tab')
        self.page.keyboard.press('Tab')
        self.assertFalse(field.evaluate('(el) => el === document.activeElement'))
        field.fill('2026-02-30')
        self.assertFalse(field.evaluate('(el) => el.checkValidity()'), field.evaluate('(el) => ({value:el.value,message:el.validationMessage})'))
        field.fill('2028-02-29')
        self.assertTrue(field.evaluate('(el) => el.checkValidity()'))
        picker=field.locator('..').locator('.date-calendar')
        picker.evaluate("""el => {
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'2026-12-31');
            el.dispatchEvent(new Event('input',{bubbles:true}));
            el.dispatchEvent(new Event('change',{bubbles:true}));
        }""")
        expect(field).to_have_value('2026-12-31')
        self.assertEqual(self.errors,[])

    def test_profile_interest_rate_default_override_and_saved_preference(self):
        from playwright.sync_api import expect
        self.open_dashboard()
        self.page.get_by_role('button',name='My profile').click()
        self.page.get_by_role('button',name='Settings',exact=True).click()
        modal=self.page.get_by_role('dialog',name='Profile',exact=True)
        source=modal.get_by_label('Interest rate source',exact=True)
        expect(source).to_have_value('treasury')
        modal.get_by_text('Treasury observation:',exact=False).wait_for()
        expect(modal.get_by_label('Annual interest yield (%)',exact=True)).to_have_attribute('readonly','')
        source.select_option('manual')
        modal.get_by_label('Annual interest yield (%)',exact=True).fill('5.5')
        modal.get_by_role('button',name='Save profile',exact=True).click()
        self.page.get_by_text('Manual override',exact=False).wait_for()
        sent=[body for path,body in self.posts if path=='exit-optimizer/scenario'][-1]
        self.assertEqual(sent['interest_rate'],{'mode':'manual','annual_percent':5.5})
        stored=self.page.evaluate("JSON.parse(localStorage.getItem('covered-call-profile-v1'))")
        self.assertEqual(stored['interestRate'],sent['interest_rate'])
        self.page.get_by_role('button',name='My profile').click()
        self.page.get_by_role('button',name='Settings',exact=True).click()
        expect(self.page.get_by_label('Annual interest yield (%)',exact=True)).to_have_value('5.5')
        self.page.get_by_label('Interest rate source',exact=True).select_option('treasury')
        self.page.get_by_role('button',name='Save profile',exact=True).click()
        self.page.get_by_text('U.S. Treasury Daily Par Yield Curve',exact=False).wait_for()
        self.assertEqual([body for path,body in self.posts if path=='exit-optimizer/scenario'][-1]['interest_rate'],{'mode':'treasury'})

    def test_download_all_rollovers_csv(self):
        import csv
        data = capture()
        for i, row in enumerate(data['result']['rows'][1:]):
            row['strategy'] = 'Roll then close'
            row['total_pl_usd'] = [10, 50, -20][i]
        self.context.route('**/api/exit-optimizer/capture?*', lambda route: route.fulfill(json=data))
        self.page.goto(self.base + '/covered-call-optimizer')
        button = self.page.get_by_role('group', name='Optimization', exact=True).get_by_role('button', name='Download all rollovers (CSV)', exact=True)
        with self.page.expect_download() as event:
            button.click()
        download = event.value
        self.assertTrue(download.suggested_filename.endswith('.csv'))
        with open(download.path(), encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 3)
        self.assertEqual([float(r['estimated_total_position_profit_usd']) for r in rows], [50, 10, -20])
        self.assertEqual(self.posts, [])

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.assertTrue(all(url.startswith(self.base) for url in self.requests), 'Runtime must use local assets only.')
        self.context.close()

    def api(self, route):
        path = route.request.url.split('/api/', 1)[1].split('?', 1)[0]
        if path.startswith('positions/') and path.endswith('/transactions'):
            route.fulfill(json=dict(account='RRSP',symbol='TEST',entries=[],realized_option_pl_usd=0,net_option_cash_usd=0,open_call_premium_usd=0,history_complete=True,note='Synthetic report.'));return
        if path == 'exit-optimizer/capture':
            route.fulfill(json=capture()); return
        if route.request.method == 'POST':
            body = route.request.post_data_json
            self.posts.append((path, body))
            if path.startswith('exit-optimizer/'):
                data = capture()
                if body.get('interest_rate'):
                    data['inputs']['interest_rate']['selection']=body['interest_rate']
                    if body['interest_rate']['mode']=='manual':
                        import math
                        percent=body['interest_rate']['annual_percent']
                        data['inputs']['interest_rate'].update(source='Manual override',observed_on=None,annual_percent=percent,rate=2*math.log1p(percent/200))
                        data['result']['rate']=2*math.log1p(percent/200)
                if path.endswith('scenario'):
                    data['scenario'] = dict(stock_price=body['stock_price'], note='Synthetic scenario.')
                    # A changed model baseline must never replace the captured one.
                    data['result']['rows'][0]['mean'] = 9999
                    data['result']['rows'][0]['cash_flows']['stock_sale'] = 9999
                route.fulfill(json=data)
            elif path == 'option-rollovers':
                record=dict(id=1, **body, buyback_total_usd=200, sale_total_usd=250, net_cash_usd=49)
                self.rollover_records.append(record)
                route.fulfill(json=record)
            elif path == 'closed-holdings':
                record=dict(id=1, **body, shares=100, contracts=1, expiry='2026-11-20', strike=25, stock_sale_usd=3000, buyback_total_usd=200, closing_cash_usd=2795, realized_pl_usd=995, accounting=dict(stock_cost_usd=2000,historical_option_net_usd=200,rollover_count=0))
                if body.get('quote_captured_at'):
                    q=capture()['inputs']
                    record['quote_snapshot']=dict(captured_at=q['captured_at'],stock=q['stock'],held=q['held'])
                self.closed_records.append(record)
                route.fulfill(json=record)
            elif path == 'optimizer-recommendations':
                route.fulfill(json=dict(id=1, model='test-model', created_at='now', assessment='Synthetic assessment.'))
            else:
                route.fulfill(json={'bases': [], 'premiums': []})
            return
        holding = dict(account='RRSP', symbol='TEST', shares=100, position_key='test-position', call_strike_native_currency=25, call_expiry='2026-11-20', call_contracts=1)
        values = {
            'auth/session': {'enabled': False},
            'interest-rate': dict(rate=.04,annual_percent=4.040268,selection={'mode':'treasury'},source='U.S. Treasury Daily Par Yield Curve',observed_on='2026-10-29',expiry='2026-11-20',lower_tenor_years=1/12,upper_tenor_years=1/12),
            'exit-optimizer/holdings': {'holdings': [] if self.closed_records else [holding]},
            'closed-holdings': {'holdings': self.closed_records},
            'option-rollovers': {'rollovers': self.rollover_records},
            'positions/availability': {'stocks':[]},
            'option-expirations': {'expirations':[]},
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
                 patch.object(api_server.covered_positions, 'availability', return_value=[]), \
                 patch.object(api_server.exit_optimizer, 'run') as refresh, \
                 patch.object(api_server.exit_optimizer, 'scenario', return_value=result) as scenario:
                self.open_dashboard()
                refresh.assert_not_called()
                self.page.get_by_role('slider').fill('25')
                self.page.get_by_text('Close today remains fixed at captured quotes. Real FastAPI round trip.').wait_for()
                scenario.assert_called_once_with(dict(account='RRSP', symbol='TEST', stock_price=25,interest_rate={'mode':'treasury'}))
                self.assertIn('Net cash US$2,100.00', self.page.locator('#chart g[role="group"]').first.get_attribute('aria-label'))

    def test_local_render_scenario_baseline_expire_and_explicit_actions(self):
        self.open_dashboard()
        self.assertEqual(self.posts, [])
        baseline = self.page.locator('#chart g[role="group"]').first
        self.assertIn('Net cash US$2,100.00', baseline.get_attribute('aria-label'))
        scenario = self.page.locator('#chart [data-scenario-close="true"]')
        self.assertEqual(scenario.count(), 0)
        slider = self.page.get_by_role('slider')
        slider.fill('25')
        self.page.get_by_text('Close today remains fixed at captured quotes. Synthetic scenario.').wait_for()
        self.assertIn('Net cash US$2,100.00', baseline.get_attribute('aria-label'))
        self.assertEqual(scenario.count(), 1)
        self.assertEqual(scenario.locator('rect[data-pnl="total"]').get_attribute('data-value'), '300')
        self.assertIn('Stock sale US$9,999.00', scenario.locator('g[role="group"]').get_attribute('aria-label'))
        self.assertIn('Close at slider price', scenario.locator('g[role="group"]').get_attribute('aria-label'))
        self.assertEqual(self.page.get_by_role('radio', name='Expire', exact=True).count(), 3)
        self.page.get_by_role('radio', name='Expire', exact=True).first.check()
        self.assertIn('Option-only P/L US$180.00', self.page.locator('#chart g[role="group"]').nth(2).get_attribute('aria-label'))
        self.page.get_by_role('button', name='Recommendation', exact=True).click()
        self.page.get_by_role('button', name='Generate recommendation').click()
        self.page.get_by_text('Synthetic assessment.', exact=True).wait_for()
        request = next(body for path, body in self.posts if path == 'optimizer-recommendations')
        self.assertEqual(request['stock_price'], 25)
        self.assertEqual(request['modes']['RRSP|TEST|2026-12-18|26'], 'expire')
        self.page.get_by_role('button', name='Reset to current quote').click()
        self.assertEqual(slider.input_value(), '23')
        self.assertEqual(scenario.count(), 0)
        self.page.get_by_role('button', name='Refresh data & analyze').click()
        self.page.get_by_text('Quotes refreshed. Chart updated.').wait_for()
        self.assertEqual(sum(path == 'exit-optimizer/run' for path, _ in self.posts), 1)

    def test_settings_database_payload_and_usd_premium(self):
        self.open_dashboard()
        self.page.get_by_role('button', name='My profile').click()
        self.page.get_by_role('button', name='Settings', exact=True).click()
        self.page.get_by_label('Profile name', exact=True).fill('Test trader')
        self.assertEqual(self.page.get_by_role('tab', name='Stock purchase', exact=True).count(), 0)
        self.page.get_by_role('button', name='Save profile', exact=True).click()
        self.page.get_by_role('button', name='Transactions', exact=True).click()
        self.page.get_by_role('tab', name='Stock purchase', exact=True).wait_for()
        self.assertEqual(self.page.get_by_label('Profile name', exact=True).count(), 0)
        self.page.get_by_label('RRSP TEST Purchase shares', exact=True).fill('100')
        self.page.get_by_label('RRSP TEST Purchase price (USD/share)', exact=True).fill('21')
        self.page.get_by_label('RRSP TEST Purchase date', exact=True).fill('2025-10-06')
        self.page.get_by_label('RRSP TEST Purchase fees (USD)', exact=True).fill('0')
        self.page.get_by_role('button', name='Save stock purchase', exact=True).click()
        self.page.get_by_text('Stock purchases saved in USD. Refresh data & analyze to update the chart.').wait_for()
        basis = next(body for path, body in self.posts if path == 'stock-cost-basis')['bases'][0]
        self.assertEqual(basis['totalCost'], 2100)
        self.assertEqual(basis['priceUsd'], 21)
        self.assertEqual(basis['currency'], 'USD')
        self.assertEqual(basis['fx'], None)
        self.page.get_by_role('tab', name='Option Opening Sale', exact=True).click()
        form = self.page.get_by_role('tabpanel', name='Option Opening Sale', exact=True)
        form.get_by_label('Settlement date', exact=True).fill('2026-10-20')
        form.get_by_label('Premium sold (USD/share)', exact=True).fill('2.5')
        form.get_by_role('checkbox').check()
        form.get_by_role('button', name='Save opening premium').click()
        form.get_by_text('Opening sale saved. Close Transactions to update chart P/L using saved quotes.').wait_for()
        premium = next(body for path, body in self.posts if path == 'option-premiums/usd')
        self.assertEqual(premium['contracts'], 1)
        self.assertEqual(premium['price_usd'], 2.5)
        self.assertTrue(premium['reviewed'])
        self.assertEqual(self.page.get_by_text('Opening option sale · CAD conversion details (optional)', exact=True).count(), 0)
        self.page.get_by_role('button', name='Close transactions').click()
        self.page.get_by_role('button', name='Test trader').wait_for()

    def test_rollover_form_shared_holding_and_both_leg_payload(self):
        self.open_dashboard()
        self.page.get_by_role('button', name='Transactions', exact=True).click()
        modal=self.page.get_by_role('dialog', name='Transactions', exact=True)
        modal.get_by_label('Holding', exact=True).wait_for()
        self.assertEqual(modal.get_by_label('Holding', exact=True).count(), 1)
        modal.get_by_role('tab', name='Rollover', exact=True).click()
        form=modal.get_by_role('tabpanel', name='Rollover', exact=True)
        form.get_by_label('Settlement date', exact=True).fill('2026-10-27')
        self.assertEqual(form.get_by_label('Contracts (both legs)', exact=True).input_value(), '1')
        self.assertEqual(form.get_by_label('Buyback strike (USD)', exact=True).input_value(), '25')
        for label, value in [('Buyback premium (USD/share)', '2'), ('Replacement expiry', '2026-12-18'), ('Replacement strike (USD)', '26'), ('Sale premium (USD/share)', '2.5'), ('Total rollover fees (USD)', '1')]:
            form.get_by_label(label, exact=True).fill(value)
        form.get_by_text('Net credit: US$49.00', exact=False).wait_for()
        form.get_by_role('checkbox').check()
        form.get_by_role('button', name='Save rollover', exact=True).click()
        form.get_by_text('Rollover saved. Close Transactions to update chart P/L using saved quotes.', exact=True).wait_for()
        payload=next(body for path,body in self.posts if path=='option-rollovers')
        self.assertEqual(payload['symbol'], 'TEST')
        self.assertEqual(payload['buyback_price_usd'], 2)
        self.assertEqual(payload['sale_price_usd'], 2.5)
        self.assertEqual(payload['fees_usd'], 1)
        self.assertTrue(payload['reviewed'])
        self.assertEqual(form.get_by_label('Settlement date', exact=True).input_value(), '')
        self.assertEqual(form.get_by_label('Total rollover fees (USD)', exact=True).input_value(), '')
        self.assertFalse(form.get_by_role('checkbox').is_checked())

    def test_hover_details_show_only_the_selected_segment(self):
        self.open_dashboard()
        group=self.page.locator('#chart g[role="group"]').nth(1)
        group.locator('rect[fill="#26856c"]').hover()
        self.assertEqual(self.page.locator('#chart-detail').inner_text(), 'Stock sale / assignment: US$2,320.00')
        group.locator('rect[fill="#518acb"]').hover()
        self.assertEqual(self.page.locator('#chart-detail').inner_text(), 'Replacement call premium sale: US$80.00')
        group.locator('rect[fill="#d45b68"]').focus()
        self.assertEqual(self.page.locator('#chart-detail').inner_text(), 'Call buyback cost: US$100.00')

    def test_new_stock_purchase_then_option_sale_and_delete_with_confirmation(self):
        import holding_records
        import covered_positions as positions
        import stock_basis
        from urllib.parse import urlsplit
        from playwright.sync_api import expect
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'new-holding.sqlite3'
            reports=Path(folder)/'reports';reports.mkdir()
            def api(route):
                request=route.request;endpoint=urlsplit(request.url).path.removeprefix('/api/')
                if endpoint=='exit-optimizer/holdings':route.fulfill(json={'holdings':[h for h in positions.synchronize([],path) if not h.get('option_expired')]});return
                if endpoint=='exit-optimizer/capture':route.fulfill(status=404,json={'error':'No saved analysis'});return
                if endpoint=='profile/holdings':route.fulfill(json={'accounts':[]});return
                if endpoint=='stock-cost-basis':route.fulfill(json={'bases':stock_basis.records(path)});return
                if endpoint=='option-expirations':route.fulfill(json={'expirations':positions.expirations(path)});return
                if endpoint=='holdings':
                    self.posts.append((endpoint,request.post_data_json));route.fulfill(status=201,json=holding_records.create(request.post_data_json,path));return
                if endpoint.startswith('positions/'):
                    pid=endpoint.split('/')[1]
                    if endpoint.endswith('/history'):route.fulfill(json=positions.history(pid,path));return
                    if endpoint.endswith('/expiration-preview'):route.fulfill(json=positions.expiration_preview(pid,path));return
                    if endpoint.endswith('/expire-worthless'):
                        self.posts.append((endpoint,request.post_data_json));route.fulfill(status=201,json=positions.expire_worthless(pid,request.post_data_json,path,retain_stock=True));return
                    if endpoint.endswith('/delete-preview'):route.fulfill(json=holding_records.preview(pid,path));return
                    if endpoint.endswith('/opening'):
                        self.posts.append((endpoint,request.post_data_json));route.fulfill(status=201,json=positions.save_opening(pid,request.post_data_json,path=path));return
                    if endpoint.endswith('/delete'):
                        self.posts.append((endpoint,request.post_data_json));route.fulfill(json=holding_records.delete(pid,request.post_data_json,path,reports));return
                self.api(route)
            self.context.unroute('**/api/**');self.context.route('**/api/**',api)
            self.page.goto(self.base+'/covered-call-optimizer')
            self.page.get_by_text('No active holdings. Use New to start with a stock purchase.',exact=True).wait_for()
            expect(self.page.get_by_role('button',name='Delete',exact=True)).to_be_disabled()
            self.page.get_by_role('button',name='New',exact=True).click()
            new=self.page.get_by_role('dialog',name='New holding',exact=True)
            for label,value in [('Ticker','NEWT'),('Purchase date','2025-01-02'),('Shares purchased','100'),('Purchase price (USD/share)','20'),('Purchase fees (USD)','1')]:
                new.get_by_label(label,exact=True).fill(value)
            self.page.screenshot(path=str(ROOT/'reports/new-holding-desktop.png'))
            new.get_by_role('button',name='Create holding',exact=True).click()
            modal=self.page.get_by_role('dialog',name='Transactions',exact=True)
            expect(modal.get_by_label('RRSP NEWT Purchase shares',exact=True)).to_have_value('100')
            self.assertIn('Stock only',modal.get_by_label('Holding',exact=True).inner_text())
            modal.get_by_role('tab',name='Option Opening Sale',exact=True).click()
            panel=modal.get_by_role('tabpanel',name='Option Opening Sale',exact=True)
            for label,value in [('Original call expiry','2026-10-23'),('Original strike (USD)','25'),('Original contracts','1'),('Settlement date','2025-01-03'),('Premium sold (USD/share)','2')]:
                panel.get_by_label(label,exact=True).fill(value)
            panel.get_by_role('checkbox',name='I verified the opening sale against my confirmation.',exact=True).check()
            panel.get_by_role('button',name='Save opening premium',exact=True).click()
            panel.get_by_role('button',name='Edit',exact=True).wait_for()
            modal.get_by_role('button',name='Close transactions',exact=True).click()
            expect(self.page.get_by_role('button',name='Refresh data & analyze',exact=True)).to_be_disabled()
            self.page.get_by_role('button',name='Expired worthless',exact=True).click()
            expiry=self.page.get_by_role('dialog',name='Expired worthless',exact=True)
            expiry.get_by_role('checkbox').check();expiry.get_by_role('button',name='Record worthless expiry',exact=True).click()
            expect(self.page.get_by_label('Holding',exact=True)).to_contain_text('Stock only')
            self.page.reload()
            expect(self.page.get_by_label('Holding',exact=True)).to_contain_text('Stock only')
            self.assertEqual(len(positions.expirations(path)),1)
            self.page.get_by_role('button',name='Transactions',exact=True).click()
            modal=self.page.get_by_role('dialog',name='Transactions',exact=True)
            modal.get_by_role('tab',name='Option Opening Sale',exact=True).click()
            panel=modal.get_by_role('tabpanel',name='Option Opening Sale',exact=True)
            expect(panel.get_by_label('Original call expiry',exact=True)).to_have_value('')
            for label,value in [('Original call expiry','2028-01-21'),('Original strike (USD)','30'),('Original contracts','1'),('Settlement date','2026-10-26'),('Premium sold (USD/share)','3')]:
                panel.get_by_label(label,exact=True).fill(value)
            panel.get_by_role('checkbox',name='I verified the opening sale against my confirmation.',exact=True).check()
            panel.get_by_role('button',name='Save opening premium',exact=True).click()
            panel.get_by_role('button',name='Edit',exact=True).wait_for()
            modal.get_by_role('button',name='Close transactions',exact=True).click()
            expect(self.page.get_by_role('button',name='Refresh data & analyze',exact=True)).to_be_enabled()
            self.page.get_by_role('button',name='Delete',exact=True).click()
            delete=self.page.get_by_role('dialog',name='Delete holding',exact=True)
            expect(delete.get_by_role('button',name='Delete holding and records',exact=True)).to_be_disabled()
            self.page.screenshot(path=str(ROOT/'reports/delete-holding-desktop.png'))
            delete.get_by_role('button',name='Cancel',exact=True).click()
            self.assertEqual(len([h for h in positions.synchronize([],path) if not h.get('option_expired')]),1)
            self.page.get_by_role('button',name='Delete',exact=True).click()
            delete=self.page.get_by_role('dialog',name='Delete holding',exact=True)
            delete.get_by_role('checkbox',name='Delete this holding and all its associated records.',exact=True).check()
            delete.get_by_role('button',name='Delete holding and records',exact=True).click()
            expect(self.page.get_by_label('Holding',exact=True).locator('option')).to_have_count(0)
            self.assertEqual(stock_basis.records(path),[])
            self.page.reload()
            expect(self.page.get_by_role('button',name='Delete',exact=True)).to_be_disabled()
            self.assertEqual(self.page.get_by_label('Holding',exact=True).locator('option').count(),0)
            self.assertFalse(any(endpoint=='exit-optimizer/run' for endpoint,body in self.posts))

    def test_past_sale_without_expiry_confirmation_prefills_its_rollover(self):
        import holding_records
        import covered_positions as positions
        import stock_basis
        from urllib.parse import urlsplit
        from playwright.sync_api import expect
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'historical-rollover.sqlite3'
            h=holding_records.create(dict(account='RRSP',symbol='RKLB',purchase_date='2025-01-02',shares=1000,price_usd=21.4581,fees_usd=0),path)
            pid=h['position_id']
            def api(route):
                request=route.request;endpoint=urlsplit(request.url).path.removeprefix('/api/')
                if endpoint=='exit-optimizer/holdings':route.fulfill(json={'holdings':[positions.history(pid,path)['position']]});return
                if endpoint=='exit-optimizer/capture':route.fulfill(status=404,json={'error':'No saved analysis'});return
                if endpoint=='profile/holdings':route.fulfill(json={'accounts':[]});return
                if endpoint=='stock-cost-basis':route.fulfill(json={'bases':stock_basis.records(path)});return
                if endpoint==f'positions/{pid}/history':route.fulfill(json=positions.history(pid,path));return
                if endpoint==f'positions/{pid}/transactions':
                    import transaction_report
                    route.fulfill(json=transaction_report.report(pid,path));return
                if endpoint in [f'positions/{pid}/opening',f'positions/{pid}/rollovers']:
                    body=request.post_data_json;self.posts.append((endpoint,body))
                    result=positions.save_opening(pid,body,path=path) if endpoint.endswith('/opening') else positions.save_rollover(pid,body,path)
                    route.fulfill(status=201,json=result);return
                self.api(route)
            self.context.unroute('**/api/**');self.context.route('**/api/**',api)
            self.page.goto(self.base+'/covered-call-optimizer')
            self.page.get_by_role('button',name='Transactions',exact=True).click()
            modal=self.page.get_by_role('dialog',name='Transactions',exact=True)
            modal.get_by_role('tab',name='Option Opening Sale',exact=True).click()
            panel=modal.get_by_role('tabpanel',name='Option Opening Sale',exact=True)
            for label,value in [('Original call expiry','2025-05-30'),('Original strike (USD)','23'),('Original contracts','10'),('Settlement date','2025-05-13'),('Premium sold (USD/share)','.65')]:
                panel.get_by_label(label,exact=True).fill(value)
            expect(panel.get_by_role('checkbox',name='This original call expired worthless, with no buyback or assignment; I retained the shares.',exact=True)).not_to_be_checked()
            panel.get_by_role('checkbox',name='I verified the opening sale against my confirmation.',exact=True).check()
            panel.get_by_role('button',name='Save opening premium',exact=True).click()
            panel.get_by_role('button',name='Edit',exact=True).wait_for()
            expect(modal.get_by_label('Holding',exact=True)).to_contain_text('2025-05-30')
            self.assertEqual(positions.expirations(path),[])
            modal.get_by_role('tab',name='Rollover',exact=True).click()
            roll=modal.get_by_role('tabpanel',name='Rollover',exact=True)
            expect(roll.get_by_label('Buyback expiry',exact=True)).to_have_value('2025-05-30')
            expect(roll.get_by_label('Buyback strike (USD)',exact=True)).to_have_value('23')
            expect(roll.get_by_label('Contracts (both legs)',exact=True)).to_have_value('10')
            for label,value in [('Settlement date','2025-05-20'),('Buyback premium (USD/share)','.901'),('Replacement expiry','2028-01-21'),('Replacement strike (USD)','25'),('Sale premium (USD/share)','1.5')]:
                roll.get_by_label(label,exact=True).fill(value)
            roll.get_by_role('checkbox').check();roll.get_by_role('button',name='Save rollover',exact=True).click()
            roll.get_by_text('Rollover saved.',exact=False).wait_for()
            self.assertEqual(positions.history(pid,path)['position']['call_expiry'],'2028-01-21')
            self.assertEqual(positions.expirations(path),[])
            self.assertFalse(self.posts[0][1]['expired_worthless'])
            report=modal.locator('.transaction-report')
            expect(report.get_by_role('heading',name='Transaction report',exact=True)).to_be_visible()
            expect(report.locator('.transaction-totals').get_by_text('US$1,249.00',exact=True)).to_be_visible()
            cash_table=report.get_by_role('region',name='Recorded buy and sell transactions',exact=True)
            rollover=cash_table.get_by_role('row').filter(has=self.page.get_by_role('cell',name='Rollover',exact=True))
            expect(rollover).to_have_count(1)
            expect(rollover.get_by_role('cell',name='Buy $0.901 Sell $1.50',exact=True)).to_be_visible()
            expect(rollover.get_by_role('cell',name='US$599.00',exact=True)).to_have_count(2)
            totals=cash_table.locator('tfoot td')
            expect(totals.nth(0)).to_contain_text('-US$20,209.10')
            expect(totals.nth(1)).to_contain_text('US$1,249.00')
            self.assertEqual(cash_table.get_by_text('-US$251.00',exact=True).count(),0)
            report.get_by_text('Closed-call accounting detail',exact=True).click()
            expect(report.locator('.completed-call-detail').get_by_role('cell',name='-US$251.00',exact=True)).to_be_visible()
            report.get_by_text('Closed-call accounting detail',exact=True).click()
            self.assertEqual(modal.get_by_text('Expired option history',exact=True).count(),0)
            report.scroll_into_view_if_needed()
            self.page.screenshot(path=str(ROOT/'reports/transaction-report-desktop.png'),full_page=True)
            self.page.set_viewport_size(dict(width=390,height=844))
            expect(report.get_by_role('region',name='Recorded buy and sell transactions',exact=True)).to_be_visible()
            report.scroll_into_view_if_needed()
            self.page.screenshot(path=str(ROOT/'reports/transaction-report-mobile.png'),full_page=True)
            modal.get_by_role('button',name='Close transactions',exact=True).click()
            expect(self.page.get_by_role('button',name='Refresh data & analyze',exact=True)).to_be_enabled()

    def test_add_second_expiry_keeps_opening_records_separate(self):
        from urllib.parse import parse_qs, urlsplit
        january=dict(account='RRSP',symbol='RKLB',shares=1000,call_contracts=10,call_expiry='2028-01-21',call_strike_native_currency=20,position_id='a'*32,position_key='a'*32)
        february=dict(january,call_expiry='2028-02-18',position_id='b'*32,position_key='b'*32)
        active=[january]
        openings={january['position_id']:dict(id=january['position_id'],account='RRSP',symbol='RKLB',expiry='2028-01-21',strike=20,contracts=10,settlement_date='2026-10-01',price_usd=3)}
        def api(route):
            request=route.request;url=urlsplit(request.url);path=url.path.removeprefix('/api/')
            if path=='exit-optimizer/holdings': route.fulfill(json={'holdings':active});return
            if path=='profile/holdings':
                route.fulfill(json={'accounts':[dict(account='RRSP',currency='USD',positions=[dict(symbol='RKLB',shares=2000,cost=40000)])]});return
            if path=='exit-optimizer/capture':
                data=capture();position_id=parse_qs(url.query)['position_id'][0]
                h=next(h for h in active if h['position_id']==position_id)
                data['inputs'].update(account='RRSP',symbol='RKLB',position_id=position_id,shares=1000,contracts=10)
                data['inputs']['held'].update(expiry=h['call_expiry'],strike=20)
                route.fulfill(json=data);return
            if path=='positions/availability':
                route.fulfill(json={'stocks':[dict(account='RRSP',symbol='RKLB',total_shares=2000,allocated_shares=len(active)*1000,available_shares=2000-len(active)*1000)]});return
            if path=='positions' and request.method=='POST':
                self.posts.append((path,request.post_data_json));active.append(february);route.fulfill(json=february);return
            if path.startswith('positions/'):
                position_id=path.split('/')[1]
                if path.endswith('/history'):
                    route.fulfill(json={'position':next(h for h in active if h['position_id']==position_id),'opening':openings.get(position_id),'rollovers':[]});return
                if path.endswith('/opening') and request.method=='POST':
                    body=request.post_data_json;self.posts.append((path,body));openings[position_id]=dict(body,id=position_id)
                    route.fulfill(json=openings[position_id]);return
            self.api(route)
        self.context.unroute('**/api/**');self.context.route('**/api/**',api)
        self.open_dashboard()
        self.page.get_by_role('button',name='Transactions',exact=True).click()
        modal=self.page.get_by_role('dialog',name='Transactions',exact=True)
        modal.get_by_role('tab',name='Option Opening Sale',exact=True).click()
        modal.get_by_text('This position already has its opening sale. Use Edit to correct it.',exact=True).wait_for()
        self.assertEqual(modal.get_by_role('button',name='Save opening premium',exact=True).count(),0)
        modal.get_by_role('button',name='Add position',exact=True).click()
        editor=modal.locator('.position-editor')
        editor.get_by_label('Call contracts',exact=True).fill('10')
        editor.get_by_label('Call strike (USD)',exact=True).fill('20')
        editor.get_by_label('Call expiry',exact=True).fill('2028-02-18')
        editor.get_by_role('button',name='Create position',exact=True).click()
        modal.get_by_label('Original call expiry',exact=True).wait_for()
        self.assertEqual(modal.get_by_label('Holding',exact=True).input_value(),february['position_id'])
        self.assertEqual(modal.get_by_label('Original call expiry',exact=True).input_value(),'2028-02-18')
        opening_panel=modal.get_by_role('tabpanel',name='Option Opening Sale',exact=True)
        opening_panel.get_by_label('Settlement date',exact=True).fill('2026-10-02')
        opening_panel.get_by_label('Premium sold (USD/share)',exact=True).fill('4')
        modal.get_by_role('tabpanel',name='Option Opening Sale',exact=True).get_by_role('checkbox',name='I verified the opening sale against my confirmation.',exact=True).check()
        modal.get_by_role('button',name='Save opening premium',exact=True).click()
        modal.get_by_text('This position already has its opening sale. Use Edit to correct it.',exact=True).wait_for()
        self.assertEqual(openings[january['position_id']]['price_usd'],3)
        self.assertEqual(openings[february['position_id']]['price_usd'],4)
        self.assertEqual(self.posts[0][1]['shares'],1000)
        modal.get_by_role('button',name='Close transactions',exact=True).click()
        self.page.get_by_label('Holding',exact=True).wait_for()
        self.page.wait_for_function("document.querySelector('select[aria-label=Holding]').value === '1'")
        self.assertEqual(self.page.get_by_label('Holding',exact=True).locator('option').count(),2)

    def test_original_before_rollovers_checkbox_and_historical_buyback(self):
        import covered_positions
        import position_history
        from urllib.parse import urlsplit
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'historical.sqlite3'
            raw=dict(account='RRSP',symbol='RKLB',shares=1000,call_contracts=10,call_expiry='2028-01-21',call_strike_native_currency=25)
            holding=covered_positions.synchronize([raw],path)[0]
            pid=holding['position_id']
            def api(route):
                request=route.request;endpoint=urlsplit(request.url).path.removeprefix('/api/')
                if endpoint=='exit-optimizer/holdings':
                    route.fulfill(json={'holdings':[covered_positions.history(pid,path)['position']]});return
                if endpoint=='exit-optimizer/capture':
                    data=capture();data['inputs'].update(account='RRSP',symbol='RKLB',position_id=pid)
                    route.fulfill(json=data);return
                if endpoint==f'positions/{pid}/history':
                    route.fulfill(json=covered_positions.history(pid,path));return
                if endpoint in [f'positions/{pid}/opening',f'positions/{pid}/rollovers']:
                    body=request.post_data_json;self.posts.append((endpoint,body))
                    try:
                        result=covered_positions.save_opening(pid,body,path=path) if endpoint.endswith('/opening') else covered_positions.save_rollover(pid,body,path)
                        route.fulfill(status=201,json=result)
                    except ValueError as error:route.fulfill(status=400,json={'error':str(error)})
                    return
                self.api(route)
            self.context.unroute('**/api/**');self.context.route('**/api/**',api)
            self.open_dashboard()
            self.page.get_by_role('button',name='Transactions',exact=True).click()
            modal=self.page.get_by_role('dialog',name='Transactions',exact=True)
            # Visit Rollover first to ensure it reloads after the opening is recorded.
            modal.get_by_role('tab',name='Rollover',exact=True).click()
            modal.get_by_role('tab',name='Option Opening Sale',exact=True).click()
            form=modal.get_by_role('tabpanel',name='Option Opening Sale',exact=True)
            for label,value in [('Original call expiry','2025-03-21'),('Original strike (USD)','24'),('Original contracts','10'),('Settlement date','2025-03-04'),('Premium sold (USD/share)','.8')]:
                form.get_by_label(label,exact=True).fill(value)
            confirmation=form.get_by_role('checkbox',name='I verified the opening sale against my confirmation.',exact=True)
            confirmation.check();form.get_by_role('button',name='Save opening premium',exact=True).click()
            form.get_by_text('For an earlier original call, check the original-before-rollovers box.',exact=False).wait_for()
            form.get_by_role('checkbox',name='This is an earlier original call; its strike or expiry differs from the current holding.',exact=True).check()
            self.assertFalse(confirmation.is_checked())
            confirmation.check();form.get_by_role('button',name='Save opening premium',exact=True).click()
            form.get_by_text('This position already has its opening sale. Use Edit to correct it.',exact=True).wait_for()
            saved=covered_positions.history(pid,path)
            self.assertTrue(saved['opening']['historical_opening'])
            self.assertEqual(saved['position']['position_revision'],holding['position_revision'])
            modal.get_by_role('tab',name='Rollover',exact=True).click()
            roll=modal.get_by_role('tabpanel',name='Rollover',exact=True)
            roll.get_by_label('Buyback expiry',exact=True).wait_for()
            from playwright.sync_api import expect
            expect(roll.get_by_label('Buyback expiry',exact=True)).to_have_value('2025-03-21')
            self.assertEqual(roll.get_by_label('Buyback strike (USD)',exact=True).input_value(),'24')
            for label,value in [('Settlement date','2025-03-20'),('Buyback premium (USD/share)','.4'),('Replacement expiry','2028-01-21'),('Replacement strike (USD)','25'),('Sale premium (USD/share)','2'),('Total rollover fees (USD)','10')]:
                roll.get_by_label(label,exact=True).fill(value)
            roll.get_by_role('checkbox').check();roll.get_by_role('button',name='Save rollover',exact=True).click()
            roll.get_by_text('Rollover saved. Close Transactions to update chart P/L using saved quotes.',exact=True).wait_for()
            saved=covered_positions.history(pid,path)
            self.assertEqual(saved['position']['position_revision'],holding['position_revision'])
            result=position_history.resolve('RRSP','RKLB',dict(expiry='2028-01-21',strike=25),10,[saved['opening']],saved['rollovers'])
            self.assertEqual(result['historical_option_net_usd'],2390)

    def test_original_expiry_checkbox_realizes_gain_before_current_opening_is_known(self):
        import covered_positions as positions
        import exit_optimizer
        import position_history
        from urllib.parse import urlsplit
        from playwright.sync_api import expect
        for mode in ['new','edit']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'original-expiry.sqlite3'
                raw=dict(account='RRSP',symbol='RKLB',shares=1000,call_contracts=10,call_expiry='2028-01-21',call_strike_native_currency=25)
                current=positions.synchronize([raw],path)[0];pid=current['position_id']
                original=dict(expiry='2025-03-21',strike=24,contracts=10,settlement_date='2025-03-04',price_usd=.8,reviewed=True,historical_opening=True)
                if mode=='edit': positions.save_opening(pid,original,path=path)
                def api(route):
                    request=route.request;endpoint=urlsplit(request.url).path.removeprefix('/api/')
                    saved=positions.history(pid,path)
                    if endpoint=='exit-optimizer/holdings':route.fulfill(json={'holdings':[saved['position']]});return
                    if endpoint=='exit-optimizer/capture':
                        data=capture();data['inputs'].update(account='RRSP',symbol='RKLB',position_id=pid,shares=1000,contracts=10)
                        ref=position_history.resolve('RRSP','RKLB',dict(expiry='2028-01-21',strike=25),10,[saved['opening']] if saved['opening'] else [],saved['rollovers'])
                        ref.update(positions.prior_realized(pid,path),stock_total_usd=21000,stock_cost_usd=21000,stock_price_usd=21)
                        data['inputs']['opening_reference']=ref
                        exit_optimizer.model.apply_accounting(data['inputs'],data['result'])
                        route.fulfill(json=data);return
                    if endpoint==f'positions/{pid}/history':route.fulfill(json=saved);return
                    if endpoint in [f'positions/{pid}/opening',f'positions/{pid}/opening/edit']:
                        body=request.post_data_json;self.posts.append((endpoint,body))
                        result=positions.save_opening(pid,body,edit=endpoint.endswith('/edit'),path=path)
                        route.fulfill(status=201,json=result);return
                    if endpoint=='option-expirations':route.fulfill(json={'expirations':positions.expirations(path)});return
                    self.api(route)
                self.context.unroute('**/api/**');self.context.route('**/api/**',api)
                self.open_dashboard()
                expect(self.page.locator('#realized-cash-summary > strong')).to_have_text('History incomplete')
                self.page.get_by_role('button',name='Transactions',exact=True).click()
                modal=self.page.get_by_role('dialog',name='Transactions',exact=True)
                modal.get_by_role('tab',name='Option Opening Sale',exact=True).click()
                panel=modal.get_by_role('tabpanel',name='Option Opening Sale',exact=True)
                if mode=='edit':
                    panel.get_by_role('button',name='Edit',exact=True).click()
                    confirmation='I verified the corrected sale against my confirmation.'
                    save='Save changes'
                else:
                    for label,value in [('Original call expiry','2025-03-21'),('Original strike (USD)','24'),('Settlement date','2025-03-04'),('Premium sold (USD/share)','.8')]:
                        panel.get_by_label(label,exact=True).fill(value)
                    confirmation='I verified the opening sale against my confirmation.'
                    save='Save opening premium'
                panel.get_by_role('checkbox',name='This original call expired worthless, with no buyback or assignment; I retained the shares.',exact=True).check()
                panel.get_by_label('Original call expiration fees (USD)',exact=True).fill('10')
                panel.get_by_text('Recorded realized P/L: US$790.00.',exact=False).wait_for()
                panel.get_by_role('checkbox',name=confirmation,exact=True).check()
                panel.get_by_role('button',name=save,exact=True).click()
                panel.get_by_text('Original call recorded as expired worthless.',exact=False).wait_for()
                expect(panel.get_by_label('Original call expiry',exact=True)).to_have_value('2028-01-21')
                self.assertIsNone(positions.history(pid,path)['opening'])
                self.assertEqual(positions.history(pid,path)['position']['position_revision'],current['position_revision'])
                modal.get_by_role('button',name='Close transactions',exact=True).click()
                expect(self.page.locator('#realized-cash-summary > strong')).to_have_text('History incomplete')
                self.assertEqual(positions.prior_realized(pid,path)['prior_realized_option_usd'],790)
                self.assertEqual(self.page.locator('#chart rect[data-pnl]').count(),0)
                self.assertIn('Total P/L unavailable',self.page.locator('#chart').inner_text())
                self.assertEqual(self.page.get_by_label('Holding',exact=True).locator('option').count(),1)
                self.assertEqual(positions.availability({('RRSP','RKLB'):1000},path)[0]['available_shares'],0)

    def test_worthless_expiry_from_dashboard_and_recorded_rollover(self):
        for entry in ['dashboard','rollover']:
            with self.subTest(entry=entry):
                expired=[]
                h=dict(account='RRSP',symbol='RKLB',shares=100,call_contracts=1,call_expiry='2026-10-23',call_strike_native_currency=25,position_id='c'*32,position_key='c'*32,position_revision='revision-1',can_mark_expired=True)
                retained=dict(h,call_contracts=0,call_expiry='',call_strike_native_currency=0,position_id='d'*32,position_key='d'*32,position_revision='stock-only',can_mark_expired=False,retained_from_position_id=h['position_id'])
                opening=dict(account='RRSP',symbol='RKLB',expiry='2026-09-18',strike=20,contracts=1,settlement_date='2026-08-01',price_usd=1,id=h['position_id'])
                roll=dict(id='roll-1',account='RRSP',symbol='RKLB',settlement_date='2026-09-01',contracts=1,buyback_expiry='2026-09-18',buyback_strike=20,buyback_total_usd=110,sale_expiry='2026-10-23',sale_strike=25,sale_total_usd=200,fees_usd=10,net_cash_usd=80)
                def api(route):
                    from urllib.parse import urlsplit
                    path=urlsplit(route.request.url).path.removeprefix('/api/')
                    if path=='exit-optimizer/holdings': route.fulfill(json={'holdings':[retained] if expired else [h]});return
                    if path=='exit-optimizer/capture':
                        data=capture();data['inputs'].update(account='RRSP',symbol='RKLB',position_id=h['position_id']);route.fulfill(json=data);return
                    if path=='positions/availability':
                        route.fulfill(json={'stocks':[dict(account='RRSP',symbol='RKLB',total_shares=100,allocated_shares=0 if expired else 100,available_shares=100 if expired else 0)]});return
                    if path.endswith('/history') and path.startswith('positions/'):
                        stock=path.split('/')[1]==retained['position_id']
                        route.fulfill(json={'position':retained if stock else h,'opening':None if stock else opening,'rollovers':[] if stock else [roll]});return
                    if path.endswith('/expiration-preview'):
                        route.fulfill(json={'position':h,'historical_option_net_usd':180,'can_mark_expired':True,'accounting':{'history_status':'linked'}});return
                    if path.endswith('/expire-worthless'):
                        body=route.request.post_data_json;self.posts.append((path,body))
                        record=dict(id=h['position_id'],position_id=h['position_id'],account='RRSP',symbol='RKLB',expiry='2026-10-23',strike=25,contracts=1,shares_retained=100,fees_usd=body['fees_usd'],cash_flow_usd=-body['fees_usd'],realized_option_pl_usd=180-body['fees_usd'],retained_position=retained)
                        expired.append(record);route.fulfill(json=record);return
                    if path=='option-expirations': route.fulfill(json={'expirations':expired});return
                    if path.endswith('/transactions'):
                        entries=[] if not expired else [dict(id='expired-sale',date='2026-09-01',action='Sell',instrument='Call',expiry='2026-10-23',strike=25,quantity=1,unit='contracts',price_usd=1.8,gross_usd=180,fees_usd=5,outcome='Expired worthless',expired=True,realized_pl_usd=175)]
                        route.fulfill(json=dict(account='RRSP',symbol='RKLB',entries=entries,realized_option_pl_usd=175 if expired else 0,net_option_cash_usd=175 if expired else 0,open_call_premium_usd=0,history_complete=True,note='Synthetic report.'));return
                    self.api(route)
                self.context.unroute('**/api/**');self.context.route('**/api/**',api)
                self.page.goto(self.base+'/covered-call-optimizer')
                self.page.get_by_text('Historical call recorded.',exact=False).wait_for()
                if entry=='rollover':
                    self.page.get_by_role('button',name='Transactions',exact=True).click()
                    transactions=self.page.get_by_role('dialog',name='Transactions',exact=True)
                    transactions.get_by_role('tab',name='Rollover',exact=True).click()
                    transactions.get_by_role('tabpanel',name='Rollover',exact=True).get_by_role('button',name='Expired worthless',exact=True).click()
                else:
                    self.page.get_by_role('button',name='Expired worthless',exact=True).click()
                modal=self.page.get_by_role('dialog',name='Expired worthless',exact=True)
                modal.get_by_label('Expiration fees (USD)',exact=True).fill('5')
                modal.get_by_text('US$175.00',exact=True).wait_for()
                modal.get_by_role('checkbox').check()
                modal.get_by_role('button',name='Record worthless expiry',exact=True).click()
                self.page.get_by_text('100 shares retained.',exact=False).wait_for()
                if entry=='rollover': self.page.get_by_role('button',name='Close transactions',exact=True).click()
                self.assertEqual(self.page.get_by_role('heading',name='Shares available for new calls',exact=True).count(),0)
                from playwright.sync_api import expect
                expect(self.page.get_by_label('Holding',exact=True).locator('option')).to_have_count(1)
                expect(self.page.get_by_label('Holding',exact=True)).to_contain_text('Stock only')
                self.assertEqual(self.page.get_by_role('heading',name='Closed holdings',exact=True).count(),0)
                self.assertEqual(expired[0]['realized_option_pl_usd'],175)
                self.page.get_by_role('button',name='Transactions',exact=True).click()
                report=self.page.locator('.transaction-report')
                expired_row=report.get_by_role('row').filter(has=self.page.get_by_role('cell',name='Expired worthless',exact=True))
                expired_row.get_by_role('cell',name='US$175.00',exact=True).wait_for()
                expect(expired_row).to_have_count(1)
                expect(expired_row.get_by_role('cell',name='Sell',exact=True)).to_be_visible()
                expect(expired_row.get_by_role('cell',name='US$180.00',exact=True)).to_be_visible()
                expect(expired_row.get_by_role('cell',name='US$5.00',exact=True)).to_be_visible()
                self.assertEqual(report.get_by_role('cell',name='Expiry',exact=True).count(),0)
                self.assertEqual(self.page.get_by_text('Expired option history',exact=True).count(),0)
                self.page.get_by_role('button',name='Close transactions',exact=True).click()
        requests=[(path,body) for path,body in self.posts if path.endswith('/expire-worthless')]
        self.assertEqual(len(requests),2)
        self.assertTrue(all(body['reviewed'] and body['fees_usd']==5 for path,body in requests))
        self.assertFalse(any(path=='closed-holdings' for path,body in self.posts))

    def test_pnl_bar_shows_total_and_close_today_profit_prominently(self):
        from playwright.sync_api import expect
        data=capture()
        for row in data['result']['rows']:
            row.update(realized_pl_usd=-19172.85,unrealized_pl_usd=28469.95,total_pl_usd=9297.10)
            if row.get('expire_worthless'):
                row['expire_worthless'].update(realized_pl_usd=100,unrealized_pl_usd=-150,total_pl_usd=-50)
        today=data['result']['rows'][0]
        today.update(mean=20110,cash_flows=dict(stock_sale=60000,option_purchase=-39890,option_sale=0))
        data['result']['baseline']=20110
        data['inputs']['opening_reference'].update(historical_option_net_usd=8092.15,prior_realized_option_usd=2560,stock_cost_usd=21465.05)
        self.context.route('**/api/exit-optimizer/capture?*',lambda route:route.fulfill(json=data))
        self.open_dashboard()
        expect(self.page.locator('#close-today-summary > p > strong')).to_have_text('US$9,297.10')
        expect(self.page.locator('#close-today-summary')).to_contain_text('US$10,652.15')
        self.assertEqual(self.page.locator('#chart rect[data-pnl="realized"]').count(),0)
        self.assertEqual(self.page.locator('#chart rect[data-pnl="unrealized"]').count(),0)
        group=self.page.locator('#chart g[role="group"]').nth(1)
        bar=group.locator('rect[data-pnl="total"]')
        expect(bar).to_have_count(1)
        self.assertAlmostEqual(float(bar.get_attribute('data-value')),9297.10)
        zero=float(self.page.locator('#chart line[stroke="#7e8c9e"]').get_attribute('y1'))
        self.assertLess(float(bar.get_attribute('y')),zero)
        self.assertAlmostEqual(float(bar.get_attribute('y'))+float(bar.get_attribute('height')),zero,places=5)
        bar.hover()
        expect(self.page.locator('#chart-detail')).to_have_text('Net full-position P/L: US$9,297.10')
        self.assertIn('Full-position P/L US$9,297.10',group.get_attribute('aria-label'))
        self.page.get_by_role('radio',name='Expire',exact=True).first.check()
        bar=group.locator('rect[data-pnl="total"]')
        expect(bar).to_have_attribute('data-value','-50')
        zero=float(self.page.locator('#chart line[stroke="#7e8c9e"]').get_attribute('y1'))
        self.assertAlmostEqual(float(bar.get_attribute('y')),zero,places=5)
        self.assertGreater(float(bar.get_attribute('height')),0)
        bar.focus()
        expect(self.page.locator('#chart-detail')).to_have_text('Net option-only P/L: -US$50.00')
        expect(self.page.locator('#close-today-summary > p > strong')).to_have_text('US$9,297.10')
        self.page.get_by_role('radio',name='Close',exact=True).first.check()
        self.page.screenshot(path=str(ROOT/'reports/net-pnl-chart-desktop.png'),full_page=True)
        self.page.set_viewport_size(dict(width=390,height=844))
        expect(self.page.locator('#close-today-summary > p > strong')).to_be_visible()
        self.page.screenshot(path=str(ROOT/'reports/net-pnl-chart-mobile.png'),full_page=True)

    def test_net_pnl_zero_and_missing_history_are_not_faked(self):
        from playwright.sync_api import expect
        data=capture()
        for row in data['result']['rows']:
            row.update(realized_pl_usd=-100,unrealized_pl_usd=100,total_pl_usd=0)
        self.context.route('**/api/exit-optimizer/capture?*',lambda route:route.fulfill(json=data))
        self.open_dashboard()
        bars=self.page.locator('#chart rect[data-pnl="total"]')
        expect(bars).to_have_count(4)
        expect(bars.first).to_have_attribute('height','0')
        bars.first.focus()
        expect(self.page.locator('#chart-detail')).to_have_text('Net full-position P/L: US$0.00')
        for row in data['result']['rows']:row['total_pl_usd']=None
        self.open_dashboard()
        expect(self.page.locator('#chart rect[data-pnl]')).to_have_count(0)
        expect(self.page.locator('#close-today-summary > p > strong')).to_contain_text('Unavailable')
        self.assertIn('Total P/L unavailable',self.page.locator('#chart').inner_text())

    def test_cash_summary_is_independent_of_closed_call_components(self):
        from playwright.sync_api import expect
        data=capture()
        data['inputs']['opening_reference']['option_total_usd']=999999
        self.context.route('**/api/exit-optimizer/capture?*',lambda route:route.fulfill(json=data))
        for value,incomplete,label in [(0,False,'US$0.00'),(-50,False,'-US$50.00'),(0,True,'History incomplete')]:
            with self.subTest(value=value,incomplete=incomplete):
                data['inputs']['opening_reference'].update(history_status='incomplete' if incomplete else 'linked',historical_option_net_usd=None if incomplete else 8092.15,prior_realized_option_usd=2560)
                for row in data['result']['rows']:
                    row.update(realized_pl_usd=value,unrealized_pl_usd=300,total_pl_usd=value+300)
                self.open_dashboard()
                expect(self.page.locator('#realized-cash-summary > strong')).to_have_text('History incomplete' if incomplete else 'US$10,652.15')
                self.assertEqual(self.page.locator('#realized-pl-summary').count(),0)
                self.assertNotIn('Original option sale premium',self.page.locator('#opening-reference').inner_text())
                self.assertEqual(self.page.locator('#chart line[stroke-dasharray="7 5"]').count(),0)
                # A stored original premium no longer controls the chart scale.
                ticks=self.page.locator('#chart svg > g > text').all_text_contents()
                self.assertTrue(all(abs(float(text.replace('US$','').replace(',',''))) < 10000 for text in ticks))

    def test_closed_report_has_own_view_and_return_preserves_simulation(self):
        self.open_dashboard()
        self.page.locator('#results').wait_for()
        self.page.get_by_role('button', name='Closed holdings', exact=True).click()
        self.page.get_by_role('heading', name='Closed holdings', exact=True).wait_for()
        self.assertEqual(self.page.locator('#results').count(), 0)
        self.assertEqual(self.page.get_by_label('Holding', exact=True).count(), 0)
        self.assertEqual(self.page.get_by_role('button', name='Recommendation', exact=True).count(), 0)
        self.page.get_by_role('button', name='Back to active holdings', exact=True).click()
        self.page.locator('#results').wait_for()
        self.assertEqual(self.page.get_by_label('Holding', exact=True).locator('option').count(), 1)

    def test_close_modal_report_and_persisted_dropdown_removal(self):
        self.open_dashboard()
        self.page.get_by_role('slider').fill('25')
        self.page.get_by_text('Close today remains fixed at captured quotes. Synthetic scenario.').wait_for()
        self.page.get_by_role('button', name='Close', exact=True).click()
        self.page.get_by_role('button', name='Cancel', exact=True).click()
        self.assertEqual(self.page.get_by_label('Holding', exact=True).locator('option').count(), 1)
        self.page.get_by_role('button', name='Close', exact=True).click()
        modal=self.page.get_by_role('dialog', name='Close holding')
        self.assertEqual(modal.get_by_label('Stock bid (USD/share)', exact=True).input_value(), '22')
        self.assertEqual(modal.get_by_label('Stock ask (USD/share)', exact=True).input_value(), '24')
        self.assertEqual(modal.get_by_label('Held call bid (USD/share)', exact=True).input_value(), '0.9')
        self.assertEqual(modal.get_by_label('Held call ask (USD/share)', exact=True).input_value(), '1')
        self.assertTrue(modal.get_by_label('Held call ask (USD/share)', exact=True).evaluate('(el) => el.readOnly'))
        self.assertEqual(modal.get_by_label('Call buyback price (USD/share)', exact=True).input_value(), '')
        modal.get_by_label('Close date', exact=True).fill('2026-10-27')
        modal.get_by_label('Stock sale price (USD/share)', exact=True).fill('30')
        modal.get_by_label('Call buyback price (USD/share)', exact=True).fill('2')
        modal.get_by_label('Total closing fees (USD)', exact=True).fill('5')
        modal.get_by_role('checkbox').check()
        modal.get_by_role('button', name='Record close', exact=True).click()
        self.page.get_by_role('heading', name='Closed holdings', exact=True).wait_for()
        self.page.get_by_text('US$995.00', exact=True).wait_for()
        self.assertEqual(self.page.get_by_label('Holding', exact=True).locator('option').count(), 0)
        self.assertEqual(self.page.locator('#results').count(), 0)
        self.assertEqual(self.page.get_by_role('button', name='Close', exact=True).count(), 0)
        self.page.get_by_text('Quote comparison', exact=True).click()
        self.page.get_by_text('Stock bid / ask: US$22.00 / US$24.00', exact=False).wait_for()
        self.page.get_by_role('button', name='Back to active holdings', exact=True).click()
        self.assertTrue(self.page.get_by_role('button', name='Close', exact=True).is_disabled())
        submitted=next(body for path, body in self.posts if path == 'closed-holdings')
        self.assertEqual(submitted['position_key'], 'test-position')
        self.assertEqual(submitted['stock_price_usd'], 30)
        self.assertEqual(submitted['buyback_price_usd'], 2)
        self.assertEqual(submitted['quote_captured_at'], '2026-10-21T12:00:00Z')
        self.page.reload()
        self.page.get_by_text('No active holdings. Use New to start with a stock purchase.').wait_for()
        self.page.get_by_role('button', name='Closed holdings', exact=True).click()
        self.page.get_by_text('US$995.00', exact=True).wait_for()
        self.assertEqual(self.page.get_by_label('Holding', exact=True).locator('option').count(), 0)

    def test_historical_closes_are_distinct_from_captured_bid_ask(self):
        self.open_dashboard()
        self.closed_records=[dict(id=1,close_date='2026-10-26',account='RRSP',symbol='ASTS',
            shares=500,contracts=5,expiry='2028-01-21',strike=40,stock_sale_usd=20000,
            stock_price_usd=40,buyback_total_usd=7955,buyback_price_usd=15.91,
            fees_usd=20.15,closing_cash_usd=12024.85,realized_pl_usd=20710.63,
            accounting=dict(historical_close_reference=dict(date='2026-10-26',
                stock=dict(close=39.45),held=dict(close=15.75))))]
        self.page.get_by_role('button',name='Closed holdings',exact=True).click()
        self.page.get_by_text('Historical closes',exact=True).click()
        reference=self.page.locator('#closed-holdings-report details').first
        self.assertIn('Stock close: US$39.45',reference.inner_text())
        self.assertIn('Held call close: US$15.75',reference.inner_text())
        self.assertIn('historical bid/ask unavailable',reference.inner_text())
        self.assertEqual(self.page.get_by_text('Quote comparison',exact=True).count(),0)
        self.page.get_by_text('US$20,710.63',exact=True).wait_for()

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
        self.assertIn('Net cash US$2,100.00', self.page.locator('#chart g[role="group"]').first.get_attribute('aria-label'))
        self.context.route('**/api/exit-optimizer/scenario', lambda route: route.fulfill(status=502, json={'error': 'Synthetic scenario failure.'}))
        self.page.get_by_role('slider').fill('25')
        self.page.get_by_text('Chart retains its previous result: Synthetic scenario failure.').wait_for()
        self.page.get_by_role('button', name='Recommendation', exact=True).click()
        self.assertFalse(self.page.get_by_role('button', name='Generate recommendation').is_enabled())
        self.page.get_by_role('button', name='Reset to current quote').click()
        self.assertTrue(self.page.get_by_role('button', name='Generate recommendation').is_enabled())

    def test_refresh_failure_mentions_retained_results_once_and_only_if_present(self):
        self.open_dashboard()
        self.context.route('**/api/exit-optimizer/run',lambda route:route.fulfill(status=503,json={'error':'Questrade is not configured. Previous results retained. Previous results retained.'}))
        self.page.get_by_role('button',name='Refresh data & analyze',exact=True).click()
        self.page.get_by_text('Questrade is not configured. Previous results retained.',exact=True).wait_for()
        self.assertEqual(self.page.locator('#status').inner_text().count('Previous results retained.'),1)
        self.context.route('**/api/exit-optimizer/capture?*',lambda route:route.fulfill(status=404,json={'error':'No saved analysis.'}))
        self.page.reload()
        self.page.get_by_text('No saved analysis for this holding. Refresh data & analyze to begin.',exact=True).wait_for()
        self.page.get_by_role('button',name='Refresh data & analyze',exact=True).click()
        self.page.get_by_text('Questrade is not configured.',exact=True).wait_for()
        self.assertNotIn('Previous results retained',self.page.locator('#status').inner_text())

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
        self.assertIn('Net cash US$2,100.00', self.page.locator('#chart g[role="group"]').first.get_attribute('aria-label'))
        (ROOT/'reports').mkdir(exist_ok=True)
        self.page.screenshot(path=str(ROOT/'reports/react-dashboard-desktop.png'), full_page=True)
        self.page.set_viewport_size(dict(width=390, height=844))
        self.assertTrue(self.page.get_by_role('button', name='Refresh data & analyze').is_visible())
        self.page.screenshot(path=str(ROOT/'reports/react-dashboard-mobile.png'), full_page=True)


if __name__ == '__main__':
    unittest.main()
