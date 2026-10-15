/* POM Connector 1.4.0 -- automatic local bridge, no codes, no remote code and no cookies. */
"use strict";
importScripts('extractor.js');
const DEFAULT_PORT = 17831;
const PROTOCOL = 1;
let socket = null, pingTimer = null, reconnectTimer = null;
let currentTask = null, connecting = false, pairedReady = false;
let generation = 0, initPromise = null;
let portCursor=0, failures=0, duplicateRetries=0;
let configQueue=Promise.resolve();
const sleep = ms => new Promise(resolve => setTimeout(resolve,ms));
const tr = {
  offline:'\u81ea\u52a8\u68c0\u6d4b\u4e2d\uff0c\u8bf7\u6253\u5f00\u914d\u5957\u7684\u684c\u9762\u8f6f\u4ef6',
  connected:'\u5df2\u81ea\u52a8\u8fde\u63a5\uff0c\u7b49\u5f85\u4f60\u5728\u8f6f\u4ef6\u4e2d\u542f\u52a8\u5de1\u68c0',
  disconnected:'\u5df2\u6682\u505c\u8fde\u63a5\uff0c\u70b9\u51fb\u201c\u6062\u590d\u8fde\u63a5\u201d\u53ef\u7ee7\u7eed'
};

async function state(extra) {
  await chrome.storage.local.set({status:{...extra,at:Date.now()}});
}
async function badge(text,color='#5B5FEF') {
  await chrome.action.setBadgeText({text});
  await chrome.action.setBadgeBackgroundColor({color});
}
function send(message) {
  if(socket?.readyState===WebSocket.OPEN)socket.send(JSON.stringify(message));
}
async function identity(cfg) {
  const p=await chrome.runtime.getPlatformInfo();
  let brand='Chromium',version=(navigator.userAgent.match(/(?:Chrome|Chromium)\/([\d.]+)/)||[])[1]||'';
  try {
    const data=await navigator.userAgentData.getHighEntropyValues(['fullVersionList']);
    const found=data.fullVersionList.find(x=>x.brand==='Google Chrome') || data.fullVersionList.find(x=>x.brand==='Chromium');
    if(found){brand=found.brand;version=found.version;}
  } catch (_) {}
  return {profile_name:cfg.profile_name||('Chrome '+cfg.instance_id.slice(0,6)), profile_directory:cfg.profile_directory||'',
    profile_path:cfg.profile_path||'', channel_label:cfg.channel_label||'',
    browser_brand:brand,browser_version:version,os:p.os,arch:p.arch,
    extension_version:chrome.runtime.getManifest().version};
}
function newToken() {
  return Array.from(crypto.getRandomValues(new Uint8Array(32)),b=>b.toString(16).padStart(2,'0')).join('');
}
function modifyConfig(change) {
  const op=configQueue.then(async()=> {
    const old=(await chrome.storage.local.get(['config'])).config||{};
    let cfg={...old};
    if(!cfg.auto_connect_schema) {
      // A never-paired old install defaulted to disabled. Migrate that case to auto on.
      // Respect a previously connected user's explicit pause.
      cfg.enabled=cfg.token?cfg.enabled!==false:true;
      cfg.auto_connect_schema=1;
    }
    if(!cfg.instance_id)cfg.instance_id=crypto.randomUUID();
    if(!cfg.token)cfg.token=newToken();
    if(change)cfg=change(cfg);
    if(JSON.stringify(cfg)!==JSON.stringify(old))await chrome.storage.local.set({config:cfg});
    return cfg;
  });
  configQueue=op.catch(()=>{});return op;
}
async function config(){return modifyConfig(null);}


