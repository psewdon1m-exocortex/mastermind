import {$, api, escape, pending, notice, dialog, search, wireSearch} from './ui.js';

const base = '/api/owner/context-indexing';

async function chooseNote(input) {
  const modal = dialog('Select a Vault note', `${search('Find a note')}<div data-notes class="list"></div><button data-more hidden>Next page</button>`, {dirtyGuard:false});
  let sequence=0, offset=0, query='', timer;
  async function load() {
    const turn=++sequence;
    try {
      const notes=await api('/api/notes?limit=100&offset='+offset+'&query='+encodeURIComponent(query));
      if(!modal.element.isConnected||turn!==sequence)return;
      $('[data-notes]',modal.element).innerHTML=notes.length?notes.map(note=>`<button type="button" class="list-row" data-path="${escape(note.path)}">${escape(note.path)}</button>`).join(''):'<p>No matching notes.</p>';
      $('[data-more]',modal.element).hidden=notes.length<100;
      for(const button of modal.element.querySelectorAll('[data-path]'))button.onclick=()=>{input.value=button.dataset.path;input.dispatchEvent(new Event('input',{bubbles:true}));modal.close();input.focus();};
    }catch(error){if(error.name!=='AbortError')modal.error.textContent=error.message;}
  }
  wireSearch($('.search-box',modal.element),value=>{query=value;offset=0;clearTimeout(timer);timer=setTimeout(load,150);});
  $('[data-more]',modal.element).onclick=()=>{offset+=100;void load();};
  await load();
}

export async function contextIndexingCard(root) {
  const box=$('[data-context-indexing]',root);
  let current, operation=null;
  const run=async(button,action)=>{try{await pending(button,action);}catch(error){if(error.name!=='AbortError'){notice(error.message,true);const target=$('[data-error]',box);if(target)target.textContent=error.message;}}};
  function statuses(value) {
    const ready=value.readiness, curator=ready.curator;
    $('[data-configuration]',box).textContent=ready.configuration==='READY'?'Configuration ready':'Configuration needs attention: '+Object.values(ready.errors).join(', ');
    $('[data-curator-status]',box).textContent=!curator.requested?'Disabled':curator.effective?'Ready':'Unavailable · '+(curator.reason||'Worker is not ready');
    const index=ready.search;
    $('[data-index-status]',box).textContent=(index.status||index.state||'Unavailable')+(index.notes_indexed!==undefined?' · '+index.notes_indexed+' / '+index.notes_total+' notes indexed':'');
  }
  async function waiting() {
    const jobs=await api(base+'/waiting');
    if(!box.isConnected)return;
    $('[data-waiting]',box).innerHTML=jobs.length?jobs.map(job=>`<div class="list-row"><span>${escape(job.source_label)} · ${escape(job.configuration_error)}<br><small>Resume uses the current configuration.</small></span><button data-resume="${escape(job.id)}">Resume</button></div>`).join(''):'<p class="muted">No jobs waiting for configuration.</p>';
    for(const button of box.querySelectorAll('[data-resume]'))button.onclick=()=>run(button,async()=>{
      await api(base+'/jobs/'+button.dataset.resume+'/resume',{method:'POST',body:{expected_revision:current.revision,operation_id:crypto.randomUUID()}});
      await waiting();notice('Processing resumed with the current configuration.');
    });
  }
  async function refresh({keepDraft=false}={}) {
    const next=await api(base+'/settings');
    if(!box.isConnected)return;
    current=next;
    if(!keepDraft) {
      operation=null;
      box.innerHTML=`<form data-context-form>
        <div class="group"><h3>Crusher notes</h3><p>Files are stored in the Crusher folder. Their links determine their place in the graph.</p>
        <label>Crusher folder<input value="${escape(current.crusher.output_dir)}" readonly></label>
        <div class="context-paths">${[['fallback_note','Fallback note'],['template_path','Crusher template']].map(([field,label])=>`<div><label for="context-${field}">${label}</label><div class="row"><input class="grow" id="context-${field}" name="${field}" value="${escape(current.crusher[field])}" required aria-describedby="context-path-error"><button type="button" data-pick="${field}">Choose note</button></div></div>`).join('')}</div>
        <p class="muted">Fallback must be reachable from ${escape(current.graph_root)}. The template provides the note structure.</p><p data-configuration></p></div>
        <div class="group"><h3>Context-indexing</h3><label class="inline"><input name="curator_enabled" type="checkbox" ${current.retrieval.curator_enabled?'checked':''}>Enable Curator</label>
        <p class="muted">The local Curator may refine an uncertain search once. Changes apply to newly accepted or explicitly resumed jobs.</p>
        <div class="status-line"><span>Curator</span><span data-curator-status></span></div><div class="status-line"><span>Search index</span><span data-index-status></span></div></div>
        <p id="context-path-error" data-error class="error-message" role="alert"></p>
        <div class="row"><button class="action" type="submit">Apply</button><button type="button" data-validate>Validate draft</button><button type="button" data-refresh>Refresh status and revision</button><button type="button" data-initialize>Initialize defaults</button></div>
      </form><div class="group"><h3>Waiting for configuration</h3><div data-waiting></div></div>`;
      const form=$('form',box);
      const chosen=new Set();
      const changes=()=>{
        const crusher={},retrieval={};
        for(const key of ['fallback_note','template_path'])if(chosen.has(key)||form.elements[key].value!==current.crusher[key])crusher[key]=form.elements[key].value;
        if(form.elements.curator_enabled.checked!==current.retrieval.curator_enabled)retrieval.curator_enabled=form.elements.curator_enabled.checked;
        return {crusher,retrieval};
      };
      form.oninput=event=>{chosen.add(event.target.name);operation=null;$('[data-error]',box).textContent='';};
      for(const button of box.querySelectorAll('[data-pick]'))button.onclick=()=>chooseNote(form.elements[button.dataset.pick]);
      $('[data-refresh]',box).onclick=event=>run(event.currentTarget,()=>refresh({keepDraft:true}));
      $('[data-validate]',box).onclick=event=>run(event.currentTarget,async()=>{await api(base+'/validate',{method:'POST',body:changes()});notice('Changed fields are valid.');});
      $('[data-initialize]',box).onclick=event=>run(event.currentTarget,async()=>{await api(base+'/initialize',{method:'POST',body:{}});await refresh({keepDraft:true});notice('Default notes are initialized. Existing notes were preserved.');});
      form.onsubmit=event=>{event.preventDefault();void run($('button[type=submit]',form),async()=>{
        operation??={...changes(),expected_revision:current.revision,operation_id:crypto.randomUUID()};
        await api(base+'/settings',{method:'PATCH',body:operation});
        await refresh();
        if(current.retrieval.curator_enabled&&!current.readiness.curator.effective)notice('Settings saved. Curator is requested but unavailable.',true);
        else notice('Obsidian & search settings saved.');
      });};
    } else operation=null;
    statuses(current);
    await waiting();
  }
  try{await refresh();}catch(error){if(error.name!=='AbortError')box.textContent=error.message;}
}
