import {Input} from './Input.js';
import {InterestRateSettings} from './InterestRateSettings.js';
import {html, useState, useEffect, useRef} from './ui.js';
import {api, money, readStored, holdingLabel, holdingIdentity} from './api.js';

import {PositionEditor} from './PositionEditor.js';
import {ExpireWorthless} from './OptionExpiration.js';
import {TransactionReport} from './TransactionReport.js';

const PROFILE = 'covered-call-profile-v1';
const transactionTabs = [['stock', 'Stock purchase'], ['option', 'Option Opening Sale'], ['rollover', 'Rollover']];
const columns = [['date', 'Purchase date'], ['quantity', 'Purchase shares'], ['priceUsd', 'Purchase price (USD/share)'], ['feesUsd', 'Purchase fees (USD)']];

export function Profile({onClose, onName, holding, onInterestRate, valuationDate}) {
  const dialog = useRef();
  const [name, setName] = useState(() => readStored(PROFILE, {}).name || '');
  const [interestRate, setInterestRate] = useState(() => readStored(PROFILE, {}).interestRate || {mode:'treasury'});
  const [status, setStatus] = useState('');
  useEffect(() => {dialog.current.showModal();}, []);
  function save(event) {
    event.preventDefault();
    try {
      const rate = interestRate.mode === 'manual' ? {mode:'manual',annual_percent:Number(interestRate.annual_percent)} : {mode:'treasury'};
      if (rate.mode === 'manual' && (interestRate.annual_percent === '' || !Number.isFinite(rate.annual_percent) || rate.annual_percent < -5 || rate.annual_percent > 25)) throw Error('Enter an annual interest yield between -5% and 25%.');
      const next = {...readStored(PROFILE, {}), name: name.trim(), interestRate:rate};
      localStorage.setItem(PROFILE, JSON.stringify(next));
      onName(next.name); onInterestRate?.(rate); onClose();
    } catch(error) {setStatus(error.message || 'Profile settings could not be saved in this browser.');}
  }
  return html`<dialog ref=${dialog} id="profile-settings" aria-labelledby="profile-title" onCancel=${onClose} onClose=${onClose}>
    <div className="settings-header"><h2 id="profile-title">Profile</h2><button type="button" aria-label="Close profile" onClick=${onClose}>×</button></div>
    <form onSubmit=${save}>
      <label>Profile name<${Input} maxLength="60" value=${name} onChange=${e => setName(e.target.value)}/></label>
      <${InterestRateSettings} holding=${holding} valuationDate=${valuationDate} value=${interestRate} onChange=${setInterestRate}/>
      <div className="entry-actions"><button>Save profile</button><button type="button" onClick=${onClose}>Cancel</button></div>
      <p role="status">${status}</p>
    </form>
  </dialog>`;
}

