const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
  const root=path.resolve(__dirname,'..'),origin='http://localhost:18390';
  async function login(){
    const response=await fetch(origin+'/api/auth/login',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json'},
      body:JSON.stringify({access_key:fs.readFileSync(path.join(root,'.local/secrets/core/bootstrap_access_key'),'utf8')})});
    assert.equal(response.status,200);return{Origin:origin,'X-CSRF-Token':(await response.json()).csrf,
      Cookie:response.headers.getSetCookie().map(item=>item.split(';')[0]).join('; ')};
  }
  let headers=await login();
  for(let i=0;i<90;i++){
    const state=await (await fetch(origin+'/api/status',{headers})).json();if(state.runtime?.bridge?.ready)break;
    assert.ok(i<89,'Initial Runtime did not become ready');await new Promise(resolve=>setTimeout(resolve,500));
  }
  const response=await fetch(origin+'/qualification/restore',{method:'POST',headers});
  const result=await response.json();assert.equal(response.status,200,JSON.stringify(result));
  assert.equal(result.native_restore,'PASS');assert.equal(result.verification_copy_removed,true);
  assert.equal((await fetch(origin+'/api/status',{headers})).status,401,'Restore kept an old owner session');
  headers=await login();
  for(let i=0;i<90;i++){
    const state=await (await fetch(origin+'/api/status',{headers})).json();if(state.runtime?.bridge?.ready&&state.runtime.startup_allowed)break;
    assert.ok(i<89,'Restored Runtime did not become ready');await new Promise(resolve=>setTimeout(resolve,500));
  }
  console.log(JSON.stringify({...result,old_session:'REVOKED',owner_relogin:'PASS',restored_runtime:'READY'}));
})().catch(error=>{console.error(error.message);process.exitCode=1;});
