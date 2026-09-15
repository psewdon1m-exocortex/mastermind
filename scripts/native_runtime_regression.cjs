// Owner-approved bounded native regression; this does not claim long-duration stability.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {execFileSync}=require('node:child_process');
const {chromium}=require('./lib/browser.cjs');
const root=path.resolve(__dirname,'..'),port=Number(process.env.SOAK_PORT||18394),origin='http://localhost:'+port;
const project=process.env.SOAK_PROJECT||'mastermind-runtime-soak';
assert.match(project,/^mastermind-runtime-soak(?:-[a-z0-9-]+)?$/);assert.ok(Number.isInteger(port)&&port>1024&&port<65536);
const credentials=path.resolve(root,process.env.SOAK_CREDENTIAL_ROOT||'.local/'+project.replace(/^mastermind-/,''));
assert.ok(credentials.startsWith(path.join(root,'.local')+path.sep));
const output=path.resolve(root,process.env.SOAK_OUTPUT||'artifacts/native-runtime-regression');
if(!output.startsWith(path.join(root,'artifacts')+path.sep))throw Error('Soak output must stay in the artifacts directory');
fs.mkdirSync(output,{recursive:true});
const maximumDuration=15*60*1000,requiredCheckpoints=6;
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const log=data=>{const line=JSON.stringify({utc:new Date().toISOString(),...data});fs.appendFileSync(path.join(output,'events.jsonl'),line+'\n');console.log(line);};
function inspect(){return ['core','runtime'].map(name=>{const state=JSON.parse(execFileSync('docker',['inspect',project+'-'+name+'-1'],{encoding:'utf8'}))[0];
  return {name,image:state.Image,started:state.State.StartedAt,restarts:state.RestartCount,oom:state.State.OOMKilled,
    memory:Number(execFileSync('docker',['exec',state.Id,'cat','/sys/fs/cgroup/memory.current'],{encoding:'utf8'}).trim())};});}