export function Settings({onClose, holding}) {
  const dialog = useRef(), tabButtons = useRef({});
  const [tab, setTab] = useState('stock');
  const [rows, setRows] = useState([]), [ready, setReady] = useState(false);
  const [holdings, setHoldings] = useState([]);
  const [activeHolding, setActiveHolding] = useState(holding || null);
  const [editor, setEditor] = useState(null);
  const [lastExpiration,setLastExpiration]=useState(null);
  const [reportRevision,setReportRevision]=useState(0);
  const [status, setStatus] = useState('Loading saved stock purchases…');
  const [busy, setBusy] = useState(false);
  async function load(preferredId) {
    const [positions, saved, choices] = await Promise.all([api('/api/profile/holdings'), api('/api/stock-cost-basis'), api('/api/exit-optimizer/holdings')]);
    setHoldings(choices.holdings);
    setActiveHolding(current => choices.holdings.find(h => holdingIdentity(h)===(preferredId || holdingIdentity(current))) || choices.holdings[0] || null);
    const unique = new Map();
    for (const a of positions.accounts) for (const p of a.positions || []) {
      const id = JSON.stringify([a.account, p.symbol]);
      if (unique.has(id)) continue;
      const basis = saved.bases.find(b => b.account === a.account && b.symbol === p.symbol && b.currency === 'USD')
        || saved.bases.find(b => b.account === a.account && b.symbol === p.symbol && b.priceUsd != null);
      unique.set(id, {id, account: a.account, symbol: p.symbol, date: basis?.date || '',
        quantity: basis?.quantity ?? p.shares, priceUsd: basis?.priceUsd ?? '', feesUsd: basis?.feesUsd ?? 0});
    }
    for(const basis of saved.bases) {
      const id=JSON.stringify([basis.account,basis.symbol]);
      if(!unique.has(id))unique.set(id,{id,account:basis.account,symbol:basis.symbol,date:basis.date || '',quantity:basis.quantity,priceUsd:basis.priceUsd ?? '',feesUsd:basis.feesUsd ?? 0});
    }
    for(const h of choices.holdings)if(h.stock_purchase)unique.set(h.position_id,{id:h.position_id,owned_position_id:h.position_id,account:h.account,symbol:h.symbol,...h.stock_purchase});
    const purchases = [...unique.values()];
    setRows(purchases);
    setReady(true); setStatus('Stock purchases are saved in USD.');setReportRevision(value => value+1);
  }
  useEffect(() => {dialog.current.showModal(); load().catch(e => setStatus(e.message));}, []);
  const change = (id, field, value) => setRows(old => old.map(row => row.id === id ? {...row, [field]: value} : row));
  async function save(event) {
    event.preventDefault(); setBusy(true);
    try {
      const bases = rows.filter(selectedPurchase).map(row => {
        const quantity = Number(row.quantity), priceUsd = Number(row.priceUsd), feesUsd = Number(row.feesUsd);
        if (!row.date || !Number.isFinite(quantity) || quantity <= 0 || !Number.isFinite(priceUsd) || priceUsd <= 0
          || row.feesUsd === '' || !Number.isFinite(feesUsd) || feesUsd < 0) throw Error('Enter a purchase date, positive shares and USD price, and fees (use 0 for none).');
        return {account: row.account, symbol: row.symbol, currency: 'USD', date: row.date,
          quantity, priceUsd, feesUsd, fx: null, totalCost: quantity * priceUsd + feesUsd};
      });
      if(activeHolding.stock_purchase) {
        const basis=bases[0];await api(`/api/positions/${activeHolding.position_id}/purchase`,{body:{purchase_date:basis.date,shares:basis.quantity,price_usd:basis.priceUsd,fees_usd:basis.feesUsd}});
        await load(holdingIdentity(activeHolding));
      } else {await api('/api/stock-cost-basis', {body: {bases}});await load(holdingIdentity(activeHolding));}
      setStatus('Stock purchases saved in USD. Refresh data & analyze to update the chart.');
    } catch (e) {setStatus(e.message);} finally {setBusy(false);}
  }
  const selectedPurchase = row => activeHolding?.stock_purchase ? row.id===activeHolding.position_id : !row.owned_position_id && row.account===activeHolding?.account && row.symbol===activeHolding?.symbol;
  function navigateTab(event, current) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const ids = transactionTabs.map(([id]) => id);
    const next = event.key === 'Home' ? ids[0] : event.key === 'End' ? ids.at(-1) : ids[(ids.indexOf(current) + (event.key === 'ArrowRight' ? 1 : -1) + ids.length) % ids.length];
    setTab(next); tabButtons.current[next]?.focus();
  }
  return html`<dialog ref=${dialog} id="transaction-records" aria-labelledby="records-title" onCancel=${() => onClose(holdingIdentity(activeHolding))} onClose=${() => onClose(holdingIdentity(activeHolding))}>
    <div className="settings-header"><h2 id="records-title">Transactions</h2><button type="button" aria-label="Close transactions" onClick=${() => onClose(holdingIdentity(activeHolding))}>×</button></div>
    <div className="purchase-controls"><label>Holding<select aria-label="Holding" value=${activeHolding ? holdingIdentity(activeHolding) : ''} disabled=${!ready || busy || !holdings.length} onChange=${e => {
      setEditor(null); setActiveHolding(holdings.find(h => holdingIdentity(h) === e.target.value));
    }}>${holdings.map(h => html`<option key=${holdingIdentity(h)} value=${holdingIdentity(h)}>${holdingLabel(h)}</option>`)}</select></label>
      <button type="button" disabled=${busy || !ready} onClick=${() => setEditor('new')}>Add position</button>
      <button type="button" disabled=${busy || !activeHolding?.position_id} onClick=${() => setEditor('allocation')}>Allocate shares</button>
    </div>
    ${editor ? html`<${PositionEditor} mode=${editor} holding=${activeHolding} onCancel=${() => setEditor(null)} onSaved=${async h => {setEditor(null); await load(h.position_id);}}/>` : null}
    ${lastExpiration ? html`<p role="status">${lastExpiration.symbol} call expired worthless. Realized option P/L: ${lastExpiration.realized_option_pl_usd==null ? 'Unavailable' : money(lastExpiration.realized_option_pl_usd)}. ${lastExpiration.shares_retained} shares retained.</p>` : null}
    <div className="settings-tabs" role="tablist" aria-label="Transaction type">${transactionTabs.map(([id, title]) => html`<button key=${id} type="button" role="tab" id=${`settings-tab-${id}`} aria-controls=${`settings-panel-${id}`} aria-selected=${tab === id} tabIndex=${tab === id ? 0 : -1} ref=${node => {tabButtons.current[id] = node;}} onKeyDown=${e => navigateTab(e, id)} onClick=${() => setTab(id)}>${title}</button>`)}</div>
    <div role="tabpanel" id="settings-panel-stock" aria-labelledby="settings-tab-stock" hidden=${tab !== 'stock'}>
    <form onSubmit=${save}>
      <p>Enter one purchase lot or a combined average price using total shares and total fees. All amounts are USD. Enter 0 if there are no fees.</p>
      <div className="table-scroll"><table><thead><tr><th>Holding / account</th>${columns.map(([field, title]) => html`<th key=${field} scope="col">${title}</th>`)}<th>Total cost (USD)</th></tr></thead>
        <tbody>${rows.filter(selectedPurchase).map(row => html`<tr key=${row.id}><td>${row.account} · ${row.symbol}</td>
          ${columns.map(([field, title]) => html`<td key=${field}><${Input} aria-label=${`${row.account} ${row.symbol} ${title}`} type=${field === 'date' ? 'date' : 'number'} step="any" min=${field === 'feesUsd' ? '0' : '0.00000001'} required value=${row[field]} onChange=${e => change(row.id, field, e.target.value)}/></td>`)}
          <td>${row.quantity !== '' && row.priceUsd !== '' && row.feesUsd !== '' ? money(Number(row.quantity) * Number(row.priceUsd) + Number(row.feesUsd)) : '—'}</td></tr>`)}</tbody></table></div>
      <div className="entry-actions"><button disabled=${busy || !ready || !activeHolding}>Save stock purchase</button><button type="button" onClick=${onClose}>Cancel</button></div>
      <p role="status">${status}</p>
    </form></div>
    <div role="tabpanel" id="settings-panel-option" aria-labelledby="settings-tab-option" hidden=${tab !== 'option'}><${PremiumForm} key=${holdingIdentity(activeHolding)} initialHolding=${activeHolding} onSaved=${() => load(holdingIdentity(activeHolding))}/></div>
    <div role="tabpanel" id="settings-panel-rollover" aria-labelledby="settings-tab-rollover" hidden=${tab !== 'rollover'}><${RolloverForm} key=${holdingIdentity(activeHolding)} initialHolding=${activeHolding} active=${tab === 'rollover'} onSaved=${() => load(holdingIdentity(activeHolding))} onExpired=${async record => {setLastExpiration(record);await load(record.retained_position?.position_id);setTab('option');}}/></div>
    <${TransactionReport} holding=${activeHolding} revision=${reportRevision}/>
  </dialog>`;
}

