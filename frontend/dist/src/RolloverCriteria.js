import {html} from './ui.js';
import {money, readStored} from './api.js';

export const CRITERIA_STORAGE = 'covered-call-rollover-criteria-v1';
export const DEFAULT_CRITERIA = {purchase_price_multiplier:1.2,min_strike_above_midpoint_pct:0,max_strike_above_midpoint_pct:null};
export function normalizeCriteria(value) {
  const raw={...DEFAULT_CRITERIA,...value};
  if (raw.purchase_price_multiplier==='' || raw.min_strike_above_midpoint_pct==='') throw Error('Enter a purchase multiplier and minimum midpoint percentage.');
  const result={purchase_price_multiplier:Number(raw.purchase_price_multiplier),min_strike_above_midpoint_pct:Number(raw.min_strike_above_midpoint_pct),
    max_strike_above_midpoint_pct:raw.max_strike_above_midpoint_pct==='' || raw.max_strike_above_midpoint_pct==null ? null : Number(raw.max_strike_above_midpoint_pct)};
  if (!Number.isFinite(result.purchase_price_multiplier) || result.purchase_price_multiplier<=0) throw Error('Purchase-price multiplier must be positive.');
  if (!Number.isFinite(result.min_strike_above_midpoint_pct) || result.min_strike_above_midpoint_pct< -100) throw Error('Minimum midpoint percentage must be at least -100%.');
  const upper=result.max_strike_above_midpoint_pct;
  if (upper!==null && (!Number.isFinite(upper) || upper<result.min_strike_above_midpoint_pct)) throw Error('Maximum midpoint percentage must be at least the minimum, or blank for no limit.');
  return result;
}
export function savedCriteria() {
  try {return normalizeCriteria(readStored(CRITERIA_STORAGE,DEFAULT_CRITERIA));} catch {return {...DEFAULT_CRITERIA};}
}

export function RolloverCriteria({draft,onChange,onReset,disabled,applied,purchasePrice,midpoint,status}) {
  const change=(key,value)=>onChange({...draft,[key]:value});
  let normalized,dirty=true,lower,upper;
  try {
    normalized=normalizeCriteria(draft);dirty=JSON.stringify(normalized)!==JSON.stringify(applied);
    if (Number.isFinite(purchasePrice) && Number.isFinite(midpoint) && midpoint>0) {
      lower=Math.max(purchasePrice*normalized.purchase_price_multiplier,midpoint*(1+normalized.min_strike_above_midpoint_pct/100));
      upper=normalized.max_strike_above_midpoint_pct===null ? null : midpoint*(1+normalized.max_strike_above_midpoint_pct/100);
    }
  } catch {}
  return html`<section id="rollover-criteria" aria-labelledby="rollover-criteria-title">
    <h2 id="rollover-criteria-title">Replacement calls</h2>
    <div>
      <div className="rollover-rule-fields">
        <fieldset disabled=${disabled}><legend>1. Minimum assignment price</legend>
          <label>Purchase-price multiplier<input type="number" min="0.00000001" step="any" required value=${draft.purchase_price_multiplier}
            onChange=${event=>change('purchase_price_multiplier',event.target.value)}/></label>
          <p>Strike ≥ original purchase price × multiplier. Default 1.2× means 20% above purchase.</p>
        </fieldset>
        <fieldset disabled=${disabled}><legend>2. Strike range relative to stock midpoint</legend>
          <label>Minimum relative to midpoint (%)<input type="number" min="-100" step="any" required value=${draft.min_strike_above_midpoint_pct}
            onChange=${event=>change('min_strike_above_midpoint_pct',event.target.value)}/></label>
          <label>Maximum relative to midpoint (%)<input type="number" min=${Math.max(-100,Number(draft.min_strike_above_midpoint_pct)||0)} step="any"
            placeholder="No upper limit" value=${draft.max_strike_above_midpoint_pct ?? ''}
            onChange=${event=>change('max_strike_above_midpoint_pct',event.target.value)}/></label>
          <p>Both boundaries are inclusive. Negative values include in-the-money calls; 0% is at the money. The purchase-price floor still applies. Blank maximum means no cap.</p>
        </fieldset>
      </div>
      ${Number.isFinite(lower) ? html`<p>Preview at stock midpoint ${money(midpoint)}: strike ≥ ${money(lower)}${upper===null ? ', no upper limit' : ` and ≤ ${money(upper)}`}.
        ${upper!==null && lower>upper ? 'No strike meets both rules at this price.' : ''}</p>` : null}
      <div className="entry-actions"><button type="button" disabled=${disabled} onClick=${onReset}>Reset criteria</button></div>
      <p>${dirty ? 'Changes are not applied. Click Refresh data & analyze to apply them.' : 'Refresh data & analyze fetches quotes and evaluates using these criteria.'}</p>
      <p role="status">${status}</p>
    </div>
  </section>`;
}
