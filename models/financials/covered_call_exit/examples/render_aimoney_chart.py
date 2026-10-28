"""Capture aiMoney's actual React Chart component with synthetic model inputs.

Optional dependencies: playwright and installed Chromium. Requires the aiMoney
frontend directory via --frontend-dir when outside the original application repo.
No application server, brokerage credentials or real portfolio files are used.
"""
import argparse
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--frontend-dir',type=Path,default=ROOT.parents[2]/'frontend')
parser.add_argument('--output-dir',type=Path,default=ROOT/'examples')
args=parser.parse_args()
frontend=args.frontend_dir.resolve()
assert (frontend/'src/Chart.js').is_file(), 'Supply the original aiMoney frontend with --frontend-dir'
spec=importlib.util.spec_from_file_location('exit_model',ROOT/'model.py')
model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
data=json.loads((ROOT/'examples/sample_input.json').read_text())
result=model.evaluate(data)
# Presentation reference; original sample/model inputs are unchanged.
view=json.loads(json.dumps(data))
view['opening_reference']['stock_price_usd']=data['initial_purchase_price_usd']
page_html='''<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/frontend/src/styles.css">
<script type="importmap">{"imports":{"react":"/frontend/vendor/react.js","react-dom/client":"/frontend/vendor/react-dom-client.js"}}</script>
</head><body><main id="capture">
<h1>aiMoney · Covered-call simulation</h1>
<p>SYNTHETIC DEMO · 100 shares / 1 call · stock midpoint $50 · 600 paths · 30 trading days</p>
<section><h2>Close today &amp; top 3 rollovers <small>USD</small></h2>
<div class="legend"><span style="--color:#26856c">Stock sale / assignment</span><span style="--color:#518acb">Replacement premium</span><span style="--color:#d45b68">Call buyback cost</span><span style="--color:#7955ac">Net full-position P/L</span><span style="--color:#8b602b">Original stock purchase cost (before fees)</span></div>
<div id="root"></div>
<p>Actual aiMoney dashboard chart component. All choices shown in Close mode.<br>
Historical-return bootstrap + Black–Scholes pricing; 4% annual rate, fixed IV and spreads.<br>
Fictional data illustrates the calculations; future fees and taxes excluded. Not a validated forecast.</p>
</section></main>
<script type="module">
import {createRoot} from 'react-dom/client';
import {html} from '/frontend/src/ui.js';
import {Chart} from '/frontend/src/Chart.js';
const analysis=await (await fetch('/analysis.json')).json();
createRoot(document.getElementById('root')).render(html`<${Chart} analysis=${analysis} baseline=${analysis} modes=${{}} onMode=${()=>{}}/>`);
</script></body></html>'''
class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
args.output_dir.mkdir(parents=True,exist_ok=True)
out=args.output_dir/'simulation-profit.png'
with tempfile.TemporaryDirectory() as temp:
    temp=Path(temp);(temp/'frontend').symlink_to(frontend,target_is_directory=True)
    (temp/'index.html').write_text(page_html)
    (temp/'analysis.json').write_text(json.dumps(dict(inputs=view,result=result)))
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(temp)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1700},device_scale_factor=1.5)
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto('http://127.0.0.1:'+str(server.server_port),wait_until='networkidle')
            bars=page.locator('#chart rect[data-pnl="total"]')
            expect(bars).to_have_count(4)
            values=[float(bars.nth(i).get_attribute('data-value')) for i in range(4)]
            expected=[next(r for r in result['rows'] if r['strategy']=='Close now')['total_pl_usd']]+[r['total_pl_usd'] for r in result['top_choices']]
            assert values==expected,(values,expected)
            assert not errors,errors
            page.locator('#capture').screenshot(path=str(out))
            browser.close()
    finally:server.shutdown();thread.join()
provenance={
 'renderer':'Actual aiMoney frontend/src/Chart.js and styles.css via React/Playwright',
 'sample_input_sha256':hashlib.sha256((ROOT/'examples/sample_input.json').read_bytes()).hexdigest(),
 'expected_result_sha256':hashlib.sha256((json.dumps(result,indent=2)+'\n').encode()).hexdigest(),
 'chart_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),
 'frontend_sha256':{name:hashlib.sha256((frontend/name).read_bytes()).hexdigest() for name in ['src/Chart.js','src/styles.css','src/ui.js','src/api.js']},
 'verified_plotted_total_pl_usd':values}
(args.output_dir/'simulation-chart-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
print('Captured actual aiMoney chart; four P/L bars match model output:',out)