function OriginalExpiryFields({marked,fees,gross,openingFees=0,disabled,onMarked,onFees}) {
  return html`<label className="review"><${Input} type="checkbox" disabled=${disabled} checked=${marked} onChange=${e => onMarked(e.target.checked)}/>This original call expired worthless, with no buyback or assignment; I retained the shares.</label>
    ${marked ? html`<label>Original call expiration fees (USD)<${Input} type="number" required min="0" step="any" disabled=${disabled} value=${fees} onChange=${e => onFees(e.target.value)}/></label>
      <p>Recorded realized P/L: ${fees!=='' ? money(gross-openingFees-Number(fees)) : '—'}. The current short call stays active. Its opening premium can be recorded separately; full P/L remains incomplete until its history is recorded.</p>` : null}`;
}

function PremiumForm({initialHolding,onSaved}) {
  const [records, setRecords] = useState([]);
  const [fields, setFields] = useState({expiry: initialHolding?.call_expiry || '', strike: initialHolding?.call_strike_native_currency || '', contracts: initialHolding?.call_contracts || ''}), [reviewed, setReviewed] = useState(false);
  const [status, setStatus] = useState(''), [busy, setBusy] = useState(false), [ready, setReady] = useState(false);
  const [editing, setEditing] = useState(null);
  const [historicalOpening, setHistoricalOpening] = useState(false);
  const [expiredWorthless,setExpiredWorthless]=useState(false), [expirationFees,setExpirationFees]=useState('0');
  const endpoint = '/api/option-premiums/usd';
  function resetForCurrentCall() {
    setFields({expiry:initialHolding.call_expiry,strike:initialHolding.call_strike_native_currency,contracts:initialHolding.call_contracts});
    setHistoricalOpening(false);setExpiredWorthless(false);setExpirationFees('0');
  }
  const expirySavedMessage = result => `Original call recorded as expired worthless. Realized P/L: ${money(result.realized_option_pl_usd)}. See Transaction report. ${initialHolding?.call_contracts ? 'Record the current call’s opening sale separately; it remains active.' : 'The stock holding remains available for its next option opening sale.'}`;
  async function update(e) {
    e.preventDefault(); setBusy(true); setStatus('Saving…');
    const target = editing.net_cad == null ? '/api/option-premiums/usd' : '/api/option-premiums';
    try {
      const body = editing.net_cad == null ? editing : {...editing, net_cad: Math.round((editing.contracts * 100 * editing.price_usd - editing.fees_usd) * editing.fx * 100) / 100};
      const result=await api(initialHolding?.position_id ? `/api/positions/${initialHolding.position_id}/opening/edit` : `${target}/${editing.id}/edit`, {body});
      setEditing(null); await load();
      if(result.expired_worthless)resetForCurrentCall();
      await onSaved?.();
      setStatus(result.expired_worthless ? expirySavedMessage(result) : 'Opening sale updated. Close Transactions to update chart P/L using saved quotes.');
    } catch (error) {setStatus(error.message);} finally {setBusy(false);}
  }

  async function load() {
    if (initialHolding?.position_id) {
      const saved=await api(`/api/positions/${initialHolding.position_id}/history`);
      setRecords(saved.opening ? [saved.opening] : []);
    } else {
      const values=await Promise.all([api('/api/option-premiums'),api('/api/option-premiums/usd')]);
      setRecords(values.flatMap(d => d.premiums));
    }
  }
  useEffect(() => {load().then(() => setReady(true)).catch(e => setStatus(e.message));}, []);
  const holding = initialHolding;
  const matching = records.filter(r => holding && r.account === holding.account && r.symbol === holding.symbol);
  const earlierCall = record => holding?.position_id && record.expiry && (holding.call_contracts===0 || record.expiry!==holding.call_expiry || Number(record.strike)!==Number(holding.call_strike_native_currency));
  const definitions = [['expiry', 'Original call expiry', 'date'], ['strike', 'Original strike (USD)', 'number'], ['contracts', 'Original contracts', 'number'], ['settlement_date', 'Settlement date', 'date'], ['price_usd', 'Premium sold (USD/share)', 'number']];
  async function save(e) {
    e.preventDefault(); if (!holding) return; setBusy(true); setStatus('Saving…');
    const payload = Object.fromEntries(definitions.map(([key, , type]) => [key, type === 'number' ? Number(fields[key]) : fields[key]]));
    delete payload.holding;
    Object.assign(payload, {account: holding.account, symbol: holding.symbol});
    try {
      const result=await api(holding.position_id ? `/api/positions/${holding.position_id}/opening` : endpoint, {body: {...payload, reviewed, historical_opening: historicalOpening,expired_worthless:expiredWorthless,expiration_fees_usd:Number(expirationFees)}});
      setReviewed(false);await load();
      if(result.expired_worthless)resetForCurrentCall();
      await onSaved?.();
      setStatus(result.expired_worthless ? expirySavedMessage(result) : historicalOpening ? 'Original opening sale saved. Record the rollovers in trade order through the current call to complete cumulative P/L.' : 'Opening sale saved. Close Transactions to update chart P/L using saved quotes.');
    }
    catch (error) {setStatus(error.message);} finally {setBusy(false);}
  }
  return html`<section className="option-sale-form"><h3>Record original option premium sale (USD)</h3>
    <p>Record a completed opening call sale against your confirmation. Saving does not place an order. Gross USD amounts exclude fees. Past-dated sales can be saved without marking them expired worthless. For a bought-back or rolled call, leave that box unchecked and record both legs in Rollover.</p>
    ${matching.length ? html`<p>This position already has its opening sale. Use Edit to correct it.</p>` : html`<form onSubmit=${save}><div className="fields">${definitions.map(([key, title, type]) => html`<label key=${key}>${title}<${Input} type=${type} required step="any" min="0.00000001" value=${fields[key] || ''} onChange=${e => {setFields(old => ({...old, [key]: e.target.value})); setReviewed(false);}}/></label>`)}</div>
      <p>Total premium: ${holding && Number(fields.price_usd) > 0 ? money(Number(fields.contracts) * 100 * Number(fields.price_usd)) : '—'}</p>
      ${holding?.position_id && holding.call_contracts>0 ? html`<label className="review"><${Input} type="checkbox" checked=${historicalOpening} onChange=${e => {setHistoricalOpening(e.target.checked);setReviewed(false);setStatus('');}}/>This is an earlier original call; its strike or expiry differs from the current holding.</label>
      ${historicalOpening && !expiredWorthless ? html`<p>The current holding stays unchanged. Record each rollover from this original call through the current call; cumulative P/L is unavailable until the history is complete.</p>` : null}` : null}
      ${earlierCall(fields) ? html`<${OriginalExpiryFields} marked=${expiredWorthless} fees=${expirationFees} gross=${Number(fields.contracts)*100*Number(fields.price_usd)} disabled=${busy} onMarked=${value => {setExpiredWorthless(value);setReviewed(false);}} onFees=${value => {setExpirationFees(value);setReviewed(false);}}/>` : null}
      <label className="review"><${Input} type="checkbox" required checked=${reviewed} onChange=${e => setReviewed(e.target.checked)}/>I verified the opening sale against my confirmation.</label>
      <button disabled=${busy || !ready || !holding}>Save opening premium</button>
    </form>`}<p role="status">${status}</p><h3>Opening sale</h3>
    ${matching.length ? matching.map(r => html`<p key=${`${r.id}-${r.net_cad ?? 'usd'}`}>${r.account} · ${r.symbol} · ${r.expiry} · strike ${r.strike} · ${r.settlement_date} · ${r.contracts} × 100 × ${money(r.price_usd)} = ${money(r.contracts * 100 * r.price_usd)} gross USD <button type="button" disabled=${busy} onClick=${() => {setEditing({...r, reviewed: false}); setStatus('');}}>Edit</button></p>`) : html`<p>No original premium recorded.</p>`}
    ${editing ? html`<form onSubmit=${update}>
      <h3>Edit ${editing.symbol} opening sale · ${editing.settlement_date}</h3>
      <p>Enter the premium per underlying share. Total = contracts × 100 × premium.</p>
      <div className="fields">${[['price_usd', 'Premium sold (USD/share)']].map(([key, label]) => html`<label key=${key}>${label}<${Input} type="number" required step="any" min=${key === 'fees_usd' ? '0' : '0.00000001'} value=${editing[key]} onChange=${e => setEditing({...editing, [key]: Number(e.target.value), reviewed: false})}/></label>`)}</div>
      <p>Total premium: ${money(editing.contracts * 100 * editing.price_usd)}</p>
      ${earlierCall(editing) ? html`<${OriginalExpiryFields} marked=${editing.expired_worthless || false} fees=${editing.expiration_fees_usd ?? '0'} gross=${editing.contracts*100*editing.price_usd} openingFees=${editing.fees_usd || 0} disabled=${busy} onMarked=${value => setEditing({...editing,expired_worthless:value,reviewed:false})} onFees=${value => setEditing({...editing,expiration_fees_usd:Number(value),reviewed:false})}/>` : null}
      <label className="review"><${Input} type="checkbox" required checked=${editing.reviewed} onChange=${e => setEditing({...editing, reviewed: e.target.checked})}/>I verified the corrected sale against my confirmation.</label>
      <button disabled=${busy}>Save changes</button>
      <button type="button" disabled=${busy} onClick=${() => setEditing(null)}>Cancel</button>
    </form>` : null}

  </section>`;
}

