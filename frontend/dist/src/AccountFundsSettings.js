import {html,useState} from './ui.js';

const ACCOUNTS=['RRSP','TFSA','LIRA'], CURRENCIES=['USD','CAD'];
export function serializeAccountFunds(funds) {
  const result={};
  for(const account of ACCOUNTS) for(const currency of CURRENCIES) {
    const entry=funds[account]?.[currency] || {};
    
    const next={};
    for(const key of ['cashAvailable','buyingPower']) {
      const value=entry[key];
      if(value==null || typeof value==='string' && value.trim()==='') next[key]=0;
      else {
        const amount=Number(value);
        if(typeof value==='boolean' || !Number.isFinite(amount)) throw Error('Enter a valid cash available and buying power amount, or leave it blank.');
        next[key]=amount;
      }
    }
    next.updatedAt=entry._dirty ? new Date().toISOString() : entry.updatedAt || null;
    result[account]={...result[account],[currency]:next};
  }
  return result;
}

export function AccountFundsSettings({holding,funds,onChange}) {
  const [account,setAccount]=useState(holding?.account || 'RRSP');
  const [currency,setCurrency]=useState('USD');
  const entry=funds[account]?.[currency] || {};
  function change(key,value) {
    onChange({...funds,[account]:{...funds[account],[currency]:{...entry,[key]:value,_dirty:true}}});
  }
  return html`<section aria-labelledby="account-funds-title">
    <h3 id="account-funds-title">Cash available and buying power</h3>
    <label>Funds account<select aria-label="Funds account" value=${account} onChange=${event=>setAccount(event.target.value)}>
      ${ACCOUNTS.map(value=>html`<option key=${value}>${value}</option>`)}</select></label>
    <label>Funds currency<select aria-label="Funds currency" value=${currency} onChange=${event=>setCurrency(event.target.value)}>
      ${CURRENCIES.map(value=>html`<option key=${value}>${value}</option>`)}</select></label>
    <div>
      <label>Cash available (${currency})<input aria-label=${`Cash available (${currency})`} type="number" step="0.01" placeholder="Not entered"
        value=${entry.cashAvailable ?? 0} onChange=${event=>change('cashAvailable',event.target.value)}/></label>
      <label>Buying power (${currency})<input aria-label=${`Buying power (${currency})`} type="number" step="0.01" placeholder="Not entered"
        value=${entry.buyingPower ?? 0} onChange=${event=>change('buyingPower',event.target.value)}/></label>
    </div>
    <p>Enter the amounts reported by your broker for this account and currency. Amounts default to zero; blank values are saved as zero.</p>
    <p>Saved in this browser. Entered USD buying power is compared with the estimated net rollover debit to mark over-budget replacements with diagonal lines. Cash available remains a reference value. Model results and rankings are unchanged; broker margin requirements can differ. No currency conversion is applied.</p>
    ${entry.updatedAt && !entry._dirty ? html`<p>Last saved: <time dateTime=${entry.updatedAt}>${new Date(entry.updatedAt).toLocaleString('en-CA')}</time></p>` : null}
  </section>`;
}
