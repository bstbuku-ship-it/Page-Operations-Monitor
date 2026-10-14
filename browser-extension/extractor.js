/* DOM candidate ordering ported from the supplied 1.9.1 desktop collector. */
function extractPageDom(pageId, wantPosts) {
"use strict";
  const pid = String(pageId);
  const clean = s => String(s || "").replace(/\s+/g, " ").trim();
  const normName = s => clean(s).replace(/\s*[|\u00b7]\s*Facebook.*$/i, "").replace(/^\(\d+\)\s*/, "");
  const validName = s => {s=normName(s);return s && s!==pid && s.length<180 &&
    !/^(facebook|log in|login|sign up|home|menu|notifications|see all|posts|photos|videos|about)$/i.test(s) &&
    !/^(?:page|\u4e3b\u9875|\u516c\u5171\u4e3b\u9875)\s*[:#]?\s*\d+$/i.test(s) &&
    !/(?:followers?|following|likes?|\u7c89\u4e1d|\u5173\u6ce8|\u767b\u5f55|\u6ce8\u518c)/i.test(s) &&
    !/^\d[\d, .]*$/.test(s);};
  const _strict_h1_candidates = (
            (els) => {
              const out = [];
              for (const el of els) {
                const r = el.getBoundingClientRect();
                const st = getComputedStyle(el);
                if (!r || r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > innerHeight * 2) continue;
                if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity || 1) === 0) continue;
                if (el.closest('[role="navigation"],[role="tablist"],[role="menu"],[role="dialog"]')) continue;
                const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                if (!text || text.length > 180) continue;
                out.push({text, top:r.top, left:r.left, fs:parseFloat(st.fontSize || '0') || 0});
              }
              out.sort((a,b) => (a.top-b.top) || (b.fs-a.fs) || (a.left-b.left));
              return out.slice(0, 20);
            }
            );
  const _profile_alt_candidates = (
            (els) => {
              const out = [];
              for (const el of els.slice(0, 300)) {
                const r = el.getBoundingClientRect();
                const st = getComputedStyle(el);
                if (!r || r.width < 28 || r.height < 28 || r.bottom < 0 || r.top > 1200) continue;
                if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity || 1) === 0) continue;
                if (el.closest('[role="navigation"],[role="menu"],[role="dialog"]')) continue;
                const alt = (el.getAttribute('alt') || '').replace(/\s+/g, ' ').trim();
                if (!alt || alt.length > 220) continue;
                const isProfile = /(?:'s\s+profile\s+(?:picture|photo)|profile\s+(?:picture|photo)|的头像|的大头贴|的个人头像|头像|foto de perfil|photo de profil|profilbild|immagine del profilo)$/i.test(alt);
                if (!isProfile) continue;
                out.push({text:alt, top:r.top, size:Math.max(r.width, r.height)});
              }
              out.sort((a,b) => (a.top-b.top) || (b.size-a.size));
              return out.slice(0, 30);
            }
            );
  const _self_link_candidates = (
            (els, pageId) => {
              const out = [];
              const id = String(pageId || '');
              const cur = new URL(location.href);
              const curPath = cur.pathname.replace(/\/+$/, '');
              for (const el of els.slice(0, 1200)) {
                if (el.closest('[role="navigation"],[role="tablist"],[role="menu"],[role="dialog"]')) continue;
                const r = el.getBoundingClientRect();
                const st = getComputedStyle(el);
                if (!r || r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > 1100) continue;
                if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity || 1) === 0) continue;
                const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                if (!text || text.length > 180) continue;
                let u; try { u = new URL(el.href, location.href); } catch (_) { continue; }
                const path = u.pathname.replace(/\/+$/, '');
                const idHit = id && (path === '/' + id || path.startsWith('/' + id + '/'));
                const profileId = id && u.searchParams.get('id') === id;
                const samePath = curPath && path === curPath;
                if (!(idHit || profileId || samePath)) continue;
                out.push({
                  text,
                  top:r.top,
                  fs:parseFloat(st.fontSize || '0') || 0,
                  fw:parseInt(st.fontWeight || '400', 10) || 400,
                  strong:idHit || profileId
                });
              }
              out.sort((a,b) => (Number(b.strong)-Number(a.strong)) || (a.top-b.top) || (b.fs-a.fs) || (b.fw-a.fw));
              return out.slice(0, 60);
            }
            );
  const _near_follower_candidates = (
            (body, needle) => {
              needle = String(needle || '').replace(/\s+/g, ' ').trim();
              if (!needle) return [];
              const all = Array.from(document.querySelectorAll('a,span,div'));
              const hits = [];
              for (const el of all.slice(0, 5000)) {
                if (el.closest('[role="navigation"],[role="tablist"],[role="menu"],[role="dialog"]')) continue;
                const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                if (!text || text.length > 220) continue;
                if (!(text === needle || text.includes(needle))) continue;
                const r = el.getBoundingClientRect();
                const st = getComputedStyle(el);
                if (!r || r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > 1400) continue;
                if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity || 1) === 0) continue;
                hits.push({el, r});
              }
              if (!hits.length) return [];
              hits.sort((a,b) => (a.r.top-b.r.top) || (a.r.left-b.r.left));
              const target = hits[0].r;
              const out = [];
              const candidates = Array.from(document.querySelectorAll('h1,h2,[role="heading"],a,span,strong'));
              for (const el of candidates.slice(0, 5000)) {
                if (el.closest('[role="navigation"],[role="tablist"],[role="menu"],[role="dialog"]')) continue;
                const r = el.getBoundingClientRect();
                const st = getComputedStyle(el);
                if (!r || r.width < 2 || r.height < 2) continue;
                if (r.top < target.top - 320 || r.top > target.bottom + 90) continue;
                if (Math.abs(r.left - target.left) > 900) continue;
                if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity || 1) === 0) continue;
                const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                if (!text || text.length > 180 || text === needle) continue;
                const fs = parseFloat(st.fontSize || '0') || 0;
                const fw = parseInt(st.fontWeight || '400', 10) || 400;
                const distance = Math.max(0, target.top - r.bottom);
                out.push({text, distance, fs, fw, top:r.top});
              }
              out.sort((a,b) => (a.distance-b.distance) || (b.fs-a.fs) || (b.fw-a.fw));
              return out.slice(0, 80);
            }
            );
  const _avatar_candidates = ((pageName) => {
          const title=document.querySelector('h1');
          const titleRect=title ? title.getBoundingClientRect() : null;
          const pageTitle=(pageName||'').trim().toLowerCase();
          const hits=[];
          const words=/profile picture|profile photo|avatar|picture of|page picture|page profile|头像|大头贴|大頭貼|头像照片|照片墙|主页照片/i;
          const cover=/cover photo|cover image|封面|封面照片|相册|帖子图片/i;
          function push(el,sel,i) {
            let r;try{r=el.getBoundingClientRect()}catch{return;}
            if(r.width<30||r.height<30||r.top>1800||r.bottom<0)return;
            const ratio=Math.max(r.width,r.height)/Math.max(1,Math.min(r.width,r.height));
            if(ratio>2.2)return;
            const tag=el.tagName.toLowerCase();
            const alt=String(el.getAttribute('alt')||el.getAttribute('aria-label')||'');
            let src=el.currentSrc||el.getAttribute('src')||el.getAttribute('href')||el.getAttribute('xlink:href')||'';
            if(!src) {
              const bg=getComputedStyle(el).backgroundImage||'';
              const m=bg.match(/url\(["']?(.*?)["']?\)/);
              if(m)src=m[1];
            }
            let score=0;
            if(words.test(alt))score+=145;
            if(cover.test(alt))score-=95;
            if(pageTitle&&alt.toLowerCase().includes(pageTitle))score+=42;
            if(ratio<=1.22)score+=35;
            if(r.width>=45&&r.width<=350&&r.height>=45&&r.height<=350)score+=25;
            if(r.top>=0&&r.top<730)score+=20;
            if(titleRect){
              let dist=Math.abs((r.top+r.height/2)-(titleRect.top+titleRect.height/2));
              if(dist<160)score+=45;
              else if(dist<310)score+=21;
            }
            const ancestor=el.closest('a[href]');
            if(ancestor&&/\/profile\.php|\/pages\/|facebook\.com\//i.test(ancestor.href||''))score+=15;
            if(el.closest('nav,[role=navigation],[role=banner],[data-pagelet=RightRail]'))score-=120;
            if(el.closest('article'))score-=85;
            if(r.width<48||r.height<48)score-=55;
            if(src.startsWith('data:image/'))score+=5;
            if(score>=25)hits.push({url:src,selector:sel,index:i,score,alt,width:r.width,height:r.height});
          }
          [...document.querySelectorAll('img')].forEach((el,i)=>push(el,'img',i));
          [...document.querySelectorAll('svg image')].forEach((el,i)=>push(el,'svg image',i));
          [...document.querySelectorAll('[role="img"]')].forEach((el,i)=>push(el,'[role="img"]',i));
          return hits.sort((a,b)=>b.score-a.score).slice(0,24);
        });
  const _post_candidates = (
        ({pid, name}) => {
          const norm=s=>(s||'').trim().replace(/\s+/g,' ').toLowerCase();
          const hostOk=h=>h==='facebook.com'||h.endsWith('.facebook.com');
          const parts=u=>{try{const a=new URL(u,location.href);if(!hostOk(a.hostname))return '';
            const id=a.searchParams.get('id');if(id)return id;
            return a.pathname.replace(/^\/|\/$/g,'').split('/')[0];}catch(e){return '';}};
          const alias=new Set([pid,parts(location.href)].filter(Boolean));
          const own=a=>alias.has(parts(a.href)) || (name && norm(a.textContent)===norm(name));
          let articles=[...document.querySelectorAll('main [role="article"], [role="main"] [role="article"]')];
          if(!articles.length)articles=[...document.querySelectorAll('[data-pagelet^="FeedUnit_"], .userContentWrapper')];
          articles=articles.filter(a=>!a.parentElement?.closest('[role="article"]'));
          const rows=[];
          for(const art of articles.slice(0,12)){
            const text=(art.innerText||'').slice(0,260);
            if(/suggested for you|为你推荐|為你推薦|sponsored|赞助内容|贊助內容/i.test(text))continue;
            const nested=n=>{let a=n.closest('[role="article"]');return a&&a!==art;};
            const anchors=[...art.querySelectorAll('a[href]')].filter(a=>!nested(a));
            const header=anchors.slice(0,8);
            const authored=header.some(own);
            if(!authored)continue;
            const links=anchors.filter(a=>/\/posts\/|story_fbid=|\/videos\/|\/reel\/|\/permalink\//.test(a.href));
            const nodes=[...art.querySelectorAll('time[datetime],abbr[data-utime],abbr[title],[data-utime]')]
              .filter(n=>!nested(n) && !n.closest('[aria-label*="Comment"],[aria-label*="评论"],[data-testid*="comment"]'));
            for(const node of nodes.slice(0,3)){
              const link=node.closest('a[href]') || links[0];
              for(const attr of ['datetime','data-utime','title','aria-label']){
                const raw=node.getAttribute(attr);
                if(raw)rows.push({raw,authored:true,url:link?link.href:'',source:'主页贴文时间节点'});
              }
            }
            // Only header/permalink timestamp labels, never the full post text or its comments.
            for(const link of links.slice(0,2)){
              for(const raw of [link.getAttribute('aria-label'),link.getAttribute('title'),link.innerText]){
                if(raw && raw.length<140)rows.push({raw,authored:true,url:link.href,source:'主页贴文链接时间'});
              }
            }
          }
          return rows;
        }
        );

  if(location.protocol!=="https:" || !["www.facebook.com","facebook.com","web.facebook.com","m.facebook.com"].includes(location.hostname)) {
    return {page_id:pid,error:"Unexpected navigation; this tab is not a Facebook page",observed_url:location.href};
  }
  if(/\/(?:login|checkpoint|recover|two_factor|login.php)(?:[/?]|$)/i.test(location.pathname)) {
    return {page_id:pid,error:"Facebook login or security check is required in the selected profile",observed_url:location.href};
  }
  const candidates=[];
  const add=(value,source)=>{value=normName(value);if(value && value.length<=220)candidates.push({text:value,source});};
  for(const r of _strict_h1_candidates([...document.querySelectorAll('h1')]))add(r.text,'h1');
  const alts=_profile_alt_candidates([...document.querySelectorAll('img[alt]')]);
  for(const r of alts)add(r.text.replace(/(?:'s\s+)?profile\s+(?:picture|photo)$|\u7684\u5934\u50cf$|\u7684\u5927\u5934\u8d34$|\u5934\u50cf$/i,''),'avatar-alt');
  for(const r of _self_link_candidates([...document.querySelectorAll('a[href]')],pid))add(r.text,'self-link');
  for(const sel of ['meta[property="og:title"]','meta[name="twitter:title"]'])add(document.querySelector(sel)?.content,'metadata');
  add(document.title,'document-title');
  const lines=[];
  for(const el of [...document.querySelectorAll('a,span,div')].slice(0,7000)) {
    if(el.closest('nav,[role="navigation"],[role="banner"],[role="dialog"],[role="article"],article,[data-pagelet^="FeedUnit_"]'))continue;
    const r=el.getBoundingClientRect(),sty=getComputedStyle(el);
    if(r.width<2 || r.height<2 || r.top<0 || r.top>1600 || sty.display==='none' || sty.visibility==='hidden')continue;
    const t=clean(el.innerText);
    if(t.length>250 || !/followers?|\u7c89\u4e1d|\u8ffd\u8e64|\u8ffd\u8e2a|seguidores|pengikut|abonn/i.test(t))continue;
    lines.push(t);
  }
  const follower_text=[...new Set(lines)].slice(0,24).join('\n');
  if(lines.length)for(const r of _near_follower_candidates(document.body,lines[0]))add(r.text,'near-followers');
  for(const el of [...document.querySelectorAll('[role="heading"]')].slice(0,80)) {
    const r=el.getBoundingClientRect();
    if(r.width>2 && r.height>2 && r.top>=0 && r.top<1000 && !el.closest('nav,[role="navigation"],[role="dialog"],[role="article"],article')) add(el.innerText,'heading');
  }
  const name=candidates.map(r=>r.text).find(validName)||'';
  const avatars=_avatar_candidates(name).filter(r => r.score>=48 && /^https:\/\//.test(r.url)).slice(0,6);
  let posts=[];
  if(wantPosts)posts=_post_candidates({pid,name}).slice(0,64);
  return {page_id:pid, observed_url:location.href, name_candidates:candidates.slice(0,100),
    follower_text, avatar_candidates:avatars, post_candidates:posts, evidence_version:1};
}
if(typeof module!=="undefined")module.exports={extractPageDom};
