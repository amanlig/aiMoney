import {html, useState, useEffect, useRef} from './ui.js';
import {api, money, readStored, holdingLabel} from './api.js';

const PROFILE = 'covered-call-profile-v1', ENTRIES = 'covered-call-entry-prices-v1';
const key = (a, p) => JSON.stringify([a.account, a.currency, p.symbol]);
const entryKey = (a, p) => JSON.stringify([a.account, a.currency, p.symbol, p.strike, p.expiry, p.shares, p.contracts]);
const columns = [['purchase', 'Original purchase / share'], ['minimum', 'Minimum bid / share'], ['fx', 'Purchase FX (CAD per USD)'], ['date', 'Purchase date'], ['quantity', 'Purchase shares'], ['priceUsd', 'USD price / share'], ['feesUsd', 'Purchase fees (USD)'], ['cadTotal', 'Actual CAD cost (optional)']];

export function Settings({onClose, onName}) {
  const dialog = useRef();
  const [rows, setRows] = useState([]), [ready, setReady] = useState(false);
  const [name, setName] = useState(() => readStored(PROFILE, {}).name || '');
  const [status, setStatus] = useState('Loading saved positions and stock basis…');
  const [busy, setBusy] = useState(false), [legacy, setLegacy] = useState([]);
  async function load() {
    const [positions, saved] = await Promise.all([api('/api/profile/holdings'), api('/api/stock-cost-basis')]);
    const profile = readStored(PROFILE, {holdings: {}}), entries = readStored(ENTRIES, {});
    const backupKey = 'covered-call-cost-basis-before-sqlite-v1';
    let backup = readStored(backupKey, null);
    if (!backup) {backup = profile.holdings || {}; try {localStorage.setItem(backupKey, JSON.stringify(backup));} catch {}}
    setLegacy(Object.entries(backup).flatMap(([k, v]) => {try {
      if (!v.costBasis) return [];
      const [account, currency, symbol] = JSON.parse(k), b = v.costBasis;
      return [{...b, account, currency, symbol, totalCost: currency === 'CAD' ? b.cadTotal : b.usdTotal ?? b.quantity * b.priceUsd + b.feesUsd}];
    } catch {return [];}}));
    setRows(positions.accounts.flatMap(a => (a.positions || []).map(p => {
      const basis = saved.bases.find(b => b.account === a.account && b.currency === a.currency && b.symbol === p.symbol);
      const entry = entries[entryKey(a, p)], preference = profile.holdings?.[key(a, p)];
      const converted = entry?.stockPrice != null ? entry.stockPrice * (entry.currency === a.currency ? 1 : entry.entryFx) : null;
      return {a, p, purchase: basis?.averageCost ?? converted ?? (p.cost === null ? '' : p.cost / p.shares), minimum: preference?.minimumBid ?? '', fx: basis?.fx ?? entry?.entryFx ?? p.entryFx ?? '', date: basis?.date || '', quantity: basis?.quantity ?? '', priceUsd: basis?.priceUsd ?? '', feesUsd: basis?.feesUsd ?? '', cadTotal: basis?.cadTotal ?? ''};
    })));
    setReady(true); setStatus('Stock cost basis is shared through SQLite. Profile and minimum bids are browser preferences.');
  }
  useEffect(() => {dialog.current.showModal(); load().catch(e => setStatus(e.message));}, []);
  const change = (index, field, value) => setRows(old => old.map((row, i) => i === index ? {...row, [field]: value} : row));
  async function save(event) {
    event.preventDefault(); setBusy(true);
    try {
      const profile = readStored(PROFILE, {holdings: {}}), entries = readStored(ENTRIES, {});
      const next = {...profile, name: name.trim(), holdings: {...profile.holdings}};
      const bases = rows.map(row => {
        const {a, p} = row, minimum = row.minimum === '' ? null : Number(row.minimum);
        if (minimum !== null && (!Number.isFinite(minimum) || minimum <= 0)) throw Error('Minimum bids must be positive or blank.');
        const basis = row.priceUsd === '' ? null : globalThis.ProfileSettings.costBasis({date: row.date, quantity: Number(row.quantity), priceUsd: Number(row.priceUsd), feesUsd: Number(row.feesUsd || 0), fx: Number(row.fx || (a.currency === 'USD' ? 1 : 0)), cadTotal: row.cadTotal === '' ? null : Number(row.cadTotal)});
        const purchase = basis ? (a.currency === 'CAD' ? basis.cadPerShare : basis.usdPerShare)
          : a.currency === 'CAD' && row.cadTotal !== '' && row.quantity !== '' ? Number(row.cadTotal) / Number(row.quantity) : Number(row.purchase);
        if (!Number.isFinite(purchase) || purchase <= 0) throw Error('Enter a positive purchase price.');
        const fx = a.currency === 'CAD' && row.fx !== '' ? Number(row.fx) : null;
        if (fx !== null && (!Number.isFinite(fx) || fx <= 0)) throw Error('Enter a positive purchase FX.');
        const {costBasis, ...preference} = next.holdings[key(a, p)] || {};
        next.holdings[key(a, p)] = {...preference, minimumBid: minimum};
        const old = entries[entryKey(a, p)] || {};
        // Preserve the option override in account currency when changing stock basis.
        const optionPrice = old.optionPrice == null ? null : old.optionPrice * (old.currency === a.currency ? 1 : old.entryFx);
        entries[entryKey(a, p)] = {currency: a.currency, stockPrice: purchase, entryFx: fx, optionPrice};
        return {account: a.account, symbol: p.symbol, currency: a.currency, date: row.date || null,
          quantity: basis?.quantity ?? (row.quantity === '' ? p.shares : Number(row.quantity)),
          priceUsd: basis?.priceUsd ?? null, feesUsd: basis?.feesUsd ?? null, fx,
          totalCost: basis && a.currency === 'CAD' ? basis.cadTotal : purchase * (basis?.quantity ?? (row.quantity === '' ? p.shares : Number(row.quantity)))};
      });
      await api('/api/stock-cost-basis', {body: {bases}});
      try {localStorage.setItem(PROFILE, JSON.stringify(next)); localStorage.setItem(ENTRIES, JSON.stringify(entries)); setStatus('Stock basis saved in SQLite. Profile and thresholds saved in this browser.');}
      catch {setStatus('Stock basis saved in SQLite. Browser preferences could not be saved.');}
      onName(next.name);
    } catch (e) {setStatus(e.message);} finally {setBusy(false);}
  }
  return html`<dialog ref=${dialog} id="profile-settings" aria-labelledby="settings-title" onCancel=${onClose} onClose=${onClose}>
    <div className="settings-header"><h2 id="settings-title">Profile / Settings</h2><button type="button" aria-label="Close settings" onClick=${onClose}>×</button></div>
    <form onSubmit=${save}>
      <p>Configure each holding by account. Purchase prices and minimum bids use the account currency. Enter verified original stock cost and purchase-time FX; missing purchase FX is never filled from today’s rate. Blank minimum bids use purchase-price break-even.</p>
      <label>Profile name<input maxLength="60" value=${name} onChange=${e => setName(e.target.value)}/></label>
      <p>Enter one purchase lot or a combined average basis using total shares and total fees. Actual CAD cost can override rounding. Opening option sales are recorded separately below.</p>
      <button type="button" disabled=${!legacy.length || busy || !ready} onClick=${async () => {
        if (!confirm(`Import ${legacy.length} previous browser cost bases into SQLite? Matching saved records will be replaced.`)) return;
        setBusy(true); try {await api('/api/stock-cost-basis', {body: {bases: legacy}}); await load();} catch(e) {setStatus(e.message);} finally {setBusy(false);}
      }}>Import previous browser cost bases</button>
      <div className="table-scroll"><table><thead><tr><th>Holding / account currency</th>${columns.map(([field, title]) => html`<th key=${field} scope="col">${title}</th>`)}<th>Restore</th></tr></thead>
        <tbody>${rows.map((row, index) => html`<tr key=${key(row.a, row.p)}><td>${row.a.account} · ${row.a.currency} · ${row.p.symbol} · ${row.p.shares} shares</td>
          ${columns.map(([field, title]) => html`<td key=${field}><input aria-label=${`${row.a.account} ${row.p.symbol} ${title}`} type=${field === 'date' ? 'date' : 'number'} step="any" min=${field === 'feesUsd' ? '0' : '0.00000001'} required=${field === 'purchase'} value=${row[field]} onChange=${e => change(index, field, e.target.value)}/></td>`)}
          <td><button type="button" onClick=${() => setRows(old => old.map((r, i) => i === index ? {...r, purchase: r.p.cost === null ? '' : r.p.cost / r.p.shares, minimum: '', fx: r.p.entryFx ?? '', date: '', quantity: '', priceUsd: '', feesUsd: '', cadTotal: ''} : r))}>Original values</button></td></tr>`)}</tbody></table></div>
      <div className="entry-actions"><button disabled=${busy || !ready}>Save settings</button><button type="button" onClick=${onClose}>Cancel</button></div>
      <p role="status">${status}</p>
    </form>
    <${PremiumForm}/><${PremiumForm} converted=${true}/>
  </dialog>`;
}

