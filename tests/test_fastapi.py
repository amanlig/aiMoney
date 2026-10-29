"""API contracts with synthetic data: no broker, Yahoo or OpenAI calls."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dashboard_server as server


class ApiContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'reports').mkdir()
        (self.root/'data').mkdir()
        (self.root/'frontend/dist/src').mkdir(parents=True)
        (self.root/'frontend/dist/index.html').write_text('<div id="root"></div>')
        (self.root/'frontend/dist/src/main.js').write_text('/* synthetic React build */')
        self.patch = patch.object(server, 'ROOT', self.root)
        self.patch.start()
        self.client = TestClient(server.create_app(refresh_macro=False), base_url='http://localhost:8765')
        self.client.__enter__()
        self.origin = {'Origin': 'http://localhost:8765'}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.patch.stop()
        self.temp.cleanup()

    def post(self, path, body):
        return self.client.post(path, json=body, headers=self.origin)

    def test_react_routes_health_and_openapi(self):
        for path in ['/', '/index.html', '/covered-call-optimizer']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn('id="root"', response.text)
        self.assertEqual(self.client.get('/api/health').json()['status'], 'ok')
        schema = self.client.get('/openapi.json').json()
        self.assertIn('/api/exit-optimizer/scenario', schema['paths'])
        self.assertIn('ScenarioRequest', schema['components']['schemas'])
        self.assertEqual(self.client.get('/frontend/dist/src/main.js').status_code, 200)
        self.assertEqual(self.client.get('/equity-chart.html', follow_redirects=False).headers['location'], '/covered-call-optimizer')

    def test_private_files_and_removed_html_are_not_served(self):
        (self.root/'reports/private.json').write_text('{"private":true}')
        for path in ['/covered-call-optimizer.html', '/private.json', '/reports/private.json', '/.secrets/openai.json',
                     '/data/fx-samples.sqlite3', '/frontend/src/App.js', '/frontend/dist/vendor/.secrets']:
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_saved_capture_only_reads_requested_snapshot(self):
        payload = {'inputs': {'symbol': 'TEST'}, 'result': {'test': 1}}
        (self.root/'reports/exit-optimizer-rrsp-test.json').write_text(json.dumps(payload))
        with patch.object(server.exit_optimizer, 'run') as run:
            self.assertEqual(self.client.get('/api/exit-optimizer/capture?account=RRSP&symbol=TEST').json(), payload)
            self.assertEqual(self.client.get('/api/exit-optimizer/capture?account=RRSP&symbol=MISSING').status_code, 404)
            self.assertEqual(self.client.get('/api/exit-optimizer/capture?account=RRSP&symbol=../secret').status_code, 422)
            run.assert_not_called()

    def test_writes_require_local_matching_origin(self):
        with patch.object(server.exit_optimizer, 'run') as run:
            for origin in [None, 'https://evil.example', 'http://localhost:9999']:
                response = self.client.post('/api/exit-optimizer/run', json={}, headers={'Origin': origin} if origin else {})
                self.assertEqual(response.status_code, 403)
                self.assertIn('error', response.json())
            run.assert_not_called()

    def test_validation_and_actual_body_size_precede_service_calls(self):
        with patch.object(server.exit_optimizer, 'scenario') as scenario:
            for body in [{'account': 'RRSP', 'symbol': 'TEST', 'stock_price': -1},
                         {'account': 'RRSP', 'symbol': 'TEST', 'stock_price': True},
                         {'account': 'INVALID', 'symbol': 'TEST', 'stock_price': 20}]:
                self.assertEqual(self.post('/api/exit-optimizer/scenario', body).status_code, 422)
            malformed = self.client.post('/api/exit-optimizer/scenario', content='{', headers=self.origin)
            self.assertEqual(malformed.status_code, 422)
            oversized = self.client.post('/api/exit-optimizer/scenario', content=iter([b'x'*1500, b'x'*1500]), headers=self.origin)
            self.assertEqual(oversized.status_code, 413)
            scenario.assert_not_called()

    def test_scenarios_use_adapter_and_release_lock_on_failure(self):
        body = {'account': 'RRSP', 'symbol': 'TEST', 'stock_price': 25}
        with patch.object(server.exit_optimizer, 'scenario', return_value={'result': {'mean': 42}}) as scenario:
            self.assertEqual(self.post('/api/exit-optimizer/scenario', body).json()['result']['mean'], 42)
            scenario.assert_called_once_with(body)
        with patch.object(server.exit_optimizer, 'scenario', side_effect=RuntimeError('private failure')):
            response = self.post('/api/exit-optimizer/scenario', body)
            self.assertEqual(response.status_code, 502)
            self.assertNotIn('private failure', response.text)
        self.assertFalse(server.ROLL_REFRESH_LOCK.locked())
        server.ROLL_REFRESH_LOCK.acquire()
        try:
            self.assertEqual(self.post('/api/exit-optimizer/scenario', body).status_code, 409)
        finally:
            server.ROLL_REFRESH_LOCK.release()

    def test_basis_roundtrip_uses_sqlite_service(self):
        path = self.root/'data/test.sqlite3'
        original_save = server.stock_basis.save_many
        original_records = server.stock_basis.records
        with patch.object(server.stock_basis, 'save_many', side_effect=lambda rows: original_save(rows, path)), \
             patch.object(server.stock_basis, 'records', side_effect=lambda _path=path: original_records(_path)):
            body = {'bases': [{'account':'RRSP','currency':'CAD','symbol':'TEST','quantity':100,'totalCost':5000}]}
            response = self.post('/api/stock-cost-basis', body)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.client.get('/api/stock-cost-basis').json()['bases'][0]['averageCost'], 50)

    def test_premium_and_sample_routes_preserve_response_contracts(self):
        for path, module, save, read, key in [
            ('/api/option-premiums', server.option_premiums, 'save', 'records', 'premiums'),
            ('/api/option-premiums/usd', server.option_premiums, 'save_usd', 'usd_records', 'premiums'),
            ('/api/fx-samples', server.fx_samples, 'save', 'records', 'samples')]:
            with patch.object(module, save, return_value={'id':1}) as write, patch.object(module, read, return_value=[{'id':1}]):
                response = self.post(path, {'reviewed':True})
                self.assertEqual(response.status_code, 201)
                write.assert_called_once_with({'reviewed':True})
                self.assertEqual(self.client.get(path).json(), {key:[{'id':1}]})

    def test_ocr_delete_and_roll_routes(self):
        with patch.object(server.fx_samples, 'ocr', return_value={'fields':{}}) as ocr:
            response = self.client.post('/api/fx-samples/ocr', content=b'synthetic image', headers=self.origin)
            self.assertEqual(response.status_code, 200)
            ocr.assert_called_once_with(b'synthetic image')
        path = self.root/'data/test.sqlite3'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE samples (id INTEGER)')
            db.execute('INSERT INTO samples VALUES (1)')
        with patch.object(server.fx_samples, 'connect', side_effect=lambda: sqlite3.connect(path)):
            self.assertEqual(self.post('/api/fx-samples/delete', {'id':1}).json(), {'deleted':1})
        report = self.root/'reports/roll.json'; report.write_text('{"candidates":[]}')
        with patch.object(server.subprocess, 'run') as run, patch.object(server, 'output_path', return_value=report):
            self.assertEqual(self.post('/api/roll-candidates/refresh', {}).json(), {'candidates':[]})
            run.assert_called_once()

    def test_recommendations_status_history_and_failure(self):
        body = dict(account='RRSP', symbol='TEST', stock_price=25, goal='keep_exposure', captured_at='synthetic', modes={})
        with patch.object(server.optimizer_assessments, 'status', return_value={'configured':True,'model':'synthetic'}):
            self.assertTrue(self.client.get('/api/optimizer-recommendations/status').json()['configured'])
        with patch.object(server.optimizer_assessments, 'history', return_value=[{'id':1}]):
            self.assertEqual(self.client.get('/api/optimizer-recommendations/history').json(), {'runs':[{'id':1}]})
        with patch.object(server.optimizer_recommendations, 'generate', return_value={'assessment':'synthetic'}) as generate:
            self.assertEqual(self.post('/api/optimizer-recommendations', body).json()['assessment'], 'synthetic')
            generate.assert_called_once_with(body)
        with patch.object(server.optimizer_recommendations, 'generate', side_effect=server.optimizer_assessments.AssessmentError('OpenAI connection failed.')):
            self.assertEqual(self.post('/api/optimizer-recommendations', body).status_code, 502)
        self.assertFalse(server.ASSESSMENT_LOCK.locked())

    def test_macro_worker_is_started_and_stopped_by_lifespan(self):
        with patch.object(server.MacroFeed, 'run') as run:
            app = server.create_app()
            with TestClient(app) as client:
                self.assertEqual(client.get('/api/macro').status_code, 200)
            run.assert_called_once()
            self.assertTrue(app.state.feed.stop.is_set())

    def test_stock_first_creation_and_confirmed_deletion(self):
        from database import connect
        path=self.root/'holding-records.sqlite3'
        with patch.object(server.exit_optimizer,'source_holdings',return_value=[]), \
             patch.object(server.closed_holdings,'records',return_value=[]), \
             patch.object(server.covered_positions,'connect',side_effect=lambda unused=None:connect(path)):
            body=dict(account='RRSP',symbol='NEW',purchase_date='2025-01-02',shares=100,price_usd=20,fees_usd=1)
            response=self.post('/api/holdings',body)
            self.assertEqual(response.status_code,201,response.text)
            h=response.json();self.assertEqual(h['call_contracts'],0)
            self.assertEqual(self.client.get('/api/exit-optimizer/holdings').json()['holdings'][0]['position_id'],h['position_id'])
            root=f"/api/positions/{h['position_id']}"
            report=self.client.get(root+'/transactions')
            self.assertEqual(report.status_code,200,report.text)
            self.assertEqual(report.json()['entries'][0]['action'],'Buy')
            self.assertEqual(report.json()['realized_option_pl_usd'],0)
            self.assertEqual(self.client.get(root+'/delete-preview').status_code,200)
            self.assertEqual(self.post(root+'/delete',dict(confirmed=False,position_revision=h['position_revision'])).status_code,400)
            response=self.post(root+'/opening',dict(expiry='2028-01-21',strike=25,contracts=1,settlement_date='2025-01-03',price_usd=2,reviewed=True))
            self.assertEqual(response.status_code,201,response.text)
            self.assertEqual(self.post(root+'/delete',dict(confirmed=True,position_revision=h['position_revision'])).status_code,400)
            current=self.client.get(root+'/history').json()['position']
            response=self.post(root+'/delete',dict(confirmed=True,position_revision=current['position_revision']))
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(self.client.get('/api/exit-optimizer/holdings').json()['holdings'],[])
            self.assertEqual(self.post('/api/holdings',dict(body,shares=-1)).status_code,400)

    def test_multiple_positions_opening_rule_and_independent_close(self):
        from database import connect
        import covered_positions
        import closed_holdings
        path=self.root/'positions.sqlite3'
        raw=dict(account='RRSP',symbol='RKLB',shares=1000,call_contracts=10,call_expiry='2028-01-21',call_strike_native_currency=20)
        original_records=closed_holdings.records
        with patch.object(server.exit_optimizer,'source_holdings',return_value=[raw]), \
             patch.object(server.exit_optimizer,'inventory',return_value={('RRSP','RKLB'):2000}), \
             patch.object(covered_positions,'connect',side_effect=lambda unused=None:connect(path)), \
             patch.object(closed_holdings,'records',side_effect=lambda:original_records(path)), \
             patch.object(server.stock_basis,'get',return_value=dict(priceUsd=20,feesUsd=0,quantity=2000)):
            january=self.client.get('/api/exit-optimizer/holdings').json()['holdings'][0]
            response=self.post('/api/positions',dict(account='RRSP',symbol='RKLB',shares=1000,contracts=10,strike=20,expiry='2028-02-18'))
            self.assertEqual(response.status_code,201,response.text)
            february=response.json()
            first=dict(expiry='2028-01-21',strike=20,contracts=10,settlement_date='2026-10-01',price_usd=3,reviewed=True)
            self.assertEqual(self.post(f"/api/positions/{january['position_id']}/opening",first).status_code,201)
            self.assertEqual(self.post(f"/api/positions/{january['position_id']}/opening",dict(first,settlement_date='2026-10-02')).status_code,400)
            self.assertEqual(self.post(f"/api/positions/{february['position_id']}/opening",dict(first,expiry='2028-02-18',price_usd=4)).status_code,201)
            self.assertEqual(self.post('/api/exit-optimizer/scenario',dict(account='RRSP',symbol='RKLB',stock_price=40)).status_code,400)
            close=dict(account='RRSP',symbol='RKLB',position_key=january['position_key'],position_revision=january['position_revision'],close_date='2026-10-27',stock_price_usd=40,buyback_price_usd=2,fees_usd=5,reviewed=True)
            captured_at='2026-10-27T12:00:00Z'
            data=dict(account='RRSP',symbol='RKLB',position_id=january['position_id'],
                      shares=1000,contracts=10,captured_at=captured_at,
                      held=dict(expiry='2028-01-21',strike=20,bidPrice=1.9,askPrice=2.1),
                      stock=dict(bidPrice=39.9,askPrice=40.1))
            target=self.root/'reports'/f"exit-optimizer-rrsp-rklb-{january['position_id']}.json"
            target.write_text(json.dumps(dict(inputs=data)))
            close.update(quote_captured_at='obsolete',quote_snapshot=dict(stock=dict(bidPrice=999)))
            with patch.object(server.exit_optimizer,'ROOT',self.root):
                self.assertEqual(self.post('/api/closed-holdings',close).status_code,400)
                self.assertEqual(self.client.get('/api/closed-holdings').json()['holdings'],[])
                close['quote_captured_at']=captured_at
                response=self.post('/api/closed-holdings',close)
            self.assertEqual(response.status_code,201,response.text)
            self.assertEqual(response.json()['quote_snapshot']['stock']['bidPrice'],39.9)
            self.assertEqual(response.json()['quote_snapshot']['captured_at'],captured_at)
            target.unlink()
            saved_close=self.client.get('/api/closed-holdings').json()['holdings'][0]
            self.assertEqual(saved_close['quote_snapshot']['held']['askPrice'],2.1)
            self.assertEqual(response.json()['realized_pl_usd'],20995)
            active=self.client.get('/api/exit-optimizer/holdings').json()['holdings']
            self.assertEqual([h['position_id'] for h in active],[february['position_id']])
            saved=self.client.get(f"/api/positions/{february['position_id']}/history").json()
            self.assertEqual(saved['opening']['price_usd'],4)
            self.assertEqual(self.client.get('/api/closed-holdings').json()['holdings'][0]['position']['position_id'],january['position_id'])

    def test_worthless_expiry_retains_stock_and_allows_a_new_call(self):
        from database import connect
        import covered_positions
        import closed_holdings
        path=self.root/'expiration.sqlite3'
        raw=dict(account='RRSP',symbol='RKLB',shares=1000,call_contracts=10,call_expiry='2026-10-23',call_strike_native_currency=20)
        original_records=closed_holdings.records
        with patch.object(server.exit_optimizer,'source_holdings',return_value=[raw]), \
             patch.object(server.exit_optimizer,'inventory',return_value={('RRSP','RKLB'):1000}), \
             patch.object(covered_positions,'connect',side_effect=lambda unused=None:connect(path)), \
             patch.object(closed_holdings,'records',side_effect=lambda:original_records(path)):
            h=self.client.get('/api/exit-optimizer/holdings').json()['holdings'][0]
            root=f"/api/positions/{h['position_id']}"
            opening=dict(expiry='2026-10-23',strike=20,contracts=10,settlement_date='2026-10-01',price_usd=3,reviewed=True)
            self.assertEqual(self.post(root+'/opening',opening).status_code,201)
            self.assertEqual(self.client.get(root+'/expiration-preview').json()['historical_option_net_usd'],3000)
            body=dict(fees_usd=2,reviewed=True,position_revision=h['position_revision'])
            self.assertEqual(self.post(root+'/expire-worthless',dict(body,reviewed=False)).status_code,400)
            response=self.post(root+'/expire-worthless',body)
            self.assertEqual(response.status_code,201,response.text)
            self.assertEqual(response.json()['realized_option_pl_usd'],2998)
            self.assertEqual(response.json()['cash_flow_usd'],-2)
            self.assertEqual(response.json()['buyback_total_usd'],0)
            self.assertEqual(self.post(root+'/expire-worthless',body).status_code,400)
            retained=response.json()['retained_position']
            ledger=self.client.get(f"/api/positions/{retained['position_id']}/transactions")
            self.assertEqual(ledger.status_code,200,ledger.text)
            self.assertEqual(ledger.json()['realized_option_pl_usd'],2998)
            self.assertEqual([e['action'] for e in ledger.json()['entries']],['Sell'])
            self.assertEqual(ledger.json()['entries'][0]['outcome'],'Expired worthless')
            self.assertEqual(ledger.json()['entries'][0]['realized_pl_usd'],2998)
            self.assertEqual(ledger.json()['entries'][0]['fees_usd'],2)
            self.assertEqual(retained['shares'],1000)
            self.assertEqual(retained['call_contracts'],0)
            self.assertEqual(self.client.get('/api/exit-optimizer/holdings').json()['holdings'][0]['position_id'],retained['position_id'])
            self.assertEqual(self.client.get('/api/positions/availability').json()['stocks'][0]['available_shares'],0)
            self.assertEqual(len(self.client.get('/api/option-expirations').json()['expirations']),1)
            self.assertEqual(self.client.get('/api/closed-holdings').json()['holdings'],[])
            close=dict(account='RRSP',symbol='RKLB',position_key=h['position_key'],position_revision=h['position_revision'],close_date='2026-10-27',stock_price_usd=40,buyback_price_usd=2,fees_usd=0,reviewed=True)
            self.assertEqual(self.post('/api/closed-holdings',close).status_code,400)
            self.assertNotEqual(retained['position_id'],h['position_id'])
            active=self.client.get('/api/exit-optimizer/holdings').json()['holdings']
            self.assertEqual([row['position_id'] for row in active],[retained['position_id']])
            position_id=retained['position_id']
            self.assertEqual(self.post(f'/api/positions/{position_id}/opening',dict(expiry='2028-01-21',strike=25,contracts=10,settlement_date='2026-10-27',price_usd=4,reviewed=True)).status_code,201)
            capture=dict(inputs=dict(account='RRSP',symbol='RKLB',position_id=position_id,shares=1000,contracts=10,held=dict(expiry='2028-01-21',strike=25)),result=dict(rows=[dict(strategy='Close now',mean=30000)]))
            capture_file=self.root/'reports'/f'exit-optimizer-rrsp-rklb-{position_id}.json'
            capture_file.write_text(json.dumps(capture));before=capture_file.read_bytes()
            with patch.object(server.stock_basis,'get',return_value=dict(priceUsd=20,feesUsd=0,quantity=1000)):
                response=self.client.get(f'/api/exit-optimizer/capture?account=RRSP&symbol=RKLB&position_id={position_id}')
            self.assertEqual(response.status_code,200,response.text)
            row=response.json()['result']['rows'][0]
            self.assertEqual(row['realized_pl_usd'],2998)
            self.assertEqual(row['unrealized_pl_usd'],14000)
            self.assertEqual(row['total_pl_usd'],16998)
            self.assertEqual(row['net_profit_usd'],14000)
            self.assertEqual(capture_file.read_bytes(),before)


    def test_missing_broker_configuration_and_history_failure_are_specific(self):
        body=dict(account='RRSP',symbol='TEST')
        message='Questrade authorization is not configured for this app. Live quote refresh is unavailable.'
        with patch.object(server.exit_optimizer,'run',side_effect=server.exit_optimizer.BrokerNotConfigured(message)):
            result=self.post('/api/exit-optimizer/run',body)
            self.assertEqual(result.status_code,503)
            self.assertEqual(result.json()['error'],message)
            self.assertNotIn('Previous results retained',result.json()['error'])
        with patch.object(server.exit_optimizer,'run',side_effect=server.exit_optimizer.StockHistoryUnavailable('Stock price history is unavailable from Yahoo Finance.')):
            result=self.post('/api/exit-optimizer/run',body)
            self.assertEqual(result.status_code,502)
            self.assertIn('Yahoo Finance',result.json()['error'])
            self.assertNotIn('Questrade',result.json()['error'])


if __name__ == '__main__':
    unittest.main()
