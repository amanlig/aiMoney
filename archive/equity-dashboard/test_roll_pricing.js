const assert=require('assert');
const Roll=require('./roll_pricing.js');
const base={shares:2000,contracts:20,stockCost:32160,originalPremium:4000,
 oldAsk:1.63,newBid:2.50,fees:40,oldStrike:30,newStrike:16,
 currentStock:12.18,targetStock:12,valuationDate:'2026-10-14',
 oldExpiry:'2028-01-21',newExpiry:'2027-01-15'};
const r=Roll.simulate(base);
assert.equal(r.buyback,3260);assert.equal(r.sale,5000);assert.equal(r.netCredit,1700);
assert.equal(r.target.roll,24000-32160+4000+1700);
assert.equal(r.target.keep,24000-32160+4000);
assert.equal(r.target.stockPnl,24000-32160);
assert.equal(r.maxProfit,32000-32160+4000+1700);
assert.equal(r.at(40).roll,r.maxProfit);
assert.equal(r.maxLoss,32160-4000-1700);
assert.equal(r.at(0).roll,-r.maxLoss);
assert.equal(r.combinedBreakeven,(32160-4000-1700)/2000);
assert(Math.abs(r.at(r.combinedBreakeven).roll)<1e-8);
assert(r.target.unacceptable);assert(!r.sameExpiry);
const breakEven=Roll.simulate({...base,newBid:r.bidForBreakeven});
assert(Math.abs(breakEven.target.roll)<1e-8);
const safe=Roll.simulate({...base,newBid:r.bidForLossBelowFive});
assert(!safe.target.unacceptable);
const unsafe=Roll.simulate({...base,newBid:r.bidForLossBelowFive-.01});
assert(unsafe.target.unacceptable);
const debit=Roll.simulate({...base,newBid:1});assert(debit.netCredit<0);assert(debit.maxLoss>base.stockCost-base.originalPremium);
const cap=Roll.simulate({...base,newStrike:5,newBid:0});assert.equal(cap.combinedBreakeven,null);assert(cap.maxProfit<0);
const lira=Roll.simulate({...base,originalPremium:26200});assert.equal(lira.bidForLossBelowFive,0);
assert(lira.currentExitPnl>0);assert.equal(lira.stockBreakeven,16.08);
const sameDate=Roll.simulate({...base,newExpiry:base.oldExpiry});assert(sameDate.sameExpiry);
for(const bad of [{newBid:-1},{fees:NaN},{contracts:21},{shares:2001},{newExpiry:'2026-10-01'},
 {newExpiry:'2027-02-30'},{newStrike:30,newExpiry:base.oldExpiry},{originalPremium:null}]){
 assert.throws(()=>Roll.simulate({...base,...bad}));
}
console.log('Roll checks passed: cash flow, premium counted once, assignment cap, break-even, loss threshold, debit, dates, exact coverage and LIRA premium proxy.');
const now=Date.parse('2026-10-14T19:00:00Z');
const option=(strike,expiry,bid,size=20)=>({strike,expiry,bidPrice:bid,askPrice:bid+.1,bidSize:size,isHalted:false,delay:0,validated:true});
const capture={symbol:'QBTS',account:'LIRA',captured_at:'2026-10-14T19:00:00Z',
 old_call:{strike:30,expiry:base.oldExpiry,askPrice:1.63,askSize:20,isHalted:false,delay:0},
 stock:{isHalted:false,delay:0},scan:{minimum_strike:21},
 candidates:[option(20,'2027-01-15',3),option(22,'2027-01-15',3,1),option(25,'2027-01-15',3),option(27,'2027-01-15',2.5),option(25,'2027-06-18',4)]};
const input={...base,symbol:'QBTS',account:'LIRA',originalPremium:26200};
const recommended=Roll.recommend(input,capture,5,now);
assert.equal(recommended.selected.strike,25);assert.equal(recommended.selected.expiry,'2027-06-18');
assert.equal(recommended.comparisons[0].strike,22);
assert.equal(recommended.comparisons[0].reason,'Bid size below full contract count');
assert(recommended.candidates.every(o=>o.strike>=21.08&&o.bidSize>=20));
assert.equal(Roll.recommend(input,capture,5,now+901000).selected,undefined);
assert.equal(Roll.recommend({...input,oldAsk:1},capture,5,now).selected,undefined);
assert.equal(Roll.recommend({...input,account:'TFSA'},capture,5,now).selected,undefined);
assert.equal(Roll.recommend({...input,fees:10000},capture,5,now).selected,null);
assert.throws(()=>Roll.recommend(input,capture,4,now));
assert.equal(Roll.recommend(input,{...capture,stock:{isHalted:false,delay:15}},5,now).selected,undefined);
assert.equal(Roll.recommend(input,{...capture,old_call:{...capture.old_call,askSize:1}},5,now).selected,undefined);
assert.equal(Roll.recommend(input,{...capture,candidates:capture.candidates.map(o=>({...o,validated:false}))},5,now).selected,null);
console.log('Recommendation checks passed: $5 gap, earliest expiry, credit ranking, size, source matching, stale/delayed data and fees.');
assert.equal(Roll.nextStrike(capture.candidates,'2027-01-15',21.08),22);
assert.equal(Roll.nextStrike(capture.candidates,'2027-01-15',22),22);
assert.equal(Roll.nextStrike(capture.candidates,'2027-01-15',22.01),25);
assert.equal(Roll.nextStrike(capture.candidates,'2027-01-15',40),null);
const futureCapture={...capture,candidates:[...capture.candidates,option(22,'2029-01-19',4),option(25,'2029-01-19',3)]};
const later=Roll.recommend(input,futureCapture,5,now,{earliestExpiry:'2028-01-22',minimumCredit:1000});
assert.equal(later.selected.strike,22);assert.equal(later.selected.expiry,'2029-01-19');
assert.equal(later.comparisons.length,1);
assert.equal(Roll.recommend(input,futureCapture,5,now,{earliestExpiry:'2028-01-22',minimumCredit:10000}).selected,null);
const missingQuote={...futureCapture,candidates:futureCapture.candidates.map(o=>o.expiry==='2029-01-19'&&o.strike===22?{...o,bidPrice:null}:o)};
assert.equal(Roll.recommend(input,missingQuote,5,now,{earliestExpiry:'2028-01-22'}).selected,null);
console.log('Expiry/strike checks passed: exact next listed strike, no higher-strike substitution, later expiry, minimum credit and missing quotes.');
