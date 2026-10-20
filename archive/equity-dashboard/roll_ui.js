/* Editable hypotheses for replacing the selected holding's short call. */
'use strict';
const rollDrafts={};
function renderRollEditor(container,symbol){
 container.replaceChildren();
 container.append(element('p','Compare Questrade-listed replacement calls for the selected holding. For each date, the replacement strike is purchase price + $5, rounded up to the next listed standard call strike. Thin quotes stay visible but are excluded from recommendations; the system does not substitute a higher strike to obtain a recommendation.','context'));
 for(const account of visibleAccounts()){
  for(const position of (account.positions||[]).filter(p=>p.symbol===symbol)){
   const key=EntryPrices.key(account,position);
   const captured=rollCaptures[account.account+':'+symbol]||null;
   const quote=captured?.old_call||marketDetails?.options.find(o=>o.symbol===symbol&&o.expiry===position.expiry&&Number(o.strike)===position.strike&&o.accounts.includes(account.account));
   const stock=captured?.stock||marketDetails?.stocks[symbol];
   const form=element('form',undefined,'roll-form entry-form');form.dataset.entryKey=key;container.append(form);
   form.append(element('h3',`${account.account} · ${symbol} · ${position.shares} shares / ${position.contracts} short calls`));
   form.append(element('p',`Existing call: USD ${position.strike} · ${position.expiry}. Buyback starts at the saved Questrade ask; all prices and fees below are USD.`,'context'));
   const fields=element('div',undefined,'fields');form.append(fields);
   const inputs={};
   function input(name,label,type,value){
    const wrap=element('label',label),node=element('input');node.type=type;node.name=name;node.required=true;
    if(type==='number'){node.min='0';node.step='any';}
    node.value=rollDrafts[key]?.[name]??(value==null?'':String(value));inputs[name]=node;wrap.append(node);fields.append(wrap);return node;
   }
   input('oldAsk','Buyback price incl. buffer (USD/share)','number',quote?.askPrice==null?null:quote.askPrice+.05);
   input('newStrike','Replacement strike (USD)','number',null).min='0.01';
   input('newExpiry','Replacement expiry','date',null);
   input('newBid','Replacement sale bid (USD/share)','number',null);
   input('fees','Total fees for both roll legs (USD)','number',0);
   input('targetStock','Stock price at replacement expiry (USD)','number',stock?.bidPrice);
   const gap=input('minimumGap','Strike gap above purchase (USD)','number',5);gap.min='5';gap.max='5';gap.value='5';gap.readOnly=true;
   input('minimumCredit','Minimum worthwhile net roll credit (USD)','number',0);
   const expiryLabel=element('label','Search replacement expiries'),expirySelect=element('select');expirySelect.name='earliestExpiry';expiryLabel.append(expirySelect);fields.append(expiryLabel);inputs.earliestExpiry=expirySelect;
   const afterCurrent=new Date(Date.parse(position.expiry+'T00:00:00Z')+86400000).toISOString().slice(0,10);
   const expiryChoices=[[afterCurrent,'Later than existing expiry'],['','All captured expiries'],...[...new Set((captured?.candidates||[]).map(o=>o.expiry))].sort().map(day=>[day,day+' or later'])];
   for(const [value,label] of expiryChoices){const option=element('option',label);option.value=value;expirySelect.append(option);}
   expirySelect.value=rollDrafts[key]?.earliestExpiry??afterCurrent;
   form.append(element('p',`Buyback starts at the captured ask plus a $0.05/share buffer. Roll fees default to $0; enter actual fees. Recommendations use replacement bids, require no reported delay, and check your combined 5% loss rule at the entered target stock price.`,'context'));
   const recommendationPanel=element('div',undefined,'roll-recommendation');recommendationPanel.setAttribute('aria-live','polite');form.append(recommendationPanel);
   {
    const refresh=element('button','Refresh Questrade candidates');refresh.type='button';form.append(refresh);
    refresh.addEventListener('click',async()=>{
     refresh.disabled=true;refresh.textContent='Refreshing quotes…';
     try{
      const effective=visibleAccounts().find(a=>a.account===account.account)?.positions.find(p=>EntryPrices.key(account,p)===key);
      const fx=EntryPrices.purchaseFx(account,effective);
      const purchase=effective?.cost/effective?.shares/fx;
      if(!Number.isFinite(purchase)||purchase<=0)throw new Error('Enter a positive stock purchase price and currency conversion before fetching the market strikes.');
      const response=await fetch('/api/roll-candidates/refresh',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account:account.account,symbol,purchasePriceUsd:purchase}),signal:AbortSignal.timeout(100000)});
      if(!response.ok)throw new Error('Candidate refresh unavailable. Run the updated local dashboard server and try again.');
      const capture=await response.json();rollCaptures[account.account+':'+symbol]=capture;
      delete rollDrafts[key].oldAsk;
      renderRollEditor(container,symbol);
     }catch(error){recommendationPanel.replaceChildren(element('p',error.message,'warning'));refresh.disabled=false;refresh.textContent='Refresh Questrade candidates';}
    });
   }
   const resultPanel=element('div',undefined,'roll-results');resultPanel.setAttribute('aria-live','polite');form.append(resultPanel);
   function update(){
    rollDrafts[key]=Object.fromEntries(Object.entries(inputs).map(([name,node])=>[name,node.value]));
    resultPanel.replaceChildren();
    recommendationPanel.replaceChildren();
    try{
     // Read the effective basis again so saving entry prices updates an open simulator.
     const effectiveAccount=visibleAccounts().find(a=>a.account===account.account);
     const effectivePosition=effectiveAccount?.positions.find(p=>EntryPrices.key(account,p)===key);
     if(!effectivePosition)throw new Error('This holding is no longer selected.');
     const fx=account.currency==='USD'?1:Number(document.querySelector('#fx-assumption').value);
     if(!Number.isFinite(fx)||fx<=0)throw new Error('Enter a positive CAD per USD assumption.');
     if(effectivePosition.cost===null||effectivePosition.premium===null)throw new Error('Enter stock purchase cost and original option sale premium first.');
     const valuationDate=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Vancouver',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
     inputs.newExpiry.min=valuationDate;
     const purchaseFx=EntryPrices.purchaseFx(account,effectivePosition);
     if(!purchaseFx)throw new Error('Enter historical purchase FX in Profile → Settings before simulating a CAD holding.');
     const settings={shares:position.shares,contracts:position.contracts,stockCost:effectivePosition.cost/purchaseFx,
      originalPremium:effectivePosition.premium/fx,oldStrike:position.strike,oldExpiry:position.expiry,valuationDate,
      currentStock:stock?.bidPrice??0,newExpiry:inputs.newExpiry.value,symbol,account:account.account};
     for(const name of ['oldAsk','newStrike','newBid','fees','targetStock'])settings[name]=Number(inputs[name].value);
     const coreFields=['oldAsk','fees','targetStock','minimumGap','minimumCredit'];
     if(coreFields.some(name=>inputs[name].value.trim()===''||!inputs[name].checkValidity()))throw new Error('Enter valid buyback price, fees, target stock price and minimum gap.');
     const recommendation=RollPricing.recommend(settings,captured,Number(inputs.minimumGap.value),Date.now(),{earliestExpiry:inputs.earliestExpiry.value,minimumCredit:Number(inputs.minimumCredit.value)});
     renderRollRecommendation(recommendationPanel,recommendation,settings,captured,inputs,update);
     if(['newStrike','newExpiry','newBid'].some(name=>inputs[name].value.trim()===''||!inputs[name].checkValidity())){
      resultPanel.append(element('p','Choose a recommended candidate or enter a replacement strike, expiry and sale bid to calculate the roll.','context'));return;
     }
     const result=RollPricing.simulate(settings);
     const listedStrike=captured?RollPricing.nextStrike(captured.candidates,settings.newExpiry,settings.stockCost/settings.shares+Number(inputs.minimumGap.value)):null;
     if(settings.newStrike<settings.stockCost/settings.shares+Number(inputs.minimumGap.value)||listedStrike!==null&&settings.newStrike!==listedStrike)resultPanel.append(element('p',`This manual scenario does not use your purchase-plus-gap rounded to the next listed strike${listedStrike===null?'':': '+detailPrice(listedStrike)}.`,'loss-alert'));
     renderRollResults(resultPanel,result,settings,stock,quote,account);
    }catch(error){resultPanel.append(element('p',error.message,'warning'));}
   }
   form.addEventListener('submit',event=>event.preventDefault());
   form.addEventListener('input',update);form.addEventListener('recalculate',update);update();
  }
 }
}
function renderRollRecommendation(panel,recommendation,input,capture,inputs,update){
 panel.append(element('h3','Replacement call recommendation'));
 panel.append(element('p',`Purchase basis: ${detailPrice(input.stockCost/input.shares)} · minimum permitted strike: USD ${(input.stockCost/input.shares+Number(inputs.minimumGap.value)).toFixed(5)}.`,'context'));
 if(capture){
  const floor=input.stockCost/input.shares+Number(inputs.minimumGap.value);
  const strikes=capture.candidates.filter(o=>o.validated&&o.strike>=floor).map(o=>o.strike);
  if(strikes.length)panel.append(element('p',`Minimum listed replacement strike in the captured market: ${detailPrice(Math.min(...strikes))}. The expiry table uses the next available strike for each individual date.`,'context'));
  else panel.append(element('p','No captured listed strike meets this purchase-price floor. Refresh Questrade candidates to scan the current market.','warning'));
  const time=new Date(capture.captured_at).toLocaleString('en-CA',{timeZone:'America/Vancouver',timeZoneName:'short'});
  panel.append(element('p',`${capture.source} capture: ${time}. Scanned ${capture.candidates.length} standard calls · strikes USD ${capture.scan.minimum_strike.toFixed(5)}–${capture.scan.maximum_strike} · expiries ${capture.scan.first_expiry}–${capture.scan.last_expiry}. Candidates expire from recommendation after 15 minutes; refresh before relying on them.`,'context'));
 }
 if(!recommendation.selected)panel.append(element('p',recommendation.reason,'warning'));
 if(recommendation.selected){
 const selected=recommendation.selected;
 panel.append(element('strong',`${detailPrice(selected.strike)} call · ${selected.expiry}`));
 panel.append(element('p',`${recommendation.reason} Gap above purchase: ${detailPrice(selected.gap)}. Sell bid ${detailPrice(selected.bidPrice)}/share; displayed bid size ${detailNumber(selected.bidSize)} contracts. Net roll credit after your buffer/fees: ${detailPrice(selected.result.netCredit)}.`));
 const lostUpside=selected.result.keepMaxProfit-selected.result.maxProfit;
 if(lostUpside>0)panel.append(element('p',`Maximum expiry P/L falls by ${detailPrice(lostUpside)} compared with keeping the current call. ${selected.expiry===input.oldExpiry?'The expiry is unchanged; this is a roll down.':'The comparison uses each contract’s own expiry.'} Review this upside trade-off before accepting the extra credit.`,'warning'));
 panel.append(element('p','This is a conditional candidate under your rule, not a prediction of the best future return. It does not guarantee loss below 5% at other stock prices, and the stock-only loss warning remains.','context'));
 }
 if(!recommendation.comparisons?.length)return;
 panel.append(element('h3','Next available strike · compare expiry dates'));
 const tableWrap=element('div',undefined,'table-scroll'),table=element('table');tableWrap.append(table);panel.append(tableWrap);
 const header=element('thead'),tr=element('tr');header.append(tr);table.append(header);
 for(const label of ['Rounded strike','Expiry','Bid / ask','Bid size','Net roll credit','Status','Simulate']){const th=element('th',label);th.scope='col';tr.append(th);}
 const body=element('tbody');table.append(body);
 for(const option of recommendation.comparisons){
  const row=element('tr');body.append(row);
  for(const text of [detailPrice(option.strike),option.expiry,`${detailPrice(option.bidPrice)} / ${detailPrice(option.askPrice)}`,detailNumber(option.bidSize),option.result?detailPrice(option.result.netCredit):'Unavailable',option.reason])row.append(element('td',text));
  const cell=element('td'),choose=element('button','Use in simulator');choose.type='button';cell.append(choose);row.append(cell);
  choose.disabled=!option.result;
  choose.addEventListener('click',()=>{inputs.newStrike.value=String(option.strike);inputs.newExpiry.value=option.expiry;inputs.newBid.value=String(option.bidPrice);update();});
 }
}
function renderRollResults(panel,result,input,stock,quote,account){
 const grid=element('div',undefined,'detail-grid');panel.append(grid);
 const breakEven=result.combinedBreakeven===null?'Unreachable under new strike cap':detailPrice(result.combinedBreakeven);
 for(const [label,value] of [
  ['Buy back existing calls',detailPrice(result.buyback)],['Sell replacement calls',detailPrice(result.sale)],
  [result.netCredit>=0?'Net roll credit after fees':'Net roll debit after fees',detailPrice(Math.abs(result.netCredit))],
  ['Combined break-even at new expiry',breakEven],['Maximum combined P/L at new expiry',detailPrice(result.maxProfit)],
  ['Maximum combined loss at stock = $0',detailPrice(result.maxLoss)],
  ['Current paired exit P/L before fees',stock?detailPrice(result.currentExitPnl):'Unavailable'],
  ['Stock-only break-even (unchanged)',detailPrice(result.stockBreakeven)]]){
  const box=element('div');box.append(element('span',label,'label'),element('strong',value));grid.append(box);
 }
 panel.append(element('p',`At your ${detailPrice(input.targetStock)} stock scenario on ${input.newExpiry}: combined P/L ${detailPrice(result.target.roll)} (${(100*result.target.rollReturn).toFixed(2)}% of stock purchase cost). ${result.target.unacceptable?'UNACCEPTABLE · combined loss reaches your 5% limit.':'Combined loss is below your 5% limit in this scenario.'}`,result.target.unacceptable?'loss-alert':'context'));
 panel.append(element('p',`Replacement sale bid needed to break even at that stock price: ${detailPrice(Math.ceil((result.bidForBreakeven-1e-10)*100)/100)}/share. To keep combined loss strictly below 5%: ${detailPrice(result.bidForLossBelowFive)}/share (cent increments). These are required premiums, not available quotes.`,'context'));
 const stockLoss=(input.targetStock*input.shares-input.stockCost)/input.stockCost;
 if(stockLoss<=-.05+1e-12)panel.append(element('p',`Stock-only loss remains ${(100*stockLoss).toFixed(2)}% at your target price and still breaches your stock loss rule. Rolling changes the combined payoff, not the stock purchase cost.`,'loss-alert'));
 if(result.netCredit<0)panel.append(element('p','This roll requires a net cash payment; it increases the combined capital at risk.','warning'));
 if(result.combinedBreakeven===null)panel.append(element('p','The replacement strike caps proceeds below combined break-even under these inputs.','warning'));
 if(quote?.askSize!==null&&quote?.askSize!==undefined&&quote.askSize<input.contracts)panel.append(element('p','The captured call ask size is smaller than the number of contracts you would buy back.','warning'));
 if(quote?.isHalted||stock?.isHalted)panel.append(element('p','A captured security is halted. Treat entered prices as hypothetical.','warning'));
 const sourceTime=quote?.captured_at||marketDetails?.captured_at;
 const capturedTime=sourceTime?new Date(sourceTime).toLocaleString('en-CA',{timeZone:'America/Vancouver',timeZoneName:'short'}):'unavailable';
 panel.append(element('p',`Existing call capture: ${capturedTime}. Delay: ${detailNumber(quote?.delay)} seconds. Listed recommendation candidates have captured quotes and validated standard deliverables. Manually entered replacement values are unverified scenarios. Displayed size does not guarantee a fill.`,'context'));
 if(account.currency!=='USD')panel.append(element('p','The original stock cost uses historical purchase FX; the simulator reports USD. Original CAD option premium is shown as a USD equivalent using the current conversion assumption, not a verified historical option-sale rate. CAD returns may differ with future FX.','context'));
 if(!result.sameExpiry)panel.append(element('p',`Keep-current outcomes below are at ${input.oldExpiry}; rollover outcomes are at ${input.newExpiry}. The table assumes the same stock price at each separate expiry; it is not a comparison at the same date.`,'warning'));
 renderRollChart(panel,result,input);
 panel.append(element('h3','Expiry payoff scenarios · total USD P/L'));
 const wrapper=element('div',undefined,'table-scroll'),table=element('table');wrapper.append(table);panel.append(wrapper);
 const header=element('thead'),row=element('tr');header.append(row);table.append(header);
 for(const label of ['Stock at expiry','Stock only',`Keep current · ${input.oldExpiry}`,`Roll · ${input.newExpiry}`,'Rolled combined loss rule']){const th=element('th',label);th.scope='col';row.append(th);}
 const body=element('tbody');table.append(body);
 const prices=[...new Set([0,input.currentStock*.8,input.currentStock,input.targetStock,result.stockBreakeven,input.newStrike,input.oldStrike])].sort((a,b)=>a-b);
 for(const price of prices){
  const outcome=result.at(price),row=element('tr');body.append(row);
  for(const text of [detailPrice(price),detailPrice(outcome.stockPnl),detailPrice(outcome.keep),detailPrice(outcome.roll),outcome.unacceptable?'Unacceptable: loss ≥ 5%':'Below loss limit'])row.append(element('td',text));
 }
 panel.append(element('p','Payoff includes the saved original premium once, existing call buyback, replacement premium and entered roll fees. Premium history is a book-value proxy unless you replace it with verified entries. Expiry calculations assume standard assignment and exclude early assignment, taxes, funding and final exit fees. A roll does not guarantee recovery.','context'));
 const source=element('a','How rolling covered calls works · Fidelity / Cboe');source.href='https://www.fidelity.com/learning-center/investment-products/options/rolling-covered-calls';source.target='_blank';source.rel='noopener noreferrer';panel.append(source);
}
function renderRollChart(panel,result,input){
 panel.append(element('h3','Payoff at each call’s expiry'));
 panel.append(element('p',`Blue: rolled call (${input.newExpiry}) · dashed green: keep current (${input.oldExpiry}) · gray: stock only · red line: 5% loss limit on stock purchase cost.`,'context'));
 const width=800,height=310,maxStock=Math.max(input.oldStrike,input.newStrike,input.targetStock,result.stockBreakeven,input.currentStock,1)*1.25;
 const prices=[...new Set([...Array.from({length:81},(_,i)=>maxStock*i/80),input.oldStrike,input.newStrike,input.targetStock])].sort((a,b)=>a-b);
 const data=prices.map(price=>result.at(price));
 const values=data.flatMap(p=>[p.keep,p.roll,p.stockPnl]);
 const x=d3.scaleLinear().domain([0,maxStock]).range([80,width-25]);
 const y=d3.scaleLinear().domain([Math.min(0,...values)*1.08,Math.max(0,...values)*1.08||1]).nice().range([height-48,20]);
 const svg=d3.select(panel).append('svg').attr('viewBox',`0 0 ${width} ${height}`).attr('role','img');
 svg.append('title').text(`Covered-call expiry P/L versus stock price: original call ${input.oldExpiry}, replacement ${input.newExpiry}; stock purchase-cost 5% loss limit`);
 svg.append('g').attr('transform',`translate(0,${height-48})`).call(d3.axisBottom(x).ticks(8).tickFormat(d=>'$'+d));
 svg.append('g').attr('transform','translate(80,0)').call(d3.axisLeft(y).ticks(6).tickFormat(d3.format('~s')));
 for(const [level,color,dash] of [[0,'#b7c7d9',null],[-.05*input.stockCost,'#bb3a4b','3 4']])svg.append('line').attr('x1',80).attr('x2',width-25).attr('y1',y(level)).attr('y2',y(level)).attr('stroke',color).attr('stroke-dasharray',dash);
 for(const [metric,color,dash] of [['stockPnl','#8c98a8',null],['keep','#087c61','6 4'],['roll','#326cc4',null]]){
  svg.append('path').datum(data).attr('d',d3.line().x(p=>x(p.stock)).y(p=>y(p[metric]))).attr('fill','none').attr('stroke',color).attr('stroke-width',2.5).attr('stroke-dasharray',dash);
 }
 const target=svg.append('circle').attr('cx',x(input.targetStock)).attr('cy',y(result.target.roll)).attr('r',6).attr('fill',result.target.unacceptable?'#bb3a4b':'#326cc4').attr('tabindex',0);
 target.append('title').text(`Target stock ${detailPrice(input.targetStock)}: rolled combined P/L ${detailPrice(result.target.roll)}`);
 svg.append('text').attr('x',width/2).attr('y',height-7).attr('text-anchor','middle').text('Stock price at the specified expiry (USD)');
}
function recalculateRolls(){document.querySelectorAll('.roll-form').forEach(form=>form.dispatchEvent(new Event('recalculate')));}
setInterval(recalculateRolls,60000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)recalculateRolls();});
