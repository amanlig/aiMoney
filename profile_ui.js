'use strict';
let stockBasisError=null;
function profileWithoutBasis(profile){return {...profile,holdings:Object.fromEntries(Object.entries(profile.holdings||{}).map(([k,v])=>{const {costBasis,...other}=v;return [k,other];}))};}
// Keep a one-time copy of legacy browser-only bases before loading authoritative DB values.
let legacyBrowserBases=[];
try{
 const backupKey='covered-call-cost-basis-before-sqlite-v1';
 const old=localStorage.getItem(backupKey);
 if(!old)localStorage.setItem(backupKey,JSON.stringify(profileSettings.holdings||{}));
 const holdings=JSON.parse(old||JSON.stringify(profileSettings.holdings||{}));
 for(const [key,value] of Object.entries(holdings)){if(!value.costBasis)continue;const [account,currency,symbol]=JSON.parse(key),b=value.costBasis;legacyBrowserBases.push({...b,account,currency,symbol,totalCost:currency==='CAD'?b.cadTotal:(b.usdTotal??b.quantity*b.priceUsd+b.feesUsd)});}
}catch{}
async function saveStockBases(bases){const response=await fetch('/api/stock-cost-basis',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({bases})});const result=await response.json();if(!response.ok)throw new Error(result.error||'Cost-basis save failed.');return result.bases;}
async function loadStockBases(){
 const response=await fetch('/api/stock-cost-basis');if(!response.ok)throw new Error('SQLite cost basis unavailable; restart the updated dashboard server.');const result=await response.json();
 for(const basis of result.bases){const account=accounts.find(a=>a.account===basis.account&&a.currency===basis.currency),position=account?.positions.find(p=>p.symbol===basis.symbol);if(!position)continue;
 const holdingKey=ProfileSettings.key(account,position);profileSettings.holdings[holdingKey]={...(profileSettings.holdings[holdingKey]||{}),costBasis:basis};
 const entryKey=EntryPrices.key(account,position),existing=entryOverrides[entryKey]||{},current=EntryPrices.apply(account,entryOverrides).positions.find(p=>p.symbol===position.symbol);
 entryOverrides[entryKey]={currency:account.currency,stockPrice:basis.averageCost,entryFx:basis.fx,optionPrice:existing.optionPrice!=null?current.premium/(current.contracts*100):null};
 }
 stockBasisError=null;renderAccounts();renderStockDetails();
}
const stockBasisReady=loadStockBases().catch(error=>{stockBasisError=error.message;});

