'use strict';
const $=id=>document.getElementById(id);
const labels={
heading:'\u4e3b\u9875\u8fd0\u8425\u00b7\u81ea\u52a8\u8fde\u63a5\u5668',subtitle:'\u65e0\u9700\u914d\u5bf9\u7801\uff0c\u6253\u5f00\u8f6f\u4ef6\u5373\u53ef\u81ea\u52a8\u8fde\u63a5',
connectHeading:'\u81ea\u52a8\u8fde\u63a5\u672c\u673a\u8f6f\u4ef6',autoNote:'\u672c\u63d2\u4ef6\u5df2\u81ea\u52a8\u5bfb\u627e\u540c\u4e00\u53f0\u7535\u8111\u4e0a\u7684\u914d\u5957\u8f6f\u4ef6\u3002\u53ea\u6709\u4e00\u4e2a\u6d4f\u89c8\u5668\u65f6\u81ea\u52a8\u9009\u4e2d\uff1b\u591a\u4e2a\u6d4f\u89c8\u5668\u65f6\uff0c\u5728\u8f6f\u4ef6\u4e2d\u9009\u62e9\u4e00\u4e2a\u3002\u8fde\u63a5\u672c\u8eab\u4e0d\u4f1a\u5f00\u59cb\u5de1\u68c0\u3002',
reconnect:'\u91cd\u65b0\u68c0\u6d4b / \u6062\u590d\u8fde\u63a5',disconnect:'\u6682\u505c\u8fde\u63a5',
profileHeading:'\u6d4f\u89c8\u5668\u5907\u6ce8\uff08\u53ef\u9009\uff09',nameLabel:'\u5907\u6ce8\u540d\u79f0',nameNote:'\u53ef\u586b\u7528\u623760\u7b49\u5bb9\u6613\u8bc6\u522b\u7684\u540d\u79f0\u3002\u7559\u7a7a\u4e5f\u80fd\u8fde\u63a5\uff0c\u8f6f\u4ef6\u4f1a\u663e\u793a Chrome \u548c\u77ed\u8fde\u63a5 ID\u3002',
advancedTitle:'\u9ad8\u7ea7\u5907\u6ce8\uff08\u4e0d\u586b\u4e5f\u80fd\u4f7f\u7528\uff09',channelLabel:'\u6e20\u9053\uff08\u4eba\u5de5\u786e\u8ba4\uff09',channelUnknown:'\u672a\u6307\u5b9a',dirLabel:'Profile \u76ee\u5f55\uff08\u53ef\u9009\uff09',pathLabel:'Profile \u5b8c\u6574\u8def\u5f84\uff08\u53ef\u9009\uff09',
pathNote:'\u8def\u5f84\u53ea\u7528\u4e8e\u5907\u6ce8\uff0c\u4e0d\u4f5c\u4e3a\u8fde\u63a5\u6761\u4ef6\u3002\u9700\u8981\u8bb0\u5f55\u65f6\u53ef\u4ece chrome://version \u590d\u5236\u3002\u8fd9\u4e9b\u4fe1\u606f\u4e0d\u4f1a\u88ab\u5199\u6210\u81ea\u52a8\u8bc6\u522b\u7ed3\u679c\u3002',openVersion:'\u6253\u5f00 chrome://version',save:'\u4fdd\u5b58\u5907\u6ce8',
privacyHeading:'\u4f7f\u7528\u8bf4\u660e',privacyText:'\u8bf7\u4fdd\u6301\u76ee\u6807 Chrome \u6253\u5f00\u4e14 Facebook \u5df2\u767b\u5f55\u3002\u63d2\u4ef6\u53ea\u8bfb\u53d6\u8f6f\u4ef6\u4e0b\u53d1\u7684\u516c\u5171\u4e3b\u9875 ID\uff0c\u4e0d\u8bfb Cookie\u3001\u5bc6\u7801\u6216\u6d4f\u89c8\u5386\u53f2\u3002\u5de1\u68c0\u4f1a\u4f7f\u7528\u975e\u6fc0\u6d3b\u6807\u7b7e\u9875\uff0c\u4e0d\u4f1a\u81ea\u52a8\u5f00\u65b0\u6d4f\u89c8\u5668\u7a97\u53e3\u3002\u8fde\u63a5\u4ec5\u9650\u672c\u673a 127.0.0.1\u3002',
reset:'\u91cd\u5efa\u8fde\u63a5\u8eab\u4efd',footer:'1.3.0 \u00b7 \u81ea\u52a8\u8fde\u63a5\u4fee\u590d\u7248'
};
for(const [id,text] of Object.entries(labels))$(id).textContent=text;
$('profile_name').placeholder='\u4f8b\u5982\uff1a\u7528\u623760\uff08\u53ef\u7559\u7a7a\uff09';
function show(st){$('status').textContent=st?.text||'\u81ea\u52a8\u68c0\u6d4b\u4e2d...';$('status').className='status'+(st?.connected?' online':st?.error?' error':'');$('endpoint').textContent=st?.port?'\u672c\u673a\u901a\u9053\uff1a127.0.0.1:'+st.port:'\u81ea\u52a8\u9009\u62e9\u672c\u673a\u53ef\u7528\u7aef\u53e3';}
async function call(msg){const r=await chrome.runtime.sendMessage(msg);if(r?.ok===false)throw new Error(r.error);return r;}
async function load(){const r=await call({type:'status'}),c=r.config||{};for(const key of ['profile_name','profile_directory','profile_path','channel_label'])$(key).value=c[key]||'';$('instance').textContent='Connection ID: '+c.instance_id;show(r.status);}
$('save').onclick=async()=>{const b=$('save');b.disabled=true;try{const c={};for(const key of ['profile_name','profile_directory','profile_path','channel_label'])c[key]=$(key).value.trim();await call({type:'save',config:c});}catch(e){show({text:e.message,error:true});}finally{b.disabled=false;}};
$('reconnect').onclick=()=>call({type:'reconnect'}).catch(e=>show({text:e.message,error:true}));
$('disconnect').onclick=()=>call({type:'disconnect'}).catch(e=>show({text:e.message,error:true}));
$('openVersion').onclick=()=>chrome.tabs.create({url:'chrome://version/'});
$('reset').onclick=async()=>{if(confirm('\u4ec5\u5728\u8eab\u4efd\u4e0d\u5339\u914d\u65f6\u4f7f\u7528\u3002\u91cd\u5efa\u540e\u4f1a\u81ea\u52a8\u8fde\u63a5\uff0c\u53ef\u80fd\u9700\u5728\u8f6f\u4ef6\u4e2d\u91cd\u65b0\u9009\u4e2d\u6b64\u6d4f\u89c8\u5668\u3002')){await call({type:'reset'});await load();}};
chrome.storage.onChanged.addListener((c,area)=>{if(area==='local'&&c.status)show(c.status.newValue);});
$('channel_label').addEventListener('wheel',e=>e.preventDefault(),{passive:false});
load().catch(e=>show({text:e.message,error:true}));