function PremiumForm({converted = false}) {
  const [holdings, setHoldings] = useState([]), [records, setRecords] = useState([]);
  const [fields, setFields] = useState({holding: '0', account: 'RRSP'}), [reviewed, setReviewed] = useState(false);
  const [status, setStatus] = useState(''), [busy, setBusy] = useState(false), [ready, setReady] = useState(false);
  const endpoint = converted ? '/api/option-premiums' : '/api/option-premiums/usd';
  async function load() {
    const values = await Promise.all([api('/api/option-premiums'), api('/api/option-premiums/usd')]);
    setRecords(values.flatMap(d => d.premiums));
  }
  useEffect(() => {Promise.all([load(), api('/api/exit-optimizer/holdings').then(d => setHoldings(d.holdings))]).then(() => setReady(true)).catch(e => setStatus(e.message));}, []);
  const holding = holdings[Number(fields.holding)];
  const matching = converted ? records.filter(r => r.net_cad != null) : records.filter(r => holding && r.account === holding.account && r.symbol === holding.symbol && r.expiry === holding.call_expiry && r.strike === Number(holding.call_strike_native_currency) && r.contracts === holding.call_contracts);
  const definitions = converted
    ? [['account', 'Account', 'select'], ['symbol', 'Ticker', 'text'], ['expiry', 'Call expiry', 'date'], ['strike', 'Strike (USD)', 'number'], ['contracts', 'Contracts (100 shares)', 'number'], ['settlement_date', 'Settlement date', 'date'], ['price_usd', 'Sale premium (USD/share)', 'number'], ['fees_usd', 'Total fees (USD)', 'number'], ['fx', 'Applied CAD per USD', 'number'], ['net_cad', 'Net premium received (CAD)', 'number']]
    : [['holding', 'Holding', 'select'], ['settlement_date', 'Settlement date', 'date'], ['price_usd', 'Premium sold (USD/share)', 'number']];
  async function save(e) {
    e.preventDefault(); if (!converted && !holding) return; setBusy(true); setStatus('Saving…');
    const payload = Object.fromEntries(definitions.map(([key, , type]) => [key, type === 'number' ? Number(fields[key]) : fields[key]]));
    if (!converted) {delete payload.holding; Object.assign(payload, {account: holding.account, symbol: holding.symbol, expiry: holding.call_expiry, strike: Number(holding.call_strike_native_currency), contracts: holding.call_contracts});}
    try {await api(endpoint, {body: {...payload, reviewed}}); setReviewed(false); await load(); setStatus('Opening sale saved in SQLite. Refresh the optimizer analysis to apply it.');}
    catch (error) {setStatus(error.message);} finally {setBusy(false);}
  }
  return html`<section><details><summary>${converted ? 'Opening option sale · CAD conversion details (optional)' : 'Record original option premium sale (USD)'}</summary>
    <p>Record a completed opening call sale against your confirmation. Saving does not place an order. ${converted ? 'Enter total fees once; net CAD must match the confirmation.' : 'Gross USD amounts exclude fees; no CAD conversion is required.'}</p>
    <form onSubmit=${save}><div className="fields">${definitions.map(([key, title, type]) => html`<label key=${key}>${title}${type === 'select'
      ? html`<select required value=${fields[key] || (key === 'account' ? 'RRSP' : '0')} onChange=${e => {setFields(old => ({...old, [key]: e.target.value, ...(key === 'holding' ? {price_usd: ''} : {})})); setReviewed(false);}}>${key === 'account' ? ['RRSP', 'TFSA', 'LIRA'].map(a => html`<option key=${a}>${a}</option>`) : holdings.map((h, i) => html`<option key=${i} value=${i}>${holdingLabel(h)}</option>`)}</select>`
      : html`<input type=${type} required step=${key === 'contracts' ? '1' : 'any'} min=${key === 'fees_usd' ? '0' : '0.00000001'} value=${fields[key] || ''} onChange=${e => {setFields(old => ({...old, [key]: e.target.value})); setReviewed(false);}}/>`}</label>`)}</div>
      ${converted ? null : html`<p>Total premium: ${holding && Number(fields.price_usd) > 0 ? money(holding.call_contracts * 100 * Number(fields.price_usd)) : '—'}</p>`}
      <label className="review"><input type="checkbox" required checked=${reviewed} onChange=${e => setReviewed(e.target.checked)}/>I verified the opening sale against my confirmation.</label>
      <button disabled=${busy || !ready || (!converted && !holding)}>Save opening premium</button><p role="status">${status}</p>
    </form><h3>Saved opening sales</h3>
    ${matching.length ? matching.map(r => html`<p key=${`${r.id}-${r.net_cad ?? 'usd'}`}>${r.account} · ${r.symbol} · ${r.expiry} · strike ${r.strike} · ${r.settlement_date} · ${r.contracts} × 100 × ${money(r.price_usd)} = ${money(r.contracts * 100 * r.price_usd)} gross USD ${r.net_cad == null ? '' : `· CAD net ${r.net_cad.toFixed(2)}`}</p>`) : html`<p>No original premium recorded.</p>`}
    ${!converted && matching.length > 1 ? html`<p>Multiple matching sales: the optimizer does not choose or aggregate them automatically.</p>` : null}
  </details></section>`;
}
