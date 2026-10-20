/* Adapt the shared Profile UI to the optimizer without loading the portfolio page. */
(async function(){
 'use strict';
 const button=document.querySelector('#profile-button');
 function loadScript(src){return new Promise((resolve,reject)=>{const script=document.createElement('script');script.src=src;script.onload=resolve;script.onerror=()=>reject(new Error('Profile settings could not load.'));document.body.append(script)})}
 try{
  const response=await fetch('/api/profile/holdings');if(!response.ok)throw Error('Profile holdings unavailable.');
  window.accounts=(await response.json()).accounts;
  window.profileSettings={name:'',holdings:{}};window.entryOverrides={};
  try{const saved=JSON.parse(localStorage.getItem(ProfileSettings.STORAGE_KEY)||'null');if(saved&&typeof saved==='object')window.profileSettings={name:typeof saved.name==='string'?saved.name.slice(0,60):'',holdings:saved.holdings&&typeof saved.holdings==='object'?saved.holdings:{}}}catch{}
  try{const saved=JSON.parse(localStorage.getItem(EntryPrices.STORAGE_KEY)||'{}');if(saved&&typeof saved==='object'&&!Array.isArray(saved))window.entryOverrides=saved}catch{}
  window.element=function(tag,text,className){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(className)node.className=className;return node};
  // Shared settings update their data state. Optimizer prices refresh explicitly.
  window.renderAccounts=function(){};window.renderStockDetails=function(){};
  await loadScript('profile_ui.js');
  await loadScript('option_premiums_ui.js');
  button.disabled=false;
 }catch(error){button.disabled=false;button.title=error.message;button.addEventListener('click',()=>{document.querySelector('#status').textContent=error.message})}
})();
