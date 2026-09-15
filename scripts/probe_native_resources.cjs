const {chromium}=require('./lib/browser.cjs');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
  const root=path.resolve(__dirname,'..'),origin='http://localhost:18390',browser=await chromium.launch({headless:true});
  try{
    const context=await browser.newContext({viewport:{width:1440,height:1000}});
    const login=await context.request.post(origin+'/api/auth/login',{data:{access_key:fs.readFileSync(path.join(root,'.local/secrets/core/bootstrap_access_key'),'utf8')},headers:{Origin:origin}});
    assert.equal(login.status(),200);const csrf=(await login.json()).csrf,headers={Origin:origin,'X-CSRF-Token':csrf};
    const fixture=JSON.parse(fs.readFileSync(path.join(root,'.local/integration/native-resources.json'),'utf8'));
    const text='# Native resources\n\n@chronos: '+fixture.event_id+'\n\n'+fixture.paths.map(p=>'@saturn: '+p).join('\n\n')+'\n';
    const previous=await context.request.get(origin+'/api/note',{params:{path:'Native resources.md'}});
    const write=previous.status()===200?await context.request.put(origin+'/api/note',{headers,data:{path:'Native resources.md',text,expected_sha256:(await previous.json()).sha256}}):await context.request.post(origin+'/api/notes',{headers,data:{path:'Native resources.md',text}});
    assert.equal(write.status(),200);
    const page=await context.newPage();await page.goto(origin+'/runtime/index.html?autoconnect=1&path=runtime/websockify&resize=remote');
    await page.waitForTimeout(3000);await page.mouse.click(700,250);await page.keyboard.press('Escape');await page.keyboard.press('Control+o');
    await page.keyboard.type('Native resources',{delay:40});await page.keyboard.press('Enter');
    await page.waitForTimeout(800);await page.keyboard.press('Control+Home');
    let state;const seen=new Set();
    for(let attempt=0;attempt<120;attempt++){
      await page.waitForTimeout(500);state=await (await context.request.get(origin+'/api/status')).json();
      const cards=(state.runtime?.bridge?.resources||[]).filter(c=>c.visible);
      if(cards.some(c=>c.kind==='chronos'&&c.state==='loaded'))seen.add('chronos');
      if(cards.some(c=>c.image_ready))seen.add('image');if(cards.some(c=>c.video_ready>=1))seen.add('video');
      if(cards.some(c=>c.audio_ready>=1))seen.add('audio');if(cards.some(c=>c.pdf))seen.add('pdf');
      if(seen.size===5)break;
      if(attempt>5&&attempt%4===0){await page.mouse.move(1050,700);await page.mouse.wheel(0,500);}
    }
    await page.screenshot({path:path.join(root,'artifacts/native-resources.png')});
    const cards=(state.runtime?.bridge?.resources||[]).filter(c=>c.visible);
    fs.writeFileSync(path.join(root,'artifacts/native-resources-diagnostics.json'),JSON.stringify({cards,media:state.runtime?.bridge?.media},null,2));
    assert.deepEqual([...seen].sort(),['audio','chronos','image','pdf','video']);
    assert.ok(state.runtime.bridge.media.range_responses>=1,'Native media did not use the Range proxy');
    const card=await (await context.request.get(origin+'/api/owner/external',{params:{kind:'chronos',target:fixture.event_id}})).json();
    assert.deepEqual(Object.keys(card).sort(),['kind','id','started_at','ended_at'].sort());
    assert.ok(!JSON.stringify(card).includes('CANARY'));
    console.log(JSON.stringify({native_chronos:'PASS',native_saturn_image:'PASS',native_video:'PASS',viewport_loading:'PASS',actual_range:'PASS',cards,media:state.runtime.bridge.media}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