async function closeOwnTab(tabId, jobId) {
  // A tab ID is saved before collection. Never query or close the user's ordinary tabs.
  if(!Number.isInteger(tabId))return;
  try {
    const stored=(await chrome.storage.session.get('owned')).owned||{};
    if(stored[String(tabId)]!==jobId)return;
    try {await chrome.tabs.remove(tabId);} catch (_) {}
    delete stored[String(tabId)];await chrome.storage.session.set({owned:stored});
  } catch (_) {}
}
async function abortCurrent() {
  if(currentTask){currentTask.cancelled=true;await closeOwnTab(currentTask.tabId,currentTask.job_id);}
}
async function recoverOwnedTabs() {
  const owned=(await chrome.storage.session.get('owned')).owned||{};
  for(const [id,job] of Object.entries(owned))await closeOwnTab(Number(id),job);
}
function check(task) {
  if(task.cancelled || task.generation!==generation || !pairedReady)throw new Error('Task cancelled or connector disconnected');
  if(Date.now()>task.deadline)throw new Error('Facebook task exceeded its time limit');
}
async function waitForTab(task) {
  while(true) {
    check(task);
    const tab=await chrome.tabs.get(task.tabId);
    if(tab.status==='complete')break;
    await sleep(250);
  }
  await sleep(2200);check(task);
}
async function extract(task,posts) {
  check(task);
  const entries=await chrome.scripting.executeScript({target:{tabId:task.tabId},func:extractPageDom,args:[task.page_id,posts]});
  const result=entries?.[0]?.result;
  if(!result || result.page_id!==task.page_id)throw new Error('Page extraction returned an invalid identity');
  return result;
}
async function load(task,url) {
  check(task);await chrome.tabs.update(task.tabId,{url});await waitForTab(task);
}
function usableName(rows) {
  return (rows||[]).some(r => r.text && !/^(?:facebook|log in|login|sign up|[0-9]+|(?:page|profile|\u4e3b\u9875)\s*[0-9]+)/i.test(r.text.trim()) &&
    !/(?:followers?|following|likes?|\u7c89\u4e1d|\u5173\u6ce8|\u767b\u5f55|\u6ce8\u518c)/i.test(r.text));
}
function allowedImage(url) {
  try {
    const u=new URL(url);return u.protocol==='https:' && !u.username && !u.password &&
      (u.hostname.endsWith('.fbcdn.net') || u.hostname==='fbcdn.net' || u.hostname.endsWith('.fbsbx.com'));
  } catch (_) {return false;}
}
async function avatarData(candidates,task) {
  for(const candidate of (candidates||[]).slice(0,3)) {
    check(task);
    if(!allowedImage(candidate.url))continue;
    try {
      const response=await fetch(candidate.url,{credentials:'omit',referrerPolicy:'no-referrer',signal:AbortSignal.timeout(7000)});
      if(!response.ok || !/^image\//i.test(response.headers.get('content-type')||''))continue;
      if(Number(response.headers.get('content-length')||0)>2000000)continue;
      const reader=response.body.getReader();let size=0;const chunks=[];
      while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;
        if(size>2000000){await reader.cancel();throw new Error('Avatar exceeds byte limit');}chunks.push(value);}
      const blob=new Blob(chunks,{type:response.headers.get('content-type')});
      const bitmap=await createImageBitmap(blob);
      if(Math.min(bitmap.width,bitmap.height)<32 || Math.max(bitmap.width,bitmap.height)/Math.min(bitmap.width,bitmap.height)>1.55 || bitmap.width*bitmap.height>24000000){bitmap.close();continue;}
      const canvas=new OffscreenCanvas(192,192),ctx=canvas.getContext('2d');
      const edge=Math.min(bitmap.width,bitmap.height);
      ctx.drawImage(bitmap,(bitmap.width-edge)/2,(bitmap.height-edge)/2,edge,edge,0,0,192,192);bitmap.close();
      const png=await canvas.convertToBlob({type:'image/png'});
      const bytes=new Uint8Array(await png.arrayBuffer());
      if(bytes.length>200000)continue;
      let binary='';for(const byte of bytes)binary+=String.fromCharCode(byte);
      return 'data:image/png;base64,'+btoa(binary);
    } catch (_) {}
  }
  return '';
}

