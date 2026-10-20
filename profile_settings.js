/* Per-stock/account profit thresholds, alongside the existing entry-price store. */
(function(root){
'use strict';
const STORAGE_KEY='covered-call-profile-v1';
function key(account,position){return JSON.stringify([account.account,account.currency,position.symbol]);}
function minimumBid(account,position,settings){
 const value=settings.holdings?.[key(account,position)]?.minimumBid;
 return Number.isFinite(value)&&value>0?value:position.cost===null?null:position.cost/position.shares;
}
function validateMinimum(value){if(value!==null&&(!Number.isFinite(value)||value<=0))throw new Error('Minimum bids must be positive prices or blank for purchase-price break-even.');return value;}
function costBasis(value){
 if(!value)return null;
 for(const field of ['quantity','priceUsd','fx'])if(!Number.isFinite(value[field])||value[field]<=0)throw new Error('Cost basis requires positive shares, USD price and purchase FX.');
 if(!Number.isFinite(value.feesUsd)||value.feesUsd<0)throw new Error('Purchase fees must be zero or positive USD.');
 if(value.cadTotal!==null&&(!Number.isFinite(value.cadTotal)||value.cadTotal<=0))throw new Error('Actual CAD cost must be positive or blank.');
 const usdTotal=value.quantity*value.priceUsd+value.feesUsd;
 const cadTotal=value.cadTotal??Math.round(usdTotal*value.fx*100)/100;
 if(value.cadTotal!==null&&Math.abs(cadTotal-usdTotal*value.fx)>Math.max(.10,usdTotal*.000051))throw new Error('Purchase CAD total does not reconcile with USD cost and purchase FX.');
 return {...value,usdTotal,cadTotal,cadPerShare:cadTotal/value.quantity,usdPerShare:usdTotal/value.quantity};
}
const api={STORAGE_KEY,key,minimumBid,validateMinimum,costBasis};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.ProfileSettings=api;
})(typeof globalThis!=='undefined'?globalThis:this);
