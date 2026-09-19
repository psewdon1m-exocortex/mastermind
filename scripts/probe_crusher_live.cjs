// Explicit, bounded live-provider qualification. This spends provider quota.
// Never load a provider credential here: Core resolves it from Kernel/Volt.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {execFileSync}=require('node:child_process');
const {chromium}=require('./lib/browser.cjs');
const origin='http://localhost:18390',container='mastermind-development-core-1';
const out=path.resolve('artifacts/live-ai-20260919');
const run=crypto.randomUUID();
const inspect=identifier=>JSON.parse(execFileSync('docker',['exec','-i',container,'python','-',identifier],{encoding:'utf8',input:`import json,sqlite3,sys
from mastermind.config import Config
c=Config.environment()
db=sqlite3.connect('file:'+str(c.state/'mastermind.sqlite3')+'?mode=ro',uri=True)
r=json.loads(db.execute('SELECT record FROM jobs WHERE id=?',(sys.argv[1],)).fetchone()[0])
print(json.dumps({k:r.get(k) for k in ['models','transitions','commit','budget','attempts','results','error']}))
`}));
(async()=>{
  assert.ok(process.argv.includes('--live'),'Pass --live only when real provider requests are authorized.');
  const mode=JSON.parse(execFileSync('docker',['inspect',container,'--format','{{json .Config.Entrypoint}}'],{encoding:'utf8'}));
  assert.ok(mode.includes('mastermind.api:create_app')&&!mode.includes('core_fixture:create_app'));
  const cases=process.argv.includes('--placement')?['placement']:process.argv.includes('--file')?['file']:process.argv.includes('--web')?['web']:process.argv.includes('--audio')?['audio']:['file','web','audio'];
  const browser=await chromium.launch({headless:true}),context=await browser.newContext();let session;
  const result={live_provider:true,model:'gemini-3.8-flash',run,cases:[]};
  const api=async(route,method='GET',data)=>{
    const r=await context.request.fetch(origin+route,{method,headers:{Origin:origin,...(session?{'X-CSRF-Token':session.csrf}:{}),'Idempotency-Key':run},...(data?{data}:{})});
    assert.ok(r.ok(),route+': HTTP '+r.status());return r.json();
  };
  const ready=async()=>{
    let status;const deadline=Date.now()+30000;
    do{status=await api('/api/status');if(status.status==='HEALTHY')break;await new Promise(resolve=>setTimeout(resolve,500));}while(Date.now()<deadline);
    assert.equal(status.status,'HEALTHY');return status;
  };
  fs.mkdirSync(out,{recursive:true});
  try{
    session=await api('/api/auth/login','POST',{access_key:fs.readFileSync('.local/secrets/core/bootstrap_access_key','utf8')});
    result.before=await ready();
    // Avoid sending real Vault context during this probe. This existing local
    // fixture hierarchy must match exactly before any job is submitted.
    for(const [note,text] of [['root.md','[[Integration branch]]'],['Integration/Integration branch.md','#main\n\nKnowledge architecture\n\n[[Integration key]]'],['Integration/Integration key.md','#key\n\nKnowledge architecture and semantic organization.']]){
      const current=await api('/api/note?'+new URLSearchParams({path:note}));assert.equal(current.text.trim(),text);
    }
    const page=await context.newPage();
    for(const kind of cases){
      await page.goto(origin+'/crusher');await page.getByLabel('Source links',{exact:true}).waitFor();
      const accepted=page.waitForResponse(r=>r.url()===origin+'/api/v1/crusher/jobs'&&r.request().method()==='POST',{timeout:30000});
      if(kind==='file'||kind==='placement'){
        const text=kind==='placement'?'Knowledge architecture and semantic organization. Knowledge architecture organizes knowledge into meaningful hierarchical topics. Semantic organization groups notes by meaning. A root leads to main branches; main branches contain more specific key notes. The purpose is to make related knowledge easy to find and to place new notes under the closest semantic topic.':
          'Synthetic knowledge architecture source. Project Cedar organizes knowledge in three main branches and ten key notes. Root is the entry point. Main notes describe broad topics. Key notes describe narrower subjects and can contain nested key branches. This hierarchy helps place each new note in an appropriate topic. This is a test dataset, not a description of any existing private system.';
        await page.getByLabel('Source files',{exact:true}).setInputFiles({name:'live-ai-knowledge.txt',mimeType:'text/plain',buffer:Buffer.from(text)});
      }else if(kind==='web'){
        await page.getByLabel('Source links',{exact:true}).fill('https://example.com/');await page.getByRole('button',{name:'Submit links',exact:true}).click();
      }else{
        const bytes=[...fs.readFileSync(path.join(out,'source.wav'))];
        const transfer=await page.evaluateHandle(bytes=>{const d=new DataTransfer();d.items.add(new File([new Uint8Array(bytes)],'live-ai-knowledge.wav',{type:'audio/wav'}));return d;},bytes);
        await page.dispatchEvent('body','dragenter',{dataTransfer:transfer});await page.locator('.file-drag-overlay').waitFor({state:'visible'});
        await page.locator('.crusher-dropzone').dispatchEvent('drop',{dataTransfer:transfer});await transfer.dispose();
      }
      const response=await accepted;assert.ok(response.ok(),'Acceptance HTTP '+response.status());const receipt=await response.json();
      const item={kind,job_id:receipt.job_id};result.cases.push(item);console.log(JSON.stringify({kind,accepted:true}));
      const started=Date.now();let job,media;
      do{
        job=await api('/api/v1/crusher/jobs/'+receipt.job_id);
        if(kind==='audio'&&!media)media=inspect(receipt.job_id).results?.['media-upload'];
        if(item.last_stage!==job.stage){item.last_stage=job.stage;console.log(JSON.stringify({kind,stage:job.stage,state:job.state}));}
        if(['COMPLETED','FAILED'].includes(job.state))break;
        await new Promise(resolve=>setTimeout(resolve,1000));
      }while(Date.now()-started<240000);
      item.state=job.state;item.error=job.error;item.seconds=Math.round((Date.now()-started)/1000);
      assert.ok(!('path' in job)&&!('result' in job));item.progress_only=true;
      const record=inspect(receipt.job_id);assert.equal(record.models.text,'gemini-3.8-flash');
      item.stages=record.transitions.map(s=>s.state);item.budget=record.budget;item.attempts=record.attempts;
      if(record.commit){
        item.placement=record.commit.placement;
        const note=await api('/api/note?'+new URLSearchParams({path:record.commit.path}));
        assert.equal(note.sha256,record.commit.sha256);assert.ok(note.text.includes(receipt.job_id));
        fs.writeFileSync(path.join(out,kind+'-result.md'),note.text);item.canonical_digest_verified=true;
        const markdown=note.text.split('<!-- mastermind:crusher')[0].trim();
        item.markdown_format_ok=!(markdown.includes('\\n')&&!markdown.includes('\n'));
        if(kind==='file'||kind==='audio'){
          const body=note.text.split('<!-- mastermind:crusher')[0];
          item.facts={cedar:/cedar/i.test(body),three:/three|\b3\b/i.test(body),ten:/ten|\b10\b/i.test(body),root:/root/i.test(body)};
        }
        media=media||record.results?.['media-upload'];
        if(media){
          item.remote_media_cleanup=JSON.parse(execFileSync('docker',['exec','-i',container,'python','-',media.name],{encoding:'utf8',input:`import json,sys,ssl,httpx
from mastermind.config import Config
from mastermind.kernel import Kernel
from mastermind.secret_store import ShellSecrets,read_credential_file
c=Config.environment()
k=Kernel(c.kernel_url,lambda:read_credential_file(c.kernel_token_file),client=httpx.Client(verify=ssl.create_default_context(cafile=c.trust_ca_file),trust_env=False))
s=ShellSecrets(c.secret_directory,k)
with httpx.Client(base_url='https://generativelanguage.googleapis.com',trust_env=False,follow_redirects=False,timeout=15) as client:
 headers={'x-goog-api-key':s.read('ai_provider_key')}
 r=client.get('/v1beta/'+sys.argv[1],headers=headers)
 # Google may return 403 for an already deleted identity; verify absence
 # against a successful complete listing, never infer deletion from 403.
 present=False;cursor=None;complete=False;list_status=None
 for _ in range(10):
  listing=client.get('/v1beta/files',params={'pageSize':100,**({'pageToken':cursor} if cursor else {})},headers=headers)
  list_status=listing.status_code
  if list_status!=200:break
  body=listing.json();present=present or any(f.get('name')==sys.argv[1] for f in body.get('files',[]))
  cursor=body.get('nextPageToken')
  if not cursor:complete=True;break
 print(json.dumps({'get_http_status':r.status_code,'list_http_status':list_status,'complete_listing':complete,'deleted':complete and not present}))
k.close()
`}));
        }
        await api('/api/note','DELETE',{path:record.commit.path,expected_sha256:note.sha256});item.test_note_removed=true;
      }
      fs.writeFileSync(path.join(out,kind+'-evidence.json'),JSON.stringify(item,null,2));
      assert.equal(job.state,'COMPLETED','Live '+kind+' pipeline: '+(job.error?.code||job.state));
      assert.equal(item.markdown_format_ok,true,'Markdown must contain actual line breaks.');
      if(item.facts)assert.ok(Object.values(item.facts).every(Boolean),'Preserve the synthetic source facts.');
      if(kind==='audio')assert.equal(item.remote_media_cleanup?.deleted,true,'Verify remote media cleanup.');
      if(kind==='placement')assert.equal(item.placement?.anchor,'Integration/Integration key.md','Unambiguous source should reach the matching key branch.');
    }
    // Canonical writes/deletes trigger asynchronous semantic reindexing.
    result.after_status=(await ready()).status;
    result.neptune=(await api('/api/owner/agents')).neptune.state;
  }finally{
    fs.writeFileSync(path.join(out,'latest-run.json'),JSON.stringify(result,null,2));
    if(session)await api('/api/auth/logout','POST',{}).catch(()=>{});await browser.close();
  }
  console.log(JSON.stringify({result:'PASS',cases:result.cases.map(i=>({kind:i.kind,state:i.state,seconds:i.seconds})),status:result.after_status}));
})().catch(error=>{console.error(error.name+': '+error.message);process.exitCode=1;});
