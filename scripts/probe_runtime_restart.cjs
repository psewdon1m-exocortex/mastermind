const {chromium}=require('C:/Users/pc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
(async()=>{
  const root=path.resolve(__dirname,'..'),origin='http://localhost:18390',browser=await chromium.launch({headless:true});
  const coreStarted=()=>execFileSync('docker',['inspect','--format','{{.State.StartedAt}}','mastermind-development-core-1'],{encoding:'utf8'}).trim();
  try{
    const context=await browser.newContext({viewport:{width:1440,height:1000}});
    const login=await context.request.post(origin+'/api/auth/login',{headers:{Origin:origin},data:{access_key:fs.readFileSync(path.join(root,'.local/secrets/core/bootstrap_access_key'),'utf8')}});
    assert.equal(login.status(),200);const csrf=(await login.json()).csrf,headers={Origin:origin,'X-CSRF-Token':csrf};
    let initial;
    for(let attempt=0;attempt<60;attempt++){
      initial=await (await context.request.get(origin+'/api/status')).json();
      if(initial.runtime?.bridge?.ready)break;
      await new Promise(resolve=>setTimeout(resolve,500));
    }
    assert.equal(initial.runtime?.bridge?.protocol_version,1);assert.equal(initial.runtime?.bridge?.ready,true);
    const previous=await context.request.get(origin+'/api/note',{params:{path:'Runtime restart.md'}});
    const body={path:'Runtime restart.md',text:'Saved text before independent Runtime restart.'};
    const write=previous.status()===200?await context.request.put(origin+'/api/note',{headers,data:{...body,expected_sha256:(await previous.json()).sha256}}):await context.request.post(origin+'/api/notes',{headers,data:body});
    assert.equal(write.status(),200);const before=coreStarted(),start=Date.now();
    execFileSync('docker',['restart','mastermind-development-runtime-1'],{stdio:'pipe'});
    let ready=false;
    for(let attempt=0;attempt<90;attempt++){
      try{
        const response=await context.request.get(origin+'/api/status',{timeout:10000});
        const state=await response.json();
        if(state.runtime?.bridge?.ready&&state.runtime?.startup_allowed){ready=true;break;}
      }catch{}
      await new Promise(resolve=>setTimeout(resolve,500));
    }
    assert.ok(ready,'Runtime did not recover automatically');assert.equal(coreStarted(),before,'Core restarted instead of adopting Runtime');
    const note=await (await context.request.get(origin+'/api/note',{params:{path:body.path}})).json();assert.equal(note.text,body.text);
    const page=await context.newPage();let sockets=0;
    page.on('websocket',socket=>{if(socket.url().includes('websockify'))sockets++;});
    await page.goto(origin+'/runtime/index.html?autoconnect=1&path=runtime/websockify&resize=remote');
    await page.waitForTimeout(2000);assert.equal(sockets,1);
    await page.screenshot({path:path.join(root,'artifacts/runtime-restarted.png')});
    console.log(JSON.stringify({independent_runtime_restart:'PASS',core_process:'UNCHANGED',canonical_text:'PRESERVED',gateway_reconnect:'PASS',elapsed_ms:Date.now()-start}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
