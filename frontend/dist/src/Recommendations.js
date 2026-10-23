import {html, useState, useEffect, useRef} from './ui.js';
import {api} from './api.js';

export function Recommendations({holding, analysis, price, modes, pending}) {
  const [goal, setGoal] = useState('keep_exposure'), [status, setStatus] = useState('');
  const [assessment, setAssessment] = useState(''), [busy, setBusy] = useState(false);
  const [history, setHistory] = useState([]), [historyError, setHistoryError] = useState('');
  const snapshot = JSON.stringify({account: holding?.account, symbol: holding?.symbol, captured_at: analysis?.inputs.captured_at, stock_price: price, goal, modes});
  const latest = useRef(snapshot), running = useRef(false), mounted = useRef(true);
  latest.current = snapshot;
  useEffect(() => {mounted.current = true; api('/api/optimizer-recommendations/status').then(d => {
    if (mounted.current) setStatus(d.configured ? `OpenAI model: ${d.model}. Load an analysis, then generate.` : d.error || 'Configure OpenAI with setup_openai.py first.');
  }).catch(e => {if (mounted.current) setStatus(e.message);}); return () => {mounted.current = false;};}, []);
  useEffect(() => {if (assessment) setStatus('Inputs changed. Generate a new recommendation for the current chart.');}, [snapshot]);
  async function loadHistory() {
    try {const d = await api('/api/optimizer-recommendations/history'); if (mounted.current) {setHistory(d.runs); setHistoryError('');}}
    catch(e) {if (mounted.current) setHistoryError(e.message);}
  }
  async function generate() {
    if (running.current) return;
    if (!analysis) {setStatus('Load or refresh an analysis first.'); return;}
    if (pending) {setStatus('Wait for the chart to finish recalculating.'); return;}
    const request = snapshot;
    running.current = true; setBusy(true); setStatus('Assessing the current chart with OpenAI…');
    try {
      const d = await api('/api/optimizer-recommendations', {body: JSON.parse(request)});
      if (mounted.current) {setAssessment(d.assessment); setStatus(`Saved assessment #${d.id} · ${d.model} · ${d.created_at}. ` + (request === latest.current ? 'Based on the current chart snapshot.' : 'Inputs changed during generation; this assessment describes the earlier snapshot. Generate again.')); await loadHistory();}
    } catch(e) {if (mounted.current) setStatus(e.message);} finally {running.current = false; if (mounted.current) setBusy(false);}
  }
  return html`<section id="recommendation-panel" aria-label="Optimizer recommendation">
    <h2>Recommendation</h2><p>Uses the selected holding, chart scenario and Close / Expire choices. Sends this snapshot to OpenAI; successful assessments are saved locally.</p>
    <div className="holding-controls"><label>Objective<select value=${goal} onChange=${e => setGoal(e.target.value)}><option value="keep_exposure">Prefer retaining stock</option><option value="free_cash">Free cash for another investment</option><option value="compare">Compare alternatives</option></select></label>
    <button onClick=${generate} disabled=${busy || pending}>Generate recommendation</button></div>
    <p role="status">${status}</p><pre className="prose">${assessment}</pre>
    <details><summary>Assessment process</summary><p>1. Load the saved Questrade / Yahoo capture and original transactions.<br/>2. Recalculate the chart scenario and apply Close / Expire choices; Close today stays at captured quotes.<br/>3. Send verified USD cash flows, profit, funding and assumptions to the configured OpenAI model.<br/>4. Save the assessment and input snapshot in the database. No trade is placed; no live news or account cash balance is supplied.</p></details>
    <details onToggle=${e => {if(e.currentTarget.open) loadHistory();}}><summary>Saved assessments</summary><p role="status">${historyError}</p>
    ${history.length ? history.map(run => {
      let saved; try {saved = JSON.parse(run.snapshot_json);} catch {saved = {};}
      return html`<details key=${run.id}><summary>${run.created_at} · ${saved.position?.account} ${saved.position?.symbol} · ${run.model}</summary><pre className="prose">${run.assessment}</pre><details><summary>Saved input snapshot</summary><pre className="prose">${JSON.stringify(saved, null, 2)}</pre></details></details>`;
    }) : html`<p>No optimizer assessments saved yet.</p>`}</details>
  </section>`;
}