function RolloverForm({initialHolding, active, onSaved, onExpired}) {
  const [expiring,setExpiring]=useState(false);
  const [fields, setFields] = useState({holding: '0', settlement_date: '', contracts: initialHolding?.call_contracts || '',
    buyback_expiry: initialHolding?.call_expiry || '', buyback_strike: initialHolding?.call_strike_native_currency || '',
    buyback_price_usd: '', sale_expiry: '', sale_strike: '', sale_price_usd: '', fees_usd: '0'});
  const [ready, setReady] = useState(false), [busy, setBusy] = useState(false), [reviewed, setReviewed] = useState(false);
  const [status, setStatus] = useState('');
  const [historicalOpening,setHistoricalOpening]=useState(false);
  useEffect(() => {
    if (!active) return;
    setReady(false);
    let cancelled = false;
    api(initialHolding?.position_id ? `/api/positions/${initialHolding.position_id}/history` : '/api/option-rollovers').then(saved => {
      if (cancelled) return;
      if(saved.position) {
        setReviewed(false);
        setFields(old => ({...old,contracts:saved.position.call_contracts || '',buyback_expiry:saved.position.call_expiry,buyback_strike:saved.position.call_strike_native_currency || ''}));
      }
      if(saved.opening?.historical_opening) {
        const previous=saved.rollovers.at(-1);
        setHistoricalOpening(true);
        setReviewed(false);
        setFields(old => ({...old,buyback_expiry:previous?.sale_expiry || saved.opening.expiry,buyback_strike:previous?.sale_strike ?? saved.opening.strike}));
      }
      setReady(true);
    }).catch(e => {if (!cancelled) setStatus(e.message);});
    return () => {cancelled = true;};
  }, [active,initialHolding?.position_revision]);
  const holding = initialHolding;
  const update = (key, value) => {setFields(old => ({...old, [key]: value})); setReviewed(false);};
  const input = (key, label, type = 'number') => html`<label>${label}<${Input} required type=${type} step=${key === 'contracts' ? '1' : 'any'} min=${key === 'fees_usd' ? '0' : '0.00000001'} value=${fields[key]} onChange=${e => update(key, e.target.value)}/></label>`;
  const totalsReady = ['contracts', 'buyback_price_usd', 'sale_price_usd', 'fees_usd'].every(key => fields[key] !== '' && Number.isFinite(Number(fields[key])));
  const buyback = Number(fields.contracts) * 100 * Number(fields.buyback_price_usd);
  const sale = Number(fields.contracts) * 100 * Number(fields.sale_price_usd);
  const net = sale - buyback - Number(fields.fees_usd);
  async function save(event) {
    event.preventDefault(); if (!holding) return;
    setBusy(true); setStatus('Saving…');
    try {
      const payload = {account: holding.account, symbol: holding.symbol, reviewed};
      for (const key of ['settlement_date', 'buyback_expiry', 'sale_expiry']) payload[key] = fields[key];
      for (const key of ['contracts', 'buyback_strike', 'buyback_price_usd', 'sale_strike', 'sale_price_usd', 'fees_usd']) payload[key] = Number(fields[key]);
      await api(holding.position_id ? `/api/positions/${holding.position_id}/rollovers` : '/api/option-rollovers', {body: payload});
      setReviewed(false);
      setFields(old => ({...old, settlement_date: '', fees_usd: '', ...(holding.position_id ? {buyback_expiry: payload.sale_expiry, buyback_strike: payload.sale_strike, buyback_price_usd: '', sale_expiry: '', sale_strike: '', sale_price_usd: ''} : {})}));
      if (holding.position_id) await onSaved?.();
      setStatus('Rollover saved. Close Transactions to update chart P/L using saved quotes.');
    } catch(e) {setStatus(e.message);} finally {setBusy(false);}
  }
  return html`<section className="option-sale-form"><h3>Record completed rollover (USD)</h3>
    ${expiring && holding ? html`<${ExpireWorthless} holding=${holding} onClose=${() => setExpiring(false)} onSaved=${async record => {setExpiring(false);await onExpired?.(record);}}/>` : null}
    <button type="button" title="Record the current call, including a replacement call, as expired worthless" disabled=${busy || !holding?.position_id || !holding?.can_mark_expired} onClick=${() => setExpiring(true)}>Expired worthless</button>
    <p>Record the call bought back and the replacement call sold for the same number of contracts. Premiums are per underlying share; each contract covers 100 shares.</p>
    <form onSubmit=${save}>
      <div className="fields">
      ${input('settlement_date', 'Settlement date', 'date')}${input('contracts', 'Contracts (both legs)')}</div>
      <fieldset><legend>Buyback · existing call</legend><div className="fields">${input('buyback_expiry', 'Buyback expiry', 'date')}${input('buyback_strike', 'Buyback strike (USD)')}${input('buyback_price_usd', 'Buyback premium (USD/share)')}</div></fieldset>
      <fieldset><legend>Sale · replacement call</legend><div className="fields">${input('sale_expiry', 'Replacement expiry', 'date')}${input('sale_strike', 'Replacement strike (USD)')}${input('sale_price_usd', 'Sale premium (USD/share)')}</div></fieldset>
      ${input('fees_usd', 'Total rollover fees (USD)')}
      <p>${totalsReady ? `Buyback: ${money(buyback)} · Sale: ${money(sale)} · Net ${net < 0 ? 'debit' : 'credit'}: ${money(Math.abs(net))}` : 'Enter both premiums to see the rollover totals.'}</p>
      <label className="review"><${Input} type="checkbox" required checked=${reviewed} onChange=${e => setReviewed(e.target.checked)}/>I verified both legs against my confirmation.</label>
      <button disabled=${!ready || !holding || busy}>Save rollover</button><p role="status">${status}</p>
    </form>
    <p>Saved rollovers are linked to the original opening sale for cumulative P/L. ${historicalOpening ? 'Record historical rollovers in trade order through the current call. The current holding stays unchanged while earlier trades are entered; a subsequent rollover of the current call updates it.' : 'A rollover updates this position’s current call.'}</p>
  </section>`;
}