function renderProfileName(){const node=document.querySelector('#profile-name');if(node)node.textContent=profileSettings.name||'My profile';}
async function openProfileSettings(){
 if(!document.querySelector('#profile-settings')){location.href='covered-call-optimizer.html#profile-settings';return;}
 await stockBasisReady;
 const dialog=document.querySelector('#profile-settings'),body=document.querySelector('#settings-body');body.replaceChildren();
 const form=element('form');form.id='profile-settings-form';body.append(form);
 const intro=element('p','Configure each holding separately by account. Purchase prices and minimum acceptable stock bids use the account’s currency. A blank minimum bid uses purchase-price break-even. For CAD accounts, enter the actual purchase-time CAD per USD rate to recover the original USD purchase price for strike selection. Today’s FX values current proceeds and CAD break-even. Missing purchase FX is never filled from today’s rate. Your separate 5% stock-loss warning remains active.','context');form.append(intro);
 form.append(element('p','Initial purchase prices are averages derived from saved broker book costs. Replace them with your verified original prices. Verified opening option sales can be recorded in the premium section below.','context'));
 const fields=element('div',undefined,'fields');form.append(fields);
 const nameLabel=element('label','Profile name'),name=element('input');name.type='text';name.maxLength=60;name.value=profileSettings.name||'';name.placeholder='My profile';nameLabel.append(name);fields.append(nameLabel);
 form.append(element('p','Purchase cost basis: enter shares, USD price, USD fees and purchase FX. The optional actual CAD cost overrides rounding. These fields describe one purchase lot or a combined average basis; use the total quantity and total fees for combined purchases. Cost per share is applied to the current holding.','context'));
 const importButton=element('button','Import previous browser cost bases');importButton.type='button';importButton.disabled=!legacyBrowserBases.length;
 importButton.addEventListener('click',async()=>{if(!confirm('Import '+legacyBrowserBases.length+' previous browser cost bases into SQLite? Matching saved records will be replaced.'))return;try{await saveStockBases(legacyBrowserBases);await loadStockBases();dialog.close();openProfileSettings();}catch(error){status.textContent=error.message;}});form.append(importButton);
 form.append(element('p','Stock cost basis is saved in SQLite and shared with the closing simulator. Previous browser values are retained in a backup for optional import. Minimum bids and profile preferences remain browser settings.','context'));
 const rows=[];
 for(const account of accounts){
  const effective=EntryPrices.apply(account,entryOverrides);
  form.append(element('h3',`${account.account} · ${account.currency}`));
  const wrap=element('div',undefined,'table-scroll'),table=element('table');wrap.append(table);form.append(wrap);
  const header=element('thead'),tr=element('tr');header.append(tr);table.append(header);
  for(const label of ['Holding','Original purchase price / share','Minimum acceptable stock bid / share','Purchase FX (CAD per USD)','Purchase date','Purchase shares','USD price / share','Purchase fees (USD)','Actual CAD cost (optional)','Restore']){const th=element('th',label);th.scope='col';tr.append(th);}
  const body=element('tbody');table.append(body);
  for(const position of account.positions||[]){
   const current=effective.positions.find(p=>p.symbol===position.symbol),row=element('tr');body.append(row);
   row.append(element('td',`${position.symbol} · ${position.shares} shares`));
   function input(label,value,required){const td=element('td'),node=element('input');node.type='number';node.min='0.00000001';node.step='any';node.required=required;node.value=value==null?'':String(value);node.setAttribute('aria-label',`${account.account} ${position.symbol} ${label} (${account.currency}/share)`);td.append(node);row.append(td);return node;}
   const purchase=input('original purchase price',current.cost===null?null:current.cost/current.shares,true);
   const bid=input('minimum acceptable stock bid',profileSettings.holdings?.[ProfileSettings.key(account,position)]?.minimumBid??null,false);
   const fx=input('purchase FX CAD per USD',account.currency==='CAD'?current.entryFx:null,false);
   fx.disabled=account.currency!=='CAD';fx.placeholder=account.currency==='CAD'?'Enter historical rate':'Not needed';
   const savedBasis=profileSettings.holdings?.[ProfileSettings.key(account,position)]?.costBasis;
   const date=input('purchase date',null,false);date.type='date';date.value=savedBasis?.date||'';
   const quantity=input('purchase shares',savedBasis?.quantity??null,false);
   const priceUsd=input('purchase USD price',savedBasis?.priceUsd??null,false);
   const feesUsd=input('purchase fees USD',savedBasis?.feesUsd??null,false);feesUsd.min='0';feesUsd.placeholder='0';
   const cadTotal=input('actual purchase CAD total',savedBasis?.cadTotal??null,false);
   for(const node of [date,quantity,priceUsd,feesUsd,cadTotal])node.setAttribute('aria-label',`${account.account} ${position.symbol} ${node===date?'purchase date':node===quantity?'purchase shares':node===priceUsd?'USD price per share':node===feesUsd?'USD fees':'actual CAD total'}`);
   function updateBasis(){
    try{const basis=ProfileSettings.costBasis({quantity:Number(quantity.value),priceUsd:Number(priceUsd.value),feesUsd:Number(feesUsd.value||0),fx:Number(fx.value|| (account.currency==='USD'?1:0)),cadTotal:cadTotal.value===''?null:Number(cadTotal.value)});purchase.value=String(account.currency==='CAD'?basis.cadPerShare:basis.usdPerShare);bid.placeholder=purchase.value;}catch{}
   }
   for(const node of [quantity,priceUsd,feesUsd,cadTotal,fx])node.addEventListener('input',updateBasis);
   bid.placeholder=purchase.value;
   purchase.addEventListener('input',()=>{bid.placeholder=purchase.value;});
   const td=element('td'),reset=element('button','Original values');reset.type='button';td.append(reset);row.append(td);
   reset.addEventListener('click',()=>{purchase.value=position.cost===null?'':String(position.cost/position.shares);bid.value='';bid.placeholder=purchase.value;fx.value=position.entryFx??'';for(const node of [date,quantity,priceUsd,feesUsd,cadTotal])node.value='';});
   rows.push({account,position,current,purchase,bid,fx,date,quantity,priceUsd,feesUsd,cadTotal});
  }
 }
 const actions=element('div',undefined,'entry-actions');form.append(actions);
 const save=element('button','Save settings');save.type='submit';save.className='primary';actions.append(save);
 const cancel=element('button','Cancel');cancel.type='button';cancel.addEventListener('click',()=>dialog.close());actions.append(cancel);
 const status=element('p',undefined,'context');status.setAttribute('role','status');form.append(status);if(stockBasisError)status.textContent=stockBasisError;
 form.addEventListener('submit',async event=>{
  event.preventDefault();if(!form.reportValidity())return;
  save.disabled=true;
  const basisRecords=[];
  const nextProfile={name:name.value.trim(),holdings:{...profileSettings.holdings}},nextEntries={...entryOverrides};
  try{
   for(const {account,position,current,purchase,bid,fx,date,quantity,priceUsd,feesUsd,cadTotal} of rows){
    const value=bid.value.trim()===''?null:Number(bid.value);ProfileSettings.validateMinimum(value);
    const holdingKey=ProfileSettings.key(account,position);
    const hasBasis=[date,quantity,priceUsd,feesUsd,cadTotal].some(node=>node.value!=='');
    const basis=hasBasis&&priceUsd.value!==''?ProfileSettings.costBasis({date:date.value,quantity:Number(quantity.value),priceUsd:Number(priceUsd.value),feesUsd:Number(feesUsd.value||0),fx:Number(fx.value||(account.currency==='USD'?1:0)),cadTotal:cadTotal.value===''?null:Number(cadTotal.value)}):null;
    nextProfile.holdings[holdingKey]={...(nextProfile.holdings[holdingKey]||{}),minimumBid:value,costBasis:basis};
    if(!basis&&cadTotal.value!==''&&quantity.value!==''&&account.currency==='CAD')purchase.value=String(Number(cadTotal.value)/Number(quantity.value));
    if(basis)purchase.value=String(account.currency==='CAD'?basis.cadPerShare:basis.usdPerShare);
    const stockPrice=Number(purchase.value);if(!Number.isFinite(stockPrice)||stockPrice<=0)throw new Error('Enter a positive purchase price.');
    const entryKey=EntryPrices.key(account,position),existing=entryOverrides[entryKey];
    // Preserve the option premium, including a USD entry previously converted to CAD.
    const optionPrice=existing?.optionPrice!=null?current.premium/(current.contracts*100):null;
    const original=position.cost===null?null:position.cost/position.shares;
    const entryFx=account.currency==='CAD'&&fx.value.trim()!==''?Number(fx.value):null;
    if(entryFx!==null&&(!Number.isFinite(entryFx)||entryFx<=0))throw new Error('Enter a positive purchase FX.');
    const quantityValue=basis?.quantity??(quantity.value!==''?Number(quantity.value):position.shares);
    basisRecords.push({account:account.account,symbol:position.symbol,currency:account.currency,date:date.value||null,
     quantity:quantityValue,priceUsd:basis?.priceUsd??null,feesUsd:basis?.feesUsd??null,fx:entryFx,
     totalCost:account.currency==='CAD'&&basis?basis.cadTotal:stockPrice*quantityValue});
    if(stockPrice===original&&optionPrice===null&&entryFx===null)delete nextEntries[entryKey];
    else nextEntries[entryKey]={currency:account.currency,stockPrice:stockPrice===original?null:stockPrice,optionPrice,entryFx};
   }
    await saveStockBases(basisRecords);
  }catch(error){status.textContent=error.message;save.disabled=false;return;}
  profileSettings=nextProfile;entryOverrides=nextEntries;
  let persisted=true;
  try{localStorage.setItem(ProfileSettings.STORAGE_KEY,JSON.stringify(profileWithoutBasis(nextProfile)));localStorage.setItem(EntryPrices.STORAGE_KEY,JSON.stringify(nextEntries));}catch{persisted=false;}
  renderProfileName();renderAccounts();renderStockDetails();
  status.textContent=persisted?'Stock cost basis saved in SQLite. Profile and thresholds saved in this browser.':'Stock cost basis saved in SQLite. Browser-only preferences could not be saved.';save.disabled=false;await loadStockBases();
 });
 mountUSDPremiumSettings(body);
 if(globalThis.legacyOptionPremiumSection)body.append(globalThis.legacyOptionPremiumSection);
 if(!dialog.open)dialog.showModal();
 document.querySelector('#profile-menu')?.classList.remove('open');document.querySelector('#profile-button')?.setAttribute('aria-expanded','false');
}
const profileMenu=document.querySelector('#profile-menu'),profileButton=document.querySelector('#profile-button');
profileButton?.addEventListener('click',()=>{profileMenu.classList.toggle('open');profileButton.setAttribute('aria-expanded',String(profileMenu.classList.contains('open')));});
profileMenu?.addEventListener('mouseenter',()=>profileButton.setAttribute('aria-expanded','true'));
profileMenu?.addEventListener('mouseleave',()=>{if(!profileMenu.contains(document.activeElement)){profileMenu.classList.remove('open');profileButton.setAttribute('aria-expanded','false');}});
document.querySelector('#open-settings')?.addEventListener('click',openProfileSettings);
document.querySelector('#close-settings')?.addEventListener('click',()=>document.querySelector('#profile-settings').close());
renderProfileName();

