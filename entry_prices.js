/* Owner-entered cost/premium overrides; broker snapshots remain the source defaults. */
(function(root){
'use strict';
const STORAGE_KEY='covered-call-entry-prices-v1';
function key(account,position){return JSON.stringify([account.account,account.currency,position.symbol,position.strike,position.expiry,position.shares,position.contracts]);}
function validate(value,currency){
 if(!value||!['USD','CAD'].includes(value.currency))throw new Error('Choose USD or CAD.');
 for(const field of ['stockPrice','optionPrice'])if(value[field]!==null&&(!Number.isFinite(value[field])||value[field]<0))throw new Error('Prices must be zero or positive numbers.');
 if(value.currency!==currency&&(value.currency!=='USD'||currency!=='CAD'||!Number.isFinite(value.entryFx)||value.entryFx<=0))throw new Error('Enter the historical CAD per USD conversion for your entry prices.');
 if(value.entryFx!=null&&(!Number.isFinite(value.entryFx)||value.entryFx<=0))throw new Error('Purchase FX must be positive CAD per USD.');
 return value;
}
function apply(account,overrides){
 let changed=false;
 const positions=(account.positions||[]).map(position=>{
  const value=overrides[key(account,position)];if(!value)return position;
  try{validate(value,account.currency);}catch{return position;}
  const fx=value.currency===account.currency?1:value.entryFx;
  changed=true;
  return {...position,cost:value.stockPrice===null?position.cost:value.stockPrice*position.shares*fx,
   premium:value.optionPrice===null?position.premium:value.optionPrice*position.contracts*100*fx,entryFx:account.currency==='USD'?1:value.entryFx??position.entryFx??null,manualEntry:true};
 });
 if(!changed)return account;
 const rows=account.rows.map(row=>{
  const p=positions.find(p=>p.symbol===row.symbol);if(!p?.manualEntry)return row;
  return {...row,pnl:p.cost===null||p.premium===null?null:Number(row.net)-p.cost+p.premium};
 });
 return {...account,rows,positions:positions,pnl:rows.every(r=>r.pnl!==null)?rows.reduce((sum,r)=>sum+Number(r.pnl),0):null,manualEntry:true};
}
function purchaseFx(account,position){return account.currency==='USD'?1:Number.isFinite(position?.entryFx)&&position.entryFx>0?position.entryFx:null;}
function stockRisk(position,bidUsd,fx=1,entryFx=fx){
 if(!Number.isFinite(position.cost)||position.cost<=0||!Number.isFinite(position.shares)||position.shares<=0||!Number.isFinite(fx)||fx<=0)return null;
 if(!Number.isFinite(entryFx)||entryFx<=0)return null;
 const purchaseUsd=position.cost/position.shares/entryFx;
 const currentBreakeven=position.cost/position.shares/fx;
 const validBid=Number.isFinite(bidUsd)&&bidUsd>0;
 const change=validBid?(bidUsd-currentBreakeven)/currentBreakeven:null;
 return {purchaseUsd,breakevenBid:Math.ceil((currentBreakeven-1e-10)*100)/100,
  acceptableBid:(Math.floor((currentBreakeven*.95+1e-10)*100)+1)/100,
  change,stockPnl:validBid?position.shares*bidUsd*fx-position.cost:null,
  unacceptable:change!==null&&change<=-.05+1e-12};
}
const api={STORAGE_KEY,key,validate,apply,purchaseFx,stockRisk};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.EntryPrices=api;
})(typeof globalThis!=='undefined'?globalThis:this);
