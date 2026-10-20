/* Covered-call roll cash flows and expiry payoff; all amounts are USD. */
(function(root){
'use strict';
function nonnegative(value,name){if(!Number.isFinite(value)||value<0)throw new Error(name+' must be a nonnegative number.');return value;}
function expiryPayoff(stock,strike,shares,quantity){return shares*stock-quantity*Math.max(stock-strike,0);}
function simulate(input){
 for(const field of ['stockCost','originalPremium','oldAsk','newBid','fees','targetStock','currentStock'])nonnegative(input[field],field);
 for(const field of ['shares','contracts','oldStrike','newStrike']){
  nonnegative(input[field],field);if(input[field]<=0)throw new Error(field+' must be positive.');
 }
 if(!Number.isInteger(input.shares)||!Number.isInteger(input.contracts)||input.contracts*100!==input.shares)throw new Error('This simulator requires one standard call per 100 shares and rolls all existing contracts.');
 if(input.stockCost===0)throw new Error('Enter a positive stock purchase cost.');
 for(const field of ['valuationDate','oldExpiry','newExpiry']){
  if(!/^\d{4}-\d{2}-\d{2}$/.test(input[field])||!Number.isFinite(Date.parse(input[field]))||new Date(input[field]).toISOString().slice(0,10)!==input[field])throw new Error('Enter a valid '+field+'.');
 }
 if(input.newExpiry<=input.valuationDate||input.oldExpiry<=input.valuationDate)throw new Error('Both calls must expire after the valuation date.');
 if(input.newExpiry===input.oldExpiry&&input.newStrike===input.oldStrike)throw new Error('Choose a different strike or expiry for the replacement call.');
 const q=input.contracts*100;
 const buyback=q*input.oldAsk,sale=q*input.newBid,netCredit=sale-buyback-input.fees;
 const basis=input.stockCost-input.originalPremium-netCredit;
 function at(stock){
  nonnegative(stock,'Terminal stock price');
  const keep=expiryPayoff(stock,input.oldStrike,input.shares,q)-input.stockCost+input.originalPremium;
  const roll=expiryPayoff(stock,input.newStrike,input.shares,q)-basis;
  return {stock,stockPnl:input.shares*stock-input.stockCost,keep,roll,
   rollReturn:roll/input.stockCost,unacceptable:roll/input.stockCost<=-.05+1e-12};
 }
 const requiredPremium=(lossFraction)=>(input.stockCost*(1-lossFraction)-input.originalPremium+
  buyback+input.fees-expiryPayoff(input.targetStock,input.newStrike,input.shares,q))/q;
 const lossLimitBid=requiredPremium(.05);
 const maxProfit=input.newStrike*input.shares-basis;
 const keepMax=input.oldStrike*input.shares-input.stockCost+input.originalPremium;
 return {buyback,sale,netCredit,oldOptionPnl:input.originalPremium-buyback,netPremium:input.originalPremium+netCredit,
  combinedBreakeven:basis<=0?0:basis/input.shares<=input.newStrike?basis/input.shares:null,
  stockBreakeven:input.stockCost/input.shares,
  maxProfit,keepMaxProfit:keepMax,maxLoss:Math.max(0,basis),
  currentExitPnl:input.currentStock*input.shares-buyback-input.stockCost+input.originalPremium,
  bidForBreakeven:Math.max(0,requiredPremium(0)),
  bidForLossBelowFive:lossLimitBid<0?0:(Math.floor((lossLimitBid+1e-10)*100)+1)/100,
  target:at(input.targetStock),at,
  sameExpiry:input.oldExpiry===input.newExpiry};
}
function nextStrike(candidates,expiry,minimum){
 const strikes=candidates.filter(o=>o.validated&&o.expiry===expiry&&Number.isFinite(o.strike)&&o.strike>=minimum-1e-10).map(o=>o.strike);
 return strikes.length?Math.min(...strikes):null;
}
function recommend(input,capture,minimumGap=5,now=Date.now(),preferences={}){
 nonnegative(minimumGap,'Minimum strike gap');if(minimumGap<5)throw new Error('Minimum strike gap must be at least USD 5.');
 if(!capture||capture.symbol!==input.symbol||capture.account!==input.account||capture.old_call?.strike!==input.oldStrike||capture.old_call?.expiry!==input.oldExpiry)return {reason:'Fetch Questrade market strikes for this stock and account using Refresh Questrade candidates.',candidates:[]};
 const age=(now-Date.parse(capture.captured_at))/1000;
 if(!Number.isFinite(age)||age< -300||age>900)return {reason:'The option-chain capture is older than 15 minutes. Refresh it before generating a recommendation.',candidates:[]};
 const purchase=input.stockCost/input.shares,minimumStrike=purchase+minimumGap;
 if(!Number.isFinite(minimumStrike))throw new Error('Enter a valid stock purchase cost.');
 if(minimumStrike<capture.scan.minimum_strike-1e-8)return {reason:'This scan does not cover the lower required strikes. Enter a manual scenario or broaden the scan range.',candidates:[]};
 const old=capture.old_call;
 if(old.isHalted!==false||old.delay!==0||!Number.isFinite(old.askPrice)||old.askPrice<=0||old.askSize<input.contracts||!Number.isFinite(old.askSize))return {reason:'The existing call needs a non-delayed, non-halted ask with size covering all contracts.',candidates:[]};
 if(capture.stock?.isHalted!==false||capture.stock?.delay!==0)return {reason:'The underlying stock needs a non-delayed, non-halted captured quote.',candidates:[]};
 if(input.oldAsk<old.askPrice)return {reason:'Your buyback input is below the captured ask. Use at least the ask for a quote-based recommendation.',candidates:[]};
 const minimumCredit=preferences.minimumCredit??0;nonnegative(minimumCredit,'Minimum net credit');
 const earliest=preferences.earliestExpiry||input.valuationDate;
 const candidates=[],comparisons=[];
 const expiries=[...new Set(capture.candidates.filter(o=>o.validated&&o.expiry>input.valuationDate&&o.expiry>=earliest).map(o=>o.expiry))].sort();
 for(const expiry of expiries){
  const strike=nextStrike(capture.candidates,expiry,minimumStrike);
  const option=capture.candidates.find(o=>o.validated&&o.expiry===expiry&&o.strike===strike);
  if(!option)continue;
  const record={...option,gap:option.strike-purchase,result:null,eligible:false};
  comparisons.push(record);
  if(option.strike===input.oldStrike&&option.expiry===input.oldExpiry){record.reason='Same as existing contract';continue;}
  if(!Number.isFinite(option.bidPrice)||option.bidPrice<=0||!Number.isFinite(option.askPrice)||option.askPrice<option.bidPrice){record.reason='No usable bid/ask';continue;}
  try{
   const result=simulate({...input,oldAsk:input.oldAsk,newBid:option.bidPrice,newStrike:option.strike,newExpiry:option.expiry});
   record.result=result;
   if(option.delay!==0||option.isHalted!==false){record.reason='Delayed or halted quote';continue;}
   if(!Number.isFinite(option.bidSize)||option.bidSize<input.contracts){record.reason='Bid size below full contract count';continue;}
   if(result.netCredit<=0||result.netCredit<minimumCredit){record.reason='Net credit below your requirement';continue;}
   if(result.target.unacceptable){record.reason='Target scenario breaches 5% loss limit';continue;}
   record.eligible=true;record.reason='Meets your rules';candidates.push(record);
  }catch{record.reason='Invalid scenario inputs';continue;}
 }
 candidates.sort((a,b)=>a.expiry.localeCompare(b.expiry)||b.result.netCredit-a.result.netCredit||b.strike-a.strike);
 return {minimumStrike,purchase,candidates,comparisons,selected:candidates[0]||null,
  reason:candidates.length?'Next listed strike above your price floor; earliest eligible expiry in your chosen date range.':'No captured next-strike contract meets your expiry, credit, full-size and target-loss rules. Keep the current call until a suitable quote is available.'};
}
const api={simulate,expiryPayoff,recommend,nextStrike};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.RollPricing=api;
})(typeof globalThis!=='undefined'?globalThis:this);
