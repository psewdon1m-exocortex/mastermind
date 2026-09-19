import { mountBackupPolicy } from './backup-policy.js';
import { mountServiceLogs } from './service-logs.js';
import { openAgentInitialization } from './agent-initialize.js';
import {state,$,$$,api,escape,card,reorder,poll,humanBytes,stamp,bind,pending,dialog,confirmation,notice,preferences,download,opaqueInput} from './ui.js';
import {hashFile} from './crusher.js';
import {wyvernCard,helperUpdates} from './wyvern.js';
import {openGroupUpdates} from './group-updates.js';
import {contextIndexingCard} from './context-indexing.js';

export async function startOperation(kind,file=null,resume=null){
  let identifier=resume,stop=()=>{},finished=false;
  const controller=new AbortController(),viewSignal=state.viewController?.signal;
  const abort=()=>controller.abort();viewSignal?.addEventListener('abort',abort,{once:true});
  const modal=dialog(kind==='restore'?'Restore snapshot':kind==='portable'?'Download Vault copy':kind==='logs'?'Download archived logs':'Create and download snapshot',
    '<p data-stage>Preparing…</p><div class="progress" role="progressbar" aria-label="Maintenance progress" aria-valuemin="0" aria-valuemax="100"><span></span></div><div data-details></div>',
    {dirtyGuard:false,onClose:()=>{stop();abort();viewSignal?.removeEventListener('abort',abort);}});
  const request=(route,options={})=>api(route,{...options,signal:controller.signal});
  const route=()=>'/api/owner/operations/'+identifier;
  function stage(text){if(modal.element.isConnected)$('[data-stage]',modal.element).textContent=text;}
  function render(record){if(!modal.element.isConnected)return;stage(record.stage.replaceAll('_',' '));$('.progress span',modal.element).style.width=record.progress+'%';$('.progress',modal.element).setAttribute('aria-valuenow',record.progress);}
  async function inspect(record){await request(route()+'/confirm',{method:'POST',body:{action:'inspect',sha256:record.sha256}});stop=poll(check,1000);}
  async function check(){
    if(!modal.element.isConnected){stop();return;}
    try{
      const record=await request(route(),{allow401:true});render(record);if(!modal.element.isConnected)return;const details=$('[data-details]',modal.element);
      if(record.state==='UPLOADED'){
        stop();details.innerHTML='<p>The complete archive is staged. Verify it before deciding whether to restore.</p><button data-inspect>Inspect staged archive</button>';
        $('[data-inspect]',modal.element).onclick=e=>pending(e.target,()=>inspect(record));
      }else if(record.state==='AWAITING_CONFIRMATION'){
        stop();const data=record.inspection;
        details.innerHTML=`<p>Verified snapshot: ${escape(stamp(Date.parse(data.manifest.boundary)/1000))}</p><p>${data.notes} notes · ${escape(humanBytes(data.manifest.expanded_bytes))} expanded · schema ${data.manifest.schema}</p><p class="danger">Restore replaces the current Vault and mandatory service state, creates a safety backup, and ends active sessions.</p><button data-restore class="danger">Restore this snapshot</button>`;
        $('[data-restore]',modal.element).onclick=()=>confirmation('Replace current state','Restore this verified snapshot and end active sessions?',async()=>{
          await api(route()+'/confirm',{method:'POST',body:{action:'restore',sha256:record.sha256}});
          await startOperation('restore',null,identifier);
        },'Restore snapshot');
      }else if(record.state==='COMPLETED'&&!finished){
        finished=true;stop();
        if(kind!=='restore'){
          if (!record.download_consumed) download(route()+'/download');details.innerHTML=`<p>The archive is ready. Your browser is downloading ${escape(humanBytes(record.size))}.</p><p>The server copy is removed when this transfer ends. If interrupted, create a fresh archive.</p><p class="muted">SHA-256: ${escape(record.sha256)}</p>`;
        }else details.textContent='Restore completed. Sign in again.';
        notice(kind==='restore'?'Restore completed.':'Archive ready for download.');
      }else if(['FAILED','INTERRUPTED'].includes(record.state)){stop();modal.error.textContent=record.error||record.state;}
      else if(record.state==='WAITING_UPLOAD'){stop();details.textContent='Upload did not finish. Remove this operation and select the file again.';}
    }catch(error){if(error.status===401){stop();modal.error.textContent='Session ended. Sign in again and check the operation in Settings.';}else if(error.name!=='AbortError')throw error;}
  }
  try{
    const record=resume?await request(route()):await request('/api/owner/operations',{method:'POST',body:{kind,...(file?{size:file.size}:{})}});
    identifier=record.id;render(record);
    if(file){
      modal.setBusy(true);
      const expected=await hashFile(file,p=>stage('Checking archive integrity · '+Math.round(p*100)+'%'),controller.signal);
      stage('Uploading archive…');
      const response=await fetch(route()+'/content',{method:'PUT',body:file,signal:controller.signal,credentials:'same-origin',headers:{'X-CSRF-Token':state.session.csrf}});
      const received=await response.json();
      if(!response.ok)throw Error(received.error?.message||'Recovery upload failed.');
      if(received.sha256!==expected)throw Error('The received archive does not match the selected file.');
      await request(route()+'/confirm',{method:'POST',body:{action:'inspect',sha256:expected}});
    }
    stop=poll(check,1000);
  }catch(error){if(error.name!=='AbortError')modal.error.textContent=error.message;}
  finally{modal.setBusy(false);}
  return identifier;
}