async function collect(message) {
  if(!pairedReady)return;
  if(currentTask) {
    send({type:'result',job_id:message.job_id,payload:{page_id:message.page_id,error:'Connector already has an active task'}});return;
  }
  if(!/^[0-9]{5,25}$/.test(message.page_id||'') || !/^[a-f0-9]{32}$/.test(message.job_id||'') ||
      !['monitor','metadata'].includes(message.purpose))return;
  const task={...message,generation,cancelled:false,tabId:null,
    deadline:Date.now()+Math.min(110000,Math.max(5000,Number(message.timeout_ms)||100000))};
  currentTask=task;
  let payload={page_id:task.page_id};
  try {
    await state({text:'\u5de1\u68c0 '+task.page_id,connected:true});await badge('...');
    // Fail instead of opening a new visible browser window without the user's consent.
    const windows=await chrome.windows.getAll({windowTypes:['normal']});
    const normal=windows.find(w=>w.focused&&!w.incognito)||windows.find(w=>!w.incognito);
    if(!normal)throw new Error('Open a normal window in this Chrome Profile before inspecting');
    const tab=await chrome.tabs.create({windowId:normal.id,url:'https://www.facebook.com/'+task.page_id,active:false});
    task.tabId=tab.id;
    const owned=(await chrome.storage.session.get('owned')).owned||{};owned[String(tab.id)]=task.job_id;
    await chrome.storage.session.set({owned});
    await waitForTab(task);
    payload={...payload,...await extract(task,!!task.posts)};
    if(payload.error)throw new Error(payload.error);
    if(task.growth && !payload.follower_text){await sleep(1000);payload={...payload,...await extract(task,!!task.posts)};}
    if(task.posts) {
      const postCandidates=[...(payload.post_candidates||[])];
      for(let i=0;i<2;i++) {
        check(task);await chrome.scripting.executeScript({target:{tabId:task.tabId},func:()=>{window.scrollBy(0,650);}});
        await sleep(750);const p=await extract(task,true);
        postCandidates.push(...(p.post_candidates||[]));
      }
      payload.post_candidates=postCandidates.slice(0,160);
    }
    payload.avatar_data=await avatarData(payload.avatar_candidates,task);
    if(!usableName(payload.name_candidates)) {
      for(const url of ['https://www.facebook.com/profile.php?id='+task.page_id,'https://www.facebook.com/'+task.page_id+'/about']) {
        try {
          await load(task,url);const more=await extract(task,false);
          if(more.error)continue;
          payload.name_candidates=[...(payload.name_candidates||[]),...(more.name_candidates||[])].slice(0,160);
          if(!payload.avatar_data)payload.avatar_data=await avatarData(more.avatar_candidates,task);
          if(usableName(more.name_candidates))break;
        } catch(err){check(task);}
      }
    }
    delete payload.avatar_candidates; // Only the bounded PNG leaves this extension, not arbitrary CDN requests.
    payload.observed_at=Date.now()/1000;
  } catch(err) {payload.error=String(err.message||err).slice(0,350);}
  finally {
    await closeOwnTab(task.tabId,task.job_id);
    if(!task.cancelled && task.generation===generation && pairedReady)send({type:'result',job_id:task.job_id,payload});
    if(currentTask===task)currentTask=null;
    if(pairedReady){await badge('ON','#20A58F');await state({text:tr.connected,connected:true});}
  }
}

