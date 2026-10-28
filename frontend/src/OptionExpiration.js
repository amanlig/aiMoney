import {html, useState, useEffect, useRef} from './ui.js';
import {api, money, holdingLabel} from './api.js';

export function ExpireWorthless({holding, onClose, onSaved}) {
  const dialog=useRef();
  const [preview,setPreview]=useState(null), [fees,setFees]=useState('0'), [reviewed,setReviewed]=useState(false);
  const [busy,setBusy]=useState(false), [status,setStatus]=useState('Loading recorded option history…');
  useEffect(() => {
    dialog.current.showModal();const controller=new AbortController();
    api(`/api/positions/${holding.position_id}/expiration-preview`,{signal:controller.signal}).then(data => {setPreview(data);setStatus('');})
      .catch(e => {if(e.name!=='AbortError') setStatus(e.message);});
    return () => controller.abort();
  }, []);
  const net=preview?.historical_option_net_usd;
  const pl=Number.isFinite(net) && fees!=='' && Number.isFinite(Number(fees)) ? net-Number(fees) : null;
  async function save(event) {
    event.preventDefault();setBusy(true);setStatus('Recording expiry…');
    try {
      const record=await api(`/api/positions/${holding.position_id}/expire-worthless`,{body:{fees_usd:Number(fees),position_revision:holding.position_revision,reviewed}});
      await onSaved(record);
    } catch(e) {setStatus(e.message);setBusy(false);}
  }
  return html`<dialog ref=${dialog} id="expire-option" aria-labelledby="expire-option-title" onCancel=${e => {if(busy)e.preventDefault();else onClose();}} onClose=${() => {if(!busy)onClose();}}>
    <div className="settings-header"><h2 id="expire-option-title">Expired worthless</h2><button type="button" aria-label="Cancel expired worthless" disabled=${busy} onClick=${onClose}>×</button></div>
    <p><strong>${holdingLabel(holding)}</strong></p>
    <p>End this call with no stock sale and no buyback. All ${holding.shares} shares remain held, and the holding stays selectable as Stock only. Record the next call in Transactions → Option Opening Sale. Recorded opening and rollover cash flows are included once in realized option P/L; stock gains and losses are excluded.</p>
    ${preview && !preview.can_mark_expired ? html`<p>Available after the expiry date, once your broker confirms no assignment.</p>` : null}
    <form onSubmit=${save}>
      <label>Expiration fees (USD)<input required disabled=${busy} type="number" min="0" step="any" value=${fees} onChange=${e => {setFees(e.target.value);setReviewed(false);}}/></label>
      <p>Realized option P/L: <strong>${pl===null ? 'Unavailable' : money(pl)}</strong><br/>Cash at expiry: ${fees!=='' ? money(Number(fees) ? -Number(fees) : 0) : '—'} · Stock sale: ${money(0)} · Buyback: ${money(0)}</p>
      ${preview && net==null ? html`<p>${preview.accounting.history_note} You can still record the expiry; P/L will be stored as unavailable.</p>` : null}
      <label className="review"><input required type="checkbox" disabled=${busy} checked=${reviewed} onChange=${e => setReviewed(e.target.checked)}/>My broker confirms this call expired worthless, no assignment occurred, and I still hold the shares.</label>
      <div className="entry-actions"><button disabled=${busy || !preview?.can_mark_expired}>Record worthless expiry</button><button type="button" disabled=${busy} onClick=${onClose}>Cancel</button></div>
      <p role="status">${status}</p>
    </form>
  </dialog>`;
}