function rotateAccessKey(){const modal=dialog('Change Access Key',`<p>Enter the current value and the same new value twice. Other sessions will end.</p><form><label>Current Access Key<textarea class="secret" name="current" autocomplete="current-password" spellcheck="false"></textarea></label><label>New Access Key<textarea class="secret" name="next" autocomplete="new-password" spellcheck="false"></textarea></label><label>Confirm new Access Key<textarea class="secret" name="confirmation" autocomplete="new-password" spellcheck="false"></textarea></label><button type="submit">Change Access Key</button></form>`);
  const current=opaqueInput($('[name=current]',modal.element)),next=opaqueInput($('[name=next]',modal.element)),confirmation=opaqueInput($('[name=confirmation]',modal.element));
  $('form',modal.element).onsubmit=async e=>{e.preventDefault();await pending($('button[type=submit]',modal.element),async()=>{if(next.value()!==confirmation.value()){modal.error.textContent='The new values do not match exactly.';return;}try{state.session=await api('/api/auth/rotate',{method:'POST',body:{current_access_key:current.value(),new_access_key:next.value(),confirm_access_key:confirmation.value()}});current.reset();next.reset();confirmation.reset();modal.close(true);document.dispatchEvent(new Event('credentials-rotated'));notice('Access Key changed. Other sessions ended.');}catch(error){modal.error.textContent=error.message;}});};}

function connectionForm(kind,connection,refresh){const token=kind==='token';const modal=dialog(token?'Replace Kernel token':'Change Kernel URL',`<p>${token?'The new credential is tested through Kernel and Volt before activation. All browser sessions will end.':'The server verifies the proposed Kernel origin with its current credential before saving it.'}</p><form><label>${token?'New Kernel service token':'Kernel URL'}<input name="value" ${token?'type="password" autocomplete="new-password"':'type="url" required'} value="${token?'':escape(connection.url||'')}"></label><button type="submit">Verify and apply</button></form>`);
  $('form',modal.element).onsubmit=async e=>{e.preventDefault();await pending($('button[type=submit]',modal.element),async()=>{try{await api('/api/owner/connection',{method:'POST',body:{[kind]:$('[name=value]',modal.element).value}});modal.close(true);if(token){state.session=null;document.dispatchEvent(new Event('session-expired'));notice('Kernel token changed. Sign in again.');}else{await refresh();notice('Kernel URL verified and saved.');}}catch(error){modal.error.textContent=error.message;}});};}

