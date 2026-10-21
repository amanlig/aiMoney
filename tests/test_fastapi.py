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


if __name__ == '__main__':
    unittest.main()
