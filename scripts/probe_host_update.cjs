// Real canonical HTTPS -> own Updater -> signed immutable three-image apply.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const {chromium}=require('./lib/browser.cjs');
const root=path.resolve(__dirname,'..'),origin='https://mastermind.qualification.test';
const version=process.argv[2]||'0.0.2';assert.match(version,/^\d+\.\d+\.\d+$/);
const manual=process.argv.includes('--manual-rollback');
const outfile=path.join(root,'artifacts/host-'+(manual?'manual-rollback-':'update-')+version+(process.argv.includes('--review')?'.review':'')+'.json');
(async()=>{
  const key=execFileSync('docker',['exec','mastermind-qualification-host','cat','/opt/exocortex/mastermind/secrets/core/bootstrap_access_key'],{encoding:'utf8'});
  const browser=await chromium.launch({headless:true,args:['--host-resolver-rules=MAP mastermind.qualification.test 127.0.0.1:18445']});
  const started=Date.now(),events=[];
  try{
    const context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1600,height:1000}});
    const page=await context.newPage();await page.goto(origin+'/settings');
    async function login(){return page.evaluate(async key=>{const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({access_key:key})});if(!r.ok)throw Error('Login HTTP '+r.status);return (await r.json()).csrf;},key);}
    let csrf=await login();
    async function api(route,method='GET',data){return page.evaluate(async({route,method,data,csrf})=>{
      const r=await fetch(route,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:data?JSON.stringify(data):undefined});
      let result;try{result=await r.json();}catch{result={};}return {http:r.status,...result};
    },{route,method,data,csrf});}
    const note='After successful update '+Date.now()+'.md',body='New data created before returning to a previous compatible version.\n';
    let preservation;
    if(!process.argv.includes('--review')){
      let accepted;
      if(manual){
        const options=await api('/api/owner/updates/rollback');assert.equal(options.available,true,JSON.stringify(options));
        assert.equal(options.version,version);assert.equal(options.preserves_current_data,true);
        const created=await api('/api/notes','POST',{path:note,text:body});assert.equal(created.http,200,JSON.stringify(created));
        preservation={path:note,text:body,job_id:options.job_id};
        accepted=await api('/api/owner/updates/rollback','POST',{job_id:options.job_id});
      }else{
        const discovery=await api('/api/owner/updates/check','POST',{});
        assert.equal(discovery.http,200,JSON.stringify(discovery));assert.equal(discovery.compatible,true);
        accepted=await api('/api/owner/updates','POST',{version});
      }
      assert.equal(accepted.http,200,JSON.stringify(accepted));
    }
    let previous='',state;
    for(let tick=0;tick<1200;tick++){
      await page.waitForTimeout(1000);
      try{
        state=await api('/api/owner/updates');
        if(state.http===401){csrf=await login();state=await api('/api/owner/updates');}
      }catch{state={phase:'RECONNECTING'};}
      const phase=state.phase||'RECONNECTING';
      if(phase!==previous){const event={utc:new Date().toISOString(),phase,error:state.error};events.push(event);console.log(JSON.stringify(event));previous=phase;}
      if(['COMPLETED','FAILED','ROLLED_BACK'].includes(phase))break;
    }
    fs.writeFileSync(outfile,JSON.stringify({state,elapsed_ms:Date.now()-started,events,preservation},null,2));
    assert.equal(state.phase,process.argv.includes('--expect-rollback')?'ROLLED_BACK':'COMPLETED',JSON.stringify(state));
    const agents=await api('/api/owner/agents');
    if(!process.argv.includes('--expect-rollback'))assert.equal(agents.version,version);
    if(preservation){const read=await api('/api/note?path='+encodeURIComponent(note));assert.equal(read.http,200);assert.equal(read.text,body);}
    await page.goto(origin+'/settings');await page.waitForTimeout(2000);
    await page.screenshot({path:outfile.replace('.json','.png')});
    fs.writeFileSync(outfile.replace('.json','.verification.json'),JSON.stringify({status:'PASS',state,installed_version:agents.version,elapsed_ms:Date.now()-started,preservation},null,2));
    console.log('PASS signed actual-host group outcome '+state.phase+' for '+version);
  }finally{await browser.close();}
})().catch(error=>{const result={status:'FAIL',error:String(error.message).split('\n')[0]};console.error(JSON.stringify(result));process.exitCode=1;});
