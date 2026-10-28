import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = readFileSync(new URL('../frontend/src/RolloverExport.js', import.meta.url), 'utf8');
const {rolloverCsv, downloadRollovers} = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const row = (strike, total) => ({strategy:'Roll then close', strike, expiry:'2030-01-18', total_pl_usd:total, net_profit_usd:999, eligible:false});
const analysis = {inputs:{account:'RRSP',symbol:'TEST',held:{},stock:{bidPrice:20,askPrice:22},candidates:[],opening_reference:{},captured_at:'2026-10-27T00:00:00Z'},result:{rows:[row(30,-10),row(31,null),row(32,0),row(33,50),{strategy:'Close now',total_pl_usd:40}],assumptions:['Example, "quoted"\nline'],search:{}}};
const csv = rolloverCsv(analysis);
assert(csv.startsWith('\uFEFF'));
assert(csv.indexOf('"33"') < csv.indexOf('"32"'));
assert(csv.indexOf('"32"') < csv.indexOf('"30"'));
assert(csv.indexOf('"30"') < csv.indexOf('"31"'));
assert(csv.includes('"Example, ""quoted""\nline"'));
assert(csv.includes('"-10"')); // losses remain numeric, not formula escaped
assert(!csv.includes('999')); // unknown total must never fall back to another profit
assert.equal(analysis.result.rows[0].strike,30); // sorting does not mutate dashboard
assert.equal(rolloverCsv({...analysis,result:{rows:[]}}),null);
const unsafe=rolloverCsv({...analysis,inputs:{...analysis.inputs,symbol:'=1+1'}});
assert(unsafe.includes('"\'=1+1"'));
let clicked=false, removed=false;
globalThis.document={createElement:()=>({click(){clicked=true;},remove(){removed=true;}}),body:{appendChild(){}}};
downloadRollovers(analysis);
assert(clicked && removed);
console.log('CSV sorting, missing profits, zero/loss, escaping, no mutation and download checks passed.');
