// Bounded real-provider owner/guest/native verification on the local stand.
// Reads only the owner bootstrap credential; never reads a provider credential.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {execFileSync}=require('node:child_process');
const {chromium}=require('./lib/browser.cjs');
const origin='http://localhost:18390',output=path.resolve('artifacts/context-indexing-native');
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const inspect=id=>JSON.parse(execFileSync('docker',['exec','-i','mastermind-development-core-1','python','-',id],{encoding:'utf8',input:`
import json,sqlite3,sys
from mastermind.config import Config
c=Config.environment()
d=sqlite3.connect('file:'+str(c.state/'mastermind.sqlite3')+'?mode=ro',uri=True)
v=json.loads(d.execute('SELECT record FROM jobs WHERE id=?',(sys.argv[1],)).fetchone()[0])
print(json.dumps({k:v.get(k) for k in ['committed_path','commit','context_receipt','context_snapshot','results','transitions']}))
`}));
const nativeOpen=note=>JSON.parse(execFileSync('docker',['exec','-i','mastermind-development-runtime-1','python','-',note],{encoding:'utf8',input:`
import json,sys,urllib.request
from pathlib import Path
r=urllib.request.Request('http://127.0.0.1:8091/internal/open',data=json.dumps({'path':sys.argv[1]}).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+Path('/run/mastermind/runtime_token').read_text()})
print(urllib.request.urlopen(r,timeout=30).read().decode())
`}));
(async()=>{
 assert.ok(process.argv.includes('--live'),'Explicit --live is required for provider requests.');
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true}),owner=await browser.newContext({viewport:{width:1440,height:1000}});
 const report={status:'RUNNING',cases:[],public_scope_denied:false},created=[];
 let session;
 const api=async(route,method='GET',data)=>{
  const r=await owner.request.fetch(origin+route,{method,headers:{Origin:origin,...(session?{'X-CSRF-Token':session.csrf}:{}),'Idempotency-Key':crypto.randomUUID()},...(data?{data}:{})});
  const value=await r.json();assert.ok(r.ok(),route+': '+r.status()+' '+value.error?.code);return value;
 };
 const ready=async()=>{
  let state;for(let i=0;i<60;i++){state=await api('/api/status');if(state.status==='HEALTHY')return state;await sleep(500);}
  assert.equal(state.status,'HEALTHY');
 };
 try{
  session=await api('/api/auth/login','POST',{access_key:fs.readFileSync('.local/secrets/core/bootstrap_access_key','utf8')});
  await ready();const before=await api('/api/owner/context-indexing/settings');
  assert.equal(before.crusher.output_dir,'root/crusher');assert.equal(before.retrieval.curator_enabled,false);
  assert.equal(before.readiness.configuration,'READY');
  const parents=new Map();for(const p of ['root.md','Integration/Integration branch.md','Integration/Integration key.md','root/pool.md'])parents.set(p,(await api('/api/note?'+new URLSearchParams({path:p}))).sha256);
  const page=await owner.newPage();let last;
  for(const kind of ['owner','guest']){
   const actor=kind==='owner'?owner:await browser.newContext({viewport:{width:1440,height:1000}});
   const view=kind==='owner'?page:await actor.newPage();await view.goto(origin+'/crusher');
   if(kind==='guest'){
    const code=await api('/api/v1/crusher/access','POST',{});
    const activation=view.waitForResponse(r=>r.url().endsWith('/api/v1/crusher/sessions')&&r.request().method()==='POST');
    await view.locator('input[autocomplete="one-time-code"]').fill(code.code);await view.getByRole('button',{name:'Enter',exact:true}).click();
    const token=(await (await activation).json()).token;
    for(const route of ['/api/owner/context-indexing/settings','/api/owner/context-indexing/waiting','/api/notes']){
     const denied=await actor.request.get(origin+route,{headers:{Authorization:'Bearer '+token}});assert.ok([401,403].includes(denied.status()));
    }
    report.public_scope_denied=true;
   }
   await view.getByLabel('Source files',{exact:true}).waitFor();
   const accepted=view.waitForResponse(r=>r.url()===origin+'/api/v1/crusher/jobs'&&r.request().method()==='POST');
   const text=kind==='owner'?'Knowledge architecture organizes knowledge into meaningful hierarchical topics. Semantic organization groups notes by meaning. A root leads to main branches and nested key notes. The purpose is to find related knowledge and place a new note under its closest semantic topic.':'Decorative napkin folding uses repeated folds to create a table ornament. Fold a square napkin into a triangle, fold the corners and stand the ornament upright. This source is unrelated to knowledge architecture or semantic organization.';
   await view.getByLabel('Source files',{exact:true}).setInputFiles({name:'context-indexing-'+kind+'.txt',mimeType:'text/plain',buffer:Buffer.from(text)});
   const receipt=await (await accepted).json();assert.ok(receipt.job_id);let job;
   const start=Date.now();for(let i=0;i<120;i++){job=await api('/api/v1/crusher/jobs/'+receipt.job_id);if(['COMPLETED','FAILED','WAITING_CONFIGURATION'].includes(job.state))break;await sleep(1000);}
   assert.equal(job.state,'COMPLETED',job.error?.code||job.state);assert.ok(!('path' in job)&&!('result' in job));
   const record=inspect(receipt.job_id),note=await api('/api/note?'+new URLSearchParams({path:record.committed_path}));
   assert.ok(record.committed_path.startsWith('root/crusher/'));assert.ok(note.text.includes('## Кратко')&&note.text.includes('## Связи'));
   assert.ok(!record.context_snapshot&&Object.keys(record.results).length===0);
   created.push({path:record.committed_path,expected_sha256:note.sha256});last=created.at(-1);
   const anchor=kind==='owner'?'Integration/Integration key.md':'root/pool.md';
   assert.ok(note.text.includes('[['+path.posix.basename(anchor,'.md')+']]'));
   const graph=await api('/api/graph');assert.ok(graph.edges.some(e=>e.includes(last.path)&&e.includes(anchor)));
   await ready();assert.equal(nativeOpen(last.path).opened,true);
   report.cases.push({kind,state:job.state,path:last.path,sha256:note.sha256,anchor,seconds:(Date.now()-start)/1000,template:record.context_receipt});
   fs.writeFileSync(path.join(output,kind+'.md'),note.text);
   if(kind==='guest')await actor.close();
  }
  for(const [p,sha] of parents)assert.equal((await api('/api/note?'+new URLSearchParams({path:p}))).sha256,sha);
  await page.goto(origin+'/runtime/index.html?autoconnect=1&path=runtime/websockify&resize=remote');await sleep(3500);
  assert.equal(nativeOpen(last.path).opened,true);await sleep(1000);await page.screenshot({path:path.join(output,'native-note.png')});
  await page.mouse.click(700,300);await page.keyboard.press('Escape');await page.keyboard.press('Control+p');await page.keyboard.type('Open graph view',{delay:30});await page.keyboard.press('Enter');await sleep(2000);
  const status=await api('/api/status');const graph=status.runtime.bridge.graphs.find(g=>g.visible&&g.nodes>0);assert.ok(graph);
  await page.screenshot({path:path.join(output,'native-graph.png')});report.native_graph=graph;
  await page.goto(origin+'/settings');await page.locator('[data-card="context_indexing"]').getByText('Obsidian & search',{exact:true}).waitFor();
  await page.locator('[data-card="context_indexing"]').screenshot({path:path.join(output,'settings.png')});
  report.parents_unchanged=true;report.settings_revision=before.revision;report.status='PASS';
 }finally{
  for(const note of created){await ready();await api('/api/note','DELETE',note);}
  report.synthetic_notes_removed=created.length;fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));
  await browser.close();
 }
 console.log(JSON.stringify({status:report.status,cases:report.cases.map(v=>({kind:v.kind,state:v.state,seconds:v.seconds})),public_scope_denied:report.public_scope_denied,synthetic_notes_removed:report.synthetic_notes_removed}));
})().catch(error=>{console.error(error.message);process.exitCode=1;});
