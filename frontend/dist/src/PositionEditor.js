import {Input} from './Input.js';
import {html, useState, useEffect} from './ui.js';
import {api, holdingLabel} from './api.js';

export function PositionEditor({mode, holding, onCancel, onSaved}) {
  const [stocks,setStocks]=useState([]), [ready,setReady]=useState(false), [busy,setBusy]=useState(false), [status,setStatus]=useState('');
  const [fields,setFields]=useState({stock:'0',shares:holding?.shares || '',contracts:holding?.call_contracts || '',strike:'',expiry:''});
  useEffect(() => {api('/api/positions/availability').then(data => {
    setStocks(data.stocks); const index=data.stocks.findIndex(s => s.account===holding?.account && s.symbol===holding?.symbol);
    setFields(old => ({...old,stock:String(Math.max(0,index)),...(mode==='new' ? {shares:'',contracts:''} : {})}));setReady(true);
  }).catch(e => setStatus(e.message));}, []);
  const stock=stocks[Number(fields.stock)];
  const update=(key,value) => setFields(old => ({...old,[key]:value,...(key==='contracts' ? {shares:Number(value)*100} : {})}));
  async function save(event) {
    event.preventDefault();setBusy(true);
    try {
      const result=mode==='allocation'
        ? await api(`/api/positions/${holding.position_id}/allocation`,{body:{shares:Number(fields.shares)}})
        : await api('/api/positions',{body:{account:stock.account,symbol:stock.symbol,shares:Number(fields.shares),contracts:Number(fields.contracts),strike:Number(fields.strike),expiry:fields.expiry}});
      await onSaved(result);
    } catch(e) {setStatus(e.message);setBusy(false);}
  }
  return html`<section className="position-editor"><h3>${mode==='new' ? 'Add covered-call position' : 'Allocate shares'}</h3>
    <form onSubmit=${save}>
      ${mode==='new' ? html`<label>Stock / account<select aria-label="Stock / account" disabled=${!ready || busy} value=${fields.stock} onChange=${e => update('stock',e.target.value)}>${stocks.map((s,i) => html`<option key=${i} value=${i}>${s.account} · ${s.symbol}</option>`)}</select></label>` : html`<p>${holdingLabel(holding)}</p>`}
      ${stock ? html`<p>Recorded shares: ${stock.total_shares} · Already allocated: ${stock.allocated_shares} · Available: ${stock.available_shares}</p>` : null}
      <p>Each position has one opening sale. Allocate at least 100 shares per call; shares allocated to closed positions remain consumed by their recorded sale.</p>
      <div className="fields">${(mode==='new' ? [['contracts','Call contracts','number'],['shares','Allocated shares','number'],['strike','Call strike (USD)','number'],['expiry','Call expiry','date']] : [['shares','Allocated shares','number']]).map(([key,label,type]) => html`<label key=${key}>${label}<${Input} required type=${type} min="0.00000001" step=${key==='contracts' ? '1' : 'any'} value=${fields[key]} disabled=${busy} onChange=${e => update(key,e.target.value)}/></label>`)}</div>
      <div className="entry-actions"><button disabled=${!ready || !stock || busy}>${mode==='new' ? 'Create position' : 'Save allocation'}</button><button type="button" disabled=${busy} onClick=${onCancel}>Cancel</button></div><p role="status">${status}</p>
    </form>
  </section>`;
}