export async function settings(root){
  root.innerHTML=`<div class="grid">${card('appearance','Appearance',`<div class="group"><h3>Color correction</h3><p>Preview the Shell accent. Apply saves it for authenticated views and sign-in.</p><div class="row"><input type="color" aria-label="Accent preview" data-color value="${state.prefs.accent}"><label class="sr-only" for="accent-hex">Accent hex</label><input id="accent-hex" data-hex value="${state.prefs.accent}" spellcheck="false"><button data-reset-color>Reset color</button><button data-apply-color>Apply color</button></div><p data-accent-error class="error-message" role="alert"></p></div><div class="group"><h3>Left menu position</h3><p>Keep the menu fixed on wide screens, or reveal it from the edge.</p><label class="inline"><input type="checkbox" data-sidebar ${state.prefs.sidebar==='fixed'?'checked':''}>Keep sidebar open</label></div><div class="group"><h3>Activity timezone</h3><label>Calendar timezone<input data-timezone value="${escape(state.prefs.timezone)}" placeholder="Europe/Istanbul"></label><p class="muted">Changes day grouping. Historical UTC events remain unchanged.</p></div>`,{wide:true})}
  ${card('security','Security',`<div class="group"><h3>Changing Access Key</h3><p>Changing the Access Key ends all other active browser sessions.</p><button class="action" data-rotate>Change Access Key</button></div><div class="group"><h3>Connection with Kernel</h3><div data-connection>Loading connection…</div><div class="row"><button data-kernel-url>Change Kernel URL</button><button data-kernel-token>Replace Kernel token</button><button data-kernel-check>Verify connection</button></div></div>`,{wide:true})}
  ${card('backup','Backup',`<div class="group"><h3>System snapshot</h3><p>Encrypted full Vault and mandatory service state. Includes Obsidian plugins and their original data. Recovery keys are stored separately.</p><button class="action" data-backup>Create and download snapshot</button></div><div class="group"><h3>Restore snapshot</h3><p>Upload a recovery ZIP, inspect its contents and explicitly confirm replacement.</p><label class="sr-only" for="restore-file">Recovery ZIP</label><input id="restore-file" type="file" accept=".zip" hidden><button class="action" data-restore-file>Inspect and restore snapshot</button></div><div class="group"><h3>Neptune archive and mirror</h3><p>Independent archive and mirror pipelines. Manage their schedules here.</p><div data-agents>Checking local agent…</div><div class="row"><button data-agent-refresh>Refresh status</button><button data-agent-init>Initialize / Repair</button></div><div data-backup-policy></div></div><div class="group"><h3>Neptune version</h3><p>Current installed version: <span data-neptune-version>Checking…</span></p><button class="action" data-neptune-update>Check Neptune for updates</button></div><div class="group"><h3>Recent maintenance operations</h3><div data-operations class="list"></div></div>`,{wide:true})}
  ${card('updates','Updates',`<div class="group"><h3>Update pipeline</h3><p>Core, Runtime and Worker update together through the local Updater.</p><p>Installed version: <strong class="accent" data-version>Loading…</strong></p><div class="status-line"><span>Local update helper</span><span data-updater>Not verified</span></div><div class="status-line"><span>Approved release registry</span><span data-registry>Not checked</span></div><button class="action" data-update-check>Check for updates</button><div class="group"><h3>Updater version</h3><p>Current installed version: <span data-helper-version>Checking…</span></p><button class="action" data-updater-update>Check Updater for updates</button></div><p data-update-state></p></div>`,{wide:true})}
  ${card('logs','Logs','<div data-service-logs></div>',{wide:true})}</div>`;
  $('.grid',root).insertAdjacentHTML('beforeend',card('wyvern','Wyverne Connection','<div data-wyvern>Checking LLM gateway…</div>',{wide:true}));
  const stopWyvern = wyvernCard(root);
  const stopPolicy = mountBackupPolicy($('[data-backup-policy]', root), {service: 'mastermind', base: '/api/owner/neptune/policy', headers: () => ({'X-CSRF-Token': state.session?.csrf || ''})});
  const stopLogs = mountServiceLogs($('[data-service-logs]', root), {base: '/api/logs?history=true', beforeParam: 'before', onDownload: () => startOperation('logs')});
  bind(root,'click','[data-neptune-update]',()=>helperUpdates('neptune'));
  bind(root,'click','[data-updater-update]',()=>helperUpdates('updater'));

  $('.grid',root).insertAdjacentHTML('beforeend',card('context_indexing','Obsidian & search','<div data-context-indexing>Checking context-indexing…</div>',{wide:true}));
  void contextIndexingCard(root);
  reorder($('.grid',root),'settings');let connection={},agentTick=0,initialization={state:'IDLE'};
  const preview=value=>{if(/^#[\da-f]{6}$/i.test(value)){document.documentElement.style.setProperty('--accent',value);$('[data-color]',root).value=value;$('[data-hex]',root).value=value;}};
  $('[data-color]',root).oninput=e=>preview(e.target.value);$('[data-hex]',root).oninput=e=>preview(e.target.value);
  bind(root,'click','[data-reset-color]',()=>preview('#00A8FF'));bind(root,'click','[data-apply-color]',(e,b)=>pending(b,async()=>{try{await preferences({accent:$('[data-hex]',root).value});$('[data-accent-error]',root).textContent='';notice('Accent saved.');}catch(error){$('[data-accent-error]',root).textContent=error.message;document.documentElement.style.setProperty('--accent',state.prefs.accent);}}));
  $('[data-sidebar]',root).onchange=async e=>{const before=state.prefs.sidebar;e.target.disabled=true;try{await preferences({sidebar:e.target.checked?'fixed':'auto'});}catch(error){e.target.checked=before==='fixed';notice(error.message,true);}finally{e.target.disabled=false;}};
  $('[data-timezone]',root).onchange=async e=>{e.target.disabled=true;try{await preferences({timezone:e.target.value});notice('Timezone saved.');}catch(error){e.target.value=state.prefs.timezone;notice(error.message,true);}finally{e.target.disabled=false;}};
  async function refreshConnection(){connection=await api('/api/owner/connection');if(root.isConnected)$('[data-connection]',root).innerHTML=`<div class="status-line"><span>${escape(connection.url||'Not configured')}</span><span>${escape(connection.state)}</span></div><p class="muted">Last successful verification: ${escape(stamp(connection.verified_at))}</p>`;}
  bind(root,'click','[data-rotate]',rotateAccessKey);bind(root,'click','[data-kernel-url]',()=>connectionForm('url',connection,refreshConnection));bind(root,'click','[data-kernel-token]',()=>connectionForm('token',connection,refreshConnection));bind(root,'click','[data-kernel-check]',(e,b)=>pending(b,async()=>{await api('/api/owner/connection',{method:'POST',body:{check:true}});await refreshConnection();notice('Kernel and Volt consumer verification passed.');}));
  bind(root,'click','[data-backup]',(e,b)=>pending(b,()=>startOperation('backup')));bind(root,'click','[data-restore-file]',()=>$('[type=file]',root).click());$('[type=file]',root).onchange=async e=>{const file=e.target.files[0];if(file)await startOperation('restore',file);e.target.value='';};bind(root,'click','[data-logs-download]',(e,b)=>pending(b,()=>startOperation('logs')));
  async function agents(){const result=await api('/api/owner/agents');if(!root.isConnected)return;initialization=result.neptune_initialization;const running=['REQUESTED','INSTALLING','ENROLLING'].includes(initialization.state);$('[data-agent-init]',root).disabled=false;$('[data-agent-init]',root).textContent=running?'View initialization progress':result.neptune.state==='PARTIAL_CONFIGURATION'?'Repair Neptune pipelines':'Initialize Neptune';const n=result.neptune;$('[data-neptune-version]',root).textContent=n.version||'Unavailable';$('[data-helper-version]',root).textContent=result.updater.version||'Unavailable';$('[data-agents]',root).innerHTML=`<div class="status-line"><span>Neptune</span><span class="${n.state==='LINKED'?'success':'danger'}">${escape(n.state==='LINKED'?'Linked to Saturn':n.state.replaceAll('_',' '))}${n.code?' · '+escape(n.code):''}</span></div>${initialization.state!=='IDLE'?`<p>Initialization: ${escape(initialization.state)} · ${escape(initialization.job_id||initialization.request_id)}${initialization.error?' · '+escape(initialization.error):''}<br><button data-agent-review>Review initialization</button></p>`:''}<p>Archive last success: ${escape(stamp(n.archive_last_success_at))}<br>Mirror last success: ${escape(stamp(n.mirror_last_success_at))}</p><p class="muted">Archive generation: ${escape(n.archive_generation??'Unknown')} · mirror generation: ${escape(n.mirror_generation??'Unknown')}</p>`;$('[data-updater]',root).textContent=result.updater.state;$('[data-version]',root).textContent=result.version;}
  function agentDialog() {
    return openAgentInitialization({ component: 'Neptune', service: 'mastermind',
      description: 'Initialize or repair this service connection through the local Updater.',
      codeLabel: 'One-time setup code', profile: 'Required: archive, Vault mirror and resource reader.',
      initialize: input => api('/api/owner/agents/neptune/enroll', {method: 'POST', body: {code: input.enrollment_code, request_id: input.request_id}}),
      observe: () => api('/api/owner/agents/neptune/initialization'),
      recover: async hint => { const job = await api('/api/owner/agents/neptune/initialization'); return job.state !== 'IDLE' && (!hint?.request_id || hint.request_id === job.request_id) ? job : null; },
      verify: async () => { const observed = await api('/api/owner/agents'); return {ready: observed.neptune.state === 'LINKED', message: 'Archive, mirror and reader are not all verified.'}; },
      onComplete: agents,
    });
  }
  bind(root,'click','[data-agent-refresh]',(e,b)=>pending(b,agents));bind(root,'click','[data-agent-init]',()=>agentDialog());bind(root,'click','[data-agent-review]',()=>agentDialog());
  bind(root,'click','[data-update-check]',()=>openGroupUpdates());
  bind(root,'click','[data-op-review]',(e,b)=>startOperation('restore',null,b.dataset.opReview));
  const rollbackButton=document.createElement('button');rollbackButton.textContent='Return to previous version';rollbackButton.dataset.versionRollback='';$('[data-update-check]',root).after(rollbackButton);
  rollbackButton.onclick=()=>openGroupUpdates({rollback:true});
  bind(root,'click','[data-op-delete]',(e,b)=>{const id=b.dataset.opDelete;confirmation('Remove staged operation','Remove this completed or abandoned operation and its staged archive?',async()=>{await api('/api/owner/operations/'+id,{method:'DELETE'});await refresh();},'Remove staged files');});
  async function refresh(){const [ops,updates]=await Promise.all([api('/api/owner/operations'),api('/api/owner/updates')]);if(!root.isConnected)return;
    $('[data-operations]',root).innerHTML=ops.length?ops.map(op=>`<div class="list-row"><div>${escape(op.kind)} · ${escape(op.stage)}<br><small>${escape(stamp(op.created_at))}${op.error?' · '+escape(op.error):''}</small></div><span>${op.size?escape(humanBytes(op.size)):''}</span><div class="row-actions">${op.kind==='restore'?`<button data-op-review="${op.id}">Review</button>`:''}${op.state==='COMPLETED'&&op.kind!=='restore'&&!op.download_consumed?`<a download href="/api/owner/operations/${op.id}/download">Download</a>`:''}<button data-op-delete="${op.id}" ${['RUNNING','RECEIVING'].includes(op.state)?'disabled':''}>Remove</button></div></div>`).join(''):'<p class="empty">No staged maintenance operations.</p>';
    $('[data-update-state]',root).textContent='Update state: '+(updates.phase||updates.state)+(updates.error?' · '+updates.error:'');if(Date.now()-agentTick>15000){agentTick=Date.now();await agents();}}
  await refreshConnection();const stop=poll(refresh,3000);return()=>{stop();stopWyvern();stopPolicy();stopLogs();document.documentElement.style.setProperty('--accent',state.prefs.accent);};
}
