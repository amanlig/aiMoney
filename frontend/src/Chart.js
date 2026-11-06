import {buyingPowerCheck,availableBuyingPower} from './BuyingPower.js';
import {html, useState, useRef, useEffect} from './ui.js';
import {money, rollKey} from './api.js';

export function displayedRows(analysis, baseline, modes, scenarioPrice = null, closeMode = 'close') {
  const rolls = (analysis.result.top_choices || []).slice(0, 3).map(row =>
    modes[rollKey(analysis, row)] === 'expire' && row.expire_worthless ? row.expire_worthless : row);
  const fixed=baseline || analysis;
  const today = fixed.result.close_alternatives?.[closeMode] || (closeMode==='close' ? fixed.result.rows.find(row => row.strategy === 'Close now') : null);
  const scenarioClose = Number.isFinite(scenarioPrice) && Number.isFinite(analysis.scenario?.stock_price)
    && Math.abs(scenarioPrice - analysis.scenario.stock_price) < 1e-8
    && baseline && Math.abs(scenarioPrice - (baseline.inputs.stock.bidPrice + baseline.inputs.stock.askPrice) / 2) >= 1e-8
    ? analysis.result.rows.find(row => row.strategy === 'Close now') : null;
  return [...(today ? [today] : []), ...(scenarioClose ? [{...scenarioClose,
    strategy: 'Close at slider price', scenario_price: scenarioPrice}] : []), ...rolls];
}

