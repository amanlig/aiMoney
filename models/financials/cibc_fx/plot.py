"""Create a standalone interactive D3 report using local data and model outputs."""
import json
from pathlib import Path
from train import load
from model import predict

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
rows,_=load(ROOT/'data/fx-samples.sqlite3')
model=json.loads((HERE/'artifacts/model.json').read_text())
report=json.loads((HERE/'evaluation/holdout.json').read_text())
evaluated={'parameters':report['evaluated_parameters']}
points=[]
for row in rows:
    holdout=row['settlement_date']>=report['test_start']
    prediction=predict(evaluated,row['direction'],row['yahoo_close'],row['usd_amount']) if holdout else None
    points.append({**{k:row[k] for k in ['id','settlement_date','direction','usd_amount','cad_amount','applied_rate','yahoo_close']},
                   'adjustment':100*(row['applied_rate']/row['yahoo_close']-1),
                   'holdout':holdout,'prediction':prediction})
html='''<!doctype html><meta charset="utf-8"><title>CIBC FX model — data and evaluation</title>
<style>body{font:16px system-ui;margin:32px auto;max-width:1200px;padding:0 20px;color:#17283c;background:#f4f7fb}h1{font-size:28px}h2{font-size:20px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(460px,1fr));gap:20px}section{background:white;padding:20px;border-radius:12px;border:1px solid #dbe3ee}svg{width:100%;height:auto}p{line-height:1.5}.tip{position:fixed;pointer-events:none;background:#17283c;color:white;padding:10px;border-radius:6px;white-space:pre-line;font-size:13px;display:none}.buy{color:#176db0}.sell{color:#d46620}button{padding:7px 12px;cursor:pointer}small{color:#4b5e72}.legend{display:flex;gap:24px}</style>
<h1>CIBC FX model: what the 55 transactions show</h1>
<p class="legend"><b class="buy">● Buy USD</b><b class="sell">● Sell USD</b><span>Hover over a point for transaction details.</span></p>
<p id="summary"></p><section><h2>How the model components interact</h2><p>The code uses functions and model dictionaries. This UML sequence follows training, evaluation, and a later prediction. The evaluation model uses earlier samples; the final model is refitted on all eligible samples.</p>__UML__</section><p>Solid arrows are requests; dashed arrows return data. The database is read-only throughout.</p><div class="cards">
<section><h2>1. Recorded conversion rates over time</h2><p>Colored points are CIBC applied rates. Gray points are the saved settlement-day Yahoo reference. Dates use their actual spacing.</p><div id="time"></div></section>
<section><h2>2. Adjustment relative to Yahoo</h2><p>Each point is (CIBC rate ÷ Yahoo rate − 1) × 100. Horizontal lines show the final model’s median adjustment, fitted on all 55 samples.</p><div id="spread"></div></section>
<section><h2>3. Held-out CAD totals: predicted vs actual</h2><p>These 20 later transactions were excluded when fitting the evaluation model. Points on the dashed diagonal are exact estimates.</p><div id="parity"></div></section>
<section><h2>4. Held-out error by transaction size</h2><p>Error = predicted CAD − actual CAD. Zero means exact. These predictions use only the earlier-data model.</p><div id="error"></div></section></div>
<p><b>Reading the results:</b> buying USD generally costs more CAD than the Yahoo reference; selling USD generally returns less. The model estimates a separate proportional adjustment for each direction. It does not currently use ticker, security type, account, or amount as features.</p>
<p><b>Limits:</b> Yahoo daily closes are retrospective. Differences include broker pricing and reference timing; they are not a direct measurement of broker fees. Multiple transactions share dates. There are no samples after November 2025. Holdout results do not establish live-rate accuracy.</p>
<div class="tip"></div><script>__D3__</script><script>
const rows=__DATA__, model=__MODEL__, report=__REPORT__;
const colors={buy_usd:'#176db0',sell_usd:'#d46620'},tip=d3.select('.tip');
const test=rows.filter(d=>d.holdout), W=540,H=340,m={top:18,right:20,bottom:62,left:78};
rows.forEach(d=>d.date=d3.utcParse('%Y-%m-%d')(d.settlement_date));
document.querySelector('#summary').textContent=`${rows.length} samples across ${new Set(rows.map(d=>d.settlement_date)).size} settlement dates. Evaluation: ${report.train_samples} earlier training samples, ${report.test_samples} later test samples. Mean absolute test error: ${report.overall.mean_absolute_percentage_cad_error.toFixed(3)}% ($${report.overall.mean_absolute_cad_error.toFixed(2)} CAD).`;
function frame(id,x,y,xlabel,ylabel){
 const container=d3.select('#'+id),svg=container.append('svg').attr('viewBox',`0 0 ${W} ${H}`).attr('role','img').attr('aria-label',ylabel+' versus '+xlabel);
 svg.append('g').attr('transform',`translate(0,${H-m.bottom})`).call(d3.axisBottom(x).ticks(5));
 svg.append('g').attr('transform',`translate(${m.left},0)`).call(d3.axisLeft(y).ticks(6));
 svg.append('text').attr('x',(W+m.left-m.right)/2).attr('y',H-12).attr('text-anchor','middle').attr('font-size',13).text(xlabel);
 svg.append('text').attr('transform','rotate(-90)').attr('x',-(H-m.bottom+m.top)/2).attr('y',17).attr('text-anchor','middle').attr('font-size',13).text(ylabel);
 container.append('button').text('Download SVG').on('click',()=>{const copy=svg.node().cloneNode(true);copy.setAttribute('xmlns','http://www.w3.org/2000/svg');const url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(copy)],{type:'image/svg+xml'}));const a=document.createElement('a');a.href=url;a.download='cibc-fx-'+id+'.svg';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});
 return svg;
}
function dots(svg,data,x,y){svg.selectAll('circle.transaction').data(data).join('circle').attr('class','transaction').attr('cx',x).attr('cy',y).attr('r',4.5).attr('fill',d=>colors[d.direction]).attr('fill-opacity',.75).attr('stroke','white').on('mousemove',(e,d)=>tip.style('display','block').style('left',Math.min(e.clientX+14,innerWidth-270)+'px').style('top',Math.min(e.clientY+12,innerHeight-150)+'px').text(`ID ${d.id} · ${d.settlement_date}\n${d.direction} · USD ${d.usd_amount.toFixed(2)}\nActual CAD ${d.cad_amount.toFixed(2)}\nRate ${d.applied_rate.toFixed(4)} · Yahoo ${d.yahoo_close.toFixed(4)}\nAdjustment ${d.adjustment.toFixed(3)}%`+(d.prediction?`\nEstimated CAD ${d.prediction.estimated_cad.toFixed(2)}`:''))).on('mouseleave',()=>tip.style('display','none'));}
function linear(values){return d3.scaleLinear().domain(d3.extent(values)).nice().range([H-m.bottom,m.top])}
const tx=d3.scaleUtc().domain(d3.extent(rows,d=>d.date)).range([m.left,W-m.right]);
const ty=linear(rows.flatMap(d=>[d.applied_rate,d.yahoo_close]));
let svg=frame('time',tx,ty,'Settlement date','CAD per USD');
svg.selectAll('circle.reference').data(rows).join('circle').attr('cx',d=>tx(d.date)).attr('cy',d=>ty(d.yahoo_close)).attr('r',3).attr('fill','#888');dots(svg,rows,d=>tx(d.date),d=>ty(d.applied_rate));
const sx=d3.scaleLog().domain([300,50000]).range([m.left,W-m.right]),sy=linear([...rows.map(d=>d.adjustment),0]);
svg=frame('spread',sx,sy,'USD converted (log scale)','Adjustment vs Yahoo (%)');
for(const [dir,p] of Object.entries(model.parameters)){svg.append('line').attr('x1',m.left).attr('x2',W-m.right).attr('y1',sy(p.adjustment*100)).attr('y2',sy(p.adjustment*100)).attr('stroke',colors[dir]).attr('stroke-dasharray','6 4');}
dots(svg,rows,d=>sx(d.usd_amount),d=>sy(d.adjustment));
const max=d3.max(test,d=>Math.max(d.cad_amount,d.prediction.estimated_cad))*1.06;
const px=d3.scaleLinear().domain([0,max]).range([m.left,W-m.right]),py=d3.scaleLinear().domain([0,max]).range([H-m.bottom,m.top]);
svg=frame('parity',px,py,'Actual CAD total','Predicted CAD total');svg.append('line').attr('x1',px(0)).attr('y1',py(0)).attr('x2',px(max)).attr('y2',py(max)).attr('stroke','#888').attr('stroke-dasharray','6 4');dots(svg,test,d=>px(d.cad_amount),d=>py(d.prediction.estimated_cad));
const ex=d3.scaleLinear().domain([0,d3.max(test,d=>d.usd_amount)*1.06]).range([m.left,W-m.right]),ey=linear([0,...test.map(d=>d.prediction.estimated_cad-d.cad_amount)]);
svg=frame('error',ex,ey,'USD converted','Prediction error (CAD)');svg.append('line').attr('x1',m.left).attr('x2',W-m.right).attr('y1',ey(0)).attr('y2',ey(0)).attr('stroke','#888').attr('stroke-dasharray','6 4');dots(svg,test,d=>ex(d.usd_amount),d=>ey(d.prediction.estimated_cad-d.cad_amount));
</script>'''
html=html.replace('__UML__',(HERE/'interactions.svg').read_text())
html=html.replace('__D3__',(ROOT/'vendor/d3.min.js').read_text()).replace('__DATA__',json.dumps(points)).replace('__MODEL__',json.dumps(model)).replace('__REPORT__',json.dumps(report))
output=HERE/'evaluation/data-plots.html'
output.write_text(html)
print(output)
