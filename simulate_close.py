"""Build a private standalone covered-call closing cash-flow visualization."""
import json
import sqlite3
import stock_basis
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
MODEL_DIR=HERE/'models/financials/cibc_fx'
with sqlite3.connect((ROOT/'coveredCallOptimizer/data/fx-samples.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as db:
    db.row_factory=sqlite3.Row
    premium=dict(db.execute("SELECT * FROM option_premiums WHERE account='RRSP' AND symbol='ASTS' AND expiry='2028-01-21' AND strike=40 AND contracts=5 ORDER BY settlement_date DESC LIMIT 1").fetchone())
basis=stock_basis.get('RRSP','ASTS')
market=json.loads((ROOT/'coveredCallOptimizer/reports/market-details.json').read_text())
option=next(r for r in market['options'] if r['symbol']=='ASTS' and r['expiry']==premium['expiry'] and float(r['strike'])==premium['strike'] and 'RRSP' in r['accounts'])
fx=json.loads((ROOT/'coveredCallOptimizer/reports/macro-data.json').read_text())
model=json.loads((MODEL_DIR/'artifacts/model.json').read_text())
data=dict(basis=basis,premium=premium,stock=market['stocks']['ASTS'],option=option,quote_time=market['captured_at'],quote_source=market.get('source','Questrade API'),reference_source=fx.get('source','Yahoo Finance'),reference=fx['cad_per_usd'],reference_time=fx['observed_at'],model=model)
html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ASTS covered-call closing simulation</title>
<style>body{font:16px system-ui;color:#193149;background:#f3f6fa;max-width:1200px;margin:30px auto;padding:0 18px}h1{font-size:28px}h2{font-size:20px}p{line-height:1.5}.card{background:white;border:1px solid #d5dfeb;border-radius:12px;padding:22px;margin:20px 0}.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}label{display:flex;flex-direction:column;gap:6px;font-size:14px}input,select{padding:9px;font:inherit;border:1px solid #9aafc2;border-radius:5px;min-width:0}.columns{display:grid;grid-template-columns:1fr 1fr;gap:24px}.row{display:flex;justify-content:space-between;gap:16px;padding:12px 0;border-bottom:1px solid #e2e8f0}.value{font-size:26px;font-weight:700}.gain{background:#e5f3ec;border-color:#91b9a2}.loss{background:#fff0ed;border-color:#d8a397}.muted{color:#52697f;font-size:14px}.warning{color:#9b4412}.model-badge{display:inline-block;background:#eaf0fb;color:#254f86;border:1px solid #c6d5ed;border-radius:5px;padding:3px 7px;font-size:11px;font-weight:600;margin-top:5px}.flow-label{display:flex;flex-direction:column;align-items:flex-start}.flow-note{font-size:12px;color:#52697f;margin-top:4px}svg{width:100%;height:auto}.wide{grid-column:1/-1}.fields>label{display:grid;grid-template-rows:2.6em auto;align-content:start;gap:6px;line-height:1.3}.fields>label input,.fields>label select{box-sizing:border-box;width:100%;min-height:44px}.fields>label.wide{grid-template-rows:auto auto}button{padding:10px;cursor:pointer}#error{color:#a32626}@media(max-width:700px){.columns{grid-template-columns:1fr}}</style>
<h1>ASTS · simulate closing today</h1><p>RRSP · 500 shares + 5 short $40 calls expiring January 21, 2028. All displayed cash flows are in CAD unless marked USD.</p>
<div class="card"><h2>Close today · hypothetical prices</h2><button id="refresh-quotes" type="button">Refresh quotes</button><p id="refresh-status" class="muted" role="status" aria-live="polite">Refresh replaces the stock bid, call ask and reference FX. Entered fees and conversion treatment are preserved.</p><p id="snapshot" class="muted"></p><div id="sources" class="muted"></div><form id="inputs" class="fields">
<label>Stock sale bid (USD/share)<input id="bid" type="number" min="0.0001" step="any" required></label>
<label>Call buyback ask (USD/share)<input id="ask" type="number" min="0" step="any" required></label>
<label>Yahoo reference FX (CAD/USD)<input id="reference" type="number" min="0.0001" step="any" required></label>
<label>Stock closing fees (USD)<input id="stockfees" type="number" min="0" step="any" value="0" required></label>
<label>Call closing fees (USD)<input id="callfees" type="number" min="0" step="any" value="0" required></label>
<label class="wide">Conversion treatment<select id="treatment"><option value="separate">Convert each closing leg separately (sell USD for shares; buy USD for call)</option><option value="net">Net closing cash flows in USD, then convert the balance</option></select></label></form><p id="error" role="status"></p><p class="muted">This simulation assumes closing today. Initial prices are saved snapshots, not a live feed; update the bid, ask and FX reference to current quotes before relying on the estimate. Zero fees means fees excluded.</p></div>
<div class="columns"><section class="card"><h2>Original position · confirmed cash flows</h2><div id="original"></div><p class="muted">The stock cost includes purchase commission. The premium received is after opening commission. These opening amounts stay fixed as you change closing assumptions.</p></section>
<section class="card"><h2>Hypothetical closing cash flows</h2><div id="closing"></div><h3>Call buyback · option details</h3><div id="option-details"></div><p id="greeks-note" class="muted"></p><h3>Model-estimated CIBC conversion rates</h3><div id="model-rates"></div><p id="rates" class="muted"></p></section></div>
<section class="card"><h2>From opening costs to hypothetical realized gain</h2><div id="waterfall"></div><p class="muted">Each bar adds to or subtracts from cumulative cash. The final total includes the original premium received, not just the cash received when closing.</p></section>
<section id="result" class="card gain" aria-live="polite"></section>
<section class="card"><button id="recommendation-button" type="button" aria-expanded="false" aria-controls="recommendation">Recommendation</button><div id="recommendation" hidden>
<h2>Fresh OpenAI assessment</h2>
<label>Assessment goal<select id="assessment-goal"><option value="free_cash">Free cash for another investment</option><option value="reduce_risk">Reduce ASTS exposure and risk</option><option value="keep_exposure">Keep long-term ASTS exposure</option><option value="compare">Compare closing versus holding</option></select></label>
<p class="muted">Generate sends this position’s details, quotes, scenario inputs and calculated cash flows to OpenAI. API usage is billed to your OpenAI project. No broker credentials or API keys are sent in the assessment input. No news research or orders are performed.</p>
<button id="generate-assessment" type="button">Generate new assessment</button>
<p id="assessment-status" role="status" aria-live="polite"></p>
<h3>Process involved</h3><ol id="assessment-process"><li>Use the displayed quote snapshot, or click Refresh quotes for a new capture.</li><li>Load confirmed stock cost and opening premium from local records.</li><li>Recalculate cash flows on the server using the fitted CIBC FX model.</li><li>Send the snapshot and selected goal to OpenAI for a fresh assessment.</li><li>Save the assessment, full input snapshot, model and timestamp in local SQLite history.</li></ol>
<div id="assessment-result" style="white-space:pre-wrap;line-height:1.6"></div>
<details><summary>Assessment inputs and calculated results</summary><pre id="assessment-snapshot" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre></details>
<h3>Saved assessments</h3><p class="muted">View a prior result with its original inputs, or generate again using today’s inputs. A new AI assessment may differ even with identical inputs.</p><div id="assessment-history"></div>
</div></section>
<p id="range" class="warning"></p><p class="muted">This is a cash-flow estimate, not an executed result or tax calculation. The FX model was fitted on settlement-day Yahoo closes and transactions ending November 2025. Live and future conversion accuracy is unvalidated. Actual CIBC conversion treatment and fills can differ. Partial closes, rolls and adjusted contracts are not represented.</p>
<script>__D3__</script><script>
const data=__DATA__, $=id=>document.getElementById(id),money=v=>new Intl.NumberFormat('en-CA',{style:'currency',currency:'CAD'}).format(v),r2=v=>Math.round((v+Number.EPSILON)*100)/100;
const today=new Date().toLocaleDateString('en-CA',{timeZone:'America/Vancouver'});
$('bid').value=data.stock.bidPrice;$('ask').value=data.option.askPrice;$('reference').value=data.reference;
function renderSnapshot(){$('snapshot').textContent=`Initial broker snapshot: ${new Date(data.quote_time).toLocaleString('en-CA',{timeZone:'America/Vancouver',timeZoneName:'short'})}. FX reference observed ${new Date(data.reference_time).toLocaleString('en-CA',{timeZone:'America/Vancouver',timeZoneName:'short'})}. Stock bid size: ${data.stock.bidSize}; a 500-share fill at the bid is not assured.`;}
renderSnapshot();
function row(parent,label,value,modelNote=null){const r=document.createElement('div');r.className='row';const a=document.createElement('span'),b=document.createElement('strong');a.className='flow-label';a.textContent=label;b.textContent=money(value);if(modelNote){const badge=document.createElement('span');badge.className='model-badge';badge.textContent='Uses predicted CIBC FX';const note=document.createElement('span');note.className='flow-note';note.textContent=modelNote;a.append(badge,note);}r.append(a,b);parent.append(r);}
function fx(direction,amount,reference){const p=data.model.parameters[direction],rate=reference*(1+p.adjustment);return {rate,cad:r2(amount*rate),outside:amount>0&&(amount<p.usd_min||amount>p.usd_max)};}
function draw(parts){const W=1100,H=360,m={l:75,r:20,t:35,b:75};let total=0;const values=parts.map(([name,value])=>{const start=total;total+=value;return {name,value,start,end:total};});values.push({name:'Total gain / loss',value:total,start:0,end:total,final:true});const extent=d3.extent(values.flatMap(d=>[d.start,d.end]));const pad=(extent[1]-extent[0])*.13||1;const y=d3.scaleLinear().domain([Math.min(0,extent[0])-pad,Math.max(0,extent[1])+pad]).nice().range([H-m.b,m.t]),x=d3.scaleBand().domain(values.map(d=>d.name)).range([m.l,W-m.r]).padding(.25);d3.select('#waterfall').selectAll('*').remove();const svg=d3.select('#waterfall').append('svg').attr('viewBox',`0 0 ${W} ${H}`).attr('role','img').attr('aria-label','Cash flow waterfall from stock cost and original premium to closing gain');svg.append('g').attr('transform',`translate(${m.l},0)`).call(d3.axisLeft(y).ticks(6).tickFormat(d3.format('~s')));svg.append('line').attr('x1',m.l).attr('x2',W-m.r).attr('y1',y(0)).attr('y2',y(0)).attr('stroke','#8a9aaa');svg.selectAll('rect').data(values).join('rect').attr('x',d=>x(d.name)).attr('y',d=>y(Math.max(d.start,d.end))).attr('width',x.bandwidth()).attr('height',d=>Math.max(1,Math.abs(y(d.start)-y(d.end)))).attr('fill',d=>d.final?'#254f86':d.value>=0?'#258564':'#c15a43');svg.selectAll('text.amount').data(values).join('text').attr('x',d=>x(d.name)+x.bandwidth()/2).attr('y',d=>y(Math.max(d.start,d.end))-10).attr('text-anchor','middle').attr('font-family','system-ui').attr('font-size',14).text(d=>(d.value>=0?'+':'−')+money(Math.abs(d.value)));svg.selectAll('text.label').data(values).join('text').attr('x',d=>x(d.name)+x.bandwidth()/2).attr('y',H-m.b+25).attr('text-anchor','middle').attr('font-family','system-ui').attr('font-size',13).text(d=>d.name);}
function renderOptionDetails(){
 const target=$('option-details');target.replaceChildren();
 const number=(v,digits=4)=>typeof v==='number'&&Number.isFinite(v)?v.toFixed(digits):'Unavailable';
 const multiplier=data.premium.contracts*100;
 const values=[['Contract',`${data.premium.symbol} $${data.premium.strike} call · ${data.premium.expiry} · ${data.premium.contracts} contracts`],
 ['Saved bid / ask (USD per share)',`${number(data.option.bidPrice,2)} / ${number(data.option.askPrice,2)}`],
 ['Delta · long call',number(data.option.delta)],['Theta · long call (USD/share/day)',number(data.option.theta,6)],
 ['Implied volatility · annualized',typeof data.option.volatility==='number'?number(data.option.volatility,2)+'%':'Unavailable'],
 ['Your short calls · delta (share equivalent)',typeof data.option.delta==='number'?number(-data.option.delta*multiplier,2):'Unavailable'],
 ['Your short calls · theta (USD/day)',typeof data.option.theta==='number'?number(-data.option.theta*multiplier,2):'Unavailable']];
 for(const [label,value] of values){const r=document.createElement('div');r.className='row';const a=document.createElement('span'),b=document.createElement('strong');a.textContent=label;b.textContent=value;r.append(a,b);target.append(r);}
 $('greeks-note').textContent=`Source: ${data.quote_source} · captured ${new Date(data.quote_time).toLocaleString('en-CA',{timeZone:'America/Vancouver',timeZoneName:'short'})}. Greeks describe the saved option snapshot and do not update when you edit prices. Delta approximates option-price sensitivity to a $1 stock move; theta approximates daily time decay, other inputs unchanged. Short-call signs reverse the long-call Greeks. These are sensitivities, not guaranteed returns. They do not enter the cash-flow calculation; the entered ask determines buyback cost.`;
 const link=document.createElement('a');link.href='https://www.questrade.com/api/documentation/rest-operations/market-calls/markets-quotes-options';link.textContent='Questrade option quote API';$('greeks-note').append(document.createTextNode(' '),link);
}
renderOptionDetails();
function render(){
 if(!$('inputs').reportValidity()){$('assessment-status').textContent='Enter valid scenario inputs before generating an assessment.';return;}
 const bid=Number($('bid').value),ask=Number($('ask').value),reference=Number($('reference').value),sf=Number($('stockfees').value),cf=Number($('callfees').value);
 if(![bid,ask,reference,sf,cf].every(Number.isFinite)||bid<=0||reference<=0||Math.min(ask,sf,cf)<0){$('error').textContent='Enter valid nonnegative prices and fees, with positive stock bid and FX reference.';return;}
 if(today>data.premium.expiry){$('error').textContent='This call has expired; the close-today simulation is no longer applicable.';return;}
 const usdStock=data.basis.quantity*bid-sf,usdCall=data.premium.contracts*100*ask+cf;
 if(usdStock<0){$('error').textContent='Stock closing fees exceed stock proceeds.';return;}$('error').textContent='';
 const sale=fx('sell_usd',usdStock,reference),buy=fx('buy_usd',usdCall,reference),netUsd=usdStock-usdCall,net=fx(netUsd>=0?'sell_usd':'buy_usd',Math.abs(netUsd),reference),separate=$('treatment').value==='separate';
 const cash=separate?r2(sale.cad-buy.cad):r2((netUsd>=0?1:-1)*net.cad),basis=data.basis.cadTotal,premium=data.premium.net_cad,gain=r2(premium-basis+cash);
 $('original').replaceChildren();row($('original'),`Stock cost · ${data.basis.date}`,-basis);row($('original'),`Call premium received · ${data.premium.settlement_date}`,premium);row($('original'),'Net opening cash flow',premium-basis);
 $('closing').replaceChildren();if(separate){row($('closing'),'Stock sale after entered fees',sale.cad,`USD ${usdStock.toFixed(2)} × predicted sell rate ${sale.rate.toFixed(5)} CAD/USD`);row($('closing'),'Call buyback including entered fees',-buy.cad,`USD ${usdCall.toFixed(2)} × predicted buy rate ${buy.rate.toFixed(5)} CAD/USD`);}else{row($('closing'),'USD balance converted to CAD',cash,`USD ${Math.abs(netUsd).toFixed(2)} × predicted ${netUsd>=0?'sell':'buy'} rate ${net.rate.toFixed(5)} CAD/USD`);}$('closing').prepend(Object.assign(document.createElement('p'),{textContent:'Close today: '+today}));row($('closing'),'Net closing cash flow',cash,'Derived from the model-converted closing cash flows above.');
 $('model-rates').replaceChildren();
 for(const [label,value] of [['Reference input · '+(Number($('reference').value)===data.reference?'Yahoo Finance':'manual override'),reference],['Predicted CIBC rate · sell USD',sale.rate],['Predicted CIBC rate · buy USD',buy.rate]]){const p=document.createElement('p'),strong=document.createElement('strong');strong.textContent=value.toFixed(5)+' CAD per USD';p.append(document.createTextNode(label+': '),strong);$('model-rates').append(p);}
 $('rates').textContent=separate?`Model sell-USD rate: ${sale.rate.toFixed(5)}; buy-USD rate: ${buy.rate.toFixed(5)} CAD/USD. USD stock proceeds: ${usdStock.toFixed(2)}; call cost: ${usdCall.toFixed(2)}.`:`Net USD balance: ${netUsd.toFixed(2)}. Model conversion rate: ${net.rate.toFixed(5)} CAD/USD.`;
 const parts=[['Stock purchase',-basis],['Premium received',premium],...(separate?[['Sell stock',sale.cad],['Buy back calls',-buy.cad]]:[['Net closing cash',cash]])];draw(parts);
 $('result').className='card '+(gain>=0?'gain':'loss');$('result').replaceChildren();const title=document.createElement('h2');title.textContent='Estimated total realized '+(gain>=0?'gain':'loss');const value=document.createElement('div');value.className='value';value.textContent=money(gain);const formula=document.createElement('p');formula.textContent=`${money(premium)} premium − ${money(basis)} stock basis + ${money(cash)} net closing cash = ${money(gain)}. Includes only the closing fees entered above.`;$('result').append(title,value,formula);
 renderRecommendation({cash,gain,usdStock,usdCall,bid,ask,reference,separate,stockFees:sf,callFees:cf});
 $('range').textContent=(separate?sale.outside||buy.outside:net.outside)?'One or more conversion amounts fall outside the model’s training amount range for that direction.':'';
}
let currentAssessmentScenario=null,lastAssessmentSignature=null;
function scenarioSignature(){return JSON.stringify([currentAssessmentScenario,$('assessment-goal').value,data.quote_time]);}
function renderRecommendation(scenario){
 currentAssessmentScenario=scenario;
 if(lastAssessmentSignature&&lastAssessmentSignature!==scenarioSignature())$('assessment-status').textContent='Inputs or quotes changed. The displayed assessment belongs to its saved snapshot; generate again for the current scenario.';
}
function assessmentRequest(){
 if(!$('inputs').reportValidity()||!currentAssessmentScenario)throw new Error('Enter valid closing inputs first.');
 return {goal:$('assessment-goal').value,bid:Number($('bid').value),ask:Number($('ask').value),reference:Number($('reference').value),stock_fees:Number($('stockfees').value),call_fees:Number($('callfees').value),treatment:$('treatment').value};
}
function showAssessment(run){
 $('assessment-result').textContent=`Assessment #${run.id} · ${new Date(run.created_at).toLocaleString('en-CA',{timeZone:'America/Vancouver',timeZoneName:'short'})} · ${run.model}\n\n${run.assessment}`;
 $('assessment-snapshot').textContent=JSON.stringify(run.snapshot||JSON.parse(run.snapshot_json),null,2);
}
async function assessmentSetup(){
 try{const response=await fetch('/api/recommendations/status');if(!response.ok)throw new Error();const setup=await response.json();$('assessment-status').textContent=setup.configured?`OpenAI configured · ${setup.model}. Ready for a fresh assessment.`:'OpenAI is not configured. In your terminal run: python3 coveredCallOptimizer/setup_openai.py. Enter the key there, never in this page or chat.';}catch{$('assessment-status').textContent='Assessment service unavailable. Start the report server with coveredCallOptimizer/close_simulator_server.py.';}
}
async function loadAssessmentHistory(){
 const response=await fetch('/api/recommendations/history');const result=await response.json();if(!response.ok)throw new Error(result.error||'History unavailable.');
 const panel=$('assessment-history');panel.replaceChildren();if(!result.runs.length){panel.textContent='No assessments saved yet.';return;}
 for(const run of result.runs){const button=document.createElement('button');button.type='button';button.style.margin='4px';button.textContent=`#${run.id} · ${new Date(run.created_at).toLocaleString('en-CA',{timeZone:'America/Vancouver'})} · ${run.model}`;button.addEventListener('click',()=>{showAssessment(run);lastAssessmentSignature=null;$('assessment-status').textContent='Viewing a saved assessment and its original snapshot, not a fresh assessment of current prices.';});panel.append(button);}
}
$('recommendation-button').addEventListener('click',()=>{const panel=$('recommendation'),button=$('recommendation-button');panel.hidden=!panel.hidden;button.setAttribute('aria-expanded',String(!panel.hidden));button.textContent=panel.hidden?'Recommendation':'Hide recommendation';if(!panel.hidden){assessmentSetup();loadAssessmentHistory().catch(error=>{$('assessment-history').textContent=error.message;});}});
$('assessment-goal').addEventListener('change',()=>{if(currentAssessmentScenario)renderRecommendation(currentAssessmentScenario);});
$('generate-assessment').addEventListener('click',async()=>{
 const button=$('generate-assessment'),status=$('assessment-status');let request;
 try{request=assessmentRequest();}catch(error){status.textContent=error.message;return;}
 const signature=scenarioSignature();button.disabled=true;$('refresh-quotes').disabled=true;
 const controls=[...$('inputs').querySelectorAll('input,select'),$('assessment-goal')];controls.forEach(n=>n.disabled=true);
 status.textContent='Loading local records, calculating cash flows, and requesting an OpenAI assessment…';
 try{
  const response=await fetch('/api/recommendations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request)});let result;try{result=await response.json();}catch{throw new Error('Assessment service returned an invalid response.');}
  if(!response.ok)throw new Error(result.error||'Assessment failed.');
  showAssessment(result);lastAssessmentSignature=signature;status.textContent=`Completed: server calculations → OpenAI assessment → saved locally as run #${result.id}.`;
  await loadAssessmentHistory();
 }catch(error){status.textContent=error.message;}
 finally{button.disabled=false;$('refresh-quotes').disabled=false;controls.forEach(n=>n.disabled=false);}
});
function renderSources(){
 const items=[
  ['Stock bid',Number($('bid').value)===data.stock.bidPrice?`${data.quote_source} · saved stock bid`:'Manual scenario override'],
  ['Call ask',Number($('ask').value)===data.option.askPrice?`${data.quote_source} · exact held call: ASTS $40, January 21, 2028`:'Manual scenario override'],
  ['Reference FX input (not a model prediction)',Number($('reference').value)===data.reference?`${data.reference_source} · CAD=X reference`:'Manual scenario override'],
  ['Stock cost basis',`CIBC purchase confirmation · ${data.basis.date} · SQLite stock_cost_basis record ${data.basis.id}`],
  ['Opening call premium',`CIBC sale confirmation · ${data.premium.settlement_date} · SQLite option_premiums record ${data.premium.id}`],
  ['Predicted CIBC FX outputs',`Local cibc_fx model · fitted ${data.model.trained_at.slice(0,10)} · ${data.model.samples} reviewed CIBC transaction samples with Yahoo settlement-day references`],
  ['Closing fees','User-entered estimates; not fetched from CIBC or Questrade'],
  ['Conversion treatment','User-selected assumption; not confirmed by a CIBC API']
 ];
 $('sources').replaceChildren();const heading=document.createElement('h3');heading.textContent='Data sources';$('sources').append(heading);
 for(const [label,text] of items){const p=document.createElement('p'),b=document.createElement('strong');b.textContent=label+': ';p.append(b,document.createTextNode(text));$('sources').append(p);}
}
$('refresh-quotes').addEventListener('click',async()=>{
 const button=$('refresh-quotes'),status=$('refresh-status');button.disabled=true;
 const controls=[...$('inputs').querySelectorAll('input,select')];controls.forEach(n=>n.disabled=true);
 status.textContent='Refreshing Questrade quotes and Yahoo reference FX…';
 try{
  const response=await fetch('/api/quotes/refresh',{method:'POST'});let next;
  try{next=await response.json();}catch{throw new Error('Start the model report server with coveredCallOptimizer/close_simulator_server.py to enable quote refresh.');}
  if(!response.ok)throw new Error(next.error||'Quote refresh failed.');
  if(![next.stock?.bidPrice,next.option?.askPrice,next.reference].every(v=>typeof v==='number'&&Number.isFinite(v)&&v>0))throw new Error('Incomplete quote response; previous inputs retained.');
  Object.assign(data,next);$('bid').value=data.stock.bidPrice;$('ask').value=data.option.askPrice;$('reference').value=data.reference;
  controls.forEach(n=>n.disabled=false);renderSnapshot();renderOptionDetails();renderSources();render();
  const delayed=[data.stock.delay,data.option.delay].some(v=>typeof v==='number'&&v>0);
  status.textContent='Quotes refreshed. Prices, Greeks and FX estimates updated; model parameters unchanged.'+(delayed?' Broker reports delayed quotes; check their age before using the estimate.':'');
 }catch(error){status.textContent=error.message+' Previous scenario values remain displayed.';}
 finally{button.disabled=false;controls.forEach(n=>n.disabled=false);}
});
$('inputs').addEventListener('input',renderSources);renderSources();
$('inputs').addEventListener('input',render);$('inputs').addEventListener('submit',e=>e.preventDefault());render();
</script></html>'''
html=html.replace('__D3__',(ROOT/'coveredCallOptimizer/vendor/d3.min.js').read_text()).replace('__DATA__',json.dumps(data).replace('<','\\u003c'))
output=HERE/'reports/covered-call-close.html';output.parent.mkdir(parents=True,exist_ok=True);output.write_text(html);print(output)
