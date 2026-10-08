/* Paired public/legacy fixtures against the real isolated Core. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('./lib/browser.cjs');
const root=path.resolve(__dirname,'..'),work=path.resolve(process.argv[2]||'');
assert.ok(work.startsWith(path.join(root,'.local','qualification')+path.sep));
const fixture=JSON.parse(fs.readFileSync(path.join(work,'fixture.json'),'utf8'));
assert.equal(fixture.fixture,'mastermind-public-shared/v1');
assert.match(fixture.origin,/^http:\/\/127\.0\.0\.1:\d+$/);
const out=path.join(root,'artifacts/public-shared');fs.mkdirSync(out,{recursive:true});
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(test,timeout=12000){const end=Date.now()+timeout;while(Date.now()<end){if(await test())return;await delay(100);}throw Error('Condition did not become true');}

(async()=>{
 const browser=await chromium.launch({headless:true}),errors=[],checks=[];
 const check=name=>{checks.push(name);console.log('PASS '+name);};
 try{
 const owner=await browser.newPage();await owner.goto(fixture.origin+'/login');
 const session=await owner.evaluate(async()=>{const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({access_key:'synthetic-public-shared-key'})});if(!r.ok)throw Error('Owner login failed');return r.json();});
 const api=(route,method='GET',body)=>owner.evaluate(async({route,method,body,csrf})=>{
   const r=await fetch(route,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},...(body?{body:JSON.stringify(body)}:{})});
   if(!r.ok)throw Error('Owner fixture request failed: '+r.status);return r.json();
 },{route,method,body,csrf:session.csrf});
 const track=page=>{
   page.on('pageerror',e=>errors.push(e.message));
   page.on('console',m=>{if(m.type()==='error'&&/Content Security Policy|Refused to/.test(m.text()))errors.push(m.text());});
 };
  for(const mode of ['public','legacy']){
   const f=fixture.modes[mode],suffix=mode==='legacy'?'?source=qualification&legacy=1':'',url=share=>share.url+suffix;
   const initial=await api('/api/note?'+new URLSearchParams({path:f.path}));
   await api('/api/note','PUT',{path:f.path,text:fixture.source,expected_sha256:initial.sha256});
   const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
   const page=await context.newPage();track(page);
   await page.goto(url(f.edit));await page.locator('#password').waitFor();
   assert.equal(await page.locator('body').getAttribute('data-view'),mode);
   assert.ok(!(await page.content()).includes('NEVER_DISCLOSE'));
   assert.equal(await page.locator('#title').textContent(),'');
   const size=await page.locator('.gate-group').boundingBox();assert.equal(size.width,mode==='public'?480:255);
   if(mode==='public'){
    for(const id of ['password','unlock'])assert.ok((await page.locator('#'+id).boundingBox()).height>=46);
    await page.locator('#password').focus();
    assert.equal(await page.locator('#password').evaluate(el=>getComputedStyle(el).outlineStyle),'solid');
    await page.keyboard.press('Tab');assert.ok(await page.locator('#unlock').evaluate(el=>el===document.activeElement));
   }
   await page.evaluate(()=>document.fonts.ready);await page.screenshot({path:path.join(out,mode+'-locked-desktop.png')});
   await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,mode+'-locked-mobile.png')});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.setViewportSize({width:1440,height:1000});
   await page.locator('#password').fill('wrong');await page.locator('#password').press('Enter');
   await until(async()=>/not accepted/.test(await page.locator('#gateError').textContent()));
   assert.equal(await page.locator('#password').inputValue(),'');
   // Visual failure states are fault-injected; authentication below uses the real server.
   await page.route('**/api/session',r=>r.fulfill({status:429,contentType:'application/json',body:JSON.stringify({error:{message:'Try later'}})}));
   await page.locator('#password').fill('1');await page.locator('#unlock').click();
   await until(async()=>/Too many attempts/.test(await page.locator('#gateError').textContent()));
   assert.equal(await page.locator('#password').inputValue(),'');await page.unroute('**/api/session');
   await page.route('**/api/session',r=>r.abort());await page.locator('#unlock').click();
   await until(async()=>/Cannot reach/.test(await page.locator('#gateError').textContent()));await page.unroute('**/api/session');
   let requests=0;
   await page.route('**/api/session',async r=>{requests++;await delay(300);await r.continue();});
   await page.locator('#password').fill('1');await page.locator('#password').press('Enter');
   await page.getByRole('button',{name:'Checking…',exact:true}).waitFor();
   assert.ok(await page.locator('#unlock').isDisabled());
   await page.locator('#surface textarea[data-segment="1"]').waitFor();assert.equal(requests,1);await page.unroute('**/api/session');
   assert.equal(await page.locator('#password').inputValue(),'');assert.equal(new URL(page.url()).search,suffix);
   if(mode==='public'){
    assert.equal(await page.locator('#access').textContent(),'Editing allowed');
    assert.match(await page.locator('#expiry').textContent(),/^Expires /);
   }
   assert.equal(await page.locator('#title').textContent(),'Fixture knowledge');
   assert.ok(!(await page.locator('#surface').textContent()).includes('NEVER_DISCLOSE'));
   await page.locator('#surface textarea[data-segment="1"]').focus();await page.keyboard.press('Tab');
   assert.ok(await page.locator('#surface textarea[data-segment="1"]').evaluate(el=>el!==document.activeElement));
   await page.screenshot({path:path.join(out,mode+'-editing-desktop.png')});
   await page.setViewportSize({width:390,height:844});
   if(mode==='public')assert.ok(await page.locator('#expiry').isVisible());
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.screenshot({path:path.join(out,mode+'-editing-mobile.png')});await page.setViewportSize({width:1440,height:1000});
   check(mode+': locked layout, password 1, rejection, rate limit, network retry, pending guard, keyboard and mobile expiry');

   const viewer=await browser.newPage({viewport:{width:1440,height:1000}});track(viewer);
   await viewer.goto(url(f.view));await viewer.locator('#surface').waitFor();
   assert.equal(await viewer.locator('#surface textarea').count(),0);
   assert.ok(!(await viewer.locator('#surface').textContent()).includes('NEVER_DISCLOSE'));
   if(mode==='public'){
    assert.equal(await viewer.locator('#access').textContent(),'View only');
    assert.equal(await viewer.locator('#expiry').textContent(),'No expiration');
    await viewer.getByText('About access',{exact:true}).click();
    assert.ok(await viewer.getByText('Content displayed in your browser can still be copied.',{exact:false}).isVisible());
   }
   await viewer.evaluate(()=>document.fonts.ready);await viewer.screenshot({path:path.join(out,mode+'-view-desktop.png')});
   assert.equal((await viewer.request.get(fixture.origin+'/api/notes')).status(),401);
   const read=()=>api('/api/note?'+new URLSearchParams({path:f.path}));
   let held=false;
   await page.route('**/api/note',async route=>{if(route.request().method()==='PUT'&&!held){held=true;const response=await route.fetch();await delay(1200);await route.fulfill({response});}else await route.continue();});
   await page.locator('#surface textarea[data-segment="1"]').fill('First save.\n\n');await page.getByText('Saving…',{exact:true}).waitFor();
   await page.locator('#surface textarea[data-segment="1"]').fill('Newest edit while saving.\n\n');
   await until(async()=>(await read()).text.includes('Newest edit while saving.'));await page.unroute('**/api/note');
   await until(async()=>await page.locator('#notice').textContent()==='Changes saved.');
   await until(async()=>(await viewer.locator('#surface').textContent()).includes('Newest edit while saving.'));
   await page.locator('#surface textarea[data-segment="1"]').fill('Browser conflict draft.\n\n');
   const current=await read();await api('/api/note','PUT',{path:f.path,text:current.text+'\nOwner concurrent change\n',expected_sha256:current.sha256});
   await page.locator('#conflict').waitFor();assert.match(await page.locator('#draft textarea').first().inputValue(),/Browser conflict draft/);
   assert.ok(!(await read()).text.includes('Browser conflict draft'));
   await page.locator('#surface textarea[data-segment="1"]').fill('Merged browser draft.\n\n');
   await page.getByRole('button',{name:'Save merged changes',exact:true}).click();
   await page.locator('#conflict').waitFor({state:'hidden'});
   assert.match((await read()).text,/Owner concurrent change/);
   await page.locator('#surface textarea[data-segment="1"]').fill('Merged browser draft. Keyboard save.\n\n');await page.keyboard.press('Control+s');
   await until(async()=>(await read()).text.includes('Keyboard save.'));
   // A delayed clean poll must not replace text typed after the read began.
   await until(async()=>await page.locator('#notice').textContent()==='Changes saved.');
   let pollHeld=false;
   await page.route('**/api/note',async route=>{
    if(route.request().method()==='GET'&&!pollHeld){pollHeld=true;const response=await route.fetch();await delay(1400);await route.fulfill({response});}
    else await route.continue();
   });
   await until(()=>pollHeld);
   await page.locator('#surface textarea[data-segment="1"]').fill('Merged browser draft. Typed during polling.\n\n');
   await until(async()=>(await read()).text.includes('Typed during polling.'));
   await delay(1500);assert.match(await page.locator('#surface textarea[data-segment="1"]').inputValue(),/Typed during polling/);
   await page.unroute('**/api/note');
   check(mode+': real autosave, in-flight edits, refresh in a second browser, ETag conflict, retained draft and explicit merge');

   await viewer.goto(url(f.empty));await viewer.locator('#surface').waitFor();
   assert.equal(await viewer.locator('#title').textContent(),'Empty note');
   await viewer.goto(url(f.long));await viewer.locator('#surface').waitFor();
   await viewer.setViewportSize({width:390,height:844});
   assert.ok(await viewer.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await viewer.mouse.wheel(0,600);await until(()=>viewer.evaluate(()=>scrollY>0));
   await viewer.evaluate(()=>scrollTo(0,0));await viewer.screenshot({path:path.join(out,mode+'-long-mobile.png')});
   // Browser zoom is represented by its reduced CSS viewport (1440px at 200% => 720 CSS px).
   await viewer.setViewportSize({width:720,height:500});
   assert.ok(await viewer.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await viewer.screenshot({path:path.join(out,mode+'-zoom-reflow.png')});
   if(mode==='public'){
    const rgb=s=>s.startsWith('#')?s.match(/[0-9a-f]{2}/gi).map(v=>parseInt(v,16)):s.match(/\d+/g).map(Number);
    const lum=s=>rgb(s.trim()).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((x,v,i)=>x+v*[.2126,.7152,.0722][i],0);
    for(const configured of ['#ffffff','#ffff00','#00ff00','#ff51b0','#000000','#00a8ff']){
     const colors=await viewer.evaluate(configured=>{
      accent(configured);const c=getComputedStyle(document.body);return {accent:c.getPropertyValue('--public-accent'),background:c.backgroundColor,muted:c.getPropertyValue('--muted')};
     },configured);
     for(const value of [colors.accent,colors.muted])assert.ok((lum(colors.background)+.05)/(lum(value)+.05)>=4.5);
    }
    assert.equal(await viewer.evaluate(()=>getComputedStyle(document.documentElement).scrollbarWidth),'none');
    const motion=await page.locator('#unlock').evaluate(el=>{const s=getComputedStyle(el);return [s.animationName,s.transitionDuration];});
    assert.deepEqual(motion,['none','0s']);
   }
   const expiring=await api('/api/v1/shares','POST',{path:f.path,permission:'view',expires_at:Date.now()/1000+3});
   await viewer.goto(url(expiring));await viewer.locator('#surface').waitFor();
   await viewer.locator('#gate').waitFor();assert.ok(await viewer.locator('#unlock').isDisabled());
   await api('/api/v1/shares/'+f.edit.share_id,'PATCH',{revoke:true});
   await page.locator('#gate').waitFor();await until(async()=>await page.locator('#unlock').isDisabled());
   assert.ok(await page.locator('#workspace').isHidden());
   const gone=await viewer.goto(url(f.edit));assert.equal(gone.status(),404);await viewer.getByRole('heading',{name:'Link unavailable'}).waitFor();
   await viewer.screenshot({path:path.join(out,mode+'-unavailable.png')});
   check(mode+': empty and long content, scrolling, mobile and 200% reflow, contrast, authorization, expiry, revoke and unavailable page');
   await viewer.close();await context.close();
  }
  assert.deepEqual(errors,[]);check('No uncaught browser errors or CSP violations');
 }finally{
  fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({checks,errors,limitations:['Chromium with actual Core and canonical files; offline Runtime, no native Obsidian.','429 and transport failure UI states are injected; password and write authorization use real HTTP.','Zoom checked as CSS viewport reflow, not browser chrome zoom.']},null,2));
  await browser.close();
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
