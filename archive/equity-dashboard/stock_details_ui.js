/* Saved Questrade market details for the selected stock and exact held calls. */
'use strict';
function detailNumber(value,digits=0){
 return typeof value==='number'&&Number.isFinite(value)?value.toLocaleString('en-CA',{minimumFractionDigits:digits,maximumFractionDigits:digits}):'Unavailable';
}
function detailPrice(value){return typeof value==='number'&&Number.isFinite(value)?amount(value,'USD'):'Unavailable';}
function displayedQuote(value,currency){
 const fx=currency==='USD'?1:Number(document.querySelector('#fx-assumption').value);
 return typeof value==='number'&&Number.isFinite(value)&&Number.isFinite(fx)&&fx>0?amount(value*fx,currency):'Unavailable';
}
function quoteValue(tag,value,currency){const node=element(tag,displayedQuote(value,currency));node.dataset.usdPrice=value??'';node.dataset.displayCurrency=currency;return node;}
function updateDisplayedQuotes(){document.querySelectorAll('[data-usd-price]').forEach(node=>{node.textContent=displayedQuote(node.dataset.usdPrice===''?null:Number(node.dataset.usdPrice),node.dataset.displayCurrency);});}
function renderStockDetails(){
 const symbol=document.querySelector('#stock-filter').value;
 const panel=document.querySelector('#stock-details');panel.replaceChildren();panel.hidden=!symbol;
 if(!symbol)return;
 panel.append(element('h2',symbol+' · stock and option details'));
 if(!visibleAccounts().length){panel.append(element('p','No covered-call holdings match this stock and account.','context'));return;}
 const edit=element('button','Enter purchase / option sale prices');edit.type='button';edit.className='primary';edit.setAttribute('aria-expanded','false');panel.append(edit);
 const editor=element('div');editor.hidden=true;panel.append(editor);
 edit.addEventListener('click',()=>{editor.hidden=!editor.hidden;edit.setAttribute('aria-expanded',String(!editor.hidden));if(!editor.hidden){renderEntryEditor(editor,symbol);editor.querySelector('input')?.focus();}});
 const risk=element('div');risk.id='stock-loss-analysis';panel.append(risk);renderStockRisk();
 const rollButton=element('button','Simulate short-call rollover');rollButton.type='button';rollButton.className='primary';rollButton.setAttribute('aria-expanded','false');panel.append(rollButton);
 const rollEditor=element('div');rollEditor.hidden=true;panel.append(rollEditor);
 rollButton.addEventListener('click',()=>{rollEditor.hidden=!rollEditor.hidden;rollButton.setAttribute('aria-expanded',String(!rollEditor.hidden));if(!rollEditor.hidden)renderRollEditor(rollEditor,symbol);});
 if(!marketDetails){panel.append(element('p','Market details have not been captured yet.','warning'));return;}
 const captured=new Date(marketDetails.captured_at).toLocaleString('en-CA',{timeZone:'America/Vancouver',timeZoneName:'short'});
 panel.append(element('p',`${marketDetails.source} · captured ${captured} · saved market-data snapshot`,'context'));
 const stock=marketDetails.stocks[symbol];
 const selectedAccount=document.querySelector('#account-filter').value;
 const quoteCurrency=accountCurrencies[selectedAccount]||'USD';
 panel.append(element('h3','Stock · '+quoteCurrency));
 if(quoteCurrency==='CAD')panel.append(element('p','Stock quotes are shown as CAD equivalents using your conversion assumption. Listed option strikes and broker Greeks retain their original units.','context'));
 if(stock){
  const grid=element('div',undefined,'detail-grid');panel.append(grid);
  for(const [label,value,isPrice] of [['Bid price',stock.bidPrice,true],['Bid size',stock.bidSize,false],['Ask price',stock.askPrice,true],['Ask size',stock.askSize,false]]){
   const box=element('div');box.append(element('span',label,'label'),isPrice?quoteValue('strong',value,quoteCurrency):element('strong',detailNumber(value)));grid.append(box);
  }
  panel.append(element('p',`Quote delay: ${detailNumber(stock.delay)} seconds · trading status: ${stock.isHalted===true?'Halted':stock.isHalted===false?'Not halted':'Unknown'}`,'context'));
 }else panel.append(element('p',marketDetails.errors[symbol]||'Stock quote unavailable.','warning'));
 panel.append(element('h3','Held short calls · exact strikes and expirations'));
 const scroller=element('div',undefined,'table-scroll'),table=element('table');scroller.append(table);panel.append(scroller);
 const caption=element('caption',symbol+' option quotes and broker Greeks');caption.className='context';table.append(caption);
 const header=element('thead'),headerRow=element('tr');header.append(headerRow);table.append(header);
 for(const label of ['Account / currency','Expiry','Strike (USD)','Bid','Bid size','Ask','Ask size','Delta','Theta (broker)','Implied volatility','Delay (sec)']){
  const cell=element('th',label);cell.scope='col';headerRow.append(cell);
 }
 const body=element('tbody');table.append(body);
 for(const account of visibleAccounts()){
  for(const position of account.positions||[]){
   const option=marketDetails.options.find(o=>o.symbol===symbol&&o.expiry===position.expiry&&Number(o.strike)===position.strike&&o.accounts.includes(account.account));
   const row=element('tr');body.append(row);
   const values=[account.account+' · '+account.currency,position.expiry,detailPrice(position.strike),null,detailNumber(option?.bidSize),null,detailNumber(option?.askSize),detailNumber(option?.delta,4),detailNumber(option?.theta,5),typeof option?.volatility==='number'?detailNumber(option.volatility,2)+'%':'Unavailable',detailNumber(option?.delay)];
   values.forEach((value,index)=>row.append(index===3||index===5?quoteValue('td',index===3?option?.bidPrice:option?.askPrice,account.currency):element('td',value)));
   if(option?.error||option?.isHalted===true)panel.append(element('p',`${account.account}: ${option.error||'Option trading is halted.'}`,'warning'));
  }
 }
 panel.append(element('p','Greeks are Questrade values for one long call; your short calls have the opposite delta and theta. Implied volatility is annualized. Sizes are displayed as reported by the broker. Missing values remain unavailable.','context'));
 panel.append(element('p','These details are separate from conversion assumptions and account screenshot values. Only the USD/CAD macro panel refreshes automatically.','context'));
}
function renderStockRisk(){
 const panel=document.querySelector('#stock-loss-analysis');if(!panel)return;
 panel.replaceChildren();
 const symbol=document.querySelector('#stock-filter').value;
 const stock=marketDetails?.stocks[symbol];
 panel.append(element('h3','Stock purchase-price protection · 5% loss limit'));
 for(const account of visibleAccounts()){
  for(const position of account.positions||[]){
   const fx=account.currency==='USD'?1:Number(document.querySelector('#fx-assumption').value);
   const risk=EntryPrices.stockRisk(position,stock?.bidPrice,fx,EntryPrices.purchaseFx(account,position));
   const minimumBid=ProfileSettings.minimumBid(account,position,profileSettings);
   const thresholdMet=Number.isFinite(stock?.bidPrice)&&Number.isFinite(minimumBid)&&stock.bidPrice*fx>=minimumBid;
   const section=element('section',undefined,'entry-form');panel.append(section);
   section.append(element('h3',account.account+' · '+symbol));
   if(position.purchaseContext)section.append(element('p',position.purchaseContext,'context'));
   if(!risk){section.append(element('p','Enter a positive purchase cost and historical purchase FX in Profile → Settings (or the entry-price editor) to calculate this holding.','warning'));continue;}
   const status=risk.change===null?'Loss status unavailable: no usable bid.':risk.unacceptable?'UNACCEPTABLE LOSS · 5% limit breached':risk.change<0?'Within your limit · stock loss is below 5%':'Stock is at or above purchase cost';
   section.append(element('p',status,risk.unacceptable?'loss-alert':risk.change===null?'warning':'context'));
   section.append(element('p',risk.change===null?'Bid threshold status unavailable.':thresholdMet?'Your minimum acceptable bid is met.':'Bid is below your minimum acceptable profit threshold.',risk.change===null?'warning':thresholdMet?'context':'loss-alert'));
   const grid=element('div',undefined,'detail-grid');section.append(grid);
   const change=risk.change===null?'Unavailable':`${risk.change>=0?'+':''}${(risk.change*100).toFixed(2)}%`;
   for(const [label,value] of [['Purchase price (USD/share)',detailPrice(risk.purchaseUsd)],['Stock P/L at current bid',amount(risk.stockPnl,account.currency)],['Change from purchase',change],['Minimum bid to break even',detailPrice(risk.breakevenBid)],['Your minimum acceptable bid ('+account.currency+')',amount(minimumBid,account.currency)],['Minimum bid for loss below 5%',detailPrice(risk.acceptableBid)]]){
    const box=element('div');box.append(element('span',label,'label'),element('strong',value));grid.append(box);
   }
   section.append(element('p',`Stock break-even = total stock purchase cost ÷ shares. Original purchase basis: USD ${risk.purchaseUsd.toFixed(5)}/share; minimum bids rounded up to cent increments. A loss of exactly 5% is unacceptable. Stock P/L excludes option premiums and closing fees.`,'context'));
   if(account.currency!=='USD')section.append(element('p',`Original USD purchase price uses purchase-time FX ${position.entryFx} CAD/USD. Current proceeds and CAD-cost break-even use today’s editable FX ${fx} CAD/USD. Today’s FX does not change your original USD purchase price.`,'context'));
  }
 }
}
function renderEntryEditor(container,symbol){
 container.replaceChildren();
 container.append(element('p','Enter the average stock purchase price per share and the option premium received per underlying share (a $2 premium equals $200 per standard contract). Blank fields keep the original value.','context'));
 container.append(element('p','Prices are saved in this browser for each account and contract. They update position P/L.','context'));
 const selectedAccount=document.querySelector('#account-filter').value;
 for(const account of accounts.filter(a=>!selectedAccount||a.account===selectedAccount)){
  for(const position of (account.positions||[]).filter(p=>p.symbol===symbol)){
   const entryKey=EntryPrices.key(account,position),saved=entryOverrides[entryKey];
   const form=element('form',undefined,'entry-form');container.append(form);
   form.append(element('h3',`${account.account} · ${position.shares} shares / ${position.contracts} short calls · USD ${position.strike} · ${position.expiry}`));
   const fields=element('div',undefined,'fields');form.append(fields);
   const currencyLabel=element('label','Entry price currency'),currency=element('select');currencyLabel.append(currency);fields.append(currencyLabel);
   for(const value of [...new Set([account.currency,'USD'])]){const option=element('option',value);option.value=value;currency.append(option);}
   currency.value=saved?.currency||account.currency;
   function priceInput(label,value){const wrap=element('label',label),input=element('input');input.type='number';input.min='0';input.step='any';input.value=value===null||value===undefined?'':String(value);wrap.append(input);fields.append(wrap);return {wrap,input};}
   const stock=priceInput('Stock purchase price per share',saved?.stockPrice??null);
   const call=priceInput('Option sale premium per share',saved?.optionPrice??null);
   const fx=priceInput('Historical entry FX · CAD per USD',saved?.entryFx??position.entryFx??null);
   const original=element('p',`Original cost/share: ${amount(position.cost===null?null:position.cost/position.shares,account.currency)} · original option premium/share: ${amount(position.premium===null?null:position.premium/(position.contracts*100),account.currency)}`,'context');form.append(original);
   function updateCurrency(){fx.wrap.hidden=account.currency!=='CAD';fx.input.required=currency.value!==account.currency;fx.input.min=fx.wrap.hidden?'0':'0.00000001';stock.wrap.firstChild.textContent=`Stock purchase price (${currency.value}/share)`;call.wrap.firstChild.textContent=`Option sale premium (${currency.value}/share)`;}
   currency.addEventListener('change',updateCurrency);updateCurrency();
   const actions=element('div',undefined,'entry-actions');form.append(actions);
   const save=element('button','Save entry prices');save.type='submit';save.className='primary';actions.append(save);
   const reset=element('button','Use original values');reset.type='button';actions.append(reset);
   const status=element('p',saved?'Your saved entry prices are active.':'Using original cost and premium values.','context');status.setAttribute('role','status');form.append(status);
   function commit(next){
    entryOverrides=next;
    try{localStorage.setItem(EntryPrices.STORAGE_KEY,JSON.stringify(next));entryStorageAvailable=true;}catch{entryStorageAvailable=false;}
    renderAccounts();renderStockRisk();recalculateRolls();
    status.textContent=entryStorageAvailable?'Saved in this browser. P/L updated.':'P/L updated for this session. Browser storage is unavailable; these values will be lost on reload.';
   }
   form.addEventListener('submit',event=>{
    event.preventDefault();if(!form.reportValidity())return;
    const number=input=>input.value.trim()===''?null:Number(input.value);
    const value={currency:currency.value,stockPrice:number(stock.input),optionPrice:number(call.input),entryFx:number(fx.input)};
    try{EntryPrices.validate(value,account.currency);}catch(error){status.textContent=error.message;return;}
    const next={...entryOverrides};if(value.stockPrice===null&&value.optionPrice===null&&value.entryFx===null)delete next[entryKey];else next[entryKey]=value;commit(next);
   });
   reset.addEventListener('click',()=>{const next={...entryOverrides};delete next[entryKey];commit(next);stock.input.value='';call.input.value='';fx.input.value='';currency.value=account.currency;updateCurrency();status.textContent=entryStorageAvailable?'Original cost and premium restored.':'Original values restored for this session; browser storage is unavailable.';});
  }
 }
}
renderStockDetails();
document.querySelector('#fx-assumption').addEventListener('input',()=>{updateDisplayedQuotes();renderStockRisk();recalculateRolls();});