export function Chart({analysis, baseline, modes, onMode, scenarioPrice, accountFunds = {}, closeMode='close', onCloseMode=()=>{}}) {
  const [detail, setDetail] = useState('Hover or focus a bar segment to see its value.');
  const container = useRef();
  const [width, setWidth] = useState(1040);
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver(entries => setWidth(Math.max(760, entries[0].contentRect.width)));
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {setDetail('Hover or focus a bar segment to see its value.');}, [analysis, modes]);
  const rows = displayedRows(analysis, baseline, modes, scenarioPrice, closeMode);
  const chartWidth = Math.max(width, rows.length * 230 + 118);
  const reference = analysis.inputs.opening_reference || {};
  if (analysis.result.rows.some(row => !row.cash_flows) || !analysis.result.minimum_stock_sale_price_usd)
    return html`<p>Refresh data & analyze to update this saved analysis.</p>`;
  if (!rows.length) return html`<p>${analysis.result.profit_reference_available === false
    ? analysis.inputs.opening_reference?.history_note || 'Save the original option sale and linked rollovers to calculate net P/L.' : 'No usable closing quotes are available.'}</p>`;
  const parts = row => {
    const legacy = ['expire','buyback'].includes(row.exit_mode) ? row.option_profit_usd : row.net_profit_usd;
    const known = Object.hasOwn(row, 'total_pl_usd');
    const realized = known ? row.realized_pl_usd : 0, unrealized = known ? row.unrealized_pl_usd : legacy;
    const value = known ? row.total_pl_usd : legacy;
    const total = Number.isFinite(value) ? value : null;
    const segments = total===null ? [] : [{kind:'total',value:total,color:'#7955ac',start:0,end:total}];
    return {realized,unrealized,total,segments,positive:Math.max(0,total || 0),negative:Math.min(0,total || 0)};
  };
  const sale = row => row.cash_flows.stock_sale + row.cash_flows.option_sale;
  const retainedValue=row=>['close','assigned','buyback'].includes(row.exit_mode) && Number.isFinite(row.retained_stock_value_usd) ? Math.max(0,row.retained_stock_value_usd) : 0;
  const purchaseTotal=reference.stock_total_usd;
  const high = Math.max(1, purchaseTotal || 0,
    ...rows.map(row => Math.max(sale(row)+retainedValue(row), Math.abs(row.cash_flows.option_purchase), parts(row).positive || 0))) * 1.16;
  const low = Math.min(0, ...rows.map(row => parts(row).negative || 0)) * 1.12;
  const buyingPower=availableBuyingPower(accountFunds,analysis.inputs.account);
  const hasBuyingPower=typeof buyingPower==='number' && Number.isFinite(buyingPower);
  const height = hasBuyingPower ? 995 : 955, left = 100, top = 40, plotHeight = 495;
  const y = value => top + (high - value) / (high - low) * plotHeight;
  const step = (chartWidth - left - 18) / rows.length;
  const floor = reference.stock_price_usd * 1.10;
  // Merge adjacent over-budget groups into one transparent hatched rectangle.
  const blockedRanges=[];
  rows.forEach((row,i)=>{
    if(row.strategy==='Close now' || row.strategy==='Close at slider price'
      || buyingPowerCheck(row,accountFunds,analysis.inputs.account).status!=='exceeds') return;
    const previous=blockedRanges[blockedRanges.length-1];
    if(previous && previous.end===i-1) previous.end=i;
    else blockedRanges.push({start:i,end:i});
  });
  return html`<div ref=${container}>
    <p className="buying-power-note">${hasBuyingPower
      ? `${analysis.inputs.account} USD buying power entered: ${money(buyingPower)}. Replacements exceeding it are marked with diagonal lines.`
      : `Buying power not checked: enter USD buying power for ${analysis.inputs.account} in My profile → Settings.`}
      Comparison uses the estimated net rollover debit before future fees. Broker margin requirements can differ.</p>
    <div className="scroll" id="chart" role="region" aria-label="Covered-call cash flows in USD" tabIndex="0">
      <svg width=${chartWidth} height=${height} viewBox=${`0 0 ${chartWidth} ${height}`} role="img" aria-label="Stock sale, call buyback, replacement premium and P/L in USD">
        <defs><pattern id="buying-power-hatch" width="18" height="18" patternUnits="userSpaceOnUse"><path d="M-4 4L4 -4M0 18L18 0M14 22L22 14" stroke="#f5ca6b" strokeWidth="1" strokeOpacity="0.38" fill="none"/></pattern></defs>
        ${Array.from({length: 9}, (_, i) => {const value = low + (high - low) * i / 8; return html`<g key=${i}><line x1=${left} x2=${chartWidth - 18} y1=${y(value)} y2=${y(value)} stroke="#333"/><text x=${left - 10} y=${y(value) + 4} textAnchor="end" fontSize="12">${money(value)}</text></g>`;})}
        <line x1=${left} x2=${chartWidth - 18} y1=${y(0)} y2=${y(0)} stroke="#7e8c9e"/>
        ${Number.isFinite(purchaseTotal) ? html`<line x1=${left} x2=${chartWidth - 18} y1=${y(purchaseTotal)} y2=${y(purchaseTotal)} stroke="#8b602b" strokeWidth="2"/>` : null}
        ${rows.map((row, i) => {
          const cx = left + step * (i + .5), w = 30, pnl = parts(row), gain = pnl.total, expire = row.exit_mode === 'expire', buyback=row.exit_mode==='buyback', assigned=row.exit_mode==='assigned', optionOnly=expire || buyback;
          const today = row.strategy === 'Close now', scenario = row.strategy === 'Close at slider price', closing = today || scenario;
          const floorStatus = expire || buyback ? `${row.stock_retained} shares retained; no stock sale`
            : closing ? (row.sale_floor_pass_rate === 1 ? 'Stock sale meets floor' : 'Stock sale below floor')
              : `Sale floor met: ${(100 * row.sale_floor_pass_rate).toFixed(1)}% of paths`;
          const funding = row.roll_funding;
          const power=closing ? null : buyingPowerCheck(row,accountFunds,analysis.inputs.account);
          const exceeds=power?.status==='exceeds';
          const powerNote=power?.status==='exceeds' ? `Exceeds entered USD buying power ${money(power.buyingPower)}; shortfall ${money(power.shortfall)}.`
            : power?.status==='within' ? `Within entered USD buying power ${money(power.buyingPower)}.`
            : power?.status==='unavailable' ? 'Buying power check unavailable: no usable rollover funding estimate.' : '';
          const captured = (baseline || analysis).inputs;
          const quote = (label, q, side) => `${label}: ${money(q?.[side + 'Price'])} × ${q?.[side + 'Size'] ?? 'N/A'}`;
          const liquidity = today ? ['Stock · bid/ask × displayed size', quote('Bid', captured.stock, 'bid'), quote('Ask', captured.stock, 'ask'), 'Held call · size in contracts', quote('Bid', captured.held, 'bid'), quote('Ask', captured.held, 'ask'), `Captured ${captured.captured_at}`] : [];
          const simulation=row.simulation_quotes;
          const pair=q=>q && Number.isFinite(q.bidPrice) && Number.isFinite(q.askPrice)
            ? `Bid ${money(q.bidPrice)} / Ask ${money(q.askPrice)}` : 'Unavailable';
          const rolloverQuotes=closing ? [] : [
            simulation ? `Simulated mean · Day ${simulation.horizon_days} · USD/share` : 'Future quotes: refresh analysis to load',
            'Stock · estimated bid/ask',
            pair(simulation?.stock),
            expire ? 'Replacement · assumed worthless expiry' : 'Replacement call · estimated bid/ask',
            expire ? 'No expiry quote; assumed $0 payoff' : simulation?.replacement_expired
              ? 'Expired by horizon; no quote' : pair(simulation?.replacement),
            expire ? 'Shares retained; no stock sale' : 'Assignment uses strike · fixed spread',
          ];
          const description = `${row.strategy} ${row.expiry || ''} ${row.strike || ''}. ${floorStatus}. Stock sale ${money(row.cash_flows.stock_sale)}; call purchase ${money(row.cash_flows.option_purchase)}; replacement sale ${money(row.cash_flows.option_sale)}. Net cash ${money(row.mean)}. ${optionOnly ? 'Option-only P/L' : 'Full-position P/L'} ${money(gain)}. Completed-call P/L ${money(pnl.realized)}. Unrealized / simulated P/L ${money(pnl.unrealized)}. ${today ? row.assumption || 'Captured midpoint close reference.' : expire ? row.assumption + ' Stock value excluded.' : `10–90% range ${money(row.p10)} to ${money(row.p90)}. Versus captured close today ${money(row.mean - (baseline?.result.baseline ?? analysis.result.baseline))}.`} ${funding ? `Roll cash needed ${money(funding.net_debit_usd)}. ${funding.note}` : ''} ${retainedValue(row)>0 ? `Retained stock value ${money(retainedValue(row))}; not cash.` : ''} ${liquidity.join('; ')} ${rolloverQuotes.join('; ')} ${powerNote}`;
          const segment = (label, value) => {
            const text = `${label}: ${money(value)}`;
            return {text, props: {tabIndex: 0, role: 'img', 'aria-label': text,
              onMouseEnter: () => setDetail(text), onFocus: () => setDetail(text), onClick: () => setDetail(text)}};
          };
          const stockSegment = segment('Stock sale / assignment', row.cash_flows.stock_sale);
          const retained=retainedValue(row);
          const retainedSegment=segment(`Retained stock value (${row.stock_retained} shares) · not cash`,retained);
          const premiumSegment = segment('Replacement call premium sale', row.cash_flows.option_sale);
          const buybackSegment = segment('Call buyback cost', Math.abs(row.cash_flows.option_purchase));
          const segmentName = () => optionOnly ? 'Net option-only P/L' : 'Net full-position P/L';
          const labels = expire ? [floorStatus, 'Replacement buyback = $0', `Held-call buyback: ${money(row.held_buyback_usd)}`, 'Assumes worthless; no assignment', 'Option P/L excludes stock value']
            : [floorStatus, `Sale price ≥ ${money(floor)}`, closing ? 'Assignment: N/A (closed)' : `Assignment strike ${row.strike >= floor ? 'meets' : 'below'} floor`, closing ? '' : `${money(row.strike)} ${row.strike >= floor ? '≥' : '<'} ${money(floor)}`, `Floor = ${money(reference.stock_price_usd)} × 1.10`];
          if(buyback)labels.splice(0,labels.length,floorStatus,'Call buyback uses captured ask','Stock value excluded from option P/L',`Retained stock value: ${money(row.retained_stock_value_usd)}`);
          if(today && !assigned && !buyback && row.stock_retained>0)labels.splice(0,labels.length,floorStatus,`${captured.contracts*100} covered shares sold`,`${row.stock_retained} excess shares retained`,`Retained value: ${money(row.retained_stock_value_usd)} · not cash`);
          if(assigned)labels.splice(0,labels.length,floorStatus,`Assigned at ${money(captured.held.strike)}`,'Hypothetical; timing not selectable',`${row.stock_retained} excess shares retained`,retainedValue(row)>0 ? `Retained value: ${money(retainedValue(row))} · not cash` : '');
          return html`<g key=${today ? 'baseline' : scenario ? 'scenario-close' : rollKey(analysis, row)} data-scenario-close=${scenario ? 'true' : undefined} data-rollover=${closing ? undefined : 'true'}
            data-buying-power=${power?.status} className=${exceeds ? 'buying-power-exceeded' : undefined}>
            <g role="group" aria-label=${description}>
              <rect x=${cx - 69} y=${y(row.cash_flows.stock_sale)} width=${w} height=${Math.max(0, y(0) - y(row.cash_flows.stock_sale))} fill="#26856c" ...${stockSegment.props}><title>${stockSegment.text}</title></rect>
              <rect x=${cx - 69} y=${y(sale(row))} width=${w} height=${Math.max(0, y(row.cash_flows.stock_sale) - y(sale(row)))} fill="#518acb" ...${premiumSegment.props}><title>${premiumSegment.text}</title></rect>
              ${retained>0 ? html`<rect data-retained-stock="true" data-value=${retained} x=${cx-69} y=${y(sale(row)+retained)} width=${w}
                height=${Math.max(0,y(sale(row))-y(sale(row)+retained))} fill="#70c8b5" ...${retainedSegment.props}><title>${retainedSegment.text}</title></rect>` : null}
              <rect x=${cx - 15} y=${y(Math.abs(row.cash_flows.option_purchase))} width=${w} height=${Math.max(0, y(0) - y(Math.abs(row.cash_flows.option_purchase)))} fill="#d45b68" ...${buybackSegment.props}><title>${buybackSegment.text}</title></rect>
              <g>
                ${pnl.segments.map(part => {const detail = segment(segmentName(part.kind), part.value); return html`<rect key=${part.kind} data-pnl=${part.kind} data-value=${part.value} x=${cx + 39} y=${y(Math.max(part.start, part.end))} width=${w} height=${Math.abs(y(part.end) - y(part.start))} fill=${part.color} ...${detail.props}><title>${detail.text}</title></rect>`;})}
              ${gain === null ? html`<text x=${cx + 54} y=${y(pnl.positive) - 12} textAnchor="middle" fontSize="10">Total P/L unavailable</text>` : html`<g>
                <line x1=${cx + 36} x2=${cx + 72} y1=${y(gain)} y2=${y(gain)} stroke="#edf2f7" strokeWidth="2" style=${{pointerEvents: 'none'}}/>
              </g>`}</g>
              <text x=${cx} y="22" textAnchor="middle" fontSize="14" fontWeight="600">${(optionOnly ? 'Option P/L ' : 'Net P/L ') + (gain===null ? 'unavailable' : money(gain))}</text>
              <text x=${cx} y="36" textAnchor="middle" fontSize="10">${(buyback ? 'Buyback cash flow ' : expire ? 'Rollover net credit(debit) ' : 'Exit cash ') + money(row.mean)}</text>
              ${[[-54, ['Sale']], [0, ['Buyback']], [54, optionOnly ? ['Option', 'P/L'] : ['P/L']]].map(([dx, lines]) => html`<text key=${dx} x=${cx + dx} y=${top + plotHeight + 19} textAnchor="middle" fontSize="11">${lines.map((line, j) => html`<tspan key=${j} x=${cx + dx} dy=${j ? 14 : 0}>${line}</tspan>`)}</text>`)}
              ${[today ? assigned ? 'Assigned (hypothetical)' : buyback ? 'Buy back call today' : 'Close today' : scenario ? `Close at ${money(row.scenario_price)}` : `Roll to $${row.strike}`, today ? assigned ? 'Held strike reference' : buyback ? 'Keep stock · captured ask' : 'Midpoint reference' : scenario ? 'Slider price scenario' : row.expiry, today ? '' : scenario ? 'Captured time to expiry' : expire ? 'Keep stock · assume worthless' : `Close in ${row.days} trading days`].map((label, j) => html`<text key=${j} x=${cx} y=${583 + j * 19} textAnchor="middle" fontSize="11">${label}</text>`)}
              ${labels.map((label, j) => html`<text key=${j} x=${cx} y=${690 + j * 20} textAnchor="middle" fontSize="11">${label}</text>`)}
              ${liquidity.map((label, j) => html`<text key=${j} x=${cx} y=${793 + j * 18} textAnchor="middle" fontSize="10">${label}</text>`)}
              ${rolloverQuotes.map((label,j)=>html`<text key=${j} data-rollover-quote="true" x=${cx} y=${793+j*18} textAnchor="middle" fontSize="10">${label}</text>`)}
              ${funding ? html`<text x=${cx} y="912" textAnchor="middle" fontSize="12" style=${{fill: '#f5ca6b'}}>Roll cash needed: ${money(funding.net_debit_usd)}</text><text x=${cx} y="931" textAnchor="middle" fontSize="10">${funding.net_credit_usd > 0 ? 'Net credit: ' + money(funding.net_credit_usd) : 'Buyback − new premium (minimum $0)'}</text>` : null}
              ${!closing && hasBuyingPower ? html`<text x=${cx} y="951" textAnchor="middle" fontSize="11" fontWeight="600">${exceeds ? 'Exceeds entered buying power' : power?.status==='within' ? 'Within entered buying power' : 'Buying power check unavailable'}</text>
                ${exceeds ? html`<text x=${cx} y="972" textAnchor="middle" fontSize="11">Shortfall: ${money(power.shortfall)}</text>` : null}` : null}
            </g>
            ${today ? html`<foreignObject x=${cx-step/2+4} y="636" width=${step-8} height="40"><div className="roll-toggle today-toggle" role="radiogroup" aria-label="Current position choice">
              ${['close','assigned','buyback'].map(mode=>html`<label key=${mode}><input type="radio" name="current-position-choice" value=${mode}
                disabled=${mode!=='close' && !(baseline || analysis).result.close_alternatives?.[mode]}
                checked=${closeMode===mode} onChange=${()=>onCloseMode(mode)}/>${{close:'Close',assigned:'Assigned',buyback:'Buyback'}[mode]}</label>`)}
            </div></foreignObject>` : null}
            ${closing ? null : html`<foreignObject x=${cx - step / 2 + 8} y="636" width=${step - 16} height="40"><div className="roll-toggle" role="radiogroup" aria-label=${`Exit choice for $${row.strike} ${row.expiry}`}>${['close', 'expire'].map(mode => html`<label key=${mode}><input type="radio" name=${'roll-mode-' + i} value=${mode} checked=${(expire ? 'expire' : 'close') === mode} onChange=${() => onMode(rollKey(analysis, row), mode)}/>${mode === 'close' ? 'Close' : 'Expire'}</label>`)}</div></foreignObject>`}
          </g>`;
        })}
        ${blockedRanges.map(({start,end})=>html`<rect key=${start} data-buying-power-overlay="true"
          x=${left+step*start+3} y=${top} width=${step*(end-start+1)-6} height=${plotHeight}
          fill="url(#buying-power-hatch)" stroke="#f5ca6b" strokeOpacity="0.7" strokeWidth="1"
          pointerEvents="none" aria-hidden="true"/>`)}
      </svg>
    </div>
    <p id="chart-detail" aria-live="polite">${detail}</p>
  </div>`;
}
