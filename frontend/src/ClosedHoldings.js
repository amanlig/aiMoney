import {html, useState, useEffect, useRef} from './ui.js';
import {api, money, holdingLabel} from './api.js';

export function ClosePosition({holding, capture, onClose, onSaved}) {
  const dialog = useRef();
  const [fields, setFields] = useState({close_date: '', stock_price_usd: '', buyback_price_usd: '', fees_usd: '0'});
  const [reviewed, setReviewed] = useState(false), [busy, setBusy] = useState(false), [status, setStatus] = useState('');
  useEffect(() => {dialog.current.showModal();}, []);
  const quotes = capture?.inputs;
  useEffect(() => {setReviewed(false);}, [quotes?.captured_at]);
  const numeric = ['stock_price_usd', 'buyback_price_usd', 'fees_usd'];
  const complete = numeric.every(key => fields[key] !== '' && Number.isFinite(Number(fields[key])));
  const stockSale = holding.shares * Number(fields.stock_price_usd);
  const buyback = holding.call_contracts * 100 * Number(fields.buyback_price_usd);
  const cash = stockSale - buyback - Number(fields.fees_usd);
  async function save(event) {
    event.preventDefault(); setBusy(true); setStatus('Saving…');
    try {
      const body = {account: holding.account, symbol: holding.symbol, position_key: holding.position_key, ...(holding.position_revision ? {position_revision:holding.position_revision} : {}), close_date: fields.close_date, quote_captured_at: quotes?.captured_at || null, reviewed};
      numeric.forEach(key => {body[key] = Number(fields[key]);});
      const record = await api('/api/closed-holdings', {body});
      onSaved(record);
    } catch(e) {setStatus(e.message); setBusy(false);}
  }
  return html`<dialog ref=${dialog} id="close-position" aria-labelledby="close-position-title" onCancel=${e => {if (busy) e.preventDefault(); else onClose();}} onClose=${() => {if (!busy) onClose();}}>
    <div className="settings-header"><h2 id="close-position-title">Close holding</h2><button type="button" aria-label="Cancel close holding" disabled=${busy} onClick=${onClose}>×</button></div>
    <p><strong>${holdingLabel(holding)}</strong><br/>Sell all ${holding.shares} shares and buy back all ${holding.call_contracts} call contracts.</p>
    <p>Record completed trades from your confirmation. Saving moves this holding to Closed holdings and removes it from the active dropdown.</p>
    <fieldset id="close-captured-quotes"><legend>Captured Questrade quotes · USD/share</legend>
      ${quotes ? html`<p>Captured <time dateTime=${quotes.captured_at}>${quotes.captured_at}</time>. Saved market quotes; actual execution prices are entered below.</p><div className="fields">${[['Stock', quotes.stock], ['Held call', quotes.held]].flatMap(([name, quote]) => ['bid', 'ask'].map(side => html`<label key=${name+side}>${name} ${side} (USD/share)<input type="number" step="any" readOnly value=${Number.isFinite(quote?.[side+'Price']) ? quote[side+'Price'] : ''} placeholder="Unavailable"/></label>`))}</div>
      <p>${[['Stock',quotes.stock],['Held call',quotes.held]].map(([name,q]) => `${name}: bid size ${q?.bidSize ?? 'unavailable'}, ask size ${q?.askSize ?? 'unavailable'}; delay ${q?.delay == null ? 'unavailable' : q.delay + ' seconds'}`).join(' · ')}</p>` : html`<p>No saved quote capture is available. The close can still be recorded; quote comparisons will be unavailable.</p>`}
    </fieldset>
    <form onSubmit=${save}><div className="fields">${[['close_date', 'Close date', 'date'], ['stock_price_usd', 'Stock sale price (USD/share)', 'number'], ['buyback_price_usd', 'Call buyback price (USD/share)', 'number'], ['fees_usd', 'Total closing fees (USD)', 'number']].map(([key, label, type]) => html`<label key=${key}>${label}<input required disabled=${busy} type=${type} step="any" min=${key === 'stock_price_usd' ? '0.00000001' : '0'} value=${fields[key]} onChange=${e => {setFields(old => ({...old, [key]: e.target.value})); setReviewed(false);}}/></label>`)}</div>
      <p>${complete ? `Stock sale: ${money(stockSale)} · Call buyback: ${money(buyback)} · Net closing cash: ${money(cash)}` : 'Enter the actual sale and buyback prices to see closing cash.'}</p>
      <label className="review"><input type="checkbox" required disabled=${busy} checked=${reviewed} onChange=${e => setReviewed(e.target.checked)}/>I verified both trades and the full position is closed.</label>
      <div className="entry-actions"><button disabled=${busy}>Record close</button><button type="button" disabled=${busy} onClick=${onClose}>Cancel</button></div>
      <p role="status">${status}</p>
    </form>
  </dialog>`;
}

