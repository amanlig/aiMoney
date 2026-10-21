"""Render the proposed TFT design. This does not download or activate a model."""
from html import escape
from pathlib import Path
import textwrap

ROOT=Path(__file__).resolve().parent
W,H=1600,1740
svg=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title description"><title id="title">Proposed TFT option pricing architecture</title><desc id="description">Offline quote collection, horizon-specific TFT training and evaluation, then proposed online scenarios, spread estimation and rollover ranking. This architecture is not implemented.</desc><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10Z" fill="#9eb4cd"/></marker></defs><style>text{{font-family:system-ui,sans-serif;fill:#eaf0f8}}.title{{font-size:29px;font-weight:700}}.head{{font-size:18px;font-weight:650}}.body{{font-size:15px}}.note{{font-size:15px;fill:#b3c4d7}}.lane{{font-size:16px;fill:#98bde6;font-weight:650;letter-spacing:1px}}</style><rect width="1600" height="1740" fill="#070b11"/>']
def txt(x,y,t,cls='body'):
    svg.append(f'<text x="{x}" y="{y}" class="{cls}">{escape(t)}</text>')
def box(x,y,w,h,title,lines,color='#4279a8',dashed=False):
    dash='stroke-dasharray="8 5"' if dashed else ''
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="#132031" stroke="{color}" stroke-width="2" {dash}/>')
    txt(x+18,y+29,title,'head')
    row=0
    for line in lines:
        for chunk in textwrap.wrap(line,width=int((w-36)/7.6)):
            txt(x+18,y+57+row*22,chunk);row+=1
    if 57+max(0,row-1)*22>h-12:raise ValueError('Text exceeds box: '+title)
def link(points,label=None,x=0,y=0):
    svg.append(f'<polyline points="{points}" fill="none" stroke="#9eb4cd" stroke-width="2" marker-end="url(#arrow)"/>')
    if label:txt(x,y,label,'note')

txt(35,44,'design1 · Proposed TFT option pricing architecture','title')
txt(35,76,'PROPOSAL ONLY · Current simulator stays unchanged until evaluation passes · USD only','note')
box(35,103,1530,120,'Important model fit',['Hugging Face TFT-Lite predicts a SPY option mark using 10-day feature sequences and a single-step output.',
    'It does not directly supply ASTS bid/ask quotes or a validated 30-trading-day forecast.',
    'Proposed adaptation: retrain / fine-tune and evaluate a direct 30-day mark target, plus a separate spread model.'],'#b48b50')
txt(35,263,'1  OFFLINE DATA AND LEARNING · app owns acquisition; models owns learning','lane')
box(35,285,470,175,'Broker / market-data collectors',['Questrade: current chain, bid/ask, Greeks','Test exact-contract historical option OHLCV','Stock history + rate / dividend inputs','Volume / open interest: verify provider coverage'],'#4279a8',True)
box(565,285,470,175,'Private historical quote archive',['Timestamped stock + option snapshots','Store bid, ask, mark, IV, Greeks, liquidity','Exact contract / expiry / strike / multiplier','Candles alone do not supply quote history'],'#4279a8',True)
box(1095,285,470,175,'Hugging Face candidate package',['major-year-project/tft-option-pricing','Weights, config and fitted scalers','Reconstruct architecture; pin version','Verify license, feature order and target'],'#8a6db0',True)
link('505,370 565,370')
box(285,510,750,165,'Feature / label pipeline · no future-data leakage',['Build 10-day sequences by exact contract, matching the verified feature schema.','Inputs: IV, Greeks, time-to-expiry, moneyness, strike, type, volume, open interest.','Proposed label: observed option mark 30 trading days later; no post-expiry labels.','Fit preprocessing on training dates only; split by time and purge overlapping targets.'],'#479b84',True)
link('800,460 800,510')
box(35,730,470,160,'Adapted TFT mark predictor',['PyTorch · feature selection → LSTM','Temporal attention → mark output','Direct 30-day target for held / rolled calls','Single-step package needs adaptation'],'#479b84',True)
box(565,730,470,160,'Separate spread estimator',['Learn spread from historical bid/ask','Use only information available at forecast','Predict nonnegative future spread','Calibrate uncertainty on held-out dates'],'#479b84',True)
box(1095,730,470,160,'Evaluation and promotion gate',['Walk-forward test on ASTS / held stocks','Compare current baseline at same horizon','Check price errors, coverage and rankings','Reject leakage or unsupported data domains'],'#b48b50',True)
link('430,675 430,700 270,700 270,730')
link('800,675 800,730')
link('1330,460 1330,485 1060,485 1060,700 505,700 505,730')
link('505,810 535,810 535,915 1080,915 1080,810 1095,810')
link('1035,810 1095,810')
box(1095,955,470,110,'Versioned model bundle',['Approved TFT + scalers + spread model','Feature schema, horizon and validation metrics'],'#479b84',True)
link('1330,890 1330,955')
txt(35,1010,'2  ONLINE SCENARIOS · proposed local inference, no trading orders','lane')
box(35,1040,470,180,'Investment application',['Current broker snapshot + saved holdings','Original stock purchase / opening premium','Read latest per-contract feature histories','Slider → hypothetical stock scenario','Close today → fixed captured market quotes'],'#4279a8')
box(565,1110,470,190,'Independent inference adapter',['models/financials: load approved bundle','Same feature order / training transforms','Predict 30-day mark + separate spread','Scenario stock changes → consistent IV / Greeks assumptions','Missing history / out-of-domain → baseline'],'#479b84',True)
link('505,1130 535,1130 535,1160 565,1160')
link('1330,1065 1330,1090 800,1090 800,1110')
box(1095,1130,470,170,'Bid / ask + uncertainty',['Validate mark-to-mid convention first','Estimated bid = midpoint − spread / 2','Estimated ask = midpoint + spread / 2','Enforce valid ordering and pricing bounds','Label forecast ranges and model version'],'#8a6db0',True)
link('1035,1200 1095,1200')
box(285,1350,750,150,'Existing cash-flow and ranking engine',['Current bids / asks for rollover execution today; forecast ask for later buyback.','Simulate stock sale; subtract call buybacks; add replacement premium.','Net profit = discounted closing wealth + original premium − original stock cost.','Keep strike / expiry search windows; rank top 3; label sale-floor failures.'],'#4279a8')
link('1330,1300 1330,1325 900,1325 900,1350')
link('270,1220 270,1325 430,1325 430,1350')
box(1095,1370,470,145,'Dashboard comparison',['First group: fixed Close today benchmark','Next: top 3 scenario-driven rollovers','Show price sources, forecast uncertainty','Baseline comparison / fallback stays available'],'#4279a8')
link('1035,1425 1095,1425')
box(35,1550,1530,145,'Design decisions and limits',['Dashed boxes: proposed new components. Solid app boxes: existing responsibilities to retain or extend.',
    'No actual future Greeks, IV or volume may be supplied as known inputs. Slider outputs are conditional scenarios, not market forecasts.',
    'The research model’s mark definition, time-step alignment and feature availability must be verified before deployment.',
    'No model download, training, API history fetch or runtime integration has been performed as part of this diagram.'],'#b48b50')
txt(35,1720,'Source: huggingface.co/major-year-project/tft-option-pricing · Details: design1.md','note')
svg.append('</svg>')
(ROOT/'design1.svg').write_text(''.join(svg))
print('Rendered design1.svg')
