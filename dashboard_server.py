"""Serve the private dashboard and refresh Yahoo USD/CAD every 60 seconds."""
import argparse
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading

import fx_samples
import option_premiums
import stock_basis
import sqlite3
import exit_optimizer
import optimizer_recommendations
import optimizer_assessments
from macro_data import usd_cad
from roll_candidates import INPUTS, SYMBOLS, output_path

ROOT = Path(__file__).resolve().parent
ROLL_REFRESH_LOCK = threading.Lock()
ASSESSMENT_LOCK = threading.Lock()


class MacroFeed:
    def __init__(self, path, interval=60):
        self.path, self.interval = path, interval
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.quote = None
        self.error = None
        self.attempted_at = None
        try:
            self.quote = json.loads(path.read_text())
        except (OSError, ValueError):
            pass

    def refresh(self):
        attempted = datetime.now(timezone.utc).isoformat()
        try:
            quote = usd_cad()
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(quote, indent=2))
            temporary.replace(self.path)
            with self.lock:
                self.quote, self.error, self.attempted_at = quote, None, attempted
        except (OSError, ValueError, KeyError, TypeError, IndexError, OverflowError):
            with self.lock:
                self.error = 'Yahoo refresh failed; showing the last successful capture.'
                self.attempted_at = attempted

    def snapshot(self):
        with self.lock:
            return dict(quote=self.quote, error=self.error, attempted_at=self.attempted_at,
                        refresh_seconds=self.interval)

    def run(self):
        while not self.stop.is_set():
            self.refresh()
            self.stop.wait(self.interval)


