import {state,$,$$,api,escape,card,poll,search,wireSearch,bind,pending,dialog,notice,stamp,humanBytes} from './ui.js';
let publicSession=null,ownerAccess=null,ownerEpoch=0;const tickets=new Map();
export function clearCrusher(){publicSession=null;ownerAccess=null;ownerEpoch++;tickets.clear();}
export function wireCrusherAccess(root){
  const button=$('[data-access]',root),value=$('[data-access-value]',root),detail=$('[data-access-detail]',root),epoch=ownerEpoch;
  let busy=false,feedback='';
  function render(){
    if(!root.isConnected)return;
    if(ownerAccess&&ownerAccess.expires_at*1000<=Date.now()){ownerAccess=null;feedback='Code expired · create a new one';}
    button.disabled=busy;root.classList.toggle('is-pending',busy);
    if(busy)button.setAttribute('aria-busy','true');else button.removeAttribute('aria-busy');
    button.setAttribute('aria-label',ownerAccess?'Copy Crusher access code':'Create and copy Crusher access code');
    value.textContent=ownerAccess?.code||(busy?'Creating…':'Create & copy');
    detail.textContent=ownerAccess?(ownerAccess.feedback||'Click to copy')+' · expires '+new Date(ownerAccess.expires_at*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):feedback||'Create a temporary upload code';
  }
  button.onclick=async event=>{
    if(busy)return;
    render();const creating=!ownerAccess;busy=true;feedback='';render();
    const result=(creating?api('/api/v1/crusher/access',{method:'POST',body:{}}):Promise.resolve(ownerAccess)).then(record=>{
      if(epoch!==ownerEpoch)throw new DOMException('Session ended','AbortError');
      ownerAccess=record;return record;
    });
    let copying=null;
    // The owner's explicit "Create & copy" action starts the clipboard write
    // synchronously. Promise-backed data preserves that activation while the API runs.
    // Restricted browsers retain the complete code and offer a fresh Copy action.
    if(event.isTrusted&&window.isSecureContext&&document.hasFocus()&&navigator.clipboard){
      try{
        if(creating&&navigator.clipboard.write&&typeof ClipboardItem!=='undefined'){
          copying=navigator.clipboard.write([new ClipboardItem({'text/plain':result.then(record=>new Blob([record.code],{type:'text/plain'}))})]);
        }else if(!creating&&navigator.clipboard.writeText){copying=navigator.clipboard.writeText(ownerAccess.code);}
      }catch{copying=Promise.reject(new Error('Clipboard unavailable'));}
    }
    // Attach the rejection handler before waiting for the generation request.
    const copied=copying?.then(()=>true,()=>false);
    try{
      await result;const success=copied?await copied:false;
      if(epoch!==ownerEpoch)return;
      ownerAccess.feedback=success?'Copied':copying?'Copy failed · select code':creating&&navigator.clipboard?.writeText?'Click to copy':'Select code to copy';
      notice(success?(creating?'Crusher access code created and copied to the clipboard.':'Crusher access code copied to the clipboard.'):'Code is ready. Clipboard unavailable: select and copy the code.',!success);
    }catch(error){if(error.name!=='AbortError'){feedback='Could not create code · retry';notice(error.message,true);}}
    finally{busy=false;if(epoch===ownerEpoch){render();if(root.isConnected)button.focus({preventScroll:true});}}
  };
  const timer=setInterval(()=>{if(!busy&&ownerAccess&&ownerAccess.expires_at*1000<=Date.now())render();},1000);
  render();return()=>clearInterval(timer);
}
export function hashFile(file,onProgress=()=>{},signal=state.viewController?.signal){return new Promise((resolve,reject)=>{if(signal?.aborted){reject(new DOMException('Cancelled','AbortError'));return;}const worker=new Worker('/assets/hash-worker.js',{type:'module'});function finish(error,digest){worker.terminate();signal?.removeEventListener('abort',abort);if(error)reject(error);else resolve(digest);}function abort(){finish(new DOMException('Cancelled','AbortError'));}signal?.addEventListener('abort',abort,{once:true});worker.onmessage=e=>{if(e.data.sha256)finish(null,e.data.sha256);else if(e.data.error)finish(Error(e.data.error));else onProgress(e.data.progress);};worker.onerror=()=>finish(Error('File hashing failed.'));worker.postMessage(file);});}

