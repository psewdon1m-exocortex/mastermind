"""Capability-scoped note editor; no owner APIs, browser persistence or resolver."""

STYLE = """*{box-sizing:border-box;scrollbar-width:none}*::-webkit-scrollbar{display:none;width:0;height:0}:root{--accent:#00a8ff}body{margin:0;background:#000;color:#fff;font:14px/1.6 Consolas,'Cascadia Mono',monospace}
header{min-height:123px;border-bottom:1px solid #ccc;padding:20px 30px;display:flex;align-items:center}h1{font:700 clamp(40px,4.2vw,80px)/1 'Space Grotesk','Segoe UI',sans-serif;color:var(--accent);margin:0;overflow-wrap:anywhere}h2{font-size:22px;color:var(--accent);margin:0 0 16px}
main{padding:20px 30px 60px}p{overflow-wrap:anywhere}button,input,textarea{font:inherit;color:inherit;background:#000;border:1px solid #ccc;border-radius:0}button,input{min-height:40px;padding:8px 12px}button{cursor:pointer}button:hover:enabled{background:#111;border-color:var(--accent)}:focus-visible{outline:1px solid var(--accent);outline-offset:3px}button:disabled{opacity:.45;cursor:default}button:active:enabled{transform:scale(.985)}
.gate{min-height:100dvh;display:grid;place-items:center;padding:24px}.gate-group{width:255px;max-width:100%}.gate-panel{border:1px solid #fff;padding:15px;display:grid;gap:10px}.gate-panel p{color:var(--accent);margin:0 0 10px}.gate-panel input{width:100%;min-width:0}.gate-panel button{color:var(--accent);border-color:var(--accent)}.gate-panel .error{color:#f83d3d;margin:0}.error:empty{display:none}.reach{margin-top:16px;border:1px solid #ccc;color:#ccc;padding:12px;display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:50px;font-size:13px}.reach i{display:inline-block;width:19px;height:19px;background:currentColor}.reach[data-state=ok]{color:#62ff8c;border-color:currentColor}.reach[data-state=error]{color:#f83d3d;border-color:currentColor}
#surface{overflow-wrap:anywhere;min-height:160px}#surface>h1:first-child{font-size:32px}.note-field{display:block;border:0;border-left:1px solid transparent;padding:0 6px;margin:0;width:100%;min-height:26px;resize:none;overflow:hidden;background:#000;line-height:1.6;outline:0;white-space:pre-wrap;tab-size:4}.note-field:focus{border-left-color:var(--accent)}.protected{border-left:1px solid #ccc;color:#ccc;padding:6px 12px;margin:8px 0;font-size:12px}pre{overflow:auto;white-space:pre-wrap}
#notice{color:#ccc;min-height:24px;font-size:12px;margin:8px 0 0}#notice[data-error=true]{color:#f83d3d}#conflict{border:1px solid #f83d3d;padding:20px;margin:24px 0}.draft-field{width:100%;min-height:100px;padding:12px;resize:vertical;margin-bottom:12px}.commands{display:flex;justify-content:flex-end;gap:12px;margin-top:16px}.commands button{border-color:var(--accent);color:var(--accent)}#retry{margin-top:16px}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}[hidden]{display:none!important}
@media(max-width:720px){header{padding:20px;min-height:96px}main{padding:16px 20px 40px}h1{font-size:40px}#conflict{padding:14px}}@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""

SCRIPT = r"""
'use strict';
const $=id=>document.getElementById(id),base=location.pathname.replace(/\/$/,'')+'/api/';
let csrf=null,projection=null,pending=false,dirty=false,revision=0,deadline=0,needsPassword=false,saveTimer=null,review=false,blocked=false,loading=false;
function notice(text,error=false){$('notice').textContent=text;$('notice').dataset.error=String(error);}
function controls(){const active=Boolean(csrf)&&Date.now()<deadline;$('gate').hidden=active;$('workspace').hidden=!active;$('unlock').disabled=pending;$('saveMerged').disabled=pending||!active||projection?.permission!=='edit';$('retry').disabled=pending||!active;for(const field of $('surface').querySelectorAll('textarea'))field.readOnly=!active||projection?.permission!=='edit';}
async function api(path,options={}){const response=await fetch(base+path,{...options,credentials:'same-origin',redirect:'error',cache:'no-store',headers:{'Content-Type':'application/json',...(options.headers||{})}});const body=await response.json();if(!response.ok){const error=new Error(body.error?.message||'Request failed.');error.status=response.status;error.body=body;throw error;}return body;}
function resize(field){field.style.height='auto';field.style.height=Math.max(26,field.scrollHeight)+'px';}
function schedule(){clearTimeout(saveTimer);if(dirty&&!review&&!blocked&&csrf)saveTimer=setTimeout(save,900);}
function values(){const result=projection.segments.filter(part=>part.kind==='text').map(part=>part.value);for(const field of $('surface').querySelectorAll('textarea')){const index=Number(field.dataset.segment),value=field.dataset.prefix+field.value;result[index]=value.replace(/\r\n?/g,'\n')===result[index].replace(/\r\n?/g,'\n')?result[index]:value;}return result;}
function draw(){
  $('title').textContent=projection.title;document.title=projection.title+' · Mastermind';const surface=$('surface');surface.replaceChildren();
  if(projection.permission!=='edit'){surface.innerHTML=projection.html;const heading=surface.firstElementChild;if(heading?.tagName==='H1'&&heading.textContent===projection.title)heading.remove();return;}
  let ordinal=0;
  for(const segment of projection.segments){if(segment.kind==='protected'){const label=document.createElement('p');label.className='protected';label.textContent=segment.label;surface.append(label);continue;}
    const index=ordinal++,field=document.createElement('textarea');field.className='note-field';field.dataset.segment=index;field.setAttribute('aria-label','Note text '+(index+1));field.spellcheck=true;
    const heading=index===0?segment.value.match(/^# +([^\r\n]+)(?:\r?\n|$)(?:\r?\n)?/):null;const prefix=heading&&heading[1].trim()===projection.title?heading[0]:'';field.dataset.prefix=prefix;field.value=segment.value.slice(prefix.length);
    field.addEventListener('input',()=>{dirty=true;revision++;blocked=false;$('retry').hidden=true;resize(field);notice(review?'Review the current version and save the merged changes.':'Unsaved changes');schedule();});
    field.addEventListener('keydown',event=>{if(event.key==='Tab'){event.preventDefault();field.setRangeText('  ',field.selectionStart,field.selectionEnd,'end');field.dispatchEvent(new Event('input'));}});
    surface.append(field);resize(field);
  }
  requestAnimationFrame(()=>surface.querySelectorAll('textarea').forEach(resize));controls();
}
function retainDraft(draft){const group=document.createElement('div');for(const value of draft){if(!value)continue;const field=document.createElement('textarea');field.className='draft-field';field.readOnly=true;field.value=value;field.setAttribute('aria-label','Retained unsaved Markdown');group.append(field);}if(group.childElementCount)$('draft').append(group);}
function conflict(next,draft){clearTimeout(saveTimer);retainDraft(draft);projection=next;review=true;dirty=false;blocked=false;draw();$('conflict').hidden=false;$('retry').hidden=true;notice('The note changed elsewhere. The current version is above; your unsaved Markdown is retained below. Merge the changes, then choose Save merged changes.',true);}
async function lock(error){csrf=null;deadline=0;clearTimeout(saveTimer);$('gateError').textContent=error.message;try{const policy=await api('policy');needsPassword=policy.password_required;$('passwordLabel').hidden=!needsPassword;}catch{}controls();}
async function save(force=false){
  clearTimeout(saveTimer);if(pending||!csrf||!projection||projection.permission!=='edit'||(!dirty&&!force)||(review&&!force))return;
  pending=true;controls();const sent=revision,draft=values();notice('Saving…');
  try{const next=await api('note',{method:'PUT',headers:{'X-CSRF-Token':csrf,'If-Match':'"'+projection.sha256+'"'},body:JSON.stringify({projection_id:projection.projection_id,values:draft})});
    projection=next;dirty=revision!==sent;review=false;blocked=false;$('conflict').hidden=true;$('draft').replaceChildren();$('retry').hidden=true;notice(dirty?'Unsaved changes':'Changes saved.');
  }catch(error){
    if(error.status===409){try{const next=error.body.projection||await api('note');if(error.body.error?.code==='PROJECTION_EXPIRED'&&next.sha256===projection.sha256&&next.permission==='edit'){projection=next;dirty=true;blocked=false;}else conflict(next,values());}catch(failure){notice(failure.message,true);blocked=true;$('retry').hidden=false;}}
    else{notice(error.message,true);blocked=true;$('retry').hidden=false;if([401,403,404,410].includes(error.status))await lock(error);}
  }finally{pending=false;controls();if(dirty&&!review&&!blocked)schedule();}
}
async function open(){
  if(pending)return;pending=true;controls();$('gateError').textContent='';
  try{const session=await api('session',{method:'POST',body:JSON.stringify({password:$('password').value})});$('password').value='';csrf=session.csrf;deadline=session.expires_at*1000;const next=await api('note');
    if(projection&&(dirty||review)){if(next.sha256===projection.sha256&&!review&&next.permission==='edit'){projection=next;schedule();}else conflict(next,values());}
    else{projection=next;draw();notice(projection.permission==='edit'?'Edits save automatically.':'');}
  }catch(error){$('gateError').textContent=error.message;csrf=null;$('password').focus();}
  finally{pending=false;controls();if(dirty&&!review)schedule();}
}
$('unlockForm').addEventListener('submit',event=>{event.preventDefault();open();});
$('saveMerged').onclick=()=>save(true);$('retry').onclick=()=>{blocked=false;save(true);};
window.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();save(true);}});
window.addEventListener('resize',()=>$('surface').querySelectorAll('textarea').forEach(resize));
window.addEventListener('beforeunload',event=>{if(dirty||review){event.preventDefault();event.returnValue='';}});
async function policy(){try{const current=await api('policy');needsPassword=current.password_required;document.documentElement.style.setProperty('--accent',current.accent);$('reach').dataset.state='ok';$('reachText').textContent='Service reachable';return current;}catch(error){$('reach').dataset.state='error';$('reachText').textContent=error.status===404?'Link unavailable':'Service unreachable';throw error;}}
async function refresh(){if(document.hidden||loading||pending)return;loading=true;try{
  await policy();
  if(csrf&&Date.now()>=deadline){if(needsPassword)await lock(new Error('Session expired. Enter the password again; your unsaved text is retained.'));else{csrf=null;await open();}return;}
  if(csrf&&!dirty&&!review){const started=revision;const next=await api('note');if(dirty||review||pending||started!==revision)return;const changed=next.sha256!==projection.sha256;projection=next;if(changed){draw();notice('Updated from the Vault.');}}
}catch(error){notice(error.message,true);if(csrf&&[401,403,404,410].includes(error.status))await lock(error);}finally{loading=false;}}
setInterval(refresh,5000);
(async()=>{try{await policy();$('passwordLabel').hidden=!needsPassword;if(needsPassword)$('password').focus();else await open();}catch(error){$('gateError').textContent=error.message;$('unlock').disabled=true;}})();
"""


def page_html(nonce, accent="#00A8FF", token=""):
    style = ('@font-face{font-family:"Space Grotesk";font-weight:700;font-display:swap;'
             'src:url("/s/' + token + '/font.woff2") format("woff2")}\n' + STYLE).replace("#00a8ff", accent)
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Shared note · Mastermind</title><style nonce="' + nonce + '">' + style + '</style>'
            '<div class="gate" id="gate"><div class="gate-group"><form id="unlockForm" class="gate-panel">'
            '<p>Please enter<br>shared link password:</p><label id="passwordLabel"><span class="sr-only">Share password</span>'
            '<input id="password" type="password" autocomplete="current-password" placeholder="Password…"></label>'
            '<button id="unlock">Enter</button><p class="error" id="gateError" role="alert"></p></form>'
            '<div class="reach" id="reach" role="status"><span id="reachText">Checking service</span><i aria-hidden="true"></i></div></div></div>'
            '<div id="workspace" hidden><header><h1 id="title"></h1></header><main>'
            '<article id="surface" aria-label="Shared note"></article><p id="notice" role="status" aria-live="polite"></p>'
            '<button id="retry" hidden>Retry save</button><section id="conflict" hidden><h2>Unsaved Markdown</h2>'
            '<p>The editor above contains the current note. Your previous draft is retained here. Copy the changes you want to keep into the editor, then save the merged version.</p>'
            '<div id="draft"></div><div class="commands"><button id="saveMerged">Save merged changes</button></div></section></main></div>'
            '<script nonce="' + nonce + '">' + SCRIPT + '</script></html>')
