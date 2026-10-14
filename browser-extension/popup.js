'use strict';
const $=id=>document.getElementById(id);let enabled=true;
$('heading').textContent='\u4e3b\u9875\u8fd0\u8425\u8fde\u63a5\u5668';$('settings').textContent='\u5907\u6ce8 / \u8bbe\u7f6e';
function status(v){$('status').textContent=v?.text||'\u6b63\u5728\u81ea\u52a8\u68c0\u6d4b\u8f6f\u4ef6';$('status').className='status'+(v?.connected?' online':v?.error?' error':'');}
async function load(){const r=await chrome.runtime.sendMessage({type:'status'}),c=r.config||{};enabled=!!c.enabled;
$('details').textContent=(c.profile_name||('Chrome '+(c.instance_id||'').slice(0,6)))+'\n\u65e0\u9700\u914d\u5bf9\u7801\uff0c\u5f00\u542f\u8f6f\u4ef6\u5373\u53ef\u8fde\u63a5';
$('toggle').textContent=enabled?'\u6682\u505c\u8fde\u63a5':'\u6062\u590d\u8fde\u63a5';status(r.status);}
$('settings').onclick=()=>chrome.runtime.openOptionsPage();
$('toggle').onclick=async()=>{const r=await chrome.runtime.sendMessage({type:enabled?'disconnect':'reconnect'});if(r.ok===false)status({text:r.error,error:true});else await load();};
chrome.storage.onChanged.addListener((c,area)=>{if(area==='local'&&(c.status||c.config))load().catch(()=>{});});
load().catch(e=>status({text:e.message,error:true}));