export async function resourcePicker(select){const modal=dialog('Select Saturn source',`<div class="toolbar"><button data-parent>Parent folder</button><span data-path class="collection-info">root</span></div><div class="list" data-files></div><button data-more hidden>Next page</button>`,{dirtyGuard:false});let current='root',cursor=null;
  async function load(path,next=null){const result=await api('/api/owner/resources?'+new URLSearchParams({path,limit:'100',...(next?{cursor:next}:{})}));if(!modal.element.isConnected)return;current=path;cursor=result.next_cursor;$('[data-path]',modal.element).textContent=path;$('[data-parent]',modal.element).disabled=path==='root';$('[data-more]',modal.element).hidden=!cursor;$('[data-files]',modal.element).innerHTML=result.entries.length?result.entries.map(item=>`<div class="list-row"><span>${escape(item.path.split('/').at(-1))}</span><small>${item.type==='folder'?'Folder':escape(humanBytes(item.size_bytes))}</small><button data-file="${escape(item.path)}" data-kind="${item.type}">${item.type==='folder'?'Open folder':'Select file'}</button></div>`).join(''):'<p class="empty">This folder is empty.</p>';}
  bind(modal.element,'click','[data-file]',async(e,b)=>{if(b.dataset.kind==='folder')await load(b.dataset.file);else{select(b.dataset.file);modal.close(true);}});bind(modal.element,'click','[data-parent]',()=>load(current.split('/').slice(0,-1).join('/')||'root'));bind(modal.element,'click','[data-more]',()=>load(current,cursor));try{await load('root');}catch(error){modal.error.textContent=error.message;}}

