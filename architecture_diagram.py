"""Render investment app architecture, excluding the separate FX model workflow."""
from html import escape
from pathlib import Path
import textwrap

ROOT=Path(__file__).resolve().parent
WIDTH,HEIGHT=1600,2270

def render():
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title description"><title id="title">Investment application architecture</title><desc id="description">High-level context: trader uses the Covered Call Optimizer system, which reads Questrade and Yahoo data and requests OpenAI assessments. Detailed proposed architecture: dashboard calls FastAPI in dashboard_server.py, which calls exit_optimizer.py and the independent model.py. Settings, persistence, Questrade, Yahoo and OpenAI assessment services stay in the application. FastAPI migration is not implemented.</desc><defs><marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0L7 3.5L0 7Z" fill="#99b1cb"/></marker></defs><style>text{{font-family:system-ui,sans-serif;fill:#e8eff8}}.title{{font-size:29px;font-weight:700}}.heading{{font-size:18px;font-weight:650}}.body{{font-size:15px}}.note{{font-size:14px;fill:#b4c7da}}</style><rect width="1600" height="2270" fill="#080c12"/>']
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
        'Dashboard, API, model, settings and local storage',
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
    text(35,550,'Inside our system: browser UI, application API / services, independent pricing model, SQLite and saved captures.','note')
    text(35,580,'Outside our system: the trader and external market-data / AI services. Brokerage trade execution remains outside this tool.','note')
    parts.append('<line x1="35" y1="715" x2="1565" y2="715" stroke="#43627e" stroke-width="2"/>')
    parts.append('<g transform="translate(0 740)">')
    text(35,45,'Covered-call optimizer · proposed FastAPI architecture','title')
    text(35,76,'Design proposal · October 20, 2026 · Framework migration not implemented · USD only · No order execution','note')
    box(420,110,760,150,'1 · Dashboard / browser',[
        'covered-call-optimizer.html · chart, slider, Close / Expire choices',
        'Profile / Settings · Recommendation panel · captured quote liquidity',
        'HTTP requests and JSON responses; no credentials or direct model access'])
    box(420,340,760,170,'2 · FastAPI boundary · dashboard_server.py · :8765',[
        'PROPOSED: replace the current built-in HTTP server with FastAPI',
        'Serve dashboard/assets; validate requests, origins and typed inputs',
        'Route holdings, refresh, scenarios, settings and recommendations',
        'Return JSON results / errors; coordinate concurrent work'])
    arrow('700,260 700,340','HTTP request',530,300)
    arrow('900,340 900,260','JSON response',920,300)
    box(35,600,430,195,'External market data',[
        'Questrade: verified calls, stock quotes, bid/ask sizes and Greeks',
        'Yahoo: three months of stock closes',
        'Explicit refresh only for optimizer',
        'Broker tokens remain server-side'])
    box(535,600,530,195,'3 · Application adapter · exit_optimizer.py',[
        'Refresh: acquire data, read original transactions, build model inputs',
        'Scenario: read capture and reprice locally; no market requests',
        'Call independent model; save refresh capture and return result'])
    box(1135,600,430,195,'Local persistence',[
        'SQLite: stock basis, opening premiums, recommendation_runs',
        'Private JSON: saved holdings and per-holding quote / model captures',
        'Slider never overwrites saved capture'])
    arrow('720,510 720,600','Analyze / scenario',735,555)
    arrow('880,600 880,510','Model result',895,555)
    arrow('465,675 535,675')
    arrow('535,720 465,720')
    arrow('1135,675 1065,675')
    arrow('1065,720 1135,720')
    box(420,890,760,195,'4 · Independent model · model.py',[
        'models/financials/covered_call_exit/model.py',
        'IV calibration, European call approximation, 600 return paths',
        '30 trading days; cash flows, profit, top 3 rolls and funding',
        'Returns data only; no HTTP, database, credentials or OpenAI',
        'Close today: captured stock bid / held-call ask; fixed reference'
    ],'#49a58a')
    arrow('720,795 720,890','Validated inputs',570,844)
    arrow('880,890 880,795','Calculated outputs',895,844)
    box(35,1180,470,210,'Recommendation application service',[
        'optimizer_recommendations.py',
        'Verify capture; rebuild selected chart snapshot using adapter / model',
        'optimizer_assessments.py sends snapshot and saves assessment',
        'Separate from pricing and ranking'
    ],'#8b73af')
    box(565,1180,470,210,'OpenAI Responses API',[
        'Explicit Generate recommendation action only',
        'Assess supplied facts, objectives, liquidity and funding assumptions',
        'No live news; no model price calculations; API key stays in app'
    ],'#8b73af')
    box(1095,1180,470,210,'Profile / Settings services',[
        'stock_basis.py / option_premiums.py',
        'FastAPI routes validate reviewed entries and persist to SQLite',
        'The model receives recorded costs and premiums as input data'
    ])
    arrow('420,425 15,425 15,1120 270,1120 270,1180')
    arrow('505,1280 565,1280','Snapshot / assessment',510,1150)
    arrow('1035,1320 1050,1320 1050,1115 270,1115 270,1180')
    arrow('1180,425 1585,425 1585,1120 1330,1120 1330,1180')
    text(35,1440,'Recommendation service also reads saved captures, calls the same independent model and writes SQLite assessment history.','note')
    text(35,1467,'Current runtime still uses SimpleHTTPRequestHandler. Existing :8766 worksheet is separate; TFT remains deferred. FX model excluded.','note')
    text(35,1495,'Design source: coveredCallOptimizer/ARCHITECTURE.md · Regenerate: python3 coveredCallOptimizer/architecture_diagram.py','note')
    parts.append('</g></svg>')
    return ''.join(parts)


def main():
    content=render()
    (ROOT/'docs/physical-architecture.svg').write_text(content)
    (ROOT/'reports').mkdir(exist_ok=True)
    (ROOT/'reports/investment-architecture.svg').write_text(content)
    print('Updated docs/physical-architecture.svg and reports/investment-architecture.svg')


if __name__=='__main__':main()
