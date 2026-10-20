"""Generate three private account widgets with position-value and P/L bar charts."""
import argparse
import json
from decimal import Decimal
from pathlib import Path
import webbrowser

import sys

# Archived renderer still uses active shared profile/accounting helpers.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from portfolio_data import account_widget

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = Path(__file__).resolve().parent
ACCOUNT_CURRENCIES = {'RRSP': 'CAD', 'TFSA': 'CAD', 'LIRA': 'USD'}
DEFAULTS = {'RRSP': 'book-values-unassigned.json', 'TFSA': 'tfsa-closing.json',
            'LIRA': 'lira-closing.json'}




HTML = r'''<!doctype html><html lang="en"><head><base href="/"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Covered-call account simulator</title><style>
*{box-sizing:border-box}[hidden]{display:none!important}body{font-family:system-ui,sans-serif;margin:0;background:#eef3f8;color:#172b45;padding:28px}
main{max-width:1600px;margin:auto}h1{font-size:28px;margin:0 0 8px}p{font-size:14px;line-height:1.5;color:#53657b}
.widgets{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;margin:24px 0}
.widget{background:white;border:1px solid #dce5ef;border-radius:16px;padding:22px;min-width:0}
header{display:flex;justify-content:space-between;align-items:center}h2{margin:0;font-size:24px}
.badge{font-size:12px;background:#eef3f8;border-radius:20px;padding:6px 10px}.totals{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:22px 0}
.label{font-size:12px;color:#53657b}strong{display:block;font-size:21px;margin-top:4px;font-variant-numeric:tabular-nums}
h3{font-size:14px;margin:22px 0 4px}.gain{color:#087c61}.loss{color:#bb3a4b}
svg{display:block;width:100%;height:auto}svg text{font-family:system-ui,sans-serif;font-size:12px}
.context{font-size:12px}.empty{padding:35px 0;color:#53657b}.foot{font-size:12px;line-height:1.6}
.controls{background:white;border:1px solid #dce5ef;border-radius:14px;padding:18px;margin-top:20px}
.fields{display:flex;gap:16px;flex-wrap:wrap}.fields label{font-size:12px;display:flex;flex-direction:column;gap:5px}
input,select{font:inherit;padding:7px;border:1px solid #bbc9d8;border-radius:6px;max-width:165px}
button{font:inherit;padding:9px 14px;border:1px solid #bbc9d8;border-radius:7px;background:#edf3fa;color:#172b45;cursor:pointer}button.primary{background:#326cc4;color:white;border-color:#326cc4}.entry-form{border-top:1px solid #dce5ef;padding-top:16px;margin-top:16px}.entry-actions{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}.entry-form input{max-width:220px}
.warning{color:#96541d;background:#fff5e7;padding:8px;border-radius:6px;font-size:12px}
.loss-alert{color:#9d1732;background:#fff0f2;border:1px solid #efb6c1;border-radius:8px;padding:12px;font-weight:700}
.topbar{display:flex;align-items:center;justify-content:space-between;gap:16px}.profile-menu{position:relative;flex-shrink:0}.profile-dropdown{display:none;position:absolute;right:0;top:100%;min-width:160px;padding:8px;background:white;border:1px solid #dce5ef;border-radius:8px;box-shadow:0 8px 24px #18324f22;z-index:20}.profile-dropdown button{width:100%;text-align:left}.profile-menu:hover .profile-dropdown,.profile-menu:focus-within .profile-dropdown,.profile-menu.open .profile-dropdown{display:block}dialog{width:min(1100px,95vw);max-height:88vh;border:1px solid #dce5ef;border-radius:16px;padding:24px;color:#172b45}dialog::backdrop{background:#172b4580}.settings-header{display:flex;align-items:center;justify-content:space-between}.settings-header button{font-size:20px}#profile-settings input{max-width:230px;width:100%}#profile-settings td{white-space:normal}
.detail-grid{display:grid;grid-template-columns:repeat(4,minmax(100px,1fr));gap:16px;margin:18px 0}.detail-grid strong{font-size:20px}.table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:12px 10px;border-bottom:1px solid #dce5ef;white-space:nowrap}th{color:#53657b;font-size:12px} @media(max-width:550px){.detail-grid{grid-template-columns:1fr 1fr}}
@media(max-width:1100px){.widgets{grid-template-columns:1fr}}@media(max-width:550px){body{padding:14px}.widget{padding:16px}strong{font-size:18px}}
</style></head><body><nav style="padding:16px"><a href="covered-call-optimizer.html">Covered-call exit optimizer</a></nav><main><div class="topbar"><h1>Covered-call simulator</h1>
<a href="covered-call-optimizer.html#profile-settings">Profile / Settings ↗</a></div>
<p>RRSP · TFSA · LIRA — stock value less short-call buyback, with combined position profit or loss.</p>
<section class="controls"><div class="fields"><label>Focus on stock<select id="stock-filter"><option value="">All stocks</option></select></label>
<label>Account<select id="account-filter"><option value="">All accounts</option></select></label></div>
<p id="stock-filter-status" class="context" aria-live="polite">Showing all covered-call holdings.</p></section>
<section class="controls" id="macro-panel" aria-label="Macro data"><h2>Macro data</h2>
<div id="macro-usdcad"></div><div id="macro-history-chart"></div>
<div class="fields"><label>CAD per USD conversion assumption<input id="fx-assumption" type="number" min="0.01" step="0.00001" value="1.42168"></label></div>
<p class="context">Conversion assumption starts at the saved Yahoo reference. Edit it for CAD account comparisons; broker conversion charges are excluded.</p>
<p id="macro-update-status" class="context" aria-live="polite">Saved capture · checking automatic refresh…</p>
<p class="context">Yahoo market reference; quotes may be delayed. Historical line shows the past month of daily observations.</p></section>
<section class="controls" id="stock-details" aria-label="Selected stock and option details" hidden></section>
<section class="controls" id="fx-entry" aria-label="FX transaction sample entry"></section>
<div class="widgets" id="widgets"></div>
<p class="foot">Each widget states its currency and source. Saved screenshot marks are estimates; captured scenarios use the supplied quotes and FX assumptions.
P/L combines stock and short-call book-value gains, using opening premium proxies. Fees are currently zero placeholders.
Cash and positions without short calls are excluded. Hover or focus a bar for position details.</p>
</main><script>__D3__</script><script>__ENTRY_PRICES__</script><script>__PROFILE_SETTINGS__</script><script>
const accounts=__DATA__;
const accountCurrencies={RRSP:'CAD',TFSA:'CAD',LIRA:'USD'};
function element(tag,text,className){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(className)node.className=className;return node;}
function updateCurrencyDisplay(){const account=document.querySelector('#account-filter').value;document.querySelector('#macro-panel').hidden=accountCurrencies[account]==='USD';}
let entryOverrides={};
let profileSettings={name:'',holdings:{}};
try{const saved=JSON.parse(localStorage.getItem(ProfileSettings.STORAGE_KEY)||'null');if(saved&&typeof saved==='object')profileSettings={name:typeof saved.name==='string'?saved.name.slice(0,60):'',holdings:saved.holdings&&typeof saved.holdings==='object'?saved.holdings:{}};}catch{}
let entryStorageAvailable=true;
try{const saved=JSON.parse(localStorage.getItem(EntryPrices.STORAGE_KEY)||'{}');if(saved&&typeof saved==='object'&&!Array.isArray(saved))entryOverrides=saved;}catch{entryStorageAvailable=false;}
let macroData=__MACRO_DATA__;
const marketDetails=__MARKET_DETAILS__;
let rollCaptures=__ROLL_CAPTURES__;
function renderMacro(){
 const panel=document.querySelector('#macro-usdcad');
 panel.replaceChildren();
 const label=document.createElement('h3');label.textContent='USD / CAD';panel.append(label);
 if(macroData){
  const value=document.createElement('strong');value.textContent=`1 USD = ${macroData.cad_per_usd.toFixed(5)} CAD`;panel.append(value);
  if(macroData.previous_close){
   const change=macroData.cad_per_usd-macroData.previous_close;
   const delta=document.createElement('p');delta.textContent=`${change>=0?'+':''}${change.toFixed(5)} (${change>=0?'+':''}${(100*change/macroData.previous_close).toFixed(2)}%) vs previous close`;panel.append(delta);
  }
  const time=value=>new Date(value).toLocaleString('en-CA',{timeZone:'America/Vancouver',timeZoneName:'short'});
  const stamp=document.createElement('p');stamp.className='context';stamp.textContent=`Quote: ${time(macroData.observed_at)} · Retrieved: ${time(macroData.retrieved_at)} · Saved capture`;panel.append(stamp);
  const link=document.createElement('a');link.href=macroData.source_url;link.textContent='Yahoo Finance · CAD=X';link.target='_blank';link.rel='noopener noreferrer';panel.append(link);
 }else{
  const message=document.createElement('p');message.textContent='USD/CAD data unavailable.';panel.append(message);
 }
 renderMacroHistory();
}
function renderMacroHistory(){
 const panel=document.querySelector('#macro-history-chart');panel.replaceChildren();
 const points=(macroData?.history||[]).map(row=>({date:new Date(row.observed_at),rate:row.cad_per_usd})).filter(row=>Number.isFinite(row.date.getTime())&&Number.isFinite(row.rate)&&row.rate>0).sort((a,b)=>a.date-b.date);
 if(macroData?.observed_at&&Number.isFinite(macroData.cad_per_usd)){
  const current={date:new Date(macroData.observed_at),rate:macroData.cad_per_usd};
  if(!points.length||current.date>=points[points.length-1].date)points.push(current);
 }
 panel.append(element('h3','USD / CAD · past month to latest quote'));
 if(points.length<2){panel.append(element('p','Monthly history is unavailable. The latest quote is shown above.','context'));return;}
 const width=900,height=240,extent=d3.extent(points,p=>p.rate),padding=Math.max((extent[1]-extent[0])*.15,.001);
 const x=d3.scaleUtc().domain(d3.extent(points,p=>p.date)).range([70,width-25]);
 const y=d3.scaleLinear().domain([extent[0]-padding,extent[1]+padding]).nice().range([height-35,15]);
 const svg=d3.select(panel).append('svg').attr('viewBox',`0 0 ${width} ${height}`).attr('role','img');
 svg.append('title').text('Yahoo USD/CAD daily observations over the past month, ending with the latest captured quote; CAD per USD');
 svg.append('g').attr('transform',`translate(0,${height-35})`).call(d3.axisBottom(x).ticks(6).tickFormat(d3.utcFormat('%b %d')));
 svg.append('g').attr('transform','translate(70,0)').call(d3.axisLeft(y).ticks(5).tickFormat(d3.format('.4f')));
 svg.append('path').datum(points).attr('d',d3.line().x(p=>x(p.date)).y(p=>y(p.rate))).attr('fill','none').attr('stroke','#326cc4').attr('stroke-width',2.5);
 const last=points[points.length-1];svg.append('circle').attr('cx',x(last.date)).attr('cy',y(last.rate)).attr('r',5).attr('fill','#326cc4');
 const markers=svg.selectAll('.fx-point').data(points).join('circle').attr('class','fx-point').attr('cx',p=>x(p.date)).attr('cy',p=>y(p.rate)).attr('r',4).attr('fill','transparent').attr('tabindex',0);
 markers.append('title').text(p=>`${p.date.toISOString().slice(0,10)}: ${p.rate.toFixed(5)} CAD per USD`);
 const first=points[0],change=100*(last.rate/first.rate-1);
 panel.append(element('p',`${first.date.toISOString().slice(0,10)} to ${last.date.toISOString().slice(0,10)} · ${change>=0?'+':''}${change.toFixed(2)}% · CAD per USD. Daily observations with latest intraday capture; dates on the chart use UTC.`,'context'));
}
renderMacro();
if(macroData?.cad_per_usd)document.querySelector('#fx-assumption').value=macroData.cad_per_usd;
let macroPolling=false;
async function refreshMacro(){
 if(macroPolling)return;
 const status=document.querySelector('#macro-update-status');
 if(location.protocol==='file:'){status.textContent='Offline saved capture · open the local dashboard server for automatic refresh.';return;}
 macroPolling=true;
 try{
  const response=await fetch('/api/macro',{cache:'no-store',signal:AbortSignal.timeout(10000)});
  if(!response.ok)throw new Error('Macro feed unavailable');
  const feed=await response.json();
  if(feed.quote){macroData=feed.quote;renderMacro();}
  const age=macroData?(Date.now()-Date.parse(macroData.retrieved_at))/1000:Infinity;
  status.textContent=feed.error||(!feed.attempted_at?'Starting automatic refresh…':age>150?'Refresh is overdue · showing the last successful capture.':`Automatic refresh every ${feed.refresh_seconds} seconds · last updated ${new Date(macroData.retrieved_at).toLocaleTimeString('en-CA',{timeZone:'America/Vancouver',timeZoneName:'short'})}`);
 }catch(error){status.textContent='Automatic refresh unavailable · showing saved data. Start dashboard_server.py to reconnect.';}
 finally{macroPolling=false;}
}
refreshMacro();setInterval(refreshMacro,60000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshMacro();});
function visibleAccounts(){
 const symbol=document.querySelector('#stock-filter').value;
 const selectedAccount=document.querySelector('#account-filter').value;
 return accounts.filter(account=>!selectedAccount||account.account===selectedAccount).map(original=>{
  const account=EntryPrices.apply(original,entryOverrides);
  if(!symbol)return account;
  const rows=account.rows.filter(row=>row.symbol===symbol);
  return {...account,rows,positions:(account.positions||[]).filter(p=>p.symbol===symbol),
   net:rows.reduce((sum,row)=>sum+Number(row.net),0),
   pnl:rows.every(row=>row.pnl!==null)?rows.reduce((sum,row)=>sum+Number(row.pnl),0):null};
 }).filter(account=>!symbol||account.rows.length);
}
function amount(value,currency){return value===null?'Unknown':new Intl.NumberFormat('en-CA',{style:'currency',currency}).format(Number(value));}
function chart(container,account,metric){
 const data=account.rows.filter(d=>d[metric]!==null), width=430,height=Math.max(130,data.length*49+48);
 const svg=d3.select(container).append('svg').attr('viewBox',`0 0 ${width} ${height}`).attr('role','img');
 svg.append('title').text(`${account.account} ${metric==='net'?'net position values':'profit or loss'} in ${account.currency}`);
 if(!data.length){svg.append('text').attr('x',20).attr('y',50).text('Cost history unavailable');return;}
 const values=data.map(d=>Number(d[metric])),lo=Math.min(0,...values),hi=Math.max(0,...values);
 const x=d3.scaleLinear().domain(lo===hi?[-1,1]:[lo<0?lo*1.12:0,hi>0?hi*1.12:0]).nice().range([66,width-12]);
 const y=d3.scaleBand().domain(data.map(d=>d.symbol)).range([10,height-34]).padding(.36);
 svg.append('g').attr('transform',`translate(0,${height-28})`).call(d3.axisBottom(x).ticks(4).tickFormat(d3.format('~s')));
 svg.append('g').attr('transform','translate(60,0)').call(d3.axisLeft(y).tickSize(0)).call(g=>g.select('.domain').remove());
 svg.append('line').attr('x1',x(0)).attr('x2',x(0)).attr('y1',5).attr('y2',height-34).attr('stroke','#b7c7d9');
 const bars=svg.selectAll('rect').data(data).join('rect').attr('x',d=>x(Math.min(0,Number(d[metric]))))
 .attr('y',d=>y(d.symbol)).attr('width',d=>Math.abs(x(Number(d[metric]))-x(0)))
 .attr('height',y.bandwidth()).attr('rx',3).attr('fill',d=>Number(d[metric])<0?'#bb3a4b':metric==='pnl'?'#087c61':'#326cc4').attr('tabindex',0);
 bars.append('title').text(d=>`${d.symbol}: ${amount(d[metric],account.currency)}\n${d.shares} shares / ${d.contracts} short calls\nStrike: USD ${d.strike}; expiry: ${d.expiry}\nNet value: ${amount(d.net,account.currency)}\nP/L: ${amount(d.pnl,account.currency)}`);
 bars.attr('aria-label',d=>`${d.symbol}: ${amount(d[metric],account.currency)}`);
 svg.selectAll('.value').data(data).join('text').attr('class','value').attr('x',d=>{
 const inside=Math.abs(x(Number(d[metric]))-x(0))>110;return x(Number(d[metric]))+(Number(d[metric])<0?(inside?5:-5):(inside?-5:5));})
 .attr('text-anchor',d=>{
 const inside=Math.abs(x(Number(d[metric]))-x(0))>110;return Number(d[metric])<0?(inside?'start':'end'):(inside?'end':'start');})
 .attr('y',d=>y(d.symbol)+y.bandwidth()/2+4)
 .attr('fill',d=>Math.abs(x(Number(d[metric]))-x(0))>110?'white':'#172b45').text(d=>amount(d[metric],account.currency));
}
function renderAccounts(){
 document.querySelector('#widgets').replaceChildren();
 if(!visibleAccounts().length){const empty=document.createElement('p');empty.className='empty';empty.textContent='No covered-call holdings match this stock and account.';document.querySelector('#widgets').append(empty);}
 for(const account of visibleAccounts()){
 const card=document.createElement('section');card.className='widget';card.dataset.account=account.account;document.querySelector('#widgets').append(card);
 const header=document.createElement('header');card.append(header);
 const title=document.createElement('h2');title.textContent=account.account;header.append(title);
 const badge=document.createElement('span');badge.className='badge';badge.textContent=account.currency;header.append(badge);
 if(!account.rows.length){const empty=document.createElement('p');empty.className='empty';empty.textContent='No positions supplied';card.append(empty);continue;}
 const totals=document.createElement('div');totals.className='totals';card.append(totals);
 for(const [label,key] of [['Net position value','net'],['Profit / loss','pnl']]){
 const box=document.createElement('div');const caption=document.createElement('span');caption.className='label';caption.textContent=label;box.append(caption);
 const value=document.createElement('strong');value.textContent=amount(account[key],account.currency);
 if(key==='pnl'&&account[key]!==null)value.className=Number(account[key])<0?'loss':'gain';box.append(value);totals.append(box);}
 for(const [label,metric] of [['Position values','net'],['Profit / loss by position','pnl']]){
 const h=document.createElement('h3');h.textContent=label;card.append(h);chart(card,account,metric);}
 const context=document.createElement('p');context.className='context';context.textContent=account.context+(account.captured?' Captured: '+account.captured:'');card.append(context);
 if(account.manualEntry){const note=document.createElement('p');note.className='context';note.textContent='P/L uses your saved entry prices for edited positions.';card.append(note);}
 if(account.excluded.length){const excluded=document.createElement('p');excluded.className='context';excluded.textContent='Stock-only positions excluded: '+account.excluded.join(', ');card.append(excluded);}
}
}
for(const symbol of [...new Set(accounts.flatMap(account=>account.rows.map(row=>row.symbol)))].sort()){
 const option=document.createElement('option');option.value=symbol;option.textContent=symbol;document.querySelector('#stock-filter').append(option);
}
for(const account of accounts){
 const option=document.createElement('option');option.value=account.account;option.textContent=account.account;document.querySelector('#account-filter').append(option);
}
function updateFilters(){
 const symbol=document.querySelector('#stock-filter').value;
 const selectedAccount=document.querySelector('#account-filter').value;
 document.querySelector('#stock-filter-status').textContent=`${symbol||'All stocks'} · ${selectedAccount||'All accounts'} · charts and totals include matching covered-call holdings only.`;
 updateCurrencyDisplay();
 renderAccounts();
 renderStockDetails();
}
document.querySelector('#stock-filter').addEventListener('change',updateFilters);
document.querySelector('#account-filter').addEventListener('change',updateFilters);
renderAccounts();
</script><script>__ROLL_PRICING__</script><script>__ROLL_UI__</script><script>__STOCK_DETAILS_UI__</script><script>__PROFILE_UI__</script><script>__FX_SAMPLES_UI__</script><script>__OPTION_PREMIUMS_UI__</script></body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for account in DEFAULTS:
        parser.add_argument('--'+account.lower(), type=Path, default=ROOT/'data'/DEFAULTS[account])
        parser.add_argument('--'+account.lower()+'-scenario', type=Path,
                            help='Importer scenario JSON; must contain exactly one scenario')
    parser.add_argument('--output', type=Path, default=ARCHIVE/'equity-chart.html')
    parser.add_argument('--open', action='store_true', help='Open the local dashboard in your browser')
    parser.add_argument('--refresh-macro', action='store_true', help='Refresh Yahoo USD/CAD reference data')
    args = parser.parse_args()
    try:
        macro_path = ROOT/'reports/macro-data.json'
        if args.refresh_macro:
            from macro_data import usd_cad
            try:
                macro_path.write_text(json.dumps(usd_cad(), indent=2))
            except (OSError, ValueError, KeyError, TypeError, IndexError):
                print('Yahoo USD/CAD refresh unavailable; retaining any dated saved capture.')
        macro = json.loads(macro_path.read_text()) if macro_path.exists() else None
        details_path = ROOT/'reports/market-details.json'
        market_details = json.loads(details_path.read_text()) if details_path.exists() else None
        roll_captures = {}
        for candidates_path in (ROOT/'reports').glob('roll-candidates-*.json'):
            captured = json.loads(candidates_path.read_text())
            roll_captures[captured['account']+':'+captured['symbol']] = captured
        accounts = []
        for account in DEFAULTS:
            path = getattr(args, account.lower())
            if not path.exists():
                accounts.append(dict(account=account, currency=ACCOUNT_CURRENCIES[account], rows=[]))
                continue
            document = json.loads(path.read_text())
            if document['account_type'] != account:
                raise ValueError(f'{account} input has the wrong account_type')
            scenario_path = getattr(args, account.lower()+'_scenario')
            scenario = None
            if scenario_path:
                scenarios = json.loads(scenario_path.read_text())
                if not isinstance(scenarios, list) or len(scenarios) != 1:
                    raise ValueError(f'{account} quote file must contain exactly one scenario')
                scenario = scenarios[0]
            accounts.append(account_widget(document, scenario))
        library = (ROOT/'vendor/d3.min.js').read_text()
        payload = json.dumps(accounts).replace('<', '\\u003c')
        (ROOT/'reports/covered-call-readme.md').write_bytes((ROOT/'COVERED_CALL_OPTIMIZER_README.md').read_bytes())
        args.output.write_text(HTML.replace('__D3__', library).replace('__DATA__', payload)
                               .replace('__MACRO_DATA__', json.dumps(macro).replace('<', '\\u003c'))
                               .replace('__MARKET_DETAILS__', json.dumps(market_details).replace('<', '\\u003c'))
                               .replace('__ROLL_CAPTURES__', json.dumps(roll_captures).replace('<', '\\u003c'))
                               .replace('__STOCK_DETAILS_UI__', (ARCHIVE/'stock_details_ui.js').read_text())
                               .replace('__ENTRY_PRICES__', (ROOT/'entry_prices.js').read_text())
                               .replace('__PROFILE_SETTINGS__', (ROOT/'profile_settings.js').read_text())
                               .replace('__PROFILE_UI__', (ROOT/'profile_ui.js').read_text())
                               .replace('__OPTION_PREMIUMS_UI__', (ROOT/'option_premiums_ui.js').read_text())
                               .replace('__FX_SAMPLES_UI__', (ARCHIVE/'fx_samples_ui.js').read_text())
                               .replace('__ROLL_PRICING__', (ARCHIVE/'roll_pricing.js').read_text())
                               .replace('__ROLL_UI__', (ARCHIVE/'roll_ui.js').read_text())
)
        print(f'Saved account widgets: {args.output.resolve()}')
        if args.open:
            webbrowser.open(args.output.resolve().as_uri())
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f'Chart input error: {error}\n')


if __name__ == '__main__':
    main()
