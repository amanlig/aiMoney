import {Input} from './Input.js';
import {html,useState,useEffect,useRef} from './ui.js';
import {api,money,holdingLabel} from './api.js';

export function NewHolding({holding,onClose,onSaved}) {
  const dialog=useRef();
  const [fields,setFields]=useState({account:holding?.account || 'RRSP',symbol:'',purchase_date:'',shares:'',price_usd:'',fees_usd:'0'});
  const [busy,setBusy]=useState(false),[status,setStatus]=useState('');
  useEffect(() => {dialog.current.showModal();},[]);
  async function save(event) {
    event.preventDefault();setBusy(true);setStatus('Saving stock purchase…');
    try {const result=await api('/api/holdings',{body:{...fields,shares:Number(fields.shares),price_usd:Number(fields.price_usd),fees_usd:Number(fields.fees_usd)}});await onSaved(result);}
    catch(error){setStatus(error.message);setBusy(false);}
  }
  return html`<dialog ref=${dialog} id="new-holding" aria-labelledby="new-holding-title" onCancel=${event => {if(busy)event.preventDefault();else onClose();}} onClose=${() => {if(!busy)onClose();}}>
    <div className="settings-header"><h2 id="new-holding-title">New holding</h2><button type="button" aria-label="Cancel new holding" disabled=${busy} onClick=${onClose}>×</button></div>
    <p>Start with the stock purchase. Add the option opening sale in Transactions when ready. All amounts are USD.</p>
    <form onSubmit=${save}><div className="fields"><label>Account<select disabled=${busy} value=${fields.account} onChange=${e => setFields({...fields,account:e.target.value})}>${['RRSP','TFSA','LIRA'].map(account => html`<option key=${account}>${account}</option>`)}</select></label>
      ${[['symbol','Ticker','text'],['purchase_date','Purchase date','date'],['shares','Shares purchased','number'],['price_usd','Purchase price (USD/share)','number'],['fees_usd','Purchase fees (USD)','number']].map(([key,label,type]) => html`<label key=${key}>${label}<${Input} required disabled=${busy} type=${type} min=${key==='fees_usd' ? '0' : '0.00000001'} step="any" value=${fields[key]} onChange=${e => setFields({...fields,[key]:key==='symbol' ? e.target.value.toUpperCase() : e.target.value})}/></label>`)}</div>
      <p>Total stock cost: ${fields.shares!=='' && fields.price_usd!=='' && fields.fees_usd!=='' ? money(Number(fields.shares)*Number(fields.price_usd)+Number(fields.fees_usd)) : '—'}</p>
      <div className="entry-actions"><button disabled=${busy}>Create holding</button><button type="button" disabled=${busy} onClick=${onClose}>Cancel</button></div><p role="status">${status}</p>
    </form>
  </dialog>`;
}

export function DeleteHolding({holding,onClose,onDeleted}) {
  const dialog=useRef();
  const [preview,setPreview]=useState(null),[confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[status,setStatus]=useState('Loading holding records…');
  useEffect(() => {
    dialog.current.showModal();const controller=new AbortController();
    api(`/api/positions/${holding.position_id}/delete-preview`,{signal:controller.signal}).then(data => {setPreview(data);setStatus('');}).catch(error => {if(error.name!=='AbortError')setStatus(error.message);});
    return () => controller.abort();
  },[]);
  async function remove(event) {
    event.preventDefault();setBusy(true);setStatus('Deleting holding and records…');
    try {const result=await api(`/api/positions/${holding.position_id}/delete`,{body:{confirmed,position_revision:preview.holding.position_revision}});await onDeleted(result);}
    catch(error){setStatus(error.message);setBusy(false);}
  }
  return html`<dialog ref=${dialog} id="delete-holding" aria-labelledby="delete-holding-title" onCancel=${event => {if(busy)event.preventDefault();else onClose();}} onClose=${() => {if(!busy)onClose();}}>
    <div className="settings-header"><h2 id="delete-holding-title">Delete holding</h2><button type="button" aria-label="Cancel delete holding" disabled=${busy} onClick=${onClose}>×</button></div>
    <p><strong>${holdingLabel(holding)}</strong></p>
    <p>Delete this holding, its stock purchase allocation, option sales, rollovers, expired-cycle records, saved analyses and recommendations. This cannot be undone.</p>
    ${preview ? html`<p>${preview.opening_sales} opening sales · ${preview.rollovers} rollovers · ${preview.expired_cycles} expired cycles.</p>${preview.shared_purchase ? html`<p>Shared purchase details and history needed by other holdings will be retained.</p>` : null}` : null}
    <form onSubmit=${remove}><label className="review"><${Input} type="checkbox" required checked=${confirmed} disabled=${busy} onChange=${e => setConfirmed(e.target.checked)}/>Delete this holding and all its associated records.</label>
      <div className="entry-actions"><button className="danger" disabled=${busy || !preview || !confirmed}>Delete holding and records</button><button type="button" disabled=${busy} onClick=${onClose}>Cancel</button></div><p role="status">${status}</p>
    </form>
  </dialog>`;
}
