// External canonical HTTPS checks against the disposable real Nginx/Ubuntu host.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),https=require('node:https');
const {execFileSync}=require('node:child_process');
const {chromium}=require('./lib/browser.cjs');
const root=path.resolve(__dirname,'..'),origin='https://mastermind.qualification.test';
function request(route,headers={},servername='mastermind.qualification.test',body){return new Promise((resolve,reject)=>{
  const req=https.request({hostname:'127.0.0.1',port:18445,servername,rejectUnauthorized:false,path:route,
    method:body===undefined?'GET':'POST',headers:{Host:'mastermind.qualification.test',...headers}},res=>{
    let text='';res.on('data',data=>{text+=data;if(text.length>2*1024*1024)req.destroy(Error('Response bound'));});
    res.on('end',()=>resolve({http:res.statusCode,headers:res.headers,text}));
  });req.setTimeout(10000,()=>req.destroy(Error('Deadline')));req.on('error',reject);req.end(body);
});}
(async()=>{
  const results=[];
  const health=await request('/healthz');assert.equal(health.http,200);assert.deepEqual(JSON.parse(health.text),{status:'ok'});
  for(const name of ['x-robots-tag','referrer-policy','x-content-type-options','strict-transport-security'])assert.ok(health.headers[name]);
  results.push('minimal public liveness and security headers');
  for(const route of ['/readyz','/internal/status','/api/internal/neptune/backup','/v1/status','/openapi.json','/docs','/metrics','/.env','/sitemap.xml']){
    assert.equal((await request(route)).http,404,route);
  }
  results.push('concealed endpoints, inventories and configuration return 404');
  for(const headers of [{},{'User-Agent':'Googlebot','X-Verified-Bot':'true','X-Forwarded-For':'127.0.0.1','Forwarded':'for=127.0.0.1;proto=https'}]){
    assert.equal((await request('/api/notes',headers)).http,401);
    assert.equal((await request('/runtime/index.html',headers)).http,401);
  }
  results.push('anonymous and forged trusted clients cannot reach owner content');
  await assert.rejects(request('/healthz',{Host:'foreign.example'}));
  await assert.rejects(request('/healthz',{},'foreign.example'));
  results.push('Host and SNI reject foreign authority');
  assert.equal((await request('/api/auth/login',{'Content-Type':'application/json'},undefined,'x'.repeat(257*1024))).http,413);
  const marker='edge-capability-redaction-'+Date.now();await request('/s/'+marker+'?secret='+marker);
  await request('/healthz?secret='+marker);
  results.push('ingress request bound and private capability route exercised');
  const browser=await chromium.launch({headless:true,args:['--host-resolver-rules=MAP mastermind.qualification.test 127.0.0.1:18445']});
  try{
    const context=await browser.newContext({ignoreHTTPSErrors:true});const page=await context.newPage();await page.goto(origin+'/login');
    const key=execFileSync('docker',['exec','mastermind-qualification-host','cat','/opt/exocortex/mastermind/secrets/core/bootstrap_access_key'],{encoding:'utf8'});
    const session=await page.evaluate(async access_key=>{const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({access_key})});return {http:r.status,...await r.json()};},key);
    assert.equal(session.http,200);
    const cookies=await context.cookies();const owner=cookies.find(cookie=>cookie.httpOnly);assert.ok(owner);
    assert.equal(owner.secure,true);assert.equal(owner.sameSite,'Strict');assert.equal(owner.domain,'mastermind.qualification.test');
    const forbidden=await page.evaluate(async()=>{const r=await fetch('/api/notes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:'Should not exist.md',text:'Rejected'})});return r.status;});assert.equal(forbidden,403);
    const logout=await page.evaluate(async csrf=>{const r=await fetch('/api/auth/logout',{method:'POST',headers:{'X-CSRF-Token':csrf}});return r.status;},session.csrf);assert.equal(logout,200);
    assert.equal(await page.evaluate(async()=>(await fetch('/api/notes')).status),401);
    results.push('host-only secure session, CSRF rejection and logout invalidation');
  }finally{await browser.close();}
  const log=execFileSync('docker',['exec','mastermind-qualification-host','tail','-n','200','/var/log/nginx/mastermind-access.log'],{encoding:'utf8'});
  assert.ok(!log.includes(marker));assert.ok(log.includes('/s/[redacted]'));
  results.push('actual edge log omits capability and query values');
  fs.writeFileSync(path.join(root,'artifacts/host-edge.json'),JSON.stringify({status:'PASS',utc:new Date().toISOString(),checks:results},null,2));
  console.log('PASS real Nginx canonical HTTPS: '+results.join('; '));
})().catch(error=>{console.error(String(error.message).split('\n')[0]);process.exitCode=1;});
