import {html, useState, useEffect} from './ui.js';
import {api, money} from './api.js';

const price = value => Number.isFinite(value) ? value.toLocaleString('en-CA', {minimumFractionDigits:2, maximumFractionDigits:8}) : '—';
const quantity = value => value.toLocaleString('en-CA', {maximumFractionDigits:8});
const signedGross = entry => entry.signed_gross_usd ?? (entry.action==='Buy' ? -entry.gross_usd : entry.gross_usd);

export function TransactionReport({holding, revision}) {
  const [report,setReport]=useState(null), [status,setStatus]=useState('');
  useEffect(() => {
    setReport(null);
    if(!holding?.position_id) {setStatus('No saved transactions for this holding.');return;}
    const controller=new AbortController();setStatus('Loading transactions…');
    api(`/api/positions/${holding.position_id}/transactions`,{signal:controller.signal})
      .then(data => {setReport(data);setStatus('');})
      .catch(error => {if(error.name!=='AbortError')setStatus(error.message);});
    return () => controller.abort();
  }, [holding?.position_id,revision]);
  const cashEntries=report?.cash_entries || report?.entries.map(entry => ({...entry,option_cash_usd:entry.instrument==='Call' ? entry.cash_flow_usd ?? signedGross(entry)-entry.fees_usd : null})) || [];
  const completed=report?.entries.filter(entry => entry.instrument==='Call' && (entry.expired || ['Buy','Expiry'].includes(entry.action))) || [];
  return html`<section className="transaction-report" aria-labelledby="transaction-report-title">
    <h3 id="transaction-report-title">Transaction report</h3>
    ${report ? html`<p>${report.account} · ${report.symbol} · Selected holding and its linked expired calls · All amounts USD</p>
      <div className="transaction-totals">
        <p>Realized option cash<strong>${money(report.net_option_cash_usd)}</strong></p>
        <p>Rollover net cash<strong>${money(report.net_rollover_cash_usd ?? cashEntries.filter(entry => entry.action==='Rollover').reduce((total,entry) => total+entry.option_cash_usd,0))}</strong></p>
        <p>Open-call premium · included in cash<strong>${money(report.open_call_premium_usd)}</strong></p>
      </div>
      <p>Realized option cash = recorded opening premiums + replacement sales − buybacks − option fees. Each rollover combines both legs. Cash received includes the premium on the still-open call; overall position P/L also needs the stock value and the call’s current closing cost.</p>
      <p>Gross amounts show buys as negative and sales as positive, including stock purchases. The gross total is net cash flow before fees.</p>
      ${report.allocated_history ? html`<p>Linked history is proportional to the retained shares allocated to this holding.</p>` : null}
      ${!report.history_complete ? html`<p role="status">Some option history is missing. Cash totals include the recorded entries only.</p>` : null}
      ${cashEntries.length ? html`<div className="table-scroll" role="region" aria-label="Recorded buy and sell transactions" tabIndex="0"><table>
        <colgroup>${[10,8,24,14,12,13,9,10].map((width,index) => html`<col key=${index} style=${{width:`${width}%`}}/>`)}</colgroup>
        <thead><tr>${['Date','Action','Security / quantity','Price (USD/share)','Gross amount (USD)','Realized option cash (USD)','Fees (USD)','Expired / outcome'].map(title => html`<th key=${title} scope="col">${title}</th>`)}</tr></thead>
        <tbody>${cashEntries.map(entry => html`<tr key=${entry.id}>
          <td>${entry.date || 'Not recorded'}</td><td>${entry.action}</td>
          <td>${entry.instrument==='Stock' ? `${report.symbol} · ${quantity(entry.quantity)} shares` : entry.action==='Rollover' ? html`${report.symbol} · ${quantity(entry.quantity)} calls<br/>Buy $${price(entry.buyback.strike)} · ${entry.buyback.expiry}<br/>Sell $${price(entry.replacement.strike)} · ${entry.replacement.expiry}` : `${report.symbol} · ${quantity(entry.quantity)} calls · $${price(entry.strike)} · ${entry.expiry}`}</td>
          <td>${entry.action==='Rollover' ? html`Buy $${price(entry.buyback.price_usd)}<br/>Sell $${price(entry.replacement.price_usd)}` : entry.price_usd==null ? '—' : `$${price(entry.price_usd)}`}</td><td>${money(signedGross(entry))}</td>
          <td>${entry.option_cash_usd==null ? '—' : money(entry.option_cash_usd)}</td>
          <td>${money(entry.fees_usd)}</td><td>${entry.outcome}</td>
        </tr>`)}</tbody>
        <tfoot><tr><th scope="row" colSpan="4">Totals</th>
          <td><strong>${money(report.gross_cash_flow_usd ?? report.entries.reduce((total,entry) => total+signedGross(entry),0))}</strong></td>
          <td><strong>${money(report.net_option_cash_usd)}</strong></td>
          <td colSpan="2"></td></tr></tfoot>
      </table></div>` : html`<p>No transactions recorded for this holding.</p>`}` : null}
      ${report ? html`<details className="completed-call-detail"><summary>Closed-call accounting detail</summary>
        <p>Closed-call P/L: <strong>${report.realized_option_pl_usd==null ? 'Unavailable — history incomplete' : money(report.realized_option_pl_usd)}</strong>. This compares each completed call’s original sale with its buyback or confirmed expiry, including fees. Replacement sales belong to the new calls. Stock gains and losses are excluded.</p>
        ${completed.length ? html`<div className="table-scroll"><table><thead><tr><th>Date</th><th>Call</th><th>Outcome</th><th>Realized P/L (USD)</th></tr></thead><tbody>
          ${completed.map(entry => html`<tr key=${entry.id}><td>${entry.date}</td><td>${report.symbol} · $${price(entry.strike)} · ${entry.expiry}</td><td>${entry.outcome}</td><td>${entry.realized_pl_usd==null ? 'Unavailable' : money(entry.realized_pl_usd)}</td></tr>`)}
        </tbody></table></div>` : html`<p>No completed calls recorded.</p>`}
      </details>` : null}
    <p role="status">${status}</p>
  </section>`;
}