function candidatePorts(cfg) {
  return [...new Set([cfg.last_port,DEFAULT_PORT,...Array.from({length:9},(_,i)=>DEFAULT_PORT+i+1),cfg.port]
    .map(Number).filter(p=>Number.isInteger(p)&&p>=1024&&p<=65535))];
}
function scheduleReconnect(gen, delay) {
  if(gen!==generation)return;
  clearTimeout(reconnectTimer);
  reconnectTimer=setTimeout(()=>connect().catch(reportError),delay);
}
async function reportError(err) {
  connecting=false;
  await state({text:String(err.message||err),connected:false,error:true});
}
async function connect() {
  if(connecting || socket?.readyState===WebSocket.OPEN)return;
  connecting=true;
  const gen=++generation;
  let cfg;
  try {cfg=await config();} catch(err) {connecting=false;throw err;}
  if(gen!==generation)return;
  if(!cfg.enabled){connecting=false;return;}
  const ports=candidatePorts(cfg),port=ports[portCursor%ports.length];
  let ws;
  try {ws=new WebSocket('ws://127.0.0.1:'+port+'/connector/v1');}
  catch(err){connecting=false;scheduleReconnect(gen,5000);throw err;}
  socket=ws;
  let wasReady=false,lastRx=Date.now(),delayOverride=0;
  const attemptTimeout=setTimeout(()=>{if(gen===generation&&!pairedReady)ws.close();},3500);
  state({text:tr.offline,connected:false,port,auto:true}).catch(()=>{});
  ws.onopen=async()=> {
    if(gen!==generation)return;
    try {
      const data={protocol:PROTOCOL,product:'PageOperationsMonitor',instance_id:cfg.instance_id,
        identity:await identity(cfg),type:'auto_hello',token:cfg.token};
      if(gen===generation && socket===ws && ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify(data));
    } catch(err){await reportError(err);ws.close();}
  };
  ws.onmessage=async event=> {
    if(gen!==generation)return;
    try {
      if(typeof event.data!=='string'||event.data.length>1048576)throw new Error('Message exceeds limit');
      const msg=JSON.parse(event.data);lastRx=Date.now();
      if(msg.type==='ready') {
        if(msg.protocol!==PROTOCOL || msg.instance_id!==cfg.instance_id || msg.product!=='PageOperationsMonitor' || msg.connection_mode!=='auto') {
          await state({text:'\u8bf7\u9000\u51fa\u65e7\u7248\u8f6f\u4ef6\uff0c\u6253\u5f00\u672c\u6b21\u914d\u5957\u7684\u81ea\u52a8\u8fde\u63a5\u7248',connected:false,error:true});ws.close();return;
        }
        clearTimeout(attemptTimeout);
        pairedReady=true;wasReady=true;connecting=false;failures=0;duplicateRetries=0;portCursor=0;
        await modifyConfig(c=>({...c,last_port:port}));
        if(gen!==generation)return;
        clearInterval(pingTimer);
        pingTimer=setInterval(()=> {
          if(Date.now()-lastRx>65000){ws.close();return;}
          send({type:'ping'});
        },20000);
        await badge('ON','#20A58F');await state({text:tr.connected,connected:true,port,auto:true});
      } else if(msg.type==='error') {
        const messages={
          BLOCKED:'\u8be5\u6d4f\u89c8\u5668\u5df2\u5728\u8f6f\u4ef6\u4e2d\u505c\u7528\uff0c\u8bf7\u5141\u8bb8\u540e\u6062\u590d\u8fde\u63a5',
          AUTH_MISMATCH:'\u8fde\u63a5\u8eab\u4efd\u4e0d\u5339\u914d\uff0c\u8bf7\u5728\u63d2\u4ef6\u8bbe\u7f6e\u4e2d\u70b9\u51fb\u201c\u91cd\u5efa\u8fde\u63a5\u8eab\u4efd\u201d',
          UPGRADE_REQUIRED:'\u8bf7\u9000\u51fa\u65e7\u7248\u8f6f\u4ef6\u5e76\u542f\u52a8\u914d\u5957\u7684\u81ea\u52a8\u8fde\u63a5\u7248',
          INSTANCE_IN_USE:'\u6b63\u5728\u533a\u5206\u590d\u5236\u7684\u6d4f\u89c8\u5668\u8eab\u4efd',
          LIMIT:'\u672c\u673a\u5df2\u4fdd\u5b58\u7684\u6d4f\u89c8\u5668\u8fde\u63a5\u8fbe\u5230\u4e0a\u9650'
        };
        if(msg.code==='INSTANCE_IN_USE') {
          duplicateRetries++;
          if(duplicateRetries>=2) {
            await modifyConfig(c=>({...c,instance_id:crypto.randomUUID(),token:newToken()}));
            duplicateRetries=0;
          }
          delayOverride=2200;
        } else if(['BLOCKED','AUTH_MISMATCH','LIMIT'].includes(msg.code)) {
          await modifyConfig(c=>({...c,enabled:false}));
        }
        await state({text:messages[msg.code]||('\u8fde\u63a5\u6682\u672a\u6210\u529f\uff1a'+String(msg.message||'')),connected:false,error:true});
        await badge('!','#D84962');ws.close();
      } else if(!pairedReady) {
        ws.close();
      } else if(msg.type==='ping')send({type:'pong'});
      else if(msg.type==='pong'){}
      else if(msg.type==='collect')collect(msg);
      else if(msg.type==='cancel') {if(currentTask?.job_id===msg.job_id)await abortCurrent();}
      else if(msg.type==='identify') {
        await badge('ID','#5B5FEF');
        await state({text:'这是当前选中的浏览器连接器',connected:true,port,auto:true});
        setTimeout(async()=>{if(pairedReady){await badge('ON','#20A58F');await state({text:tr.connected,connected:true,port,auto:true});}},5000);
      } else if(msg.type==='revoked') {
        await modifyConfig(c=>({...c,enabled:false}));
        await state({text:'\u8f6f\u4ef6\u5df2\u505c\u7528\u6b64\u8fde\u63a5',connected:false,error:true});ws.close();
      }
    } catch(err) {
      await state({text:String(err.message||err),connected:false,error:true});ws.close();
    }
  };
  ws.onerror=()=>{};
  ws.onclose=async()=> {
    clearTimeout(attemptTimeout);
    if(gen!==generation)return;
    pairedReady=false;connecting=false;clearInterval(pingTimer);socket=null;
    await abortCurrent();
    if(gen!==generation)return;
    await badge('OFF','#66758D');
    const st=(await chrome.storage.local.get('status')).status;
    if(!st?.error)await state({text:tr.offline,connected:false,auto:true});
    const latest=await config();
    if(gen!==generation||!latest.enabled)return;
    if(wasReady){portCursor=0;failures=0;scheduleReconnect(gen,1500);return;}
    if(!delayOverride){portCursor++;failures++;}
    const delay=delayOverride || (failures>=ports.length?5000:120);
    if(failures>=ports.length)failures=0;
    scheduleReconnect(gen,delay);
  };
}

