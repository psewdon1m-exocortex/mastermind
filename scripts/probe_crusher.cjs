const { chromium } = require('./lib/browser.cjs');
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const assert = require('node:assert/strict'), { execFileSync } = require('node:child_process');

(async () => {
  const root = path.resolve(__dirname, '..'), origin = 'http://localhost:18390';
  const browser = await chromium.launch({headless: true});
  const owner = await browser.newContext(), visitor = await browser.newContext();
  const evidence = [], run = crypto.randomBytes(8).toString('hex');
  let ownerHeaders;
  const checked = async (response, status=200) => {
    if (response.status() !== status) {
      let code = 'UNKNOWN'; try { code = (await response.json()).error?.code || code; } catch {}
      throw new Error(`${response.request?.method || 'request'} ${new URL(response.url()).pathname}: HTTP ${response.status()} ${code}`);
    }
    return response.json();
  };
  const login = async () => {
    const session = await checked(await owner.request.post(origin+'/api/auth/login', {
      headers:{Origin:origin}, data:{access_key:fs.readFileSync(path.join(root,'.local/secrets/core/bootstrap_access_key'),'utf8')}}));
    ownerHeaders = {Origin:origin,'X-CSRF-Token':session.csrf};
  };
  const ensureNote = async (notePath, text, append=false) => {
    const previous = await owner.request.get(origin+'/api/note', {params:{path:notePath}});
    if (previous.status() === 200) {
      const current = await previous.json();
      if (append && !current.text.includes(text)) text = current.text+'\n'+text;
      else if (append) return;
      await checked(await owner.request.put(origin+'/api/note', {headers:ownerHeaders,data:{path:notePath,text,expected_sha256:current.sha256}}));
    } else await checked(await owner.request.post(origin+'/api/notes',{headers:ownerHeaders,data:{path:notePath,text}}));
  };
  const waitJob = async (receipt, expected='COMPLETED', restart=false) => {
    let previous = 0, restarted = false, stages = [];
    const until = Date.now()+180000;
    while (Date.now() < until) {
      const result = await checked(await visitor.request.get(origin+'/api/v1/crusher/jobs/'+receipt.job_id, {
        headers:{'X-Crusher-Status-Ticket':receipt.status_ticket}}));
      assert.deepEqual(Object.keys(result).sort(), ['job_id','source_label','state','stage','progress_percent','created_at','updated_at','error'].sort());
      assert.ok(!JSON.stringify(result).includes('Fixture knowledge'));
      assert.ok(result.progress_percent >= previous); previous = result.progress_percent;
      if (!stages.includes(result.stage)) stages.push(result.stage);
      if (restart && result.stage === 'GENERATING' && !restarted) {
        execFileSync('docker',['kill','--signal','KILL','mastermind-development-core-1'],{stdio:'pipe'});
        execFileSync('docker',['start','mastermind-development-core-1'],{stdio:'pipe'});
        restarted = true;
        for (let i=0;i<90;i++) {
          await new Promise(resolve=>setTimeout(resolve,500));
          try { if ((await visitor.request.get(origin+'/readyz')).status() === 200) break; } catch {}
        }
        await login();
      }
      if (['COMPLETED','FAILED'].includes(result.state)) {
        assert.equal(result.state,expected, result.error?.code);
        if (restart) assert.ok(restarted,'The real process interruption did not occur');
        evidence.push({job:receipt.job_id,state:result.state,stages,restarted}); return result;
      }
      await new Promise(resolve=>setTimeout(resolve,250));
    }
    throw new Error('Crusher fixture exceeded its bounded end-to-end wait');
  };
  const submit = async (source, principal=owner, headers=ownerHeaders, expected='COMPLETED', restart=false) => {
    const key = 'crusher-'+run+'-'+crypto.randomBytes(8).toString('hex');
    let accepted;
    for (let attempt=0;attempt<30;attempt++) {
      accepted = await principal.request.post(origin+'/api/v1/crusher/jobs',{headers:{...headers,'Idempotency-Key':key},data:source});
      // 100% denotes durable commit. Its immediate cleanup may still hold the
      // previous archive expansion reservation; retry only unaccepted capacity.
      if (accepted.status() !== 507) break;
      await new Promise(resolve=>setTimeout(resolve,500));
    }
    const receipt = await checked(accepted);
    await waitJob(receipt,expected,restart);
    console.log(JSON.stringify({source:source.type,job:receipt.job_id,outcome:expected}));
    const repeated = await checked(await principal.request.post(origin+'/api/v1/crusher/jobs',{
      headers:{...(principal === owner ? ownerHeaders : headers),'Idempotency-Key':key},data:source}));
    assert.equal(repeated.job_id,receipt.job_id);
    return receipt;
  };
  try {
    await login();
    await ensureNote('root.md','[[Integration branch]]',true);
    await ensureNote('Integration/Integration branch.md','#main\n\nKnowledge architecture\n\n[[Integration key]]');
    await ensureNote('Integration/Integration key.md','#key\n\nKnowledge architecture and semantic organization.');
    const access = await checked(await owner.request.post(origin+'/api/v1/crusher/access',{headers:ownerHeaders}));
    const session = await checked(await visitor.request.post(origin+'/api/v1/crusher/sessions',{data:{code:access.code}}));
    const publicHeaders = {Authorization:'Bearer '+session.token};
    assert.equal((await visitor.request.post(origin+'/api/v1/crusher/sessions',{data:{code:access.code}})).status(),401);
    assert.equal((await visitor.request.get(origin+'/api/notes',{headers:publicHeaders})).status(),401);
    assert.equal((await visitor.request.post(origin+'/api/v1/crusher/jobs',{headers:{...publicHeaders,'Idempotency-Key':'forbidden-'+run},data:{type:'saturn',path:'root/mastermind/Crusher fixture.txt'}})).status(),403);
    await submit({type:'text',text:'Knowledge architecture facts '+run});
    await submit({type:'text',text:'Public knowledge source '+run},visitor,publicHeaders);
    await submit({type:'text',text:'Knowledge retry fixture [RETRY_ONCE] '+run});
    await submit({type:'text',text:'Knowledge failure fixture [FAIL_SCHEMA] '+run},owner,ownerHeaders,'FAILED');
    for (const name of ['source.docx','legacy.doc','source.rtf','source.xlsx','scan.pdf','source.wav']) {
      const bytes = fs.readFileSync(path.join(root,'.local/integration/crusher',name));
      const upload = await checked(await owner.request.post(origin+'/api/v1/crusher/uploads',{headers:ownerHeaders,data:{name,size:bytes.length}}));
      await checked(await owner.request.put(origin+'/api/v1/crusher/uploads/'+upload.upload_id+'/content',{headers:{...ownerHeaders,'Content-Type':'application/octet-stream'},data:bytes}));
      await checked(await owner.request.post(origin+'/api/v1/crusher/uploads/'+upload.upload_id+'/complete',{headers:ownerHeaders,data:{sha256:crypto.createHash('sha256').update(bytes).digest('hex')}}));
      await submit({type:'upload',upload_id:upload.upload_id});
    }
    await submit({type:'youtube',url:'https://www.youtube.com/watch?v=abcdefghijk'});
    await submit({type:'url',url:'https://example.com/'});
    await submit({type:'git',url:'https://github.com/octocat/Hello-World.git'});
    await submit({type:'saturn',path:'root/mastermind/Crusher fixture.txt'});
    await submit({type:'text',text:'Knowledge crash fixture [HOLD_GENERATE] '+run},owner,ownerHeaders,'COMPLETED',true);
    const notes = await checked(await owner.request.get(origin+'/api/notes',{params:{limit:500}}));
    const matches = new Map(evidence.map(item=>[item.job,[]]));
    for (const note of notes.filter(note=>note.name.startsWith('Fixture knowledge'))) {
      const full = await checked(await owner.request.get(origin+'/api/note',{params:{path:note.path}}));
      for (const [job, found] of matches) if (full.text.includes('job_id: "'+job+'"')) found.push(note.path);
    }
    for (const result of evidence) assert.equal(matches.get(result.job).length,result.state==='COMPLETED'?1:0);
    for (let i=0;i<120;i++) {
      const status = await checked(await owner.request.get(origin+'/api/index/semantic'));
      if (status.status === 'READY') break;
      await new Promise(resolve=>setTimeout(resolve,500));
    }
    const semantic = await checked(await owner.request.get(origin+'/api/search/semantic',{params:{query:'knowledge architecture',limit:5}}));
    assert.equal(semantic.index.status,'READY'); assert.ok(semantic.results.length > 0);
    fs.writeFileSync(path.join(root,'artifacts/crusher-live.json'),JSON.stringify({provider:'CONTROLLED_REST_FIXTURE',actual_services:['Core','Worker','Obsidian','Kernel','Volt','Neptune','Saturn','SFTP'],jobs:evidence,local_commit:'EXACTLY_ONE',semantic:'PASS'},null,2));
    console.log(JSON.stringify({crusher:'PASS',jobs:evidence.length,local_commit:'EXACTLY_ONE',real_core_kill_restart:'PASS',local_semantic:'PASS',provider:'CONTROLLED_REST_FIXTURE'}));
  } finally { await browser.close(); }
})().catch(error=>{console.error(error.message);process.exitCode=1;});
