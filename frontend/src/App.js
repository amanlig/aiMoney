import {downloadRollovers} from './RolloverExport.js';
import {html, useState, useEffect, useRef} from './ui.js';
import {api, midpoint, money, holdingLabel, readStored, holdingIdentity, positionRequest, captureQuery} from './api.js';
import {Chart} from './Chart.js';
import {Settings, Profile} from './Settings.js';
import {Recommendations} from './Recommendations.js';
import {ClosePosition, ClosedHoldings} from './ClosedHoldings.js';
import {ExpireWorthless} from './OptionExpiration.js';
import {NewHolding,DeleteHolding} from './Holdings.js';

export function Home() {
  return html`<main className="home"><h1>Covered Call Optimizer</h1><p>Compare closing a covered call today with potential rollovers. Explore stock-price scenarios, estimated cash flows, profit and funding needs to support your trading decisions.</p><a className="primary-link" href="/covered-call-optimizer">Open covered-call optimizer →</a></main>`;
}

export function Dashboard() {
  const [holdings, setHoldings] = useState([]), [selected, setSelected] = useState('0');
  const [baseline, setBaseline] = useState(null), [analysis, setAnalysis] = useState(null);
  const [price, setPrice] = useState(0), [modes, setModes] = useState({});
  const [status, setStatus] = useState('Loading saved holdings…'), [scenarioStatus, setScenarioStatus] = useState('');
  const [refreshBusy, setRefreshBusy] = useState(false), [pending, setPending] = useState(false);
  const [settings, setSettings] = useState(location.hash === '#profile-settings'), [menu, setMenu] = useState(false);
  const [name, setName] = useState(() => readStored('covered-call-profile-v1', {}).name || 'My profile');
  const [expiring,setExpiring]=useState(false), [lastExpiration,setLastExpiration]=useState(null);
  const [closing, setClosing] = useState(false), [closedReport, setClosedReport] = useState(false), [closedRevision, setClosedRevision] = useState(0);
  const [records, setRecords] = useState(false);
  const [creating,setCreating]=useState(false),[deleting,setDeleting]=useState(false);
  const [recommendations, setRecommendations] = useState(false);
  const generation = useRef(0), scenarioGeneration = useRef(0), scenarioAbort = useRef(null), refreshRunning = useRef(false);
  const holding = holdings[Number(selected)];
  useEffect(() => {
    const controller = new AbortController();
    api('/api/exit-optimizer/holdings', {signal: controller.signal}).then(d => {setHoldings(d.holdings); if(!d.holdings.length) setStatus('No active holdings. Use New to start with a stock purchase.');}).catch(e => {if(e.name !== 'AbortError') setStatus(e.message);});
    const hash = () => setSettings(location.hash === '#profile-settings');
    window.addEventListener('hashchange', hash);
    return () => {controller.abort(); generation.current++; scenarioGeneration.current++; scenarioAbort.current?.abort(); window.removeEventListener('hashchange', hash);};
  }, []);
  useEffect(() => {
    const token = ++generation.current, controller = new AbortController();
    scenarioGeneration.current++; scenarioAbort.current?.abort();
    setAnalysis(null); setBaseline(null); setModes({}); setPending(false);
    if (!holding) return;
    if(holding.call_contracts===0) {setStatus('Stock purchase recorded. Use Transactions → Option Opening Sale to record the call before optimizing.');return;}
    if(holding.can_mark_expired) {setStatus('Historical call recorded. Use Transactions → Rollover to enter its buyback and replacement sale, or record its actual expiry outcome.');return;}
    setStatus('Loading saved analysis…');
    api(`/api/exit-optimizer/capture?${captureQuery(holding)}`, {signal: controller.signal, allowMissing: true}).then(d => {
      if(token !== generation.current) return;
      if(d) {setBaseline(d); setAnalysis(d); setPrice(midpoint(d)); setScenarioStatus('At captured quotes. Close today stays fixed. Options are repriced at fixed captured volatility and spreads.'); setStatus('Saved quotes loaded. Refresh for current prices.');}
      else setStatus('No saved analysis for this holding. Refresh data & analyze to begin.');
    }).catch(e => {if(e.name !== 'AbortError' && token === generation.current) setStatus('Saved analysis unavailable: ' + e.message);});
    return () => controller.abort();
  }, [holding]);
  useEffect(() => {
    if(!baseline || refreshBusy) return;
    const sequence = ++scenarioGeneration.current, controller = new AbortController();
    scenarioAbort.current?.abort(); scenarioAbort.current = controller;
    if(Math.abs(price - midpoint(baseline)) < 1e-8) {setAnalysis(baseline); setPending(false); setScenarioStatus('At captured market quotes. Close today stays fixed.'); return;}
    setPending(true); setScenarioStatus('Updating hypothetical scenario…');
    const timer = setTimeout(async () => {
      try {
        const d = await api('/api/exit-optimizer/scenario', {signal: controller.signal, body: {...positionRequest(holding), stock_price: price}});
        if(sequence !== scenarioGeneration.current) return;
        setAnalysis(d); setScenarioStatus('Close today remains fixed at captured quotes. ' + (d.scenario?.note || ''));
      } catch(e) {if(e.name !== 'AbortError' && sequence === scenarioGeneration.current) setScenarioStatus('Chart retains its previous result: ' + e.message);}
      finally {if(sequence === scenarioGeneration.current) setPending(false);}
    }, 180);
    return () => {clearTimeout(timer); controller.abort();};
  }, [price, baseline, refreshBusy]);
  async function refresh() {
    if(!holding || refreshRunning.current) return;
    refreshRunning.current = true; const token = ++generation.current;
    scenarioGeneration.current++; scenarioAbort.current?.abort(); setPending(false); setRefreshBusy(true);
    setStatus('Retrieving history and verified option quotes, then simulating…');
    try {
      const d = await api('/api/exit-optimizer/run', {body: positionRequest(holding)});
      if(token !== generation.current) return;
      setBaseline(d); setAnalysis(d); setPrice(midpoint(d)); setModes({}); setStatus('Quotes refreshed. Chart updated.');
    } catch(e) {if(token === generation.current) setStatus(e.message.replace(/(?:\s*Previous results retained\.)+$/, '') + (baseline ? ' Previous results retained.' : ''));}
    finally {refreshRunning.current = false; setRefreshBusy(false);}
  }
  async function closeTransactions(positionId) {
    setRecords(false);
    const token=++generation.current;
    try {
      const fresh=await api('/api/exit-optimizer/holdings');
      if(token!==generation.current) return;
      const target=typeof positionId === 'string' ? positionId : holdingIdentity(holding);
      const index=Math.max(0,fresh.holdings.findIndex(h => holdingIdentity(h)===target));
      setHoldings(fresh.holdings);setSelected(String(index));setClosedRevision(value => value+1);
      setStatus('Position records updated.');
    } catch(e) {if(token===generation.current) setStatus('Could not reload positions: '+e.message);}
  }
  async function holdingCreated(created) {
    setCreating(false);await closeTransactions(created.position_id);setRecords(true);
  }
  async function holdingDeleted() {
    generation.current++;scenarioGeneration.current++;scenarioAbort.current?.abort();
    setDeleting(false);setAnalysis(null);setBaseline(null);setModes({});setRecommendations(false);setLastExpiration(null);
    setHoldings(old => old.filter(h => holdingIdentity(h)!==holdingIdentity(holding)));setSelected('0');setClosedRevision(value => value+1);
    try {const fresh=await api('/api/exit-optimizer/holdings');setHoldings(fresh.holdings);setStatus('Holding and associated records deleted.');}
    catch {setStatus('Holding deleted. Reload the page to refresh the remaining holdings.');}
  }
  function holdingClosed(record) {
    generation.current++; scenarioGeneration.current++; scenarioAbort.current?.abort();
    const remaining = holdings.filter(h => h.position_key !== record.position_key);
    setClosing(false); setHoldings(remaining); setSelected('0');
    setAnalysis(null); setBaseline(null); setModes({}); setPending(false); setRecommendations(false);
    setClosedReport(true); setClosedRevision(value => value + 1);
    setStatus(remaining.length ? 'Holding closed and moved to the report.' : 'No active covered-call holdings. See Closed holdings below.');
  }
  async function optionExpired(record) {
    setLastExpiration(record);setExpiring(false);generation.current++;scenarioGeneration.current++;scenarioAbort.current?.abort();
    setAnalysis(null);setBaseline(null);setModes({});setPending(false);setRecommendations(false);
    const remaining=holdings.filter(h => h.position_id!==record.position_id);
    if(record.retained_position)remaining.push(record.retained_position);
    setHoldings(remaining);setSelected(String(record.retained_position ? remaining.length-1 : 0));
    setClosedRevision(value => value+1);
    setStatus(`${record.symbol} call expired worthless. Realized option P/L: ${record.realized_option_pl_usd==null ? 'Unavailable' : money(record.realized_option_pl_usd)}. ${record.shares_retained} shares retained. Use Transactions → Option Opening Sale for the next call.`);
  }
  const renderedPrice = analysis ? analysis.scenario?.stock_price ?? midpoint(analysis) : null;
  const unsettled = pending || refreshBusy || (analysis && Math.abs(price - renderedPrice) > 1e-7);
  const openingReference = analysis?.inputs.opening_reference || {};
  const priorCash = openingReference.prior_realized_option_usd === undefined ? 0 : openingReference.prior_realized_option_usd;
  const realizedCash = Number.isFinite(openingReference.historical_option_net_usd) && Number.isFinite(priorCash) ? openingReference.historical_option_net_usd+priorCash : null;
  const closeToday=(baseline?.result.rows || analysis?.result.rows || []).find(row => row.strategy==='Close now');
  const closeProfit=closeToday ? Object.hasOwn(closeToday,'total_pl_usd') ? closeToday.total_pl_usd : closeToday.net_profit_usd : null;
  const closeReference=(baseline || analysis)?.inputs.opening_reference || {};
  const closeSettings = () => {setSettings(false); if(location.hash === '#profile-settings') history.replaceState(null, '', location.pathname + location.search);};
  if (closedReport) return html`<main>
    <header className="optimizer-header"><div><a href="/">Home</a><h1>Closed holdings</h1></div>
      <button type="button" onClick=${() => setClosedReport(false)}>Back to active holdings</button>
    </header>
    <${ClosedHoldings} revision=${closedRevision}/>
  </main>`;
  return html`<main>
    <header className="optimizer-header"><div><a href="/">Home</a><h1>Covered-call optimizer</h1></div>
      <nav className=${'profile-menu' + (menu ? ' open' : '')} aria-label="Profile" onBlur=${e => {if(!e.currentTarget.contains(e.relatedTarget)) setMenu(false);}}>
        <button type="button" aria-expanded=${menu} aria-controls="profile-dropdown" onClick=${() => setMenu(!menu)}>${name || 'My profile'} ▾</button>
        ${menu ? html`<div className="profile-dropdown" id="profile-dropdown"><button onClick=${() => {setSettings(true); setMenu(false);}}>Settings</button></div>` : null}
      </nav>
    </header>
    ${settings ? html`<${Profile} onClose=${closeSettings} onName=${setName}/>` : null}
    ${closing && holding ? html`<${ClosePosition} holding=${holding} capture=${baseline} onClose=${() => setClosing(false)} onSaved=${holdingClosed}/>` : null}
    ${expiring && holding ? html`<${ExpireWorthless} holding=${holding} onClose=${() => setExpiring(false)} onSaved=${optionExpired}/>` : null}
    ${records ? html`<${Settings} holding=${holding} onClose=${closeTransactions}/>` : null}
    ${creating ? html`<${NewHolding} holding=${holding} onClose=${() => setCreating(false)} onSaved=${holdingCreated}/>` : null}
    ${deleting && holding ? html`<${DeleteHolding} holding=${holding} onClose=${() => setDeleting(false)} onDeleted=${holdingDeleted}/>` : null}
    <section><div className="holding-controls">
      <div className="holding-picker"><label>Holding<select aria-label="Holding" value=${selected} disabled=${refreshBusy || !holdings.length} onChange=${e => {generation.current++; scenarioGeneration.current++; scenarioAbort.current?.abort(); setAnalysis(null); setBaseline(null); setSelected(e.target.value);}}>${holdings.map((h, i) => html`<option key=${i} value=${i}>${holdingLabel(h)}</option>`)}</select></label></div>
      <div className="action-groups">
        <div className="action-group optimize" role="group" aria-labelledby="optimization-actions-title"><h2 id="optimization-actions-title">Optimization</h2><div className="action-buttons">
          <button onClick=${refresh} disabled=${refreshBusy || !holding || holding.call_contracts===0 || holding.can_mark_expired}>Refresh data & analyze</button>
          <button type="button" disabled=${!analysis || unsettled || !(analysis.result.rows || []).some(r => r.strategy==='Roll then close')} title="Download all matching rollovers for the displayed stock-price scenario, highest estimated whole-position profit first" onClick=${() => downloadRollovers(analysis, baseline)}>Download all rollovers (CSV)</button>
          <button type="button" disabled=${holding?.call_contracts===0 || holding?.can_mark_expired} aria-expanded=${recommendations} aria-controls="recommendation-panel" onClick=${() => setRecommendations(!recommendations)}>Recommendation</button>
        </div></div>
        <div className="action-group records" role="group" aria-labelledby="holding-actions-title"><h2 id="holding-actions-title">Holdings & records</h2><div className="action-buttons">
          <button type="button" disabled=${refreshBusy} onClick=${() => setCreating(true)}>New</button>
          <button type="button" aria-haspopup="dialog" aria-controls="transaction-records" disabled=${refreshBusy} onClick=${() => setRecords(true)}>Transactions</button>
          <button type="button" aria-haspopup="dialog" aria-controls="close-position" disabled=${refreshBusy || !holding || holding.call_contracts===0} onClick=${() => setClosing(true)}>Close</button>
          <button type="button" title="Available after expiry, once your broker confirms the call expired without assignment" disabled=${refreshBusy || !holding?.position_id || !holding?.can_mark_expired} onClick=${() => setExpiring(true)}>Expired worthless</button>
          <button type="button" onClick=${() => setClosedReport(true)}>Closed holdings</button>
          <button type="button" className="danger" disabled=${refreshBusy || !holding?.position_id} onClick=${() => setDeleting(true)}>Delete</button>
        </div></div>
      </div>
    </div><p id="status" role="status">${status}</p></section>
    ${lastExpiration ? html`<p role="status">${lastExpiration.symbol} call expired worthless. Realized option P/L: ${lastExpiration.realized_option_pl_usd==null ? 'Unavailable' : money(lastExpiration.realized_option_pl_usd)}. ${lastExpiration.shares_retained} shares retained.</p>` : null}
    <div hidden=${!recommendations}><${Recommendations} holding=${holding} analysis=${analysis} price=${price} modes=${modes} pending=${unsettled}/></div>
    ${analysis ? html`<section id="results" aria-busy=${refreshBusy || pending}><h2>Close today & top 3 rollovers <small>USD · recorded historical fees included; future trade fees excluded</small></h2>
      <div id="close-today-summary" aria-labelledby="close-today-title">
        <h3 id="close-today-title">If you close today</h3>
        <p>Estimated total position P/L<strong className=${Number.isFinite(closeProfit) ? closeProfit>=0 ? 'gain' : 'loss' : ''}>${Number.isFinite(closeProfit) ? money(closeProfit) : 'Unavailable — complete transaction history is required'}</strong></p>
        <div className="close-today-breakdown">
          <p>Stock sale<strong>${money(closeToday?.cash_flows.stock_sale)}</strong></p>
          <p>− Call buyback<strong>${money(Math.abs(closeToday?.cash_flows.option_purchase))}</strong></p>
          <p>+ Realized option cash<strong>${money(realizedCash)}</strong></p>
          <p>− Stock purchase and fees<strong>${money(closeReference.stock_cost_usd ?? closeReference.stock_total_usd)}</strong></p>
        </div>
        <small>Based on captured bid/ask quotes. Includes recorded stock and option fees; future closing fees excluded. Close today stays fixed when the scenario slider changes.</small>
      </div>
      <div id="stock-scenario"><div className="scenario-header"><strong>Stock price scenario · USD/share</strong><button disabled=${refreshBusy} onClick=${() => {scenarioGeneration.current++; scenarioAbort.current?.abort(); setPrice(midpoint(baseline)); setAnalysis(baseline); setPending(false);}}>Reset to current quote</button></div>
        <p><strong>${money(price)} / share</strong> ${price >= midpoint(baseline) ? '+' : ''}${money(price - midpoint(baseline))} (${(100 * (price / midpoint(baseline) - 1)).toFixed(1)}%)</p>
        <div className="slider-track"><input aria-label="Hypothetical stock price in USD per share" type="range" min=${midpoint(baseline) * .5} max=${midpoint(baseline) * 1.5} step="any" value=${price} disabled=${refreshBusy} onChange=${e => {scenarioGeneration.current++; scenarioAbort.current?.abort(); setPending(true); setPrice(Number(e.target.value));}}/><div className="quote-marker"><span>Current quote (mid) ${money(midpoint(baseline))}</span></div></div><p role="status">${scenarioStatus}</p>
      </div>
      <div className="legend">${[['#26856c', 'Stock sale / assignment'], ['#d45b68', 'Purchase calls to close'], ['#518acb', 'Sell replacement calls'], ['#7955ac', 'Net P/L']].map(([color, label]) => html`<span key=${label} style=${{'--color': color}}>${label}</span>`)}</div>
      <div id="opening-reference"><div>Original stock purchase · solid line<strong>${money(openingReference.stock_total_usd)}</strong><small>${Number.isFinite(openingReference.stock_price_usd) ? money(openingReference.stock_price_usd) + ' per share · fees excluded' : 'Save the original stock purchase for this holding'}</small></div>
        <div id="realized-cash-summary">Realized option cash<strong>${realizedCash===null ? openingReference.history_status==='incomplete' ? 'History incomplete' : 'Unavailable' : money(realizedCash)}</strong><small>Recorded premiums − buybacks − option fees · includes the open-call premium</small>
        </div>
      </div>
      ${analysis.inputs.opening_reference?.history_status ? html`<p className="center" id="position-history">${analysis.inputs.opening_reference.history_status === 'linked'
        ? `Historical option net cash: ${money(analysis.inputs.opening_reference.historical_option_net_usd)} · ${analysis.inputs.opening_reference.rollover_count} recorded rollovers · historical option fees: ${money(analysis.inputs.opening_reference.historical_option_fees_usd)}`
        : 'Cumulative P/L unavailable.'} ${analysis.inputs.opening_reference.history_note}</p>` : null}
      <p className="center">Each P/L bar shows the total result for that choice: profit above zero, loss below zero. Close includes the stock and option exit; Expire shows option-only P/L while retaining the shares. The slider close scenario uses captured time to expiry, volatility and spreads; it does not predict when the price is reached. Future outcomes are simulations.</p>
      ${analysis.inputs.opening_reference?.prior_realized_option_usd === null ? html`<p className="center">${analysis.inputs.opening_reference.realized_history_note}</p>` : null}
      <p className="exit-mode-note">Close: sell stock and close the replacement call at the model horizon. Expire: assume worthless expiry and retain stock. The existing-call buyback is charged in both modes. Top three are ranked in Close mode; switches do not rerank them.</p>
      <${Chart} key=${holdingIdentity(holding)} analysis=${analysis} baseline=${baseline} modes=${modes} scenarioPrice=${pending ? null : price} onMode=${(key, mode) => setModes(old => ({...old, [key]: mode}))}/>
      <p className="center">Sale floor = original purchase × 1.10.<br/>Close P/L = accumulated option cash + exit cash − stock purchase cost and recorded purchase fees.<br/>Expire option P/L = accumulated option cash + new premium − held-call buyback today.<br/><small>Path percentages describe this simulation, not guaranteed probabilities. Early assignment is not simulated.</small></p>
      <p className="center funding-note">Roll cash needed = max(existing-call buyback − new premium, $0), before fees. Assumes a combined rollover; separate legs may require the full buyback first. This is the net debit, not broker margin or an additional-deposit estimate. <a href="https://invest.questrade.com/learning/questrade-basics/balances-and-reports/real-time-buying-power" target="_blank" rel="noopener">About broker buying power</a></p>
      <details className="analysis-details"><summary>Analysis details & sources</summary><${AnalysisDetails} analysis=${analysis}/></details>
    </section>` : null}
  </main>`;
}

