// Bounded smoke for the explicitly configured local provider fixture. Never
// dispatches a paid request and removes only the note committed by this probe.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {execFileSync}=require('node:child_process');
const {chromium,firefox}=require('./lib/browser.cjs');
const origin='http://localhost:18390',container='mastermind-development-core-1';
(async()=>{
  const entry=JSON.parse(execFileSync('docker',['inspect',container,'--format','{{json .Config.Entrypoint}}'],{encoding:'utf8'}));
  assert.ok(entry.includes('core_fixture:create_app'),'This probe is restricted to the explicitly configured local fixture.');
  const browser=await (process.argv.includes('--firefox')?firefox:chromium).launch({headless:true}),context=await browser.newContext();let session,jobId;
  const api=async(route,method='GET',data)=>{const r=await context.request.fetch(origin+route,{method,headers:{Origin:origin,...(session?{'X-CSRF-Token':session.csrf}:{}),'Idempotency-Key':'readiness-'+run},...(data?{data}:{})});assert.ok(r.ok(),`${route}: ${r.status()}`);return r.json();};
  const run=crypto.randomUUID(),result={provider_mode:'controlled local Gemini REST fixture',live_google_api:false,browser:browser.version()};
  try{
    session=await api('/api/auth/login','POST',{access_key:fs.readFileSync('.local/secrets/core/bootstrap_access_key','utf8')});
    const before=await api('/api/status');assert.equal(before.status,'HEALTHY');
    const text=`Local verification ${run}. Hierarchical knowledge organizes facts under main branches and nested key notes. This is a disposable service smoke-test source.`;
    if(process.argv.includes('--file-ui')){
      const page=await context.newPage();await page.goto(origin+'/crusher');await page.getByLabel('Source links',{exact:true}).waitFor();assert.equal(await page.locator('select').count(),0);
      const accepted=page.waitForResponse(r=>r.url()===origin+'/api/v1/crusher/jobs'&&r.request().method()==='POST');
      if(process.argv.includes('--drop')){
        const transfer=await page.evaluateHandle(text=>{const value=new DataTransfer();value.items.add(new File([text],'crusher-verification.txt',{type:'text/plain'}));return value;},text);
        await page.dispatchEvent('body','dragenter',{dataTransfer:transfer});await page.locator('.file-drag-overlay').waitFor({state:'visible'});
        await page.locator('.crusher-dropzone').dispatchEvent('drop',{dataTransfer:transfer});await transfer.dispose();
      }else await page.getByLabel('Source files',{exact:true}).setInputFiles({name:'crusher-verification.txt',mimeType:'text/plain',buffer:Buffer.from(text)});
      const response=await accepted;assert.ok(response.ok(),await response.text());jobId=(await response.json()).job_id;
      await page.getByText('1 source accepted.',{exact:true}).first().waitFor();result.input='Real browser '+(process.argv.includes('--drop')?'drag and drop':'file selection')+', hashing, upload, digest verification and acceptance';
    }else{const receipt=await api('/api/v1/crusher/jobs','POST',{type:'text',text});jobId=receipt.job_id;}
    let job;const deadline=Date.now()+60000;
    do{job=await api('/api/v1/crusher/jobs/'+jobId);if(['COMPLETED','FAILED'].includes(job.state))break;await new Promise(resolve=>setTimeout(resolve,700));}while(Date.now()<deadline);
    assert.equal(job.state,'COMPLETED',JSON.stringify(job));assert.equal(job.progress_percent,100);assert.ok(!('path' in job)&&!('result' in job));
    const inspect=`import json,sqlite3,sys\nfrom mastermind.config import Config\nc=Config.environment()\ndb=sqlite3.connect('file:'+str(c.state/'mastermind.sqlite3')+'?mode=ro',uri=True)\nr=json.loads(db.execute('SELECT record FROM jobs WHERE id=?',(sys.argv[1],)).fetchone()[0])\nprint(json.dumps({k:r[k] for k in ['models','transitions','commit','budget']}))`;
    const record=JSON.parse(execFileSync('docker',['exec','-i',container,'python','-',jobId],{input:inspect,encoding:'utf8'}));
    result.status=before.status;result.pipeline=job.state;result.models=record.models;result.stages=record.transitions.map(item=>item.state);result.placement={confidence:record.commit.placement.confidence,fallback:record.commit.placement.diagnostic};
    const note=await api('/api/note?'+new URLSearchParams({path:record.commit.path}));assert.ok(note.text.includes(jobId));assert.equal(note.sha256,record.commit.sha256);
    await api('/api/note','DELETE',{path:record.commit.path,expected_sha256:note.sha256});result.probe_note_removed=true;result.progress_only_response=true;
    const out=path.resolve(process.argv.includes('--firefox')?'artifacts/hashing-fix':process.argv.includes('--file-ui')?'artifacts/public-editing-20260919':'artifacts/shared-ui-20260919');fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,process.argv.includes('--drop')?'crusher-drop-readiness.json':'crusher-readiness.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
  }finally{if(session)await api('/api/auth/logout','POST',{}).catch(()=>{});await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