// Opening-sale capture lives in Profile / Settings, separate from optimizer scenarios.
function mountUSDPremiumSettings(container){
 const section=element('section'),details=element('details'),summary=element('summary','Record original option premium sale (USD)');details.append(summary);section.append(details);container.append(section);
 details.append(element('p','Save a completed opening call sale. Gross USD amounts exclude fees; no CAD conversion is required. Saving a record does not place an order.'));
 const form=element('form'),grid=element('div',undefined,'fields');form.append(grid);details.append(form);
 const fields={};
 for(const [key,title,type] of [['holding','Holding','select'],['date','Settlement date','date'],['price','Premium sold (USD/share)','number']]){
  const label=element('label',title),node=element(type==='select'?'select':'input');if(type!=='select')node.type=type;node.required=true;
  if(type==='number'){node.step='any';node.min='.000001'}fields[key]=node;label.append(node);grid.append(label);
 }
 const total=element('p','Total premium: —');form.append(total);
 const checkLabel=element('label',' I verified this sale against my confirmation.'),review=element('input');review.type='checkbox';review.required=true;review.style.width='auto';checkLabel.prepend(review);form.append(checkLabel);
 const save=element('button','Save option sale');save.type='submit';save.className='primary';form.append(save);
 const status=element('p');status.setAttribute('role','status');form.append(status);
 const list=element('div');details.append(list);let holdings=[],records=[];
 const money=n=>n.toLocaleString('en-CA',{style:'currency',currency:'USD'});
 const selected=()=>holdings[Number(fields.holding.value)];
 function update(){
  const h=selected(),price=Number(fields.price.value);total.textContent='Total premium: '+(h&&price>0?money(h.call_contracts*100*price):'—');review.checked=false;
 }
 function showRecords(){
  const h=selected();list.replaceChildren();if(!h)return;
  const matching=records.filter(r=>r.account===h.account&&r.symbol===h.symbol&&r.expiry===h.call_expiry&&r.strike===Number(h.call_strike_native_currency)&&r.contracts===h.call_contracts);
  list.append(element('h3','Saved opening sales'));
  if(!matching.length)list.append(element('p','No original premium recorded for this holding.'));
  for(const r of matching)list.append(element('p',`${r.settlement_date} · ${r.contracts} contracts × 100 × ${money(r.price_usd)} = ${money(r.contracts*100*r.price_usd)} gross USD`));
  if(matching.length>1)list.append(element('p','Multiple matching sales: the optimizer does not choose or aggregate them automatically.'));
 }
 async function loadRecords(){
  const responses=await Promise.all([fetch('/api/option-premiums'),fetch('/api/option-premiums/usd')]);
  if(responses.some(r=>!r.ok))throw Error('Opening premium storage unavailable.');
  records=(await Promise.all(responses.map(r=>r.json()))).flatMap(d=>d.premiums);showRecords();
 }
 fields.holding.addEventListener('change',()=>{fields.price.value='';update();showRecords()});
 fields.price.addEventListener('input',update);fields.date.addEventListener('input',()=>review.checked=false);
 save.disabled=true;
 fetch('/api/exit-optimizer/holdings').then(async response=>{
  if(!response.ok)throw Error('Saved holdings unavailable.');holdings=(await response.json()).holdings;
  for(const [i,h] of holdings.entries()){const option=element('option',`${h.account} · ${h.symbol} · ${h.call_contracts} calls · $${h.call_strike_native_currency} · ${h.call_expiry}`);option.value=i;fields.holding.append(option)}
  save.disabled=!holdings.length;await loadRecords();
 }).catch(error=>{status.textContent=error.message});
 form.addEventListener('submit',async event=>{
  event.preventDefault();if(!form.reportValidity())return;const h=selected();if(!h)return;save.disabled=true;status.textContent='Saving…';
  try{
   const response=await fetch('/api/option-premiums/usd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account:h.account,symbol:h.symbol,expiry:h.call_expiry,strike:Number(h.call_strike_native_currency),contracts:h.call_contracts,settlement_date:fields.date.value,price_usd:Number(fields.price.value),reviewed:review.checked})});
   const result=await response.json();if(!response.ok)throw Error(result.error||'Save failed.');await loadRecords();review.checked=false;
   status.textContent='Saved in SQLite. Refresh the optimizer analysis to apply this premium.';
  }catch(error){status.textContent=error.message}finally{save.disabled=false}
 });
}

// Direct link from the optimizer opens the existing profile dialog.
if(location.hash==='#profile-settings')setTimeout(openProfileSettings,0);
window.addEventListener('hashchange',()=>{if(location.hash==='#profile-settings'&&!document.querySelector('#profile-settings')?.open)openProfileSettings()});
