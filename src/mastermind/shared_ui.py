"""Public browser application: no persistence, links, resource APIs or owner scope."""

STYLE = """*{box-sizing:border-box}body{margin:0;background:#000;color:#fff;font:14px/1.6 Consolas,'Cascadia Mono',monospace}
header{min-height:123px;border-bottom:1px solid #fff;padding:20px 30px;display:flex;align-items:center}
h1{font:700 clamp(48px,4.2vw,80px)/1 'Space Grotesk','Segoe UI',sans-serif;color:#00a8ff;margin:0}
main{max-width:1180px;padding:30px;margin:auto}h2{font-size:24px;color:#00a8ff;margin:0 0 20px}
p{overflow-wrap:anywhere}button,input,textarea{font:inherit;color:inherit;background:#000;border:1px solid #ccc;border-radius:0}
button,input{min-height:40px;padding:8px 12px}button{cursor:pointer}button:hover{background:#111;border-color:#00a8ff}
:focus-visible{outline:1px solid #00a8ff;outline-offset:3px;background:#111}button:active{transform:scale(.985)}
button:disabled{opacity:.45;cursor:default;transform:none}textarea{width:100%;min-height:140px;resize:vertical;padding:10px}
label{display:block;margin:10px 0}.commands{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}
.protected{border-left:1px solid #ccc;color:#ccc;padding:10px;margin:10px 0}#notice{min-height:48px;color:#ccc;white-space:pre-wrap}
#notice[data-error=true]{color:#f83d3d}article{border:1px solid #fff;padding:30px;overflow-wrap:anywhere}
pre{overflow:auto;white-space:pre-wrap}#conflict{border:1px solid #f83d3d;padding:20px;margin:20px 0}
[hidden]{display:none!important}@media(max-width:720px){header{padding:20px}main{padding:20px}article{padding:20px}}
"""

SCRIPT = r"""
'use strict';
const $=id=>document.getElementById(id), base=location.pathname.replace(/\/$/,'')+'/api/';
let csrf=null, projection=null, editing=false, pending=false, dirty=false, deadline=0;
function notice(text,error=false){$('notice').textContent=text;$('notice').dataset.error=String(error)}
function controls(){const active=Boolean(csrf)&&Date.now()<deadline;
 $('save').disabled=pending||!active;$('edit').disabled=pending||!active;
 $('unlock').disabled=pending;$('save').hidden=!editing;$('edit').hidden=!projection||projection.permission!=='edit';
 $('unlockForm').hidden=active;}
async function api(path,options={}){const response=await fetch(base+path,{...options,credentials:'same-origin',redirect:'error',cache:'no-store',headers:{'Content-Type':'application/json',...(options.headers||{})}});
 const body=await response.json();if(!response.ok){const e=new Error(body.error?.message||'Request failed.');e.status=response.status;e.body=body;throw e;}return body;}
function draw(){const surface=$('surface');surface.replaceChildren();if(!projection)return;
 if(!editing){surface.innerHTML=projection.html;return;}
 let ordinal=0;const total=projection.segments.filter(part=>part.kind==='text').length;
 for(const segment of projection.segments){if(segment.kind==='protected'){const p=document.createElement('p');p.className='protected';p.textContent=segment.label;surface.append(p);}
 else{const index=ordinal++;if(segment.value===''&&index<total-1)continue;
 const label=document.createElement('label');label.textContent='Text segment '+ordinal;const field=document.createElement('textarea');field.value=segment.value;field.dataset.segment=String(index);field.spellcheck=true;
 field.addEventListener('input',()=>{dirty=true});label.append(field);surface.append(label);}}
}
function values(){const result=projection.segments.filter(part=>part.kind==='text').map(part=>part.value);
 for(const field of $('surface').querySelectorAll('textarea'))result[Number(field.dataset.segment)]=field.value;return result;}
function conflict(next,draft,message){const panel=$('draft');panel.replaceChildren();draft.forEach((value,i)=>{if(!value)return;
 const label=document.createElement('label');label.textContent='Unsaved segment '+(i+1);const field=document.createElement('textarea');field.readOnly=true;field.value=value;label.append(field);panel.append(label);});
 $('conflict').hidden=false;projection=next;editing=next.permission==='edit';draw();dirty=true;notice(message,true);}
async function run(action){if(pending)return;pending=true;controls();try{await action()}catch(e){notice(e.message,true);
 if([401,403,404,410].includes(e.status)){csrf=null;deadline=0;}}finally{pending=false;controls()}}
$('unlockForm').addEventListener('submit',event=>{event.preventDefault();run(async()=>{
 const result=await api('session',{method:'POST',body:JSON.stringify({password:$('password').value})});$('password').value='';csrf=result.csrf;deadline=result.expires_at*1000;
 if(!dirty){projection=await api('note');draw();notice('Shared note. Hidden content cannot be opened or changed.');}
 else conflict(await api('note'),values(),'Access renewed. Compare your retained unsaved text with the current note, then save your changes.');controls();});});
$('edit').addEventListener('click',()=>{if(editing&&dirty){notice('Save your changes before leaving the editor.');return;}
 editing=!editing;$('edit').textContent=editing?'View':'Edit';draw();controls();});
$('save').addEventListener('click',()=>run(async()=>{const draft=values();try{
 projection=await api('note',{method:'PUT',headers:{'X-CSRF-Token':csrf,'If-Match':'"'+projection.sha256+'"'},body:JSON.stringify({projection_id:projection.projection_id,values:draft})});
 dirty=false;draw();$('conflict').hidden=true;notice('Changes saved.');
 }catch(e){if(e.status===409&&e.body.projection){conflict(e.body.projection,draft,'The note changed. Your unsaved text is retained below. Copy the changes you want into the current note, then save.');return;}throw e;}}));
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue=''}});
setInterval(()=>{if(csrf&&Date.now()>=deadline){csrf=null;notice('Share session expired. Unlock again; your unsaved text is still present.',true);controls();}},1000);
run(async()=>{const policy=await api('policy');$('passwordLabel').hidden=!policy.password_required;if(policy.password_required){$('password').focus();notice('Enter the password to open this note.');}
 else{const result=await api('session',{method:'POST',body:'{}'});csrf=result.csrf;deadline=result.expires_at*1000;projection=await api('note');draw();notice('Shared note. Hidden content cannot be opened or changed.');}});
"""


def page_html(nonce, accent="#00A8FF", token=""):
    style = ('@font-face{font-family:"Space Grotesk";font-weight:700;font-display:swap;'
             'src:url("/s/' + token + '/font.woff2") format("woff2")}\n' + STYLE).replace("#00a8ff", accent)
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Shared note · Mastermind</title><style nonce="' + nonce + '">' + style + '</style>'
            '<header><h1>Shared note</h1></header><main><form id="unlockForm"><label id="passwordLabel">Share password'
            '<input id="password" type="password" autocomplete="current-password"></label><button id="unlock">Unlock</button></form>'
            '<p id="notice" role="status" aria-live="polite"></p><div class="commands"><button id="edit" hidden>Edit</button>'
            '<button id="save" hidden>Save changes</button></div><article id="surface" aria-label="Shared note"></article>'
            '<section id="conflict" hidden><h2>Unsaved text</h2><p>Compare this text with the current note above. '
            'Select and copy the changes you want to keep.</p><div id="draft"></div></section></main>'
            '<script nonce="' + nonce + '">' + SCRIPT + '</script></html>')
