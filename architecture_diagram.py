"""Render investment app architecture, excluding the separate FX model workflow."""
from html import escape
from pathlib import Path
import textwrap

ROOT=Path(__file__).resolve().parent
WIDTH,HEIGHT=1600,2820

def render():
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title description"><title id="title">Investment application architecture</title><desc id="description">High-level context: trader uses the Covered Call Optimizer system, which reads Questrade and Yahoo data and requests OpenAI assessments. Application architecture: React.js dashboard calls FastAPI in dashboard_server.py, which calls exit_optimizer.py and the independent model.py. Settings, persistence, Questrade, Yahoo and OpenAI assessment services stay in the application. React.js and FastAPI are implemented; Docker packages the API and React build.</desc><defs><marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0L7 3.5L0 7Z" fill="#99b1cb"/></marker></defs><style>text{{font-family:system-ui,sans-serif;fill:#e8eff8}}.title{{font-size:29px;font-weight:700}}.heading{{font-size:18px;font-weight:650}}.body{{font-size:15px}}.note{{font-size:14px;fill:#b4c7da}}</style><rect width="1600" height="2820" fill="#080c12"/>']
    def text(x,y,value,css='body'):
        parts.append(f'<text x="{x}" y="{y}" class="{css}">{escape(value)}</text>')
    def box(x,y,w,h,title,lines,color='#497fae',dashed=False):
        dash='stroke-dasharray="7 5"' if dashed else ''
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="#142131" stroke="{color}" stroke-width="2" {dash}/>')
        text(x+18,y+30,title,'heading');row=0
        for line in lines:
            for wrapped in textwrap.wrap(line,width=int((w-36)/7.7)):
                text(x+18,y+58+row*22,wrapped);row+=1
        if 58+max(0,row-1)*22>h-12:raise ValueError('Text exceeds box: '+title)
    def arrow(points,label=None,x=0,y=0):
        parts.append(f'<polyline points="{points}" fill="none" stroke="#99b1cb" stroke-width="2" marker-end="url(#arrow)"/>')
        if label:text(x,y,label,'note')
    text(35,45,'Covered Call Optimizer · system context','title')
    text(35,76,'High-level view · actor, system under development and external resources · No order execution','note')
    box(35,270,300,170,'Actor · Trader',[
        'Provides purchase / premium records and objectives',
        'Explores scenarios and decides whether to trade'
    ],'#d3ab64')
    box(450,230,460,230,'System · Covered Call Optimizer',[
        'The system we are developing',
        'React.js UI, API, model, settings and local storage',
        'Compares closing / rolling covered calls; shows cash, profit and liquidity',
        'Provides requested assessments; trader keeps execution control'
    ],'#49a58a')
    box(1110,140,450,140,'External · Questrade API',[
        'Stock / option quotes, displayed sizes, Greeks, listed calls and positions',
        'Read-only broker access; no order submission'
    ])
    box(1110,340,450,140,'External · Yahoo Finance',[
        'Three months of daily stock closes',
        'Historical input to scenario simulations'
    ])
    box(1110,540,450,140,'External · OpenAI API',[
        'Receives selected position / scenario snapshot',
        'Returns an assessment on explicit request'
    ],'#8b73af')
    arrow('335,330 450,330','Inputs',350,310)
    arrow('450,390 335,390','Results',350,420)
    arrow('1110,210 1000,210 1000,270 910,270','Quotes / chains',925,190)
    arrow('1110,410 910,410','Stock history',940,390)
    arrow('910,440 980,440 980,605 1110,605','Snapshot',1005,585)
    arrow('1110,645 945,645 945,480 800,480 800,460','Assessment',980,666)
    text(35,550,'Inside our system: React.js browser UI, application API / services, independent pricing model, SQLite and saved captures.','note')
    text(35,580,'Outside our system: the trader and external market-data / AI services. Brokerage trade execution remains outside this tool.','note')
    parts.append('<line x1="35" y1="715" x2="1565" y2="715" stroke="#43627e" stroke-width="2"/>')
    parts.append('<g transform="translate(0 740)">')
    text(35,45,'Covered-call optimizer · running deployment','title')
    text(35,76,'October 21, 2026 · Docker Desktop / WSL 2 · React → FastAPI → application services → model','note')
    box(420,115,760,150,'Browser · React.js · frontend/',[
        'Home / covered-call-optimizer, chart, slider and Close / Expire controls',
        'Profile / Settings, opening premiums and Recommendation panel',
        'Same-origin /api/ requests; credentials remain on the server'])
    parts.append('<rect x="350" y="340" width="900" height="1160" rx="16" fill="#0c1623" stroke="#49a58a" stroke-width="2" stroke-dasharray="10 6"/>')
    text(375,373,'Docker Compose · api service · aimoney-api image','heading')
    text(375,398,'Non-root runtime · one Uvicorn worker · host 127.0.0.1:8765 → container :8765','note')
    box(420,440,760,170,'FastAPI · dashboard_server.py',[
        'Serves the React build and typed /api/ routes; OpenAPI at /docs',
        'Holdings / saved capture / scenario / refresh / settings / assessments',
        'Origin checks, body limits, JSON errors and shared operation locks',
        'Lifespan starts / stops Yahoo reference feed; /api/health health check'])
    arrow('700,265 700,300 330,300 330,475 420,475','HTTP / JSON request',370,290)
    arrow('1180,485 1270,485 1270,300 900,300 900,265','React assets / JSON response',930,290)
    box(25,725,300,210,'External · market data',[
        'Questrade: stock / option quotes, Greeks, chains and positions',
        'Yahoo: stock history; separate periodic FX reference',
        'Broker requests only on explicit optimizer refresh'])
    box(420,720,760,170,'Application adapter · exit_optimizer.py',[
        'Refresh: acquire market data, read transactions and build inputs',
        'Scenario: reprice saved capture locally, without market requests',
        'Evaluate the independent model; persist captures only on refresh'])
    arrow('700,610 700,720','Refresh / scenario',505,665)
    arrow('900,720 900,610','Analysis result',920,665)
    arrow('325,790 420,790','Quotes',335,770)
    arrow('420,845 325,845','Requests',335,875)
    box(420,985,760,195,'Independent pricing model · model.py',[
        'models/financials/covered_call_exit/model.py',
        'IV calibration, European call approximation and 600 return paths',
        '30-trading-day baseline; cash flows, profit, top 3 rolls and funding',
        'Fixed captured Close today reference; hypothetical stock scenarios',
        'Pure calculations: no HTTP, database, credentials or OpenAI'
    ],'#49a58a')
    arrow('700,890 700,985','Validated model inputs',490,940)
    arrow('900,985 900,890','Calculated outputs',920,940)
    box(420,1270,350,200,'Settings services',[
        'stock_basis.py',
        'option_premiums.py / fx_samples.py',
        'Validate reviewed entries; save original costs and premiums to SQLite'
    ])
    box(820,1270,360,200,'Recommendation services',[
        'optimizer_recommendations.py',
        'Rebuild verified chart snapshot',
        'optimizer_assessments.py',
        'Call OpenAI; save assessment history'
    ],'#8b73af')
    box(1280,1270,295,200,'External · OpenAI API',[
        'Responses API',
        'Explicit Generate action only',
        'Receives selected facts; returns an assessment',
        'No trade submission'
    ],'#8b73af')
    arrow('1000,1270 1000,1180','Rebuild snapshot',1010,1225)
    arrow('420,525 380,525 380,1370 420,1370')
    arrow('1180,525 1220,525 1220,1370 1180,1370')
    arrow('1180,1325 1280,1325','Snapshot',1188,1305)
    arrow('1280,1420 1180,1420','Assessment',1188,1450)
    parts.append('<rect x="25" y="1615" width="1550" height="315" rx="16" fill="#0c1623" stroke="#d3ab64" stroke-width="2"/>')
    text(50,1650,'WSL host storage · bind mounts · persists across container replacement','heading')
    box(55,1680,465,175,'data/ → /app/data · read / write',[
        'fx-samples.sqlite3: shared stock basis, opening premiums, FX samples and recommendation_runs',
        'Private saved account holdings JSON'
    ],'#d3ab64')
    box(565,1680,465,175,'reports/ → /app/reports · read / write',[
        'Per-holding quote / model captures and generated reports',
        'GET /api/exit-optimizer/capture loads saved chart data; slider never saves'
    ],'#d3ab64')
    box(1075,1680,465,175,'.secrets/ → /app/.secrets · read / write',[
        'OpenAI configuration and Questrade authorization',
        'Writable because broker refresh tokens rotate; never sent to browser'
    ],'#d3ab64')
    text(55,1895,'Optional CIBC FX artifacts mount read-only; its separate training / publishing workflow is outside this view.','note')
    arrow('590,1470 590,1540 290,1540 290,1680')
    arrow('1000,1470 1000,1575 380,1575 380,1680')
    arrow('1180,875 1235,875 1235,1555 800,1555 800,1680')
    arrow('1540,1780 1585,1780 1585,650 1205,650 1205,570 1180,570','Server credentials',1280,630)
    text(35,1980,'Image build: Python dependencies + application / model code + local React assets. Private runtime files stay outside the image.','note')
    text(35,2010,'Docker health verified · host loopback only · rprivate bind propagation · one worker preserves refresh / token locks.','note')
    text(35,2040,'Sources: ARCHITECTURE.md / compose.yaml / Dockerfile · Regenerate: python architecture_diagram.py','note')
    parts.append('</g></svg>')
    return ''.join(parts)


def main():
    content=render()
    (ROOT/'docs/physical-architecture.svg').write_text(content, encoding='utf-8')
    (ROOT/'reports').mkdir(exist_ok=True)
    (ROOT/'reports/investment-architecture.svg').write_text(content, encoding='utf-8')
    print('Updated docs/physical-architecture.svg and reports/investment-architecture.svg')


if __name__=='__main__':main()