function AnalysisDetails({analysis: d}) {
  const r = d.result;
  return html`<p>${d.scenario ? 'HYPOTHETICAL stock price ' + money(d.scenario.stock_price) + '. ' : ''}Captured ${d.inputs.captured_at}. ${r.history_count} completed stock closes (${r.history_start} to ${r.history_end}); ${d.inputs.candidates.length} listed candidates, ${r.excluded} excluded. Ranked by estimated net P/L, including losses and sale-floor failures. All amounts USD.</p>
    <p>Original purchase: ${money(r.initial_purchase_price_usd)} per share. Minimum stock sale: ${money(r.minimum_stock_sale_price_usd)} (+10%). Strike range: ${r.search ? (r.search.minimum_exclusive ? 'above ' : 'at least ') + money(r.search.minimum_strike) + '; no fixed upper cap' : 'refresh required'}. Expiry range: ${r.search ? r.search.first_expiry + ' to ' + r.search.last_expiry : 'refresh required'}. Assignment-strike checks are separate from sale-floor path frequencies. Expire reports option-only P/L excluding retained stock value; this is not directly comparable to fully liquidated position P/L.</p>
    <p><a href="/covered-call-readme.md" target="_blank" rel="noopener">How the model works</a> · <a href="/investment-architecture.svg" target="_blank" rel="noopener">App architecture</a> · <a href="/covered-call-design.svg" target="_blank" rel="noopener">Current design</a> · <a href="/design1.svg" target="_blank" rel="noopener">Proposed TFT design</a></p>
    <pre className="prose">${JSON.stringify({sources: d.inputs.sources, assumptions: r.assumptions, paths: r.paths, seed: r.seed, constraint: r.constraint, heldImpliedVolatility: r.held_implied_volatility, realizedVolatility: r.realized_volatility}, null, 2)}</pre>`;
}
