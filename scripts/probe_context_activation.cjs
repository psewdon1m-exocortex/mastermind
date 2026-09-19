// Read-only final stand checks, plus an explicitly requested candidate restart.
const assert=require('node:assert/strict'),fs=require('node:fs'),crypto=require('node:crypto');
const {execFileSync}=require('node:child_process');const {chromium}=require('./lib/browser.cjs');
const origin='http://localhost:18390';
(async()=>{
 const browser=await chromium.launch({headless:true}),context=await browser.newContext();
 const get=async(route)=>{const r=await context.request.get(origin+route);assert.ok(r.ok(),route+': '+r.status());return r.json();};
 const login=async()=>{const r=await context.request.post(origin+'/api/auth/login',{headers:{Origin:origin},data:{access_key:fs.readFileSync('.local/secrets/core/bootstrap_access_key','utf8')}});assert.equal(r.status(),200);};
 const ready=async()=>{for(let i=0;i<120;i++){try{const status=await get('/api/status'),configuration=await get('/api/owner/context-indexing/settings');if(status.status==='HEALTHY'&&configuration.readiness.search.status==='READY'&&configuration.readiness.curator.ready)return {status,configuration};}catch(error){if(error.message.endsWith(': 401'))await login();}await new Promise(r=>setTimeout(r,1000));}throw new Error('Final stand readiness timeout');};
 try{
  await login();
  const before=await ready();assert.equal(before.configuration.retrieval.curator_enabled,false);
  const template=await get('/api/note?'+new URLSearchParams({path:before.configuration.crusher.template_path}));
  const resources=await get('/api/owner/resources?limit=5');assert.ok(Array.isArray(resources.entries));
  const entry=resources.entries.find(v=>v.type==='file'&&v.size>0&&v.size<=4096);
  let content=false;if(entry){const r=await context.request.get(origin+'/api/owner/resources/content?'+new URLSearchParams({path:entry.path}));assert.ok(r.ok());assert.equal((await r.body()).length,entry.size);content=true;}
  if(process.argv.includes('--restart')){
   execFileSync('docker',['restart','mastermind-development-worker-1','mastermind-development-core-1'],{stdio:'pipe',timeout:90000});
   // This host-agent fixture shares Core's network namespace; recreate it after Core.
   execFileSync('docker',['compose','-f','.local/integration/compose.yml','up','-d','--no-deps','--force-recreate','neptune'],{stdio:'pipe',timeout:90000});
  }
  const after=await ready();assert.deepEqual(after.configuration.crusher,before.configuration.crusher);assert.equal(after.configuration.revision,before.configuration.revision);assert.equal(after.configuration.retrieval.curator_enabled,false);
  assert.equal((await get('/api/note?'+new URLSearchParams({path:after.configuration.crusher.template_path}))).sha256,template.sha256);
  const native=JSON.parse(fs.readFileSync('artifacts/context-indexing-native/report.json','utf8'));
  for(const row of native.cases){const r=await context.request.get(origin+'/api/note?'+new URLSearchParams({path:row.path}));assert.equal(r.status(),404,'Deleted qualification output reappeared after restart');}
  const report={status:'PASS',origin,health:after.status.status,revision:after.configuration.revision,template_sha256:template.sha256,curator_enabled:false,curator_ready:after.configuration.readiness.curator.ready,search:after.configuration.readiness.search,restart:process.argv.includes('--restart'),neptune_saturn_listing:true,neptune_saturn_content:content,resource_entries:resources.entries.length,completed_jobs_not_replayed:true};
  report.images={};for(const component of ['core','runtime','worker'])report.images[component]=JSON.parse(execFileSync('docker',['inspect','mastermind-development-'+component+'-1','--format','{{json .Image}}'],{encoding:'utf8'}));
  report.calibration_sha256=crypto.createHash('sha256').update(fs.readFileSync('src/mastermind/context_indexing/calibration.json')).digest('hex');
  fs.writeFileSync('artifacts/context-indexing-activation.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
