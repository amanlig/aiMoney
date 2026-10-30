import {html} from './ui.js';
import {money,midpoint} from './api.js';

export function StockPriceScenario({baseline,price,refreshBusy,pending,onPrice,onReset,status}) {
  const stock=baseline?.inputs.stock;
  const ready=Number.isFinite(stock?.bidPrice) && Number.isFinite(stock?.askPrice) && stock.bidPrice>0 && stock.askPrice>=stock.bidPrice;
  const captured=ready ? midpoint(baseline) : null;
  return html`<div id="stock-scenario" aria-busy=${pending}>
    <div className="scenario-header"><strong>Stock price scenario · USD/share</strong>
      <button disabled=${refreshBusy || !ready} title="Restore the captured stock midpoint and baseline analysis" onClick=${onReset}>Reset to current quote</button></div>
    ${ready ? html`<p><strong>${money(price)} / share</strong> ${price>=captured ? '+' : ''}${money(price-captured)} (${(100*(price/captured-1)).toFixed(1)}%)</p>`
      : html`<p>Load a saved analysis or use Refresh data & analyze to enable stock-price scenarios.</p>`}
    <div className="slider-track"><input aria-label="Hypothetical stock price in USD per share" type="range"
      min=${ready ? captured*.5 : 0} max=${ready ? captured*1.5 : 1} step="any" value=${ready ? price : 0}
      disabled=${refreshBusy || !ready} onChange=${event=>onPrice(Number(event.target.value))}/>
      ${ready ? html`<div className="quote-marker"><span>Current quote (mid) ${money(captured)}</span></div>` : null}
    </div>
    <p role="status">${status}</p>
  </div>`;
}