(async()=>{
  const lock=path.join(credentials,'running.lock');const handle=fs.openSync(lock,'wx');fs.writeSync(handle,String(process.pid));
  let browser;
  try{
    browser=await chromium.launch({headless:true});const context=await browser.newContext({viewport:{width:1440,height:1000}});
    const login=await context.request.post(origin+'/api/auth/login',{headers:{Origin:origin},data:{access_key:fs.readFileSync(path.join(credentials,'core/bootstrap_access_key'),'utf8')}});
    assert.equal(login.status(),200);const csrf=(await login.json()).csrf,headers={Origin:origin,'X-CSRF-Token':csrf};
    async function api(route,method='GET',data){const response=await context.request.fetch(origin+route,{method,headers,data,timeout:180000});
      assert.equal(response.status(),200,route+' HTTP '+response.status());return response.json();}
    async function ready(){for(let i=0;i<120;i++){const state=await api('/api/status');if(state.runtime?.bridge?.ready&&state.runtime.startup_allowed)return state;
      await sleep(500);}throw Error('Runtime did not become ready');}
    const page=await context.newPage();let connections=0,frames=0;page.on('websocket',socket=>{if(socket.url().includes('websockify')){connections++;socket.on('framereceived',()=>frames++);}});
    async function connect(){await page.goto(origin+'/runtime/index.html?autoconnect=1&path=runtime/websockify&resize=remote');await sleep(3000);}
    await connect();
    if(process.argv.includes('--inspect')){await page.screenshot({path:path.join(output,'initial.png')});log({status:'INSPECT_ONLY',containers:inspect()});return;}
    if(process.argv.includes('--trust-generated-fixture')){await page.mouse.click(880,608);await sleep(3000);}
    if(process.argv.includes('--close-first-settings')){await page.mouse.click(1418,14);await sleep(700);}
    if(process.argv.includes('--setup-only')){await page.screenshot({path:path.join(output,'after-setup.png')});log({status:'SETUP_ONLY',containers:inspect()});return;}
    const initial=await ready(),baseline=inspect(),started=Date.now(),run=crypto.randomBytes(6).toString('hex');
    log({status:'STARTED',profile:'bounded-native-regression',required_checkpoints:requiredCheckpoints,maximum_ms:maximumDuration,run,containers:baseline,bridge:initial.runtime.bridge});
    const initialNote=await api('/api/note?path=Runtime%20soak.md');let expected=initialNote.text,checkpoints=0;
    async function openNote(){await page.mouse.click(650,500);await page.keyboard.press('Control+o');await sleep(300);await page.keyboard.type('Runtime soak');await sleep(400);await page.keyboard.press('Enter');await sleep(700);}
    await openNote();let coordinatedMutations=0,portableExports=0,exportBytes=0;
    while(checkpoints<requiredCheckpoints){
      assert.ok(Date.now()-started<maximumDuration,'Native regression exceeded its bounded execution time');
      const elapsed=Date.now()-started;await api('/api/auth/session');await ready();
      {
        const editStarted=Date.now();
        await openNote();await page.keyboard.press('Escape');await page.mouse.click(720,450);await page.keyboard.press('Control+End');
        const marker='\nSOAK '+run+' '+checkpoints+'\n';await page.keyboard.type(marker,{delay:15});
        const inputSent=Date.now();let note;
        while(Date.now()-inputSent<60000){await sleep(250);note=await api('/api/note?path=Runtime%20soak.md');if(note.text.includes(marker.trim()))break;}
        if(!note.text.includes(marker.trim())){await page.screenshot({path:path.join(output,'save-failed.png')});throw Error('Native editor checkpoint was not saved');}
        assert.ok(note.text.includes(expected.trim()),'Earlier canonical text changed');
        assert.equal(note.text.split(marker.trim()).length,2,'Duplicate native checkpoint');expected=note.text;checkpoints++;
        log({event:'NATIVE_SAVE',elapsed_ms:Date.now()-started,checkpoints,sha256:note.sha256,input_ms:inputSent-editStarted,save_wait_ms:Date.now()-inputSent});
      }
      if(checkpoints===2||checkpoints===4){const before=Date.now();await api('/api/notes','POST',{path:'Soak pulse '+run+' '+checkpoints+'.md',text:'# Pulse\n\n@root\n'});await ready();await connect();coordinatedMutations++;
        log({event:'COORDINATED_RESTART',elapsed_ms:Date.now()-started,pause_ms:Date.now()-before});}
      if(checkpoints===3){
        // Native fetch streams; Playwright APIResponse would retain the complete archive in memory.
        const cookies=await context.cookies(origin),cookie=cookies.map(item=>item.name+'='+item.value).join('; '),before=Date.now();
        const response=await fetch(origin+'/api/exports/portable',{method:'POST',headers:{...headers,Cookie:cookie},signal:AbortSignal.timeout(180000)});
        assert.equal(response.status,200);let bytes=0;const hash=crypto.createHash('sha256');for await(const chunk of response.body){bytes+=chunk.length;hash.update(chunk);}
        assert.ok(bytes>=350*1024**2);assert.equal(bytes,Number(response.headers.get('content-length')));await ready();await connect();
        portableExports++;exportBytes=bytes;
        log({event:'STREAMED_EXPORT',elapsed_ms:Date.now()-started,duration_ms:Date.now()-before,bytes,sha256:hash.digest('hex')});
      }
      {const states=inspect();for(let i=0;i<states.length;i++){assert.equal(states[i].started,baseline[i].started);assert.equal(states[i].restarts,baseline[i].restarts);assert.equal(states[i].oom,false);}
        assert.ok(connections&&frames,'VNC session did not transmit frames');await page.screenshot({path:path.join(output,'checkpoint-'+checkpoints+'.png')});
        log({event:'HEALTH',elapsed_ms:Date.now()-started,connections,frames,containers:states});}
    }
    const note=await api('/api/note?path=Runtime%20soak.md');assert.equal(note.text,expected);await api('/api/auth/session');
    assert.ok(Date.now()-started<=maximumDuration);assert.ok(connections>=3);assert.equal(coordinatedMutations,2);assert.equal(portableExports,1);
    const result={schema:'mastermind.native-runtime-regression.v1',status:'PASS',revision:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),
      elapsed_ms:Date.now()-started,checkpoints,connections,frames,coordinated_mutations:coordinatedMutations,portable_exports:portableExports,export_bytes:exportBytes,
      content_preserved:true,single_copy_markers:true,long_duration_stability:'NOT_TESTED_BY_OWNER_DECISION',containers:inspect()};
    fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(result,null,2));log(result);
  }finally{if(browser)await browser.close();fs.closeSync(handle);fs.unlinkSync(lock);}
})().catch(error=>{const result={status:'FAIL',failed_at:new Date().toISOString(),message:String(error.message).split('\n')[0]};
  fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(result,null,2));log(result);process.exitCode=1;});
