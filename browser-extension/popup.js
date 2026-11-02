'use strict';
const $=id=>document.getElementById(id);
function paint(status){
  const connected=!!status?.connected, error=!!status?.error;
  $('statusText').textContent=status?.text||(connected?'已连接软件':'等待软件');
  $('dot').className='dot '+(connected?'online':error?'error':'waiting');
}
async function call(msg){const r=await chrome.runtime.sendMessage(msg);if(r?.ok===false)throw new Error(r.error||'操作失败');return r;}
async function load(){
  const r=await call({type:'status'}), c=r.config||{};
  $('profile_name').value=c.profile_name||'';paint(r.status);
}
$('save').onclick=async()=>{
  const b=$('save');b.disabled=true;$('saved').textContent='';
  try{await call({type:'save',config:{profile_name:$('profile_name').value.trim()}});$('saved').textContent='已保存';setTimeout(()=>{$('saved').textContent='';},1800);await load();}
  catch(e){$('saved').textContent=e.message||String(e);}
  finally{b.disabled=false;}
};
$('profile_name').addEventListener('keydown',e=>{if(e.key==='Enter')$('save').click();});
chrome.storage.onChanged.addListener((changes,area)=>{if(area==='local'&&(changes.status||changes.config))load().catch(()=>{});});
load().catch(e=>{paint({text:e.message,error:true});});
