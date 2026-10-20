"""Serve the investment closing simulator with an explicit read-only quote refresh endpoint."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import subprocess
import sys
import threading
import close_recommendations as recommendations
import sqlite3
import stock_basis

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
REFRESH_LOCK=threading.Lock()
ASSESSMENT_LOCK=threading.Lock()
LATEST_QUOTES=None


def refreshed_quotes():
    subprocess.run([sys.executable,str(ROOT/'coveredCallOptimizer/market_details.py')],
                   cwd=ROOT/'coveredCallOptimizer',check=True,capture_output=True,timeout=120)
    sys.path.insert(0,str(ROOT/'coveredCallOptimizer'))
    from macro_data import usd_cad
    fx=usd_cad()
    market=json.loads((ROOT/'coveredCallOptimizer/reports/market-details.json').read_text())
    stock=market['stocks']['ASTS']
    option=next(r for r in market['options'] if r['symbol']=='ASTS' and r['expiry']=='2028-01-21' and float(r['strike'])==40 and 'RRSP' in r['accounts'])
    for value in (stock.get('bidPrice'),option.get('askPrice'),fx.get('cad_per_usd')):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
            raise ValueError('Required quote unavailable')
    if stock.get('isHalted') or option.get('isHalted'):
        raise ValueError('Trading halted')
    return dict(basis=stock_basis.get('RRSP','ASTS'),stock=stock,option=option,quote_time=market['captured_at'],
                quote_source=market.get('source','Questrade API'),reference=fx['cad_per_usd'],
                reference_source=fx.get('source','Yahoo Finance'),reference_time=fx['observed_at'])


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control','no-store')
        super().end_headers()

    def send_json(self,value,status=200):
        payload=json.dumps(value,allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path.split('?',1)[0]=='/covered-call-close.html':
            try:subprocess.run([sys.executable,str(HERE/'simulate_close.py')],check=True,capture_output=True,timeout=15)
            except (OSError,subprocess.SubprocessError):
                self.send_error(503,'Unable to load saved stock basis or simulator source data');return
        if self.path=='/api/recommendations/status':
            self.send_json(recommendations.status());return
        if self.path=='/api/recommendations/history':
            try:self.send_json({'runs':recommendations.history()})
            except (OSError,sqlite3.Error):self.send_json({'error':'Local history unavailable.'},503)
            return
        super().do_GET()

    def assess(self):
        if not ASSESSMENT_LOCK.acquire(blocking=False):
            self.send_json({'error':'An assessment is already running.'},409);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=8192:raise ValueError('Invalid assessment request size.')
            request=json.loads(self.rfile.read(length))
            self.send_json(recommendations.generate(request,LATEST_QUOTES))
        except recommendations.ConfigurationError as error:self.send_json({'error':str(error)},503)
        except recommendations.AssessmentError as error:self.send_json({'error':str(error)},502)
        except (ValueError,TypeError) as error:self.send_json({'error':str(error)},400)
        except (OSError,KeyError,StopIteration,sqlite3.Error):self.send_json({'error':'Assessment source data or history unavailable. Check saved position inputs.'},503)
        finally:ASSESSMENT_LOCK.release()

    def do_POST(self):
        global LATEST_QUOTES
        if self.path not in ['/api/quotes/refresh','/api/recommendations']:
            self.send_error(404);return
        port=self.server.server_port
        if self.headers.get('Origin') not in {f'http://localhost:{port}',f'http://127.0.0.1:{port}'}:
            self.send_json({'error':'Use this report origin.'},403);return
        if self.path=='/api/recommendations':
            self.assess();return
        if not REFRESH_LOCK.acquire(blocking=False):
            self.send_json({'error':'A quote refresh is already running. Try again shortly.'},409);return
        try:
            LATEST_QUOTES=refreshed_quotes()
            self.send_json(LATEST_QUOTES)
        except (OSError,ValueError,KeyError,TypeError,StopIteration,subprocess.SubprocessError):
            self.send_json({'error':'Quote refresh failed. Previous scenario values remain displayed. Check broker authorization and try again.'},502)
        finally:
            REFRESH_LOCK.release()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8766)
    args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),partial(Handler,directory=str(HERE/'reports')))
    print(f'Closing simulator: http://localhost:{args.port}/covered-call-close.html',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
