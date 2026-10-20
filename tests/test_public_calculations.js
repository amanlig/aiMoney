const assert=require('assert');
const Entry=require('../entry_prices.js'),Profile=require('../profile_settings.js'),Roll=require('../archive/equity-dashboard/roll_pricing.js');
// Fictional prices and quantities; no private captures are required.
const position={symbol:'QBTS',currency:'USD',shares:100,contracts:1,strike:20,expiry:'2030-01-18',cost:1000,premium:100,fees:0};
const account={account:'LIRA',currency:'USD',positions:[position],rows:[{symbol:'QBTS',net:1100,pnl:200}],pnl:200};
const edited=Entry.apply(account,{[Entry.key(account,position)]:{currency:'USD',stockPrice:11,optionPrice:2,entryFx:null}});
assert.equal(edited.positions[0].cost,1100);assert.equal(edited.positions[0].premium,200);
assert.equal(edited.rows[0].pnl,200);assert.equal(account.positions[0].cost,1000);
assert(Entry.stockRisk(position,9.5).unacceptable);assert(!Entry.stockRisk(position,9.51).unacceptable);
const settings={holdings:{[Profile.key(account,position)]:{minimumBid:12}}};
assert.equal(Profile.minimumBid(account,position,settings),12);
assert.equal(Profile.minimumBid({...account,account:'RRSP'},position,settings),10);
assert.throws(()=>Profile.validateMinimum(-1));
const input={shares:100,contracts:1,stockCost:1000,originalPremium:100,oldAsk:1,newBid:2,fees:5,oldStrike:20,newStrike:15,currentStock:12,targetStock:12,valuationDate:'2026-01-01',oldExpiry:'2030-01-18',newExpiry:'2031-01-17'};
const result=Roll.simulate(input);
assert.equal(result.netCredit,95);assert.equal(result.target.roll,395);
assert.equal(result.at(30).roll,695);assert.equal(result.combinedBreakeven,8.05);
assert.equal(result.at(0).roll,-805);
assert.equal(Roll.nextStrike([{validated:true,expiry:input.newExpiry,strike:14},{validated:true,expiry:input.newExpiry,strike:16}],input.newExpiry,15),16);
assert.throws(()=>Roll.simulate({...input,contracts:2}));
console.log('Synthetic entry-price, threshold, profile and rollover checks passed.');
// Historical purchase FX fixes USD acquisition basis; current FX values CAD proceeds.
const cad={...account,account:'TFSA',currency:'CAD'};
const cadPosition={...position,cost:1400,entryFx:1.4};
const r1=Entry.stockRisk(cadPosition,10,1.3,Entry.purchaseFx(cad,cadPosition));
const r2=Entry.stockRisk(cadPosition,10,1.5,Entry.purchaseFx(cad,cadPosition));
assert.equal(r1.purchaseUsd,10);assert.equal(r2.purchaseUsd,10);
assert.equal(r1.stockPnl,-100);assert.equal(r2.stockPnl,100);
assert(r1.unacceptable);assert(!r2.unacceptable);
assert.equal(Entry.purchaseFx(cad,position),null);
assert.equal(Entry.stockRisk(cadPosition,10,1.3,null),null);
const historical=Entry.apply({...cad,positions:[cadPosition]}, {[Entry.key(cad,cadPosition)]:{currency:'USD',stockPrice:10,optionPrice:null,entryFx:1.4}});
assert.equal(historical.positions[0].cost,1400);assert.equal(historical.positions[0].entryFx,1.4);

// Purchase confirmation: commission belongs in the stock basis once.
{
 const settings=require('../profile_settings.js');
 const basis=settings.costBasis({quantity:500,priceUsd:25.115,feesUsd:6.95,fx:1.3855,cadTotal:17408.05});
 const assert=require('node:assert/strict');
 assert.equal(basis.usdTotal,12564.45);
 assert.equal(basis.cadPerShare,34.8161);
 assert.throws(()=>settings.costBasis({...basis,cadTotal:100}));
 assert.throws(()=>settings.costBasis({...basis,quantity:0}));
}
