import {html, useState, useRef, useEffect} from './ui.js';
import {money, rollKey} from './api.js';

export function displayedRows(analysis, baseline, modes) {
  const rolls = (analysis.result.top_choices || []).slice(0, 3).map(row =>
    modes[rollKey(analysis, row)] === 'expire' && row.expire_worthless ? row.expire_worthless : row);
  const today = (baseline?.result.rows || analysis.result.rows).find(row => row.strategy === 'Close now');
  return today ? [today, ...rolls] : rolls;
}

export function Chart({analysis, baseline, modes, onMode}) {
  const [detail, setDetail] = useState('Select a strategy to inspect its cash flows. Close liquidates the position; Expire retains stock and assumes worthless expiry.');
  const container = useRef();
  const [width, setWidth] = useState(1040);
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver(entries => setWidth(Math.max(760, entries[0].contentRect.width)));
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {setDetail('Select a strategy to inspect its cash flows. Close liquidates the position; Expire retains stock and assumes worthless expiry.');}, [analysis, modes]);
  const rows = displayedRows(analysis, baseline, modes);
  const reference = analysis.inputs.opening_reference || {};
  if (analysis.result.rows.some(row => !row.cash_flows) || !analysis.result.minimum_stock_sale_price_usd)
    return html`<p>Refresh data & analyze to update this saved analysis.</p>`;
  if (!rows.length) return html`<p>${analysis.result.profit_reference_available === false
    ? 'Save the original option sale premium for this exact holding to calculate net profit.' : 'No usable closing quotes are available.'}</p>`;
  const profit = row => row.exit_mode === 'expire' ? row.option_profit_usd
    : Number.isFinite(reference.stock_total_usd) && Number.isFinite(reference.option_total_usd)
      ? row.mean + reference.option_total_usd - reference.stock_total_usd : null;
  const sale = row => row.cash_flows.stock_sale + row.cash_flows.option_sale;
  const high = Math.max(1, reference.stock_total_usd || 0, reference.option_total_usd || 0,
    ...rows.map(row => Math.max(sale(row), Math.abs(row.cash_flows.option_purchase), profit(row) || 0))) * 1.16;
  const low = Math.min(0, ...rows.map(row => profit(row) || 0)) * 1.12;
  const height = 955, left = 100, top = 40, plotHeight = 495;
  const y = value => top + (high - value) / (high - low) * plotHeight;
  const step = (width - left - 18) / rows.length;
  const floor = reference.stock_price_usd * 1.10;
  return html`<div ref=${container}>
    <div className="scroll" id="chart" role="region" aria-label="Covered-call cash flows in USD" tabIndex="0">
      <svg width=${width} height=${height} viewBox=${`0 0 ${width} ${height}`} role="img" aria-label="Stock sale, call buyback, replacement premium and profit in USD">
        ${Array.from({length: 9}, (_, i) => {const value = low + (high - low) * i / 8; return html`<g key=${i}><line x1=${left} x2=${width - 18} y1=${y(value)} y2=${y(value)} stroke="#333"/><text x=${left - 10} y=${y(value) + 4} textAnchor="end" fontSize="12">${money(value)}</text></g>`;})}
        <line x1=${left} x2=${width - 18} y1=${y(0)} y2=${y(0)} stroke="#7e8c9e"/>
        ${[['stock_total_usd', '#8b602b', 'none'], ['option_total_usd', '#7955ac', '7 5']].filter(([key]) => Number.isFinite(reference[key])).map(([key, color, dash]) => html`<line key=${key} x1=${left} x2=${width - 18} y1=${y(reference[key])} y2=${y(reference[key])} stroke=${color} strokeWidth="2" strokeDasharray=${dash}/>`)}
        ${rows.map((row, i) => {
          const cx = left + step * (i + .5), w = 36, gain = profit(row), expire = row.exit_mode === 'expire';
          const today = row.strategy === 'Close now';
          const floorStatus = expire ? `${row.stock_retained} shares retained; no stock sale`
            : today ? (row.sale_floor_pass_rate === 1 ? 'Stock sale meets floor' : 'Stock sale below floor')
              : `Sale floor met: ${(100 * row.sale_floor_pass_rate).toFixed(1)}% of paths`;
          const funding = row.roll_funding;
          const captured = (baseline || analysis).inputs;
          const quote = (label, q, side) => `${label}: ${money(q?.[side + 'Price'])} × ${q?.[side + 'Size'] ?? 'N/A'}`;
          const liquidity = today ? ['Stock · bid/ask × displayed size', quote('Bid', captured.stock, 'bid'), quote('Ask', captured.stock, 'ask'), 'Held call · size in contracts', quote('Bid', captured.held, 'bid'), quote('Ask', captured.held, 'ask'), `Captured ${captured.captured_at}`] : [];
          const description = `${row.strategy} ${row.expiry || ''} ${row.strike || ''}. ${floorStatus}. Stock sale ${money(row.cash_flows.stock_sale)}; call purchase ${money(row.cash_flows.option_purchase)}; replacement sale ${money(row.cash_flows.option_sale)}. Net cash ${money(row.mean)}. ${expire ? 'Option-only P&L' : 'Full-position profit'} ${money(gain)}. ${expire ? row.assumption + ' Stock value excluded.' : `10–90% range ${money(row.p10)} to ${money(row.p90)}. Versus captured close today ${money(row.mean - (baseline?.result.baseline ?? analysis.result.baseline))}.`} ${funding ? `Roll cash needed ${money(funding.net_debit_usd)}. ${funding.note}` : ''} ${liquidity.join('; ')}`;
          const labels = expire ? [floorStatus, 'Replacement buyback = $0', `Held-call buyback: ${money(row.held_buyback_usd)}`, 'Assumes worthless; no assignment', 'Option P&L excludes stock value']
            : [floorStatus, `Sale price ≥ ${money(floor)}`, today ? 'Assignment: N/A (closed)' : `Assignment strike ${row.strike >= floor ? 'meets' : 'below'} floor`, today ? '' : `${money(row.strike)} ${row.strike >= floor ? '≥' : '<'} ${money(floor)}`, `Floor = ${money(reference.stock_price_usd)} × 1.10`];
          return html`<g key=${today ? 'baseline' : rollKey(analysis, row)}>
            <g tabIndex="0" role="img" aria-label=${description} onMouseEnter=${() => setDetail(description)} onFocus=${() => setDetail(description)} onClick=${() => setDetail(description)}>
              <title>${description}</title>
              <rect x=${cx - 59} y=${y(row.cash_flows.stock_sale)} width=${w} height=${Math.max(0, y(0) - y(row.cash_flows.stock_sale))} fill="#26856c"/>
              <rect x=${cx - 59} y=${y(sale(row))} width=${w} height=${Math.max(0, y(row.cash_flows.stock_sale) - y(sale(row)))} fill="#518acb"/>
              <rect x=${cx - 18} y=${y(Math.abs(row.cash_flows.option_purchase))} width=${w} height=${Math.max(0, y(0) - y(Math.abs(row.cash_flows.option_purchase)))} fill="#d45b68"/>
              ${gain === null ? null : html`<g><rect x=${cx + 23} y=${y(Math.max(0, gain))} width=${w} height=${Math.max(.5, Math.abs(y(gain) - y(0)))} fill="#7955ac"/><text x=${cx + 41} y=${gain >= 0 ? y(gain) - 12 : y(gain) + 17} textAnchor="middle" fontSize="10">${money(gain)}</text></g>`}
              <text x=${cx} y="24" textAnchor="middle" fontSize="12">${'Cash ' + money(row.mean)}</text>
              ${[[-41, 'Sale'], [0, 'Buyback'], [41, expire ? 'Option P&L' : 'Profit']].map(([dx, label]) => html`<text key=${label} x=${cx + dx} y=${y(0) + 18} textAnchor="middle" fontSize="10">${label}</text>`)}
              ${[today ? 'Close today' : `Roll to $${row.strike}`, today ? 'Fixed reference' : row.expiry, today ? '' : expire ? 'Keep stock · assume worthless' : `Close in ${row.days} trading days`].map((label, j) => html`<text key=${j} x=${cx} y=${583 + j * 19} textAnchor="middle" fontSize="11">${label}</text>`)}
              ${labels.map((label, j) => html`<text key=${j} x=${cx} y=${690 + j * 20} textAnchor="middle" fontSize="11">${label}</text>`)}
              ${liquidity.map((label, j) => html`<text key=${j} x=${cx} y=${793 + j * 18} textAnchor="middle" fontSize="10">${label}</text>`)}
              ${funding ? html`<text x=${cx} y="912" textAnchor="middle" fontSize="12" style=${{fill: '#f5ca6b'}}>Roll cash needed: ${money(funding.net_debit_usd)}</text><text x=${cx} y="931" textAnchor="middle" fontSize="10">${funding.net_credit_usd > 0 ? 'Net credit: ' + money(funding.net_credit_usd) : 'Buyback − new premium (minimum $0)'}</text>` : null}
            </g>
            ${today ? null : html`<foreignObject x=${cx - step / 2 + 8} y="636" width=${step - 16} height="40"><div className="roll-toggle" role="radiogroup" aria-label=${`Exit choice for $${row.strike} ${row.expiry}`}>${['close', 'expire'].map(mode => html`<label key=${mode}><input type="radio" name=${'roll-mode-' + i} value=${mode} checked=${(expire ? 'expire' : 'close') === mode} onChange=${() => onMode(rollKey(analysis, row), mode)}/>${mode === 'close' ? 'Close' : 'Expire'}</label>`)}</div></foreignObject>`}
          </g>`;
        })}
      </svg>
    </div>
    <p id="chart-detail" aria-live="polite">${detail}</p>
  </div>`;
}
