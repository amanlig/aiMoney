/* Persistent opening-premium confirmations for exact covered-call holdings. */
(function(){
'use strict';
const section=element('section');section.id='option-premium-entry';globalThis.legacyOptionPremiumSection=section;
const settingsBody=document.querySelector('#profile-settings[open] #settings-body');if(settingsBody)settingsBody.append(section);
const details=element('details'),summary=element('summary','Opening option sale · CAD conversion details (optional)');details.append(summary);section.append(details);
details.append(element('p','Enter the opening call sale confirmation. Premiums are saved locally in SQLite and matched by account, ticker, expiry, strike and contract quantity. Enter total USD fees once; net CAD must match the confirmation.'));
const form=element('form'),grid=element('div',undefined,'fields'),fields={};form.append(grid);details.append(form);
const definitions=[['account','Account',['RRSP','TFSA','LIRA']],['symbol','Ticker','text'],['expiry','Call expiry','date'],['strike','Strike (USD)','number'],['contracts','Contracts (100 shares each)','number'],['settlement_date','Premium settlement date','date'],['price_usd','Sale premium (USD per share)','number'],['fees_usd','Total fees (USD)','number'],['fx','Applied CAD per USD','number'],['net_cad','Net premium received (CAD)','number']];
for(const [key,title,type] of definitions){const label=element('label',title),node=element(Array.isArray(type)?'select':'input');if(Array.isArray(type)){for(const v of type){const o=element('option',v);o.value=v;node.append(o);}}else{node.type=type;if(type==='number'){node.step=key==='contracts'?'1':'any';node.min=key==='fees_usd'?'0':'0.00000001';}}node.required=true;node.name=key;fields[key]=node;label.append(node);grid.append(label);}
const review=element('input');review.type='checkbox';review.required=true;const label=element('label',' I verified the opening call sale against the confirmation.');label.prepend(review);form.append(label);
const save=element('button','Save opening premium');save.type='submit';save.className='primary';form.append(save);
const status=element('p');status.setAttribute('role','status');form.append(status);const list=element('div',undefined,'table-scroll');details.append(list);
form.addEventListener('input',e=>{if(e.target!==review)review.checked=false;});
async function load(){
 const response=await fetch('/api/option-premiums');if(!response.ok)throw new Error('Opening premium storage unavailable. Restart the updated dashboard server.');const result=await response.json();list.replaceChildren();
 const table=element('table'),header=element('tr');for(const title of ['Account','Ticker','Expiry','Strike USD','Contracts','Settlement','Net USD','Net CAD'])header.append(element('th',title));table.append(header);list.append(table);
 for(const p of result.premiums){const row=element('tr');for(const value of [p.account,p.symbol,p.expiry,p.strike,p.contracts,p.settlement_date,p.net_usd.toFixed(2),p.net_cad.toFixed(2)])row.append(element('td',String(value)));table.append(row);}
 // Exact matches only. Multiple opening lots require explicit aggregation rather than guessing.
 for(const account of accounts)for(const position of account.positions||[]){const matches=result.premiums.filter(p=>p.account===account.account&&p.symbol===position.symbol&&p.expiry===position.expiry&&p.strike===Number(position.strike)&&p.contracts===position.contracts);if(matches.length!==1)continue;
 const p=matches[0],key=EntryPrices.key(account,position),existing=entryOverrides[key]||{};
 const current=EntryPrices.apply(account,entryOverrides).positions.find(v=>v.symbol===position.symbol);
 entryOverrides[key]={currency:account.currency,stockPrice:existing.stockPrice!=null?current.cost/current.shares:null,entryFx:current.entryFx??null,optionPrice:(account.currency==='CAD'?p.net_cad:p.net_usd)/(position.contracts*100)};
 }
 try{localStorage.setItem(EntryPrices.STORAGE_KEY,JSON.stringify(entryOverrides));}catch{}
 renderAccounts();renderStockDetails();
}
form.addEventListener('submit',async e=>{e.preventDefault();if(!form.reportValidity())return;save.disabled=true;status.textContent='Saving…';try{const data=Object.fromEntries(Object.entries(fields).map(([k,n])=>[k,n.type==='number'?Number(n.value):n.value]));data.reviewed=review.checked;const response=await fetch('/api/option-premiums',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw new Error(result.error||'Save failed.');form.reset();await load();status.textContent='Opening premium saved in SQLite. Matching holding calculations updated.';}catch(error){status.textContent=error.message;}finally{save.disabled=false;}});
load().catch(error=>{status.textContent=error.message;});
})();
