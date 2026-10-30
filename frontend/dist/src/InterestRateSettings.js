import {html, useEffect, useState} from './ui.js';
import {api} from './api.js';

const tenor = years => years < 1 ? `${Number((years*12).toFixed(2))} months` : `${years} ${years === 1 ? 'year' : 'years'}`;

export function InterestRateSettings({holding, value, onChange, valuationDate}) {
  const [reference, setReference] = useState(null), [status, setStatus] = useState('Loading Treasury default…');
  useEffect(() => {
    const controller = new AbortController();
    setReference(null); setStatus('Loading Treasury default…');
    const expiry = holding?.call_contracts > 0 ? holding.call_expiry : null;
    api('/api/interest-rate' + (expiry ? `?expiry=${encodeURIComponent(expiry)}${valuationDate ? '&valuation_date='+encodeURIComponent(valuationDate) : ''}` : ''), {signal: controller.signal})
      .then(data => {setReference(data); setStatus(data.warning || data.note || '');})
      .catch(error => {if (error.name !== 'AbortError') setStatus(error.message);});
    return () => controller.abort();
  }, [holding?.call_expiry, holding?.call_contracts, valuationDate]);
  const automatic = value.mode === 'treasury';
  const percent = automatic ? reference?.annual_percent : value.annual_percent;
  const continuous = percent !== '' && Number.isFinite(Number(percent)) && percent != null ? 200*Math.log1p(Number(percent)/200) : null;
  return html`<section aria-labelledby="interest-rate-title">
    <h3 id="interest-rate-title">Interest rate</h3>
    <label>Interest rate source<select aria-label="Interest rate source" value=${value.mode} onChange=${event => onChange(event.target.value === 'treasury'
      ? {mode: 'treasury'} : {mode: 'manual', annual_percent: reference?.annual_percent ?? ''})}>
      <option value="treasury">U.S. Treasury — match held option maturity</option><option value="manual">Manual override</option>
    </select></label>
    <label>Annual interest yield (%)<input aria-label="Annual interest yield (%)" type="number" min="-5" max="25" step="any" required=${!automatic}
      readOnly=${automatic} value=${automatic ? (Number.isFinite(percent) ? percent.toFixed(4) : '') : percent}
      placeholder=${automatic ? 'Awaiting Treasury rate' : 'Enter annual yield'}
      onChange=${event => onChange({mode: 'manual', annual_percent: event.target.value})}/></label>
    <p>Default source: <a href="https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve" target="_blank" rel="noreferrer">U.S. Treasury Daily Par Yield Curve</a>.</p>
    ${reference?.observed_on ? html`<p>${`Treasury observation: ${reference.observed_on} · Held call expiry: ${reference.expiry}. ` +
      (reference.lower_tenor_years === reference.upper_tenor_years ? `Published tenor: ${tenor(reference.lower_tenor_years)}.` : `Interpolated between ${tenor(reference.lower_tenor_years)} and ${tenor(reference.upper_tenor_years)}.`)}</p>` : null}
    ${continuous !== null ? html`<p>Model rate: ${continuous.toFixed(4)}% annually, continuously compounded. The annual yield uses semiannual compounding.</p>` : null}
    <p>One rate, matched to the held call, applies to all option pricing and cash-flow discounting. Treasury par yields are a proxy for a zero-coupon rate. Settings are saved in this browser.</p>
    <p role="status">${status}</p>
  </section>`;
}
