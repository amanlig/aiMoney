"""Render a standalone SVG of the implemented design; no external dependencies."""
from html import escape
from pathlib import Path

ROOT=Path(__file__).resolve().parent
W,H=1500,1330
parts=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc"><title id="title">Covered-call exit model design</title><desc id="desc">Current data acquisition, independent simulation, fixed closing benchmark, slider recalculation, and separate planned research.</desc><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill="#93aac1"/></marker></defs><style>text{{font-family:system-ui,sans-serif;fill:#e8eff8}}.title{{font-size:28px;font-weight:700}}.heading{{font-size:18px;font-weight:650}}.body{{font-size:15px}}.muted{{fill:#b1c1d2;font-size:15px}}</style><rect width="1500" height="1330" fill="#080c12"/>']
def text(x,y,value,cls='body'):
    parts.append(f'<text x="{x}" y="{y}" class="{cls}">{escape(value)}</text>')
def box(x,y,w,h,title,lines,color='#355e83',dashed=False):
    dash='stroke-dasharray="8 5"' if dashed else ''
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="#131d29" stroke="{color}" stroke-width="2" {dash}/>')
    text(x+18,y+30,title,'heading')
    for i,line in enumerate(lines):text(x+18,y+58+i*23,line)
def arrow(points,label=None,x=0,y=0):
    parts.append(f'<polyline points="{points}" fill="none" stroke="#93aac1" stroke-width="2" marker-end="url(#arrow)"/>')
    if label:text(x,y,label,'muted')
text(35,45,'Covered-call exit model · implemented design','title')
text(35,76,'USD only · fees excluded · top 3 rollovers + fixed Close today reference','muted')
box(35,110,440,150,'Local investment records',['Holdings JSON: account / shares / short call','SQLite: original USD stock purchase price','Original opening premium: exact contract match'])
box(530,110,435,150,'Market data · refresh only',['Yahoo: last 3 months of daily stock closes','Questrade: stock / chain / current bid-ask','Verify contract, size, delay and halt status'])
box(1020,110,445,150,'Browser dashboard',['Select holding · Refresh data & analyze','Record original opening option premium','Stock-price slider and reset control'])
box(245,320,730,125,'coveredCallOptimizer/exit_optimizer.py · application adapter',['Owns credentials, data retrieval, original transactions and capture storage','POST /api/exit-optimizer/run → validated model input dictionary'])
arrow('250,260 250,290 430,290 430,320')
arrow('745,260 745,320')
arrow('1230,260 1230,290 900,290 900,320')
parts.append('<rect x="35" y="490" width="970" height="390" rx="16" fill="#0d1820" stroke="#42a48a" stroke-width="2"/>')
text(55,522,'models/financials/covered_call_exit/model.py · independent pure Python','heading')
box(55,548,440,130,'Stock paths',['600 seeded return-bootstrap simulations','Start at captured or hypothetical stock midpoint','30 trading days; historical drift retained'],'#42a48a')
box(535,548,450,130,'Option valuation',['Calibrate IV per captured option midpoint','European call formula + captured half-spread','Keep IV / spreads fixed; handle expiry'],'#42a48a')
box(155,730,730,125,'Cash flows and ranking',['Stock sale − call purchases + replacement premium = discounted closing wealth','Net profit = closing wealth + original premium − original stock cost','Top 3 by net profit; show losses and sale-floor failures'],'#42a48a')
arrow('610,445 610,475 285,475 285,548')
arrow('610,475 760,475 760,548')
arrow('285,678 285,730')
arrow('760,678 760,730')
box(1045,340,420,145,'Private captured JSON',['Original inputs + scenario results','coveredCallOptimizer/reports/exit-optimizer-*.json','Refresh writes; slider never overwrites'])
arrow('975,385 1045,385')
box(1045,550,420,180,'Slider scenario · local POST',['Read original saved capture','Hypothetical spot: ±50% of current midpoint','Reprice calls at captured IV and spreads','Reuse history, seed and 30-day period','No broker requests / no persistence'],'#ab8acb')
arrow('1255,485 1255,550')
arrow('1045,645 1018,645 1018,710 760,710 760,730')
box(1045,780,420,100,'Fixed baseline',['Captured stock bid − original held-call ask','Unaffected by the stock-price slider'],'#c4a35c')
arrow('1465,415 1480,415 1480,830 1465,830')
box(245,935,1060,145,'Interactive chart · browser',['First group: Close today (fixed) · next groups: top 3 rollovers (scenario-sensitive)','Green = stock sale · red = buybacks · blue = replacement sale premium · purple = net profit','Original stock purchase: solid line · opening premium: dashed line · all amounts USD'],'#518acb')
arrow('520,880 520,935')
arrow('1255,880 1255,935')
box(35,1135,1430,145,'Planned research · NOT implemented',['Test Questrade exact-contract option candles (OHLCV) → potential historical evaluation','Historical bid/ask / Greeks collection and Hugging Face pricing-model comparisons remain future work','No historical option backtest or learned bid/ask forecast is currently used; no order execution'],'#8c779e',True)
text(35,1310,'Details and interaction sequence: DESIGN.md · Generator: draw_design.py','muted')
parts.append('</svg>')
(ROOT/'DESIGN.svg').write_text(''.join(parts))

if __name__=='__main__':
    print('Rendered DESIGN.svg')
