'use strict';
const $=id=>document.getElementById(id),base=location.pathname.replace(/\/$/,'')+'/api/';
let csrf=null,projection=null,pending=false,dirty=false,revision=0,deadline=0,needsPassword=null,saveTimer=null,review=false,blocked=false,loading=false,ready=false,unavailable=false;
const modern=document.body.dataset.view==='public';
function notice(text,error=false){$('notice').textContent=text;$('notice').dataset.error=String(error);}
function facts(){
  if(!$('access')||!projection)return;
  $('access').textContent=projection.permission==='edit'?'Editing allowed':'View only';
  $('expiry').textContent=projection.expires_at?'Expires '+new Date(projection.expires_at*1000).toLocaleString():'No expiration';
  $('editingHelp').textContent=projection.permission==='edit'?'Edit the Markdown directly. Changes save automatically. If the note changes elsewhere, review and merge your draft before saving.':'The sender has shared this note for reading.';
}
function accent(value){
  if(!/^#[0-9a-f]{6}$/i.test(value))return;
  document.documentElement.style.setProperty('--accent',value);
  const rgb=value.match(/[0-9a-f]{2}/gi).map(v=>parseInt(v,16));
  const luminance=c=>c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((v,x,i)=>v+x*[.2126,.7152,.0722][i],0);
  let weight=.48,mix;
  do{mix=rgb.map((v,i)=>Math.round(v*weight+[23,23,20][i]*(1-weight)));weight-=.02;}while((luminance([243,241,235])+.05)/(luminance(mix)+.05)<4.5&&weight>0);
  document.body.style.setProperty('--public-accent','rgb('+mix.join(',')+')');
}
function controls(){
  const active=Boolean(csrf&&projection)&&Date.now()<deadline&&!unavailable;
  if($('loading'))$('loading').hidden=ready;
  $('gate').hidden=active||(!ready&&modern);$('workspace').hidden=!active;
  $('unlock').disabled=pending||unavailable;
  $('unlock').textContent=pending?'Checking…':modern?'Continue':'Enter';
  $('passwordLabel').hidden=needsPassword!==true||unavailable;
  $('password').disabled=pending||unavailable;
  $('saveMerged').disabled=pending||!active||projection?.permission!=='edit';
  $('retry').disabled=pending||!active;
  for(const field of $('surface').querySelectorAll('textarea'))field.readOnly=!active||projection?.permission!=='edit';
  if(modern){
    $('gate').querySelector('h1').textContent=unavailable?'Link unavailable':needsPassword?'This link is protected':'Open shared note';
    $('gate').querySelector('.explanation').textContent=unavailable?'Ask the sender for a new link.':needsPassword?'Enter the password provided by the sender to open this note.':'Continue to open the note shared with you.';
  }
}
function failure(error){
  if(error.status===429)return 'Too many attempts. Wait 15 minutes before trying again.';
  if([404,410].includes(error.status))return 'This shared link is not available. Ask the sender for a new link.';
  if(!error.status)return 'Cannot reach Mastermind. Check your connection and try again.';
  return error.message;
}

async function api(path,options={}){const response=await fetch(base+path,{...options,credentials:'same-origin',redirect:'error',cache:'no-store',headers:{'Content-Type':'application/json',...(options.headers||{})}});const body=await response.json();if(!response.ok){const error=new Error(body.error?.message||'Request failed.');error.status=response.status;error.body=body;throw error;}return body;}
function resize(field){field.style.height='auto';field.style.height=Math.max(26,field.scrollHeight)+'px';}
function schedule(){clearTimeout(saveTimer);if(dirty&&!review&&!blocked&&csrf)saveTimer=setTimeout(save,900);}
function values(){const result=projection.segments.filter(part=>part.kind==='text').map(part=>part.value);for(const field of $('surface').querySelectorAll('textarea')){const index=Number(field.dataset.segment),value=field.dataset.prefix+field.value;result[index]=value.replace(/\r\n?/g,'\n')===result[index].replace(/\r\n?/g,'\n')?result[index]:value;}return result;}
function draw(){
  facts();$('title').textContent=projection.title;document.title=projection.title+' · Mastermind';const surface=$('surface');surface.replaceChildren();
  if(projection.permission!=='edit'){surface.innerHTML=projection.html;const heading=[...surface.children].find(el=>!el.classList.contains('protected'));if(heading?.tagName==='H1'&&heading.textContent===projection.title)heading.remove();if(!surface.textContent.trim()){const empty=document.createElement('p');empty.textContent='This note is empty.';surface.append(empty);}return;}
  let ordinal=0,seenText=false;
  for(const segment of projection.segments){if(segment.kind==='protected'){const label=document.createElement('p');label.className='protected';label.textContent=segment.label;surface.append(label);continue;}
    const index=ordinal++;if(index===0&&!segment.value&&projection.segments.length>1)continue;
    const field=document.createElement('textarea');field.className='note-field';field.dataset.segment=index;field.setAttribute('aria-label','Note text '+(index+1));field.spellcheck=true;
    const heading=!seenText?segment.value.match(/^(?:[ \t]*\r?\n)*# +([^\r\n]+)(?:\r?\n|$)(?:\r?\n)?/):null;const prefix=heading&&heading[1].trim()===projection.title?heading[0]:'';if(segment.value.trim())seenText=true;field.dataset.prefix=prefix;field.value=segment.value.slice(prefix.length);
    field.addEventListener('input',()=>{dirty=true;revision++;blocked=false;$('retry').hidden=true;resize(field);notice(review?'Review the current version and save the merged changes.':'Unsaved changes');schedule();});
    surface.append(field);resize(field);
  }
  requestAnimationFrame(()=>surface.querySelectorAll('textarea').forEach(resize));controls();
}
function retainDraft(draft){const group=document.createElement('div');for(const value of draft){if(!value)continue;const field=document.createElement('textarea');field.className='draft-field';field.readOnly=true;field.value=value;field.setAttribute('aria-label','Retained unsaved Markdown');group.append(field);}if(group.childElementCount)$('draft').append(group);}
function conflict(next,draft){clearTimeout(saveTimer);retainDraft(draft);projection=next;review=true;dirty=false;blocked=false;draw();$('conflict').hidden=false;$('retry').hidden=true;notice('The note changed elsewhere. The current version is above; your unsaved Markdown is retained below. Merge the changes, then choose Save merged changes.',true);}
async function lock(error){
  csrf=null;deadline=0;clearTimeout(saveTimer);ready=true;
  unavailable=[404,410].includes(error.status);$('gateError').textContent=failure(error);
  document.title='Shared note · Mastermind';
  try{const current=await policy();needsPassword=current.password_required;}catch{}
  controls();
}

async function save(force=false){
  clearTimeout(saveTimer);if(pending||!csrf||!projection||projection.permission!=='edit'||(!dirty&&!force)||(review&&!force))return;
  pending=true;controls();const sent=revision,draft=values();notice('Saving…');
  try{const next=await api('note',{method:'PUT',headers:{'X-CSRF-Token':csrf,'If-Match':'"'+projection.sha256+'"'},body:JSON.stringify({projection_id:projection.projection_id,values:draft})});
    projection=next;facts();dirty=revision!==sent;review=false;blocked=false;$('conflict').hidden=true;$('draft').replaceChildren();$('retry').hidden=true;notice(dirty?'Unsaved changes':'Changes saved.');
  }catch(error){
    if(error.status===409){try{const next=error.body.projection||await api('note');if(error.body.error?.code==='PROJECTION_EXPIRED'&&next.sha256===projection.sha256&&next.permission==='edit'){projection=next;dirty=true;blocked=false;}else conflict(next,values());}catch(failed){notice(failure(failed),true);blocked=true;$('retry').hidden=false;}}
    else{notice(failure(error),true);blocked=true;$('retry').hidden=false;if([401,403,404,410].includes(error.status))await lock(error);}
  }finally{pending=false;controls();if(dirty&&!review&&!blocked)schedule();}
}
async function open(){
  if(pending||unavailable)return;
  pending=true;controls();$('gateError').textContent='';$('password').removeAttribute('aria-invalid');
  const password=$('password').value;
  try{
    if(needsPassword===null){await policy();if(needsPassword)return;}
    const session=await api('session',{method:'POST',body:JSON.stringify({password})});
    csrf=session.csrf;deadline=session.expires_at*1000;
    const next=await api('note');
    if(projection&&(dirty||review)){if(next.sha256===projection.sha256&&!review&&next.permission==='edit'){projection=next;facts();schedule();}else conflict(next,values());}
    else{projection=next;draw();notice(projection.permission==='edit'?'Edits save automatically.':'');}
  }catch(error){
    csrf=null;unavailable=[404,410].includes(error.status);$('gateError').textContent=failure(error);if(error.status===401)$('password').setAttribute('aria-invalid','true');
  }finally{
    $('password').value='';pending=false;ready=true;controls();
    if(!csrf&&needsPassword&&!unavailable)$('password').focus();
    if(dirty&&!review)schedule();
  }
}

$('unlockForm').addEventListener('submit',event=>{event.preventDefault();open();});
$('saveMerged').onclick=()=>save(true);$('retry').onclick=()=>{blocked=false;save(true);};
window.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();save(true);}});
window.addEventListener('resize',()=>$('surface').querySelectorAll('textarea').forEach(resize));
window.addEventListener('beforeunload',event=>{if(dirty||review){event.preventDefault();event.returnValue='';}});
async function policy(){
  try{const current=await api('policy');needsPassword=current.password_required;accent(current.accent);$('reach').dataset.state='ok';$('reachText').textContent='Service reachable';return current;}
  catch(error){unavailable=[404,410].includes(error.status);$('reach').dataset.state='error';$('reachText').textContent=unavailable?'Link unavailable':'Service unreachable';throw error;}
}

async function refresh(){if(document.hidden||loading||pending)return;loading=true;try{
  await policy();
  if(csrf&&Date.now()>=deadline){if(needsPassword)await lock(Object.assign(new Error('Session expired. Enter the password again; your unsaved text is retained.'),{status:401}));else{csrf=null;await open();}return;}
  if(csrf&&!dirty&&!review){const started=revision;const next=await api('note');if(dirty||review||pending||started!==revision)return;const changed=next.sha256!==projection.sha256;projection=next;facts();if(changed){draw();notice('Updated from the Vault.');}}
}catch(error){notice(failure(error),true);if([401,403,404,410].includes(error.status))await lock(error);}finally{loading=false;controls();}}
setInterval(refresh,5000);
(async()=>{
  try{await policy();if(!needsPassword)await open();}
  catch(error){$('gateError').textContent=failure(error);}
  finally{ready=true;controls();if(needsPassword&&!unavailable)$('password').focus();}
})();
