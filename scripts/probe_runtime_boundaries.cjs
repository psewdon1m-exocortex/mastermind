const {chromium}=require('./lib/browser.cjs');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
  const root=path.resolve(__dirname,'..'),origin='http://localhost:18390',browser=await chromium.launch({headless:true});
  try{
    const context=await browser.newContext({viewport:{width:1440,height:1000}});
    const login=await context.request.post(origin+'/api/auth/login',{data:{access_key:fs.readFileSync(path.join(root,'.local/secrets/core/bootstrap_access_key'),'utf8')},headers:{Origin:origin}});
    assert.equal(login.status(),200);const csrf=(await login.json()).csrf;
    const page=await context.newPage();let opened=0,closed=0;
    page.on('websocket',socket=>{if(socket.url().includes('/runtime/websockify')){opened++;socket.on('close',()=>closed++);}});
    await page.goto(origin+'/runtime/index.html?autoconnect=1&path=runtime/websockify&resize=remote');await page.waitForTimeout(3500);
    assert.equal(opened,1);assert.equal(closed,0);
    await page.mouse.click(710,250);await page.keyboard.press('Escape');await page.keyboard.press('Control+o');
    await page.keyboard.type('Runtime test',{delay:40});await page.keyboard.press('Enter');await page.waitForTimeout(900);
    const before=await page.evaluate(async()=>(await fetch('/api/note?path=Runtime%20test.md')).json());
    const marker='Dirty buffer '+Date.now();await page.keyboard.press('Control+End');await page.keyboard.press('Enter');
    await page.keyboard.type(marker,{delay:30});await page.waitForTimeout(150);
    const conflict=await page.evaluate(async({csrf,sha})=>{
      const response=await fetch('/api/note',{method:'PUT',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
        body:JSON.stringify({path:'Runtime test.md',text:'This stale save must not win',expected_sha256:sha})});return response.status;
    },{csrf,sha:before.sha256});
    assert.equal(conflict,409);
    const after=await page.evaluate(async()=>(await fetch('/api/note?path=Runtime%20test.md')).json());
    assert.ok(after.text.includes(marker),'Owner dirty text was lost');assert.ok(!after.text.includes('stale save'));
    assert.equal(closed,0,'Mutation should preserve the authenticated VNC transport');
    const start=Date.now();const logout=await page.evaluate(async csrf=>(await fetch('/api/auth/logout',{method:'POST',headers:{'X-CSRF-Token':csrf}})).status,csrf);
    assert.equal(logout,200);
    while(closed===0&&Date.now()-start<3000)await page.waitForTimeout(50);
    assert.ok(closed>0,'Revocation left the existing Runtime transport open');
    const reconnect=await page.evaluate(()=>new Promise(resolve=>{
      const socket=new WebSocket('ws://localhost:18390/runtime/websockify',['binary']);
      socket.onopen=()=>{socket.close();resolve('opened');};socket.onclose=()=>resolve('denied');socket.onerror=()=>resolve('denied');
    }));assert.equal(reconnect,'denied');
    console.log(JSON.stringify({dirty_buffer_conflict:'PASS',owner_text_preserved:'PASS',active_socket_revoke:'PASS',reconnect:'DENIED',revoke_ms:Date.now()-start}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
