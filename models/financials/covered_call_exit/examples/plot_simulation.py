"""Render the synthetic reference chart. Optional dependency: matplotlib.

Run from the downloaded package: python3 examples/plot_simulation.py
The model and example runner themselves require only Python's standard library.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('exit_model',ROOT/'model.py')
model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
data=json.loads((ROOT/'examples/sample_input.json').read_text())
result=model.evaluate(data)
result_bytes=(json.dumps(result,indent=2)+'\n').encode()
close=next(r for r in result['rows'] if r['strategy']=='Close now')
rolls=sorted((r for r in result['rows'] if r['strategy']=='Roll then close'),key=lambda r:r['total_pl_usd'],reverse=True)
rows=[close]+rolls
labels=['Close now\nCaptured bid / ask']+[
    f"Roll to ${r['strike']:.0f} call\n{r['expiry']} expiry" for r in rolls]
profits=[r['total_pl_usd'] for r in rows]
# Translate liquidation-wealth quantiles to the exact same whole-position P/L basis.
adjustment=profits[0]-close['mean']
p10=[r['p10']+adjustment for r in rows]
p90=[r['p90']+adjustment for r in rows]
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':12,'svg.fonttype':'none','text.parse_math':False})
fig,ax=plt.subplots(figsize=(13,8.5),facecolor='#f5f7fb')
fig.subplots_adjust(left=.24,right=.94,top=.73,bottom=.32)
ax.set_facecolor('#f5f7fb')
colors=['#64748b']+['#7255cf']*len(rolls)
ax.barh(range(len(rows)),profits,height=.52,color=colors,zorder=2)
for i,r in enumerate(rows):
    if i:
        ax.plot([p10[i],p90[i]],[i,i],color='#182b49',linewidth=2,zorder=3)
        ax.plot([p10[i],p10[i]],[i-.10,i+.10],color='#182b49',linewidth=2)
        ax.plot([p90[i],p90[i]],[i-.10,i+.10],color='#182b49',linewidth=2)
    ax.text(max(profits[i],p90[i])+45,i,f'${profits[i]:,.2f}',va='center',color='#182b49',weight='bold',fontsize=12)
ax.axvline(0,color='#182b49',linewidth=1)
ax.axvline(profits[0],color='#64748b',linewidth=1.5,linestyle='--',zorder=1)
ax.set_yticks(range(len(rows)),labels)
ax.invert_yaxis()
ax.set_xlim(0,max(p90)*1.19)
ax.xaxis.set_major_formatter(FuncFormatter(lambda x,pos:f'${x:,.0f}'))
ax.set_xlabel('Whole-position profit / loss (USD)',labelpad=12,color='#182b49')
ax.grid(axis='x',alpha=.17,zorder=0)
ax.set_axisbelow(True)
ax.tick_params(axis='both',length=0,labelcolor='#182b49')
for edge in ['top','right','left']:ax.spines[edge].set_visible(False)
ax.spines['bottom'].set_color('#ced6e3')
fig.text(.055,.94,'Close today or roll the covered call?',fontsize=24,weight='bold',color='#182b49')
fig.text(.055,.895,'SYNTHETIC DEMO  ·  Historical bootstrap + Black–Scholes option pricing',fontsize=13,color='#7255cf',weight='bold')
fig.text(.055,.844,'100 shares · 1 short call · stock $50 midpoint · purchase cost $3,005\nHeld call: $40 strike, Jan 15, 2027 · recorded net option cash: $800 incl. prior cycles',fontsize=12,color='#344866',linespacing=1.6)
fig.text(.055,.19,'Bars: estimated total profit. Dark whiskers: 10th–90th percentiles of simulated profit.\nDashed line: close-now profit. Rollovers ranked by mean profit; same 600 paths, seed 42.',fontsize=11.5,color='#344866',linespacing=1.6)
fig.text(.055,.075,'Roll now, then liquidate after 30 trading days; earlier expiry settles within the path.\n4% annual rate · calibrated IV and spreads held constant · future fees / taxes excluded.\nEntirely fictional data. Scenario output, not a validated forecast or investment return.',fontsize=10.5,color='#53647e',linespacing=1.6)
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir',type=Path,default=ROOT/'examples')
output_dir=parser.parse_args().output_dir
output_dir.mkdir(parents=True,exist_ok=True)
out=output_dir/'simulation-profit.png'
fig.savefig(out,dpi=180,facecolor=fig.get_facecolor())
plt.close(fig)
provenance={'sample_input_sha256':hashlib.sha256((ROOT/'examples/sample_input.json').read_bytes()).hexdigest(),
            'expected_result_sha256':hashlib.sha256(result_bytes).hexdigest(),
            'chart_sha256':hashlib.sha256(out.read_bytes()).hexdigest()}
(output_dir/'simulation-chart-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
print('Rendered',out)
