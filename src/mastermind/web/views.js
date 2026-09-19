import {$,api,escape,card,handle,reorder,poll,humanBytes,duration,bind,pending,notice} from './ui.js';
import {wireCrusherAccess} from './crusher.js';
export {shares,shareCapabilities} from './shared.js';

function metric(id,title){return `<section class="card metric hoverable" data-card="${id}"><span class="ordinal"></span>${handle(title)}<h2>${escape(title)}</h2><div class="metric-value" data-value>Unknown</div><span class="metric-scope" data-scope></span>${['cpu','ram','disk','connectedness'].includes(id)?'<div class="progress" role="progressbar" aria-label="'+escape(title)+'" aria-valuemin="0" aria-valuemax="100"><span></span></div>':''}</section>`;}
function progress(card,value){const bar=$('.progress',card);if(!bar)return;bar.firstChild.style.width=(value??0)+'%';if(value!=null)bar.setAttribute('aria-valuenow',Math.min(100,Math.max(0,value)));else bar.removeAttribute('aria-valuenow');bar.setAttribute('aria-valuetext',value==null?'Unknown':value.toFixed(1)+' percent');}
function activityMonths(days){
  const months=new Map(),shortMonth=new Intl.DateTimeFormat('en',{month:'short',timeZone:'UTC'}),longMonth=new Intl.DateTimeFormat('en',{month:'long',year:'numeric',timeZone:'UTC'});
  for(const day of days){const key=day.date.slice(0,7);if(!months.has(key))months.set(key,[]);months.get(key).push(day);}
  return [...months].map(([month,entries])=>{
    const first=new Date(entries[0].date+'T12:00:00Z'),offset=(first.getUTCDay()+6)%7;
    const cells='<span aria-hidden="true"></span>'.repeat(offset)+entries.map(day=>`<button type="button" class="day" data-date="${day.date}" data-level="${day.level}" aria-label="${day.date}: ${day.count} actions" title="${day.date}: ${day.count} actions" data-detail="${escape(day.date+': '+day.count+' actions · '+Object.entries(day.kinds).map(([k,v])=>k+' '+v).join(', '))}"></button>`).join('');
    return `<section class="heatmap-month" role="group" aria-label="${longMonth.format(first)}"><h3 class="heatmap-month-label"><span>${shortMonth.format(first)}</span><span class="heatmap-year">${month.slice(0,4)}</span></h3><div class="heatmap-days">${cells}</div></section>`;
  }).join('');
}
export async function dashboard(root){
  root.innerHTML=`<div class="grid">${metric('cpu','CPU Usage')}${metric('ram','RAM Usage')}${metric('disk','Disk Usage')}${metric('uptime','Uptime')}${metric('connectedness','Connectedness')}${metric('items','Total items')}${card('heatmap','Activity Heatmap',`
    <div class="row heatmap-controls"><label>From<input type="date" data-first></label><label>Through<input type="date" data-last></label><button data-period>Apply period</button><span data-zone class="muted"></span></div>
    <div class="heatmap-scroll"><div class="heatmap" role="group" aria-label="Daily owner activity"></div></div><p data-day-detail aria-live="polite">Select a day for its action count.</p><p class="muted">CREATE · EDIT · RENAME · MOVE. Intensity is relative to the busiest displayed day.</p>`,{wide:true})}<section class="card quarter metric access-card hoverable" data-card="crusher_access"><span class="ordinal"></span>${handle('Crusher access')}<h2>Crusher access</h2><button class="card-action" type="button" data-access aria-label="Create and copy Crusher access code" aria-describedby="crusher-access-detail"><span class="metric-value" data-access-value>Create &amp; copy</span></button><span class="metric-scope" id="crusher-access-detail" data-access-detail role="status">Create a temporary upload code</span></section></div>`;
  $('[data-card="heatmap"]',root).classList.add('hoverable');
  reorder($('.grid',root),'dashboard');
  const stopAccess=wireCrusherAccess($('[data-card="crusher_access"]',root));
  const stopMetrics=poll(async()=>{
    const m=await api('/api/owner/metrics');if(!root.isConnected)return;
    for(const id of ['cpu','ram','disk','uptime']){
      const c=$(`[data-card="${id}"]`,root),data=m[id];let value,scope;
      if(id==='uptime'){value='Active: '+duration(m.uptime_seconds);scope='Current Core process';}
      else if(id==='cpu'){value=(data?.percent==null?'Unknown':data.percent.toFixed(1)+'%')+' · cores: '+(data?.cores??'Unknown');scope='Server CPU';}
      else{value=data?`${data.percent==null?'Unknown':data.percent.toFixed(1)+'%'} · ${humanBytes(data.used)} / ${humanBytes(data.total)}`:'Unknown';scope=id==='disk'?'Canonical Vault filesystem · available to service':'Server RAM';}
      $('[data-value]',c).textContent=value;$('[data-scope]',c).textContent=scope;progress(c,data?.percent);
    }
  },3000);
  let selectedPeriod='';
  async function refreshActivity(){
    const result=await api('/api/owner/analytics'+selectedPeriod);if(!root.isConnected)return;
    if(!$('[data-first]',root).value){$('[data-first]',root).value=result.first;$('[data-last]',root).value=result.last;}
    $('[data-zone]',root).textContent=result.timezone;
    const heatmap=$('.heatmap',root),focusedDay=$('.day:focus',heatmap)?.dataset.date;
    heatmap.innerHTML=activityMonths(result.days);
    if(focusedDay)$(`[data-date="${focusedDay}"]`,heatmap)?.focus({preventScroll:true});
    const connected=$('[data-card="connectedness"]',root),items=$('[data-card="items"]',root);
    $('[data-value]',connected).textContent=result.connectedness.toLocaleString(undefined,{maximumFractionDigits:2})+'%';
    $('[data-scope]',connected).textContent='Internal note graph';progress(connected,result.connectedness);
    $('[data-value]',items).textContent=result.items.total.toLocaleString();
    $('[data-scope]',items).textContent=`${result.items.notes} notes · ${result.items.attachments} attachments`;
  }
  bind(root,'click','[data-period]',(e,b)=>pending(b,async()=>{selectedPeriod='?'+new URLSearchParams({first:$('[data-first]',root).value,last:$('[data-last]',root).value});await refreshActivity();}));
  bind(root,'click','.day',(e,b)=>$('[data-day-detail]',root).textContent=b.dataset.detail);
  const stopActivity=poll(refreshActivity,15000);return()=>{stopMetrics();stopActivity();stopAccess();};
}

