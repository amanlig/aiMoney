/* Paste confirmations locally, review OCR, and save structured SQLite samples. */
(function(){
'use strict';
const section=document.querySelector('#fx-entry');
section.innerHTML=`<details><summary style="cursor:pointer;font-size:20px;font-weight:700">FX model · add transaction samples</summary>
<p>Paste a CIBC confirmation screenshot here, or choose a PNG/JPEG. Review all extracted fields before saving. Images are processed locally and discarded; only reviewed transaction data is saved in SQLite.</p>
<div id="fx-paste" tabindex="0" role="region" aria-label="Paste confirmation image" style="border:2px dashed #bbc9d8;border-radius:10px;padding:20px;margin:16px 0">Click here and paste an image (Ctrl+V), or <label>choose image <input id="fx-file" type="file" accept="image/png,image/jpeg"></label></div>
<img id="fx-preview" alt="Confirmation being reviewed" hidden style="max-width:100%;max-height:360px;object-fit:contain">
<p id="fx-entry-status" role="status" aria-live="polite"></p>
<form id="fx-sample-form"><div class="fields" id="fx-sample-fields"></div>
<p>USD converted is the confirmation subtotal, including any commission deducted or added before conversion. Direction means buying USD (CAD pays for a purchase) or selling USD (proceeds converted to CAD). Verify this for every confirmation.</p>
<label><input id="fx-reviewed" type="checkbox" required> I verified these fields against the confirmation.</label>
<div class="entry-actions"><button class="primary" type="submit">Save sample</button><button id="fx-clear" type="button">Clear entry</button><button id="fx-export" type="button">Export dataset (JSON)</button></div></form>
<details><summary>Extracted text</summary><pre id="fx-ocr-text" style="white-space:pre-wrap"></pre></details>
<h3 id="fx-sample-count">Saved samples</h3><p>Yahoo’s settlement-day daily close is added when available. It is a retrospective feature and cannot be used for predictions made before that close. No prediction model has been trained yet.</p><div class="table-scroll" id="fx-sample-list"></div></details>`;
const form=section.querySelector('form'),fields={},status=section.querySelector('#fx-entry-status');
const definitions=[['account','Account',['','TFSA','RRSP','Other CAD']],['symbol','Stock symbol','text'],['instrument','Security type',['','stock','option']],['action','Security transaction',['','buy','sell']],['direction','FX direction',['','buy_usd','sell_usd']],['trade_date','Trade date (optional)','date'],['settlement_date','Settlement date','date'],['usd_amount','USD converted (subtotal)','number'],['commission_usd','Commission (USD, optional)','number'],['cad_amount','CAD charged / received','number'],['applied_rate','Applied CAD per USD','number'],['notes','Notes (optional)','text']];
for(const [key,title,type] of definitions){
 const label=element('label',title),node=element(Array.isArray(type)?'select':'input');
 node.name=key;node.id='fx-sample-'+key;
 if(Array.isArray(type))for(const value of type){const opt=element('option',({buy_usd:'Buy USD · pay CAD',sell_usd:'Sell USD · receive CAD'})[value]||value||'Choose…');opt.value=value;node.append(opt);}
 else {node.type=type;if(type==='number'){node.min=key==='commission_usd'?'0':'0.00000001';node.step='any';}if(type==='date')node.max=new Date().toLocaleDateString('en-CA');}
 node.required=!['trade_date','commission_usd','notes'].includes(key);label.append(node);section.querySelector('#fx-sample-fields').append(label);fields[key]=node;
}
let url=null,busy=false,samples=[];
function message(text,error=false){status.textContent=text;status.className=error?'warning':'context';}
function lock(value){busy=value;form.querySelector('button[type=submit]').disabled=value;section.querySelector('#fx-file').disabled=value;section.querySelector('#fx-clear').disabled=value;}
function clear(){form.reset();section.querySelector('#fx-reviewed').checked=false;section.querySelector('#fx-ocr-text').textContent='';const img=section.querySelector('#fx-preview');img.hidden=true;img.removeAttribute('src');if(url)URL.revokeObjectURL(url);url=null;section.querySelector('#fx-file').value='';}
async function request(path,options){const response=await fetch(path,options);let value;try{value=await response.json();}catch{throw new Error('Restart the updated dashboard server to enable sample entry.');}if(!response.ok)throw new Error(value.error||'Request failed.');return value;}
async function read(file){
 if(busy){message('Please wait for the current operation.',true);return;}
 if(!['image/png','image/jpeg'].includes(file.type)||file.size>8*1024*1024){message('Choose a PNG/JPEG smaller than 8 MB.',true);return;}
 clear();url=URL.createObjectURL(file);const img=section.querySelector('#fx-preview');img.src=url;img.hidden=false;lock(true);message('Reading the confirmation locally…');
 try{const result=await request('/api/fx-samples/ocr',{method:'POST',headers:{'Content-Type':file.type},body:file});for(const [key,value] of Object.entries(result.fields))if(fields[key])fields[key].value=value;section.querySelector('#fx-ocr-text').textContent=result.text;message('Extraction finished. Check every value, select the account, and confirm before saving.');}
 catch(error){message(error.message+' The preview remains available for manual entry.',true);}finally{lock(false);}
}
section.addEventListener('paste',event=>{const file=[...(event.clipboardData?.items||[])].find(item=>item.kind==='file'&&item.type.startsWith('image/'))?.getAsFile();if(file){event.preventDefault();read(file);}});
section.querySelector('#fx-file').addEventListener('change',event=>{if(event.target.files[0])read(event.target.files[0]);});
form.addEventListener('input',event=>{if(event.target.id!=='fx-reviewed')section.querySelector('#fx-reviewed').checked=false;});
section.querySelector('#fx-clear').addEventListener('click',()=>{clear();message('Entry cleared.');});
async function load(){
 const result=await request('/api/fx-samples');samples=result.samples.sort((a,b)=>b.settlement_date.localeCompare(a.settlement_date)||b.id-a.id);
 section.querySelector('#fx-sample-count').textContent=`Saved samples · ${samples.length} (${samples.filter(s=>s.direction==='buy_usd').length} buy USD / ${samples.filter(s=>s.direction==='sell_usd').length} sell USD)`;
 const panel=section.querySelector('#fx-sample-list');panel.replaceChildren();
 if(!samples.length){panel.append(element('p','No samples saved yet.'));return;}
 const table=element('table'),head=element('thead'),tr=element('tr');for(const title of ['Settlement','Account','Symbol','Type / action','FX direction','USD converted','CAD total','Applied rate','Yahoo close',''])tr.append(element('th',title));head.append(tr);table.append(head);const body=element('tbody');table.append(body);panel.append(table);
 for(const sample of samples){const row=element('tr');for(const value of [sample.settlement_date,sample.account,sample.symbol,sample.instrument+' / '+sample.action,sample.direction,sample.usd_amount.toFixed(2),sample.cad_amount.toFixed(2),sample.applied_rate.toFixed(5),sample.yahoo_close?.toFixed(5)||'Unavailable'])row.append(element('td',value));const td=element('td'),del=element('button','Delete');del.type='button';td.append(del);row.append(td);body.append(row);del.addEventListener('click',async()=>{if(!confirm('Delete this saved transaction sample?'))return;try{await request('/api/fx-samples/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:sample.id})});await load();}catch(error){message(error.message,true);}});}
}
form.addEventListener('submit',async event=>{
 event.preventDefault();if(busy||!form.reportValidity())return;
 const value=Object.fromEntries(Object.entries(fields).map(([key,node])=>[key,node.type==='number'?(node.value===''?null:Number(node.value)):node.value]));value.reviewed=section.querySelector('#fx-reviewed').checked;
 lock(true);message('Saving reviewed data and looking up Yahoo’s historical reference…');
 try{const saved=await request('/api/fx-samples',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});clear();message('Saved in SQLite. '+saved.yahoo_status);await load();}catch(error){message(error.message,true);}finally{lock(false);}
});
section.querySelector('#fx-export').addEventListener('click',async()=>{try{await load();const blob=new Blob([JSON.stringify({schema_version:1,samples},null,2)],{type:'application/json'}),link=element('a');const href=URL.createObjectURL(blob);link.href=href;link.download='cibc-fx-samples.json';link.click();setTimeout(()=>URL.revokeObjectURL(href),1000);}catch(error){message(error.message,true);}});
section.querySelector('details').addEventListener('toggle',event=>{if(event.target.open)load().catch(error=>message(error.message,true));});
})();