const reachability='<div class="crusher-reach" role="status"><span>Checking service</span><i class="status-square" aria-hidden="true"></i></div>';
function watchReachability(root){return poll(async()=>{const node=$('.crusher-reach',root);try{const response=await fetch('/healthz',{cache:'no-store',signal:state.viewController?.signal});if(!response.ok)throw Error();node.className='crusher-reach success';$('span',node).textContent='Service reachable';}catch(error){if(error.name==='AbortError')return;node.className='crusher-reach danger';$('span',node).textContent='Service unreachable';}},10000);}
export function sourceFromUrl(value){
  const url=new URL(value);if(!['https:','http:'].includes(url.protocol)||url.username||url.password)throw Error('Enter a public HTTP or HTTPS link.');
  const host=url.hostname.toLowerCase().replace(/^www\./,''),parts=url.pathname.split('/').filter(Boolean);
  const type=['youtube.com','m.youtube.com','youtu.be'].includes(host)?'youtube':/\.git\/?$/.test(url.pathname)||(['github.com','gitlab.com','bitbucket.org'].includes(host)&&parts.length===2)?'git':'url';
  return {type,url:url.href};
}
export async function crusher(root,{publicOnly=false}={}){
  const authHeaders=()=>publicOnly&&publicSession?{Authorization:'Bearer '+publicSession.token}:{};
  const request=(route,options={})=>api('/api/v1/crusher'+route,{...options,headers:{...authHeaders(),...options.headers},allow401:publicOnly});
  if(publicOnly&&!publicSession){
    root.innerHTML=`<div class="crusher-gate"><div class="gate-group"><form class="gate-panel"><p>Please enter<br>Crusher access code:</p><label class="sr-only" for="crusher-code">Crusher access code</label><input id="crusher-code" name="code" placeholder="Code…" autocomplete="one-time-code" inputmode="numeric" required><button type="submit">Enter</button><p class="error-message" role="alert"></p></form>${reachability}</div></div>`;
    const form=$('form',root),input=$('input',form);requestAnimationFrame(()=>input.focus());
    form.onsubmit=async event=>{event.preventDefault();await pending($('button',form),async()=>{try{publicSession=await request('/sessions',{method:'POST',body:{code:input.value}});document.dispatchEvent(new Event('crusher-activated'));}catch(error){$('.error-message',form).textContent=error.message;input.focus();}});};
    return watchReachability(root);
  }
  root.innerHTML=`<div class="crusher-workspace">${publicOnly?'<h1>mastermind crusher</h1>':''}<div class="crusher-columns"><section class="crusher-drop-panel"><div class="crusher-intro"><p class="accent">Submit sources</p><p>Add links or files to turn into notes. This page shows processing progress; completed notes appear in the owner's Vault.</p></div><div class="crusher-access-status"><div class="crusher-session" role="status"><span>${publicOnly?'Access code status':'Owner access'}</span><span data-remaining></span></div>${reachability}</div><form class="crusher-links"><label for="crusher-links">Source links</label><textarea id="crusher-links" name="links" rows="2" placeholder="Paste links here, one per line" spellcheck="false" required></textarea><button type="submit">Submit links</button></form><label class="crusher-dropzone" tabindex="0" role="button" aria-label="Choose source files"><strong>DRAG AND DROP FILES HERE</strong><span>or choose files · up to 2 GiB each</span><input class="sr-only" type="file" multiple tabindex="-1" aria-label="Source files"></label><p data-submit-status role="status"></p><p class="error-message" role="alert"></p></section><section class="crusher-submissions" aria-label="Processing history"><div class="toolbar" role="toolbar" aria-label="Submission filters">${search('Search submissions')}<div class="collection-info" data-count></div><button data-previous disabled>Previous</button><button data-next disabled>Next</button></div><div class="list" data-jobs></div></section></div></div>`;
  let records=[],query='',offset=0,busy=false,expired=false;const receipts=new Map(),form=$('.crusher-links',root),fileInput=$('input[type=file]',root),zone=$('.crusher-dropzone',root);
  const uploadKeys=new WeakMap(),urlKeys=new Map();
  const live=()=>!publicOnly||Boolean(publicSession&&publicSession.expires_at*1000>Date.now());
  function controls(){expired=!live();$('button[type=submit]',form).disabled=busy||expired;fileInput.disabled=busy||expired;zone.setAttribute('aria-disabled',String(busy||expired));zone.classList.toggle('is-pending',busy);}
  function timer(){const seconds=publicOnly?Math.max(0,Math.ceil((publicSession.expires_at*1000-Date.now())/1000)):null;$('[data-remaining]',root).textContent=seconds==null?'Active':`${Math.floor(seconds/60).toString().padStart(2,'0')}:${(seconds%60).toString().padStart(2,'0')}`;controls();if(expired)$('[data-submit-status]',root).textContent='Submission access expired. Existing receipts remain available in this tab.';}
  function render(){const needle=query.trim().toLocaleLowerCase('en-US'),visible=records.filter(job=>[job.source_label,job.state,job.stage,job.job_id].join(' ').toLocaleLowerCase('en-US').includes(needle));$('[data-count]',root).textContent=`${visible.length} of ${records.length} on page ${offset/100+1}`;
    $('[data-jobs]',root).innerHTML=visible.length?visible.map(job=>`<section class="job"><div class="job-head"><strong>${escape(job.source_label)}</strong><span>${escape(job.state)} · ${job.progress_percent}%</span></div><p>${escape(job.stage.replaceAll('_',' '))}</p><div class="progress" role="progressbar" aria-label="Processing ${escape(job.source_label)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${job.progress_percent}"><span style="width:${job.progress_percent}%"></span></div><small>Submitted ${escape(stamp(job.created_at))}</small>${job.error?'<p class="danger">'+escape(job.error.message||job.error.code)+'</p>':''}</section>`).join(''):'<p class="empty">No submissions on this page.</p>';
    $('[data-previous]',root).disabled=!offset;$('[data-next]',root).disabled=records.length<100;}
  async function refresh(){try{records=await request('/jobs?limit=100&offset='+offset);}catch(error){if(!publicOnly||error.status!==401)throw error;records=await Promise.all([...tickets].slice(-100).map(([id,ticket])=>request('/jobs/'+id,{headers:{'X-Crusher-Status-Ticket':ticket}})));}if(root.isConnected)render();}
  async function accept(source,key){const result=await request('/jobs',{method:'POST',body:source,headers:{'Idempotency-Key':key}});tickets.set(result.job_id,result.status_ticket);while(tickets.size>100)tickets.delete(tickets.keys().next().value);receipts.set(key,result);await refresh();}
  async function execute(items,action){if(busy||!live())return;if(items.length>20){notice('Submit up to 20 sources at a time.',true);return;}busy=true;controls();const error=$('.error-message',root),status=$('[data-submit-status]',root);error.textContent='';let accepted=0;try{for(const item of items){await action(item,status);accepted++;}status.textContent=`${accepted} source${accepted===1?'':'s'} accepted.`;notice(status.textContent);}catch(failure){if(failure.name!=='AbortError'){error.textContent=failure.message;status.textContent=accepted?`${accepted} sources accepted before the error.`:'';notice(failure.message,true);}}finally{busy=false;controls();fileInput.value='';}}
  form.onsubmit=event=>{event.preventDefault();let sources;try{sources=form.elements.links.value.split(/\r?\n/).map(value=>value.trim()).filter(Boolean).map(sourceFromUrl);}catch{notice('Enter valid public links, one per line.',true);return;}execute(sources,async(source,status)=>{status.textContent='Accepting link…';let key=urlKeys.get(source.url);if(!key){key=crypto.randomUUID();urlKeys.set(source.url,key);}await accept(source,key);urlKeys.delete(source.url);form.elements.links.value=form.elements.links.value.split(/\r?\n/).filter(value=>{try{return new URL(value.trim()).href!==source.url;}catch{return Boolean(value.trim());}}).join('\n');});};
  async function files(values){await execute(values,async(file,status)=>{if(file.size>2*1024**3)throw Error('The source file exceeds 2 GiB.');let record=uploadKeys.get(file);if(!record){status.textContent='Checking '+file.name+'…';const sha=await hashFile(file,p=>status.textContent=`Checking ${file.name} · ${Math.round(p*100)}%`);const upload=await request('/uploads',{method:'POST',body:{name:file.name,size:file.size}});status.textContent='Uploading '+file.name+'…';const response=await fetch('/api/v1/crusher/uploads/'+upload.upload_id+'/content',{method:'PUT',body:file,signal:state.viewController?.signal,credentials:'same-origin',headers:{...authHeaders(),...(state.session?{'X-CSRF-Token':state.session.csrf}:{})}});const received=await response.json();if(!response.ok)throw Error(received.error?.message||'Upload failed.');if(received.sha256!==sha)throw Error('Uploaded file integrity check failed.');await request('/uploads/'+upload.upload_id+'/complete',{method:'POST',body:{sha256:sha}});record={source:{type:'upload',upload_id:upload.upload_id},key:crypto.randomUUID()};uploadKeys.set(file,record);}if(!receipts.has(record.key))await accept(record.source,record.key);});}
  fileInput.onchange=()=>files([...fileInput.files]);zone.onkeydown=event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();if(!busy&&live())fileInput.click();}};
  const overlay=document.createElement('div');overlay.className='file-drag-overlay';overlay.hidden=true;overlay.innerHTML='<strong>UPLOAD HERE</strong><span>Mastermind Crusher</span>';document.body.append(overlay);let depth=0;
  const hasFiles=event=>[...event.dataTransfer?.types||[]].includes('Files');const hide=()=>{depth=0;overlay.hidden=true;};
  const enter=event=>{if(!hasFiles(event))return;event.preventDefault();depth++;if(!busy&&live())overlay.hidden=false;};
  const over=event=>{if(!hasFiles(event))return;event.preventDefault();event.dataTransfer.dropEffect=busy||!live()?'none':'copy';};
  const leave=event=>{if(!hasFiles(event))return;if(--depth<=0)hide();};
  const drop=event=>{if(!hasFiles(event))return;event.preventDefault();hide();files([...event.dataTransfer.files]);};
  const escapeDrop=event=>{if(event.key==='Escape')hide();};
  document.addEventListener('dragenter',enter);document.addEventListener('dragover',over);document.addEventListener('dragleave',leave);document.addEventListener('drop',drop);document.addEventListener('keydown',escapeDrop);window.addEventListener('blur',hide);
  wireSearch($('.search-box',root),value=>{query=value;render();});bind(root,'click','[data-previous]',async()=>{offset=Math.max(0,offset-100);await refresh();});bind(root,'click','[data-next]',async()=>{offset+=100;await refresh();});
  const clock=setInterval(timer,1000),stopReach=watchReachability(root),stopJobs=poll(refresh,3000);timer();
  return()=>{clearInterval(clock);stopReach();stopJobs();overlay.remove();document.removeEventListener('dragenter',enter);document.removeEventListener('dragover',over);document.removeEventListener('dragleave',leave);document.removeEventListener('drop',drop);document.removeEventListener('keydown',escapeDrop);window.removeEventListener('blur',hide);};
}