export async function vault(root){
  root.innerHTML=`<section class="runtime" aria-label="Native Obsidian viewport"><div class="runtime-toolbar"><span class="state" role="status">Connecting to Runtime…</span><button data-reconnect>Reconnect</button><button data-fullscreen>Fullscreen</button></div><iframe title="Obsidian Runtime" allow="clipboard-read; clipboard-write; fullscreen"></iframe><div class="runtime-downloads" hidden></div></section>`;
  const runtime=$('.runtime',root),frame=$('iframe',root);const connect=()=>{frame.src='/runtime/index.html?autoconnect=1&path=runtime/websockify&resize=remote';};connect();let disconnected=false;
  bind(root,'click','[data-reconnect]',()=>{connect();notice('Runtime connection reopened.');});
  bind(root,'click','[data-fullscreen]',async()=>{if(document.fullscreenElement)await document.exitFullscreen();else await runtime.requestFullscreen();});
  const fullscreen=()=>{$('[data-fullscreen]',root).textContent=document.fullscreenElement?'Exit fullscreen':'Fullscreen';};document.addEventListener('fullscreenchange',fullscreen);
  const stop=poll(async()=>{const [s,downloads]=await Promise.all([api('/api/status'),api('/api/runtime/downloads')]);if(!root.isConnected)return;const ready=s.runtime?.bridge?.ready&&s.runtime?.startup_allowed;$('.state',root).textContent=ready?'Obsidian connected':s.runtime?.owner_setup_required?'First launch: complete the Vault trust prompt in Obsidian below.':'Runtime recovering · '+(s.runtime_failure||s.failure||s.runtime?.state||'waiting');if(ready&&disconnected)connect();disconnected=!ready;
    const queue=$('.runtime-downloads',root);queue.hidden=!downloads.length;queue.innerHTML=downloads.map(item=>`<a download href="/api/owner/resources/content?${new URLSearchParams({path:item.path,download:'true'})}">Download ${escape(item.path.split('/').at(-1))}</a>`).join('');},3000);
  return()=>{stop();document.removeEventListener('fullscreenchange',fullscreen);frame.src='about:blank';};
}