class DashboardHandler(SimpleHTTPRequestHandler):
    def send_json(self, value, status=200):
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if self.path == '/api/optimizer-recommendations':
            port = self.server.server_port
            if self.headers.get('Origin') not in {f'http://localhost:{port}', f'http://127.0.0.1:{port}'}:
                self.send_json({'error': 'Use this dashboard origin.'}, 403)
                return
            if not ASSESSMENT_LOCK.acquire(blocking=False):
                self.send_json({'error': 'A recommendation is already running.'}, 409)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384:
                    raise ValueError('Invalid request size.')
                self.send_json(optimizer_recommendations.generate(json.loads(self.rfile.read(length))))
            except (ValueError, TypeError) as error:
                self.send_json({'error': str(error)}, 400)
            except optimizer_assessments.AssessmentError as error:
                self.send_json({'error': str(error)}, 502)
            except Exception:
                self.send_json({'error': 'Recommendation unavailable. Check saved analysis and local storage.'}, 503)
            finally:
                ASSESSMENT_LOCK.release()
            return
        if self.path in {'/api/exit-optimizer/run', '/api/exit-optimizer/scenario'}:
            port = self.server.server_port
            if self.headers.get('Origin') not in {f'http://localhost:{port}', f'http://127.0.0.1:{port}'}:
                self.send_json({'error': 'Use this dashboard origin.'}, 403)
                return
            if not ROLL_REFRESH_LOCK.acquire(blocking=False):
                self.send_json({'error': 'A market-data refresh is already running.'}, 409)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 2048:
                    raise ValueError('Invalid request size')
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise ValueError('Invalid request')
                self.send_json(exit_optimizer.scenario(request) if self.path.endswith('/scenario') else exit_optimizer.run(request))
            except (ValueError, TypeError) as error:
                self.send_json({'error': str(error)}, 400)
            except Exception:
                self.send_json({'error': 'Market data unavailable; check Questrade authorization and market-data access. Previous results retained.'}, 502)
            finally:
                ROLL_REFRESH_LOCK.release()
            return
        if self.path in {'/api/fx-samples', '/api/fx-samples/ocr', '/api/fx-samples/delete', '/api/option-premiums', '/api/option-premiums/usd', '/api/stock-cost-basis'}:
            port = self.server.server_port
            if self.headers.get('Origin') not in {f'http://localhost:{port}', f'http://127.0.0.1:{port}'}:
                self.send_json({'error': 'Use this dashboard origin.'}, 403)
                return
            try:
                limit = 8 * 1024 * 1024 if self.path.endswith('/ocr') else 16384
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= limit:
                    raise ValueError('Request is empty or too large (image limit: 8 MB).')
                body = self.rfile.read(length)
                if self.path == '/api/stock-cost-basis':
                    request=json.loads(body)
                    self.send_json({'bases': stock_basis.save_many(request.get('bases'))})
                elif self.path == '/api/option-premiums/usd':
                    self.send_json(option_premiums.save_usd(json.loads(body)), 201)
                elif self.path == '/api/option-premiums':
                    self.send_json(option_premiums.save(json.loads(body)), 201)
                elif self.path.endswith('/ocr'):
                    self.send_json(fx_samples.ocr(body))
                elif self.path.endswith('/delete'):
                    request = json.loads(body)
                    identifier = request.get('id')
                    if type(identifier) is not int or identifier <= 0:
                        raise ValueError('Choose a saved sample.')
                    with fx_samples.connect() as db:
                        db.execute('DELETE FROM samples WHERE id=?', (identifier,))
                    self.send_json({'deleted': identifier})
                else:
                    self.send_json(fx_samples.save(json.loads(body)), 201)
            except (ValueError, TypeError, KeyError) as error:
                self.send_json({'error': str(error)}, 400)
            except (OSError, sqlite3.Error, subprocess.SubprocessError):
                self.send_json({'error': 'Local OCR or storage unavailable. You can enter the fields manually.'}, 503)
            return
        if self.path != '/api/roll-candidates/refresh':
            self.send_error(404)
            return
        port = self.server.server_port
        if self.headers.get('Origin') not in {f'http://localhost:{port}', f'http://127.0.0.1:{port}'}:
            self.send_error(403)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 <= length <= 2048:
                raise ValueError()
            request = json.loads(self.rfile.read(length)) if length else {}
            if not isinstance(request, dict):
                raise ValueError()
            account, symbol = request.get('account', 'LIRA'), request.get('symbol', 'QBTS')
            purchase = request.get('purchasePriceUsd')
            if account not in INPUTS or symbol not in SYMBOLS:
                raise ValueError()
            if purchase is not None and (isinstance(purchase, bool) or not isinstance(purchase, (int, float)) or not 0 < purchase < float('inf')):
                raise ValueError()
        except (ValueError, TypeError):
            self.send_error(400, 'Choose a supported account, stock and positive USD purchase price')
            return
        if not ROLL_REFRESH_LOCK.acquire(blocking=False):
            self.send_error(409, 'Candidate refresh already in progress')
            return
        try:
            command = [sys.executable, str(ROOT/'roll_candidates.py'), '--account', account, '--symbol', symbol]
            if purchase is not None:
                command += ['--purchase-price-usd', str(purchase)]
            subprocess.run(command,
                           cwd=ROOT, check=True, timeout=90, capture_output=True)
            payload = output_path(account, symbol).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (OSError, subprocess.SubprocessError):
            self.send_error(502, 'Questrade candidate refresh failed; previous capture retained')
        finally:
            ROLL_REFRESH_LOCK.release()

    def do_GET(self):
        if self.path == '/api/optimizer-recommendations/status':
            self.send_json(optimizer_assessments.status())
            return
        if self.path == '/api/optimizer-recommendations/history':
            try:
                self.send_json({'runs': optimizer_assessments.history()})
            except sqlite3.Error:
                self.send_json({'error': 'Recommendation history unavailable.'}, 503)
            return
        if self.path.split('?', 1)[0] == '/equity-chart.html':
            self.send_response(302)
            self.send_header('Location', '/covered-call-optimizer.html')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            return
        if self.path == '/archive/equity-chart.html':
            path = ROOT/'archive/equity-dashboard/equity-chart.html'
            if not path.exists():
                self.send_error(404, 'Archived dashboard not found')
                return
            payload = path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == '/api/profile/holdings':
            from portfolio_data import account_widget
            try:
                accounts = [account_widget(json.loads((ROOT/'data'/name).read_text()))
                            for name in INPUTS.values()]
                self.send_json({'accounts': accounts})
            except (OSError, ValueError, KeyError, TypeError):
                self.send_json({'error': 'Saved profile holdings unavailable.'}, 503)
            return
        profile_assets = {
            '/entry_prices.js': 'entry_prices.js',
            '/profile_settings.js': 'profile_settings.js',
            '/profile_ui.js': 'profile_ui.js',
            '/option_premiums_ui.js': 'option_premiums_ui.js',
            '/optimizer_profile.js': 'optimizer_profile.js',
        }
        if self.path in profile_assets:
            payload = (ROOT/profile_assets[self.path]).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == '/api/option-premiums/usd':
            self.send_json({'premiums': option_premiums.usd_records()})
            return
        if self.path.split('?', 1)[0] in {'/', '/index.html', '/covered-call-optimizer.html'}:
            page = 'covered-call-optimizer.html' if self.path.split('?', 1)[0] == '/covered-call-optimizer.html' else 'index.html'
            payload = (ROOT/page).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == '/api/exit-optimizer/holdings':
            self.send_json({'holdings': exit_optimizer.holdings()})
            return
        if self.path == '/api/stock-cost-basis':
            self.send_json({'bases': stock_basis.records()})
            return
        if self.path == '/api/option-premiums':
            self.send_json({'premiums': option_premiums.records()})
            return
        if self.path == '/api/fx-samples':
            self.send_json({'samples': fx_samples.records()})
            return
        if self.path.split('?', 1)[0] == '/api/macro':
            payload = json.dumps(self.server.feed.snapshot()).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            super().do_GET()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    feed = MacroFeed(ROOT/'reports/macro-data.json')
    server = ThreadingHTTPServer(('127.0.0.1', args.port),
                                 partial(DashboardHandler, directory=str(ROOT/'reports')))
    server.feed = feed
    worker = threading.Thread(target=feed.run, daemon=True)
    worker.start()
    print(f'Optimizer: http://localhost:{args.port}/covered-call-optimizer.html · Yahoo refresh every 60 seconds', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        feed.stop.set()
        server.server_close()


if __name__ == '__main__':
    main()