async function disconnect(disable=true) {
  if(disable)await modifyConfig(c=>({...c,enabled:false}));
  generation++;pairedReady=false;connecting=false;clearTimeout(reconnectTimer);clearInterval(pingTimer);
  await abortCurrent();
  if(socket)socket.close();socket=null;
  await badge('OFF','#66758D');await state({text:tr.disconnected,connected:false});
}
chrome.runtime.onMessage.addListener((msg,sender,reply)=> {
  if(sender.id!==chrome.runtime.id || !sender.url?.startsWith(chrome.runtime.getURL('')))return false;
  (async()=> {
    if(msg.type==='save') {
      if(currentTask)throw new Error('\u8bf7\u7b49\u5f85\u5f53\u524d\u4e3b\u9875\u5de1\u68c0\u5b8c\u6210\u540e\u4fee\u6539\u5907\u6ce8');
      const v=msg.config||{},allowed={};
      const limits={profile_name:80,profile_directory:100,profile_path:800,channel_label:100};
      for(const [key,limit] of Object.entries(limits)) {
        if(!Object.prototype.hasOwnProperty.call(v,key))continue;
        const value=String(v[key]??'').trim();
        if(value.length>limit||/[\x00-\x1f]/.test(value))throw new Error('Invalid identity field: '+key);
        allowed[key]=value;
      }
      if(allowed.profile_directory&&!/^(?:Default|Profile [0-9]{1,6})$/.test(allowed.profile_directory))throw new Error('Profile directory: Default / Profile 201');
      if(allowed.profile_path) {
        if(!/^(?:[a-zA-Z]:[\\/]|\/)/.test(allowed.profile_path))throw new Error('\u8def\u5f84\u9700\u4e3a\u5b8c\u6574\u7edd\u5bf9\u8def\u5f84');
        const tail=allowed.profile_path.replace(/[\\/]+$/,'').split(/[\\/]/).at(-1);
        if(!/^(?:Default|Profile [0-9]{1,6})$/.test(tail)||allowed.profile_directory&&tail!==allowed.profile_directory)throw new Error('\u8def\u5f84\u4e0e Profile \u76ee\u5f55\u4e0d\u4e00\u81f4');
      }
      await disconnect(false);await modifyConfig(c=>({...c,...allowed}));
      await connect();return {ok:true};
    }
    if(msg.type==='disconnect'){await disconnect();return {ok:true};}
    if(msg.type==='reconnect') {
      await disconnect(false);await modifyConfig(c=>({...c,enabled:true}));
      portCursor=0;failures=0;await connect();return {ok:true};
    }
    if(msg.type==='reset') {
      await disconnect(false);
      await modifyConfig(c=>({...c,instance_id:crypto.randomUUID(),token:newToken(),enabled:true}));
      portCursor=0;failures=0;await connect();return {ok:true};
    }
    if(msg.type==='status') {
      const cfg=await config();const {token,...safe}=cfg;
      return {config:safe,status:(await chrome.storage.local.get('status')).status};
    }
    return {ok:false,error:'Unsupported request'};
  })().then(reply).catch(err=>reply({ok:false,error:String(err.message||err)}));
  return true;
});
chrome.alarms.onAlarm.addListener(alarm=>{if(alarm.name==='pom-reconnect')connect().catch(reportError);});
chrome.runtime.onStartup.addListener(()=>init().then(()=>connect()).catch(reportError));
chrome.runtime.onInstalled.addListener(()=>init().catch(reportError));
async function init() {
  if(initPromise)return initPromise;
  initPromise=initialize();return initPromise;
}
async function initialize() {
  await chrome.storage.local.setAccessLevel({accessLevel:'TRUSTED_CONTEXTS'});
  await chrome.alarms.create('pom-reconnect',{periodInMinutes:0.5});
  await recoverOwnedTabs();await config();await connect();
}
init().catch(reportError);
