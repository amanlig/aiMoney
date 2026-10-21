import {html, useState, useEffect, useRef} from './ui.js';
import {api, midpoint, money, holdingLabel, readStored} from './api.js';
import {Chart} from './Chart.js';
import {Settings} from './Settings.js';
import {Recommendations} from './Recommendations.js';

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
  const [recommendations, setRecommendations] = useState(false);
  const generation = useRef(0), scenarioGeneration = useRef(0), scenarioAbort = useRef(null), refreshRunning = useRef(false);
  const holding = holdings[Number(selected)];
  useEffect(() => {
    const controller = new AbortController();
    api('/api/exit-optimizer/holdings', {signal: controller.signal}).then(d => {setHoldings(d.holdings); if(!d.holdings.length) setStatus('No saved covered-call holdings available. Import positions first.');}).catch(e => {if(e.name !== 'AbortError') setStatus(e.message);});
    const hash = () => setSettings(location.hash === '#profile-settings');
    window.addEventListener('hashchange', hash);
    return () => {controller.abort(); generation.current++; scenarioGeneration.current++; scenarioAbort.current?.abort(); window.removeEventListener('hashchange', hash);};
  }, []);
  useEffect(() => {
    const token = ++generation.current, controller = new AbortController();
    scenarioGeneration.current++; scenarioAbort.current?.abort();
    setAnalysis(null); setBaseline(null); setModes({}); setPending(false);
    if (!holding) return;
    setStatus('Loading saved analysis…');
    api(`/api/exit-optimizer/capture?account=${encodeURIComponent(holding.account)}&symbol=${encodeURIComponent(holding.symbol)}`, {signal: controller.signal, allowMissing: true}).then(d => {
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
        const d = await api('/api/exit-optimizer/scenario', {signal: controller.signal, body: {account: holding.account, symbol: holding.symbol, stock_price: price}});
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
      const d = await api('/api/exit-optimizer/run', {body: {account: holding.account, symbol: holding.symbol}});
      if(token !== generation.current) return;
      setBaseline(d); setAnalysis(d); setPrice(midpoint(d)); setModes({}); setStatus('Quotes refreshed. Chart updated.');
    } catch(e) {if(token === generation.current) setStatus(e.message + ' Previous results retained.');}
    finally {refreshRunning.current = false; setRefreshBusy(false);}
  }
  const renderedPrice = analysis ? analysis.scenario?.stock_price ?? midpoint(analysis) : null;
  const unsettled = pending || refreshBusy || (analysis && Math.abs(price - renderedPrice) > 1e-7);
  const closeSettings = () => {setSettings(false); if(location.hash === '#profile-settings') history.replaceState(null, '', location.pathname + location.search);};
  return html`<main>
    <header className="optimizer-header"><div><a href="/">Investment</a><h1>Covered-call optimizer</h1></div>
      <nav className=${'profile-menu' + (menu ? ' open' : '')} aria-label="Profile" onBlur=${e => {if(!e.currentTarget.contains(e.relatedTarget)) setMenu(false);}}>
        <button type="button" aria-expanded=${menu} aria-controls="profile-dropdown" onClick=${() => setMenu(!menu)}>${name || 'My profile'} ▾</button>
        ${menu ? html`<div className="profile-dropdown" id="profile-dropdown"><button onClick=${() => {setSettings(true); setMenu(false);}}>Settings</button></div>` : null}
      </nav>
    </header>
    ${settings ? html`<${Settings} onClose=${closeSettings} onName=${setName}/>` : null}
    <section><div className="holding-controls"><label>Holding<select aria-label="Holding" value=${selected} disabled=${refreshBusy || !holdings.length} onChange=${e => {generation.current++; scenarioGeneration.current++; scenarioAbort.current?.abort(); setAnalysis(null); setBaseline(null); setSelected(e.target.value);}}>${holdings.map((h, i) => html`<option key=${i} value=${i}>${holdingLabel(h)}</option>`)}</select></label>
      <button onClick=${refresh} disabled=${refreshBusy || !holding}>Refresh data & analyze</button><button type="button" aria-expanded=${recommendations} aria-controls="recommendation-panel" onClick=${() => setRecommendations(!recommendations)}>Recommendation</button></div><p id="status" role="status">${status}</p></section>
    <div hidden=${!recommendations}><${Recommendations} holding=${holding} analysis=${analysis} price=${price} modes=${modes} pending=${unsettled}/></div>
    ${analysis ? html`<section id="results" aria-busy=${refreshBusy || pending}><h2>Close today & top 3 rollovers <small>USD · fees excluded</small></h2>
      <div id="stock-scenario"><div className="holding-controls"><strong>Stock price scenario · USD/share</strong><button disabled=${refreshBusy} onClick=${() => {scenarioGeneration.current++; scenarioAbort.current?.abort(); setPrice(midpoint(baseline)); setAnalysis(baseline); setPending(false);}}>Reset to current quote</button></div>
        <p><strong>${money(price)} / share</strong> ${price >= midpoint(baseline) ? '+' : ''}${money(price - midpoint(baseline))} (${(100 * (price / midpoint(baseline) - 1)).toFixed(1)}%)</p>
        <div className="slider-track"><input aria-label="Hypothetical stock price in USD per share" type="range" min=${midpoint(baseline) * .5} max=${midpoint(baseline) * 1.5} step="any" value=${price} disabled=${refreshBusy} onChange=${e => {scenarioGeneration.current++; scenarioAbort.current?.abort(); setPending(true); setPrice(Number(e.target.value));}}/><div className="quote-marker"><span>Current quote (mid) ${money(midpoint(baseline))}</span></div></div><p role="status">${scenarioStatus}</p>
      </div>
      <div className="legend">${[['#26856c', 'Stock sale / assignment'], ['#d45b68', 'Purchase calls to close'], ['#518acb', 'Sell replacement calls'], ['#7955ac', 'Close: net profit · Expire: option-only P&L']].map(([color, label]) => html`<span key=${label} style=${{'--color': color}}>${label}</span>`)}</div>
      <div id="opening-reference">${[['Original stock purchase · solid line', 'stock_total_usd', 'stock_price_usd', 'per share'], ['Original option sale premium · dashed line', 'option_total_usd', 'option_price_usd', 'per underlying share']].map(([label, total, unit, suffix]) => {const ref = analysis.inputs.opening_reference || {}; return html`<div key=${total}>${label}<strong>${money(ref[total])}</strong><small>${Number.isFinite(ref[unit]) ? money(ref[unit]) + ' ' + suffix + ' · fees excluded' : 'Save the original transaction for this holding'}</small></div>`;})}</div>
      <p className="exit-mode-note">Close: sell stock and close the replacement call at the model horizon. Expire: assume worthless expiry and retain stock. The existing-call buyback is charged in both modes. Top three are ranked in Close mode; switches do not rerank them.</p>
      <${Chart} key=${holding.account + holding.symbol} analysis=${analysis} baseline=${baseline} modes=${modes} onMode=${(key, mode) => setModes(old => ({...old, [key]: mode}))}/>
      <p className="center">Sale floor = original purchase × 1.10.<br/>Close profit = closing cash + original premium − original stock cost.<br/>Expire option P&L = original premium + new premium − held-call buyback today.<br/><small>Path percentages describe this simulation, not guaranteed probabilities. Early assignment is not simulated.</small></p>
      <p className="center funding-note">Roll cash needed = max(existing-call buyback − new premium, $0), before fees. Assumes a combined rollover; separate legs may require the full buyback first. This is the net debit, not broker margin or an additional-deposit estimate. <a href="https://invest.questrade.com/learning/questrade-basics/balances-and-reports/real-time-buying-power" target="_blank" rel="noopener">About broker buying power</a></p>
      <details className="analysis-details"><summary>Analysis details & sources</summary><${AnalysisDetails} analysis=${analysis}/></details>
    </section>` : null}
  </main>`;
}

function AnalysisDetails({analysis: d}) {
  const r = d.result;
  return html`<p>${d.scenario ? 'HYPOTHETICAL stock price ' + money(d.scenario.stock_price) + '. ' : ''}Captured ${d.inputs.captured_at}. ${r.history_count} completed stock closes (${r.history_start} to ${r.history_end}); ${d.inputs.candidates.length} listed candidates, ${r.excluded} excluded. Ranked by estimated net profit, including losses and sale-floor failures. All amounts USD.</p>
    <p>Original purchase: ${money(r.initial_purchase_price_usd)} per share. Minimum stock sale: ${money(r.minimum_stock_sale_price_usd)} (+10%). Strike range: ${r.search ? (r.search.minimum_exclusive ? 'above ' : 'at least ') + money(r.search.minimum_strike) + '; no fixed upper cap' : 'refresh required'}. Expiry range: ${r.search ? r.search.first_expiry + ' to ' + r.search.last_expiry : 'refresh required'}. Assignment-strike checks are separate from sale-floor path frequencies. Expire reports option-only P&L excluding retained stock value; this is not directly comparable to fully liquidated position profit.</p>
    <p><a href="/covered-call-readme.md" target="_blank" rel="noopener">How the model works</a> · <a href="/investment-architecture.svg" target="_blank" rel="noopener">App architecture</a> · <a href="/covered-call-design.svg" target="_blank" rel="noopener">Current design</a> · <a href="/design1.svg" target="_blank" rel="noopener">Proposed TFT design</a></p>
    <pre className="prose">${JSON.stringify({sources: d.inputs.sources, assumptions: r.assumptions, paths: r.paths, seed: r.seed, constraint: r.constraint, heldImpliedVolatility: r.held_implied_volatility, realizedVolatility: r.realized_volatility}, null, 2)}</pre>`;
}