export function ClosedHoldings({revision}) {
  const [records, setRecords] = useState([]), [status, setStatus] = useState('Loading closed holdings…');
  useEffect(() => {
    const controller = new AbortController();
    setStatus('Loading closed holdings…');
    api('/api/closed-holdings', {signal: controller.signal}).then(data => {
      setRecords(data.holdings); setStatus(data.holdings.length ? '' : 'No closed holdings recorded.');
    }).catch(e => {if (e.name !== 'AbortError') setStatus(e.message);});
    return () => controller.abort();
  }, [revision]);
  return html`<section id="closed-holdings-report" aria-labelledby="closed-holdings-title"><h2 id="closed-holdings-title">Recorded exits</h2>
    <p>Actual recorded exits in USD. P/L includes linked opening and rollover cash flows, stock cost and recorded fees. A missing history shows “Unavailable”. Earlier expired-option P/L is recorded separately and is not added again to this exit amount. Records preserve the accounting snapshot at closure.</p>
    <p role="status">${status}</p>
    ${records.length ? html`<div className="scroll"><table><thead><tr>${['Close date', 'Account', 'Stock', 'Shares / calls', 'Stock sale', 'Call buyback', 'Closing fees', 'Net closing cash', 'Realized P/L', 'Captured quotes', 'History'].map(label => html`<th key=${label} scope="col">${label}</th>`)}</tr></thead>
      <tbody>${records.map(record => html`<tr key=${record.id}><td>${record.close_date}</td><td>${record.account}</td><td>${record.symbol}<br/><small>Call $${record.strike} · ${record.expiry}</small></td><td>${record.shares} / ${record.contracts}</td><td>${money(record.stock_sale_usd)}<br/><small>${money(record.stock_price_usd)}/share</small></td><td>${money(record.buyback_total_usd)}<br/><small>${money(record.buyback_price_usd)}/share</small></td><td>${money(record.fees_usd)}</td><td>${money(record.closing_cash_usd)}</td><td>${record.realized_pl_usd == null ? 'Unavailable' : money(record.realized_pl_usd)}</td><td><${ClosingMarketReference} record=${record}/></td><td><details><summary>Accounting</summary><p>Stock cost: ${money(record.accounting.stock_cost_usd)}<br/>Historical option net: ${money(record.accounting.historical_option_net_usd)}<br/>Earlier realized option P/L: ${record.accounting.prior_realized_option_usd===null ? 'Unavailable' : money(record.accounting.prior_realized_option_usd || 0)}<br/>Combined P/L including earlier realized results: ${record.realized_pl_usd==null || record.accounting.prior_realized_option_usd===null ? 'Unavailable' : money(record.realized_pl_usd+(record.accounting.prior_realized_option_usd || 0))}<br/>Recorded rollovers: ${record.accounting.rollover_count ?? 'Unknown'}<br/>${record.accounting.history_note || ''}</p></details></td></tr>`)}</tbody>
    </table></div>` : null}
  </section>`;
}

export function ClosingMarketReference({record}) {
  const quote = record.quote_snapshot;
  const history = record.accounting?.historical_close_reference;
  if (!quote && !history) return 'Unavailable';
  return html`<div>
    ${quote ? html`<details><summary>Quote comparison</summary><p>Questrade · USD/share<br/>Captured ${quote.captured_at}<br/>Stock bid / ask: ${money(quote.stock?.bidPrice)} / ${money(quote.stock?.askPrice)}<br/>Held call bid / ask: ${money(quote.held?.bidPrice)} / ${money(quote.held?.askPrice)}</p></details>` : null}
    ${history ? html`<details><summary>Historical closes</summary><p>Questrade · ${history.date} · USD/share<br/>Stock close: ${money(history.stock?.close)}<br/>Held call close: ${money(history.held?.close)}<br/>Daily candle prices; historical bid/ask unavailable. These are not quotes at execution.</p></details>` : null}
  </div>`;
}
