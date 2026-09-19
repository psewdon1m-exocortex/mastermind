// Part 01 §4.1 login contract. Rejections are browser fixtures; the final login is real.
// Never rotate credentials or include the actual Access Key in retained evidence.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('./lib/browser.cjs');
const origin=process.env.MASTERMIND_ORIGIN||'http://localhost:18390';
const out=path.resolve('artifacts/login-refresh-20260919');
const keyPath=process.env.MASTERMIND_ACCESS_KEY_FILE||'.local/secrets/core/bootstrap_access_key';
fs.mkdirSync(out,{recursive:true});
const closeTo=(actual,expected)=>assert.ok(Math.abs(actual-expected)<=1,`${actual} differs from ${expected}`);
(async()=>{
  const browser=await chromium.launch({headless:true});
  const context=await browser.newContext({viewport:{width:1919,height:1034},reducedMotion:'reduce'});
  const page=await context.newPage(),results={},errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>{if(message.type()==='error'&&message.text().includes('Content Security Policy'))errors.push(message.text());});
  let health='checking',releaseHealth;
  const healthPending=new Promise(resolve=>releaseHealth=resolve);
  await page.route('**/healthz',async route=>{
    if(health==='checking')await healthPending;
    await route.fulfill({status:health==='unreachable'?503:200,contentType:'application/json',body:'{}'});
  });
  async function geometry(){return page.evaluate(()=>{
    const box=selector=>{const n=document.querySelector(selector),b=n.getBoundingClientRect();return {x:b.x,y:b.y,width:b.width,height:b.height};};
    return {panel:box('.login-panel'),reachability:box('.reachability'),square:box('.status-square'),field:box('#access-key'),target:box('.login-key'),button:box('.login form button'),icon:box('.login-brand img')};
  });}
  try{
    await page.goto(origin+'/login');
    const input=page.getByLabel('Access Key',{exact:true}),button=page.getByRole('button',{name:'Enter service',exact:true});
    await input.waitFor();await page.evaluate(()=>document.fonts.ready);
    assert.equal(await input.inputValue(),'');
    assert.equal(await page.locator('.login input,.login textarea').count(),1);
    assert.equal(await input.getAttribute('autocomplete'),'current-password');
    for(const attribute of ['minlength','maxlength','pattern','required'])assert.equal(await input.getAttribute(attribute),null);
    assert.equal(await input.evaluate(n=>getComputedStyle(n).webkitTextSecurity),'disc');
    assert.equal(await page.locator('.reachability').textContent(),'Checking service');
    assert.equal(await page.locator('.status-square').evaluate(n=>getComputedStyle(n).animationName),'none');
    const baseline=await geometry();results.desktop=baseline;
    for(const [name,expected] of Object.entries({panel:[680,444,560,268],reachability:[705,466,255,50],square:[926,482,18,18],field:[705,578,511,31],button:[705,635,511,50]})){
      for(const [index,key] of ['x','y','width','height'].entries())closeTo(baseline[name][key],expected[index]);
    }
    assert.equal(baseline.icon.width,100);assert.equal(baseline.icon.height,100);assert.ok(baseline.target.height>=44);
    const wordmark=await page.locator('.login-brand h1').evaluate(n=>{const s=getComputedStyle(n);return {size:s.fontSize,spacing:s.letterSpacing,font:s.fontFamily};});
    assert.equal(wordmark.size,'72px');assert.equal(wordmark.spacing,'normal');assert.ok(wordmark.font.includes('Space Grotesk'));
    health='reachable';releaseHealth();await page.getByText('Service reachable',{exact:true}).waitFor();
    assert.deepEqual(await geometry(),baseline);
    assert.equal(await page.locator('.reachability').evaluate(n=>getComputedStyle(n).borderTopColor),'rgb(78, 204, 112)');
    await page.emulateMedia({reducedMotion:'no-preference'});
    const motion=await page.locator('.status-square').evaluate(n=>{const s=getComputedStyle(n);return {name:s.animationName,duration:s.animationDuration,frames:n.getAnimations()[0].effect.getKeyframes().map(frame=>Number(frame.opacity))};});
    assert.equal(motion.name,'reachable');assert.equal(motion.duration,'2s');assert.ok(motion.frames.every(value=>value>0));
    await page.emulateMedia({reducedMotion:'reduce'});
    assert.equal(await page.locator('.status-square').evaluate(n=>getComputedStyle(n).animationName),'none');
    await input.blur();await page.screenshot({path:path.join(out,'login-desktop.png')});

    let releaseLogin;const loginPending=new Promise(resolve=>releaseLogin=resolve),submitted=[];
    await page.route('**/api/auth/login',async route=>{
      submitted.push(route.request().postDataJSON().access_key);
      if(submitted.length===1)await loginPending;
      await route.fulfill({status:401,contentType:'application/json',body:JSON.stringify({error:{code:'UNAUTHORIZED',message:'Access Key was not accepted.'}})});
    });
    const opaque='  Key Å e\u0301\r\nsecond\rthird\t🧠  ';
    await input.evaluate((node,value)=>{const data=new DataTransfer();data.setData('text/plain',value);node.dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));},opaque);
    await input.press('Enter');
    await page.getByRole('button',{name:'Working…',exact:true}).waitFor();
    assert.equal(await page.locator('.login form button').isDisabled(),true);
    assert.deepEqual(await geometry(),baseline);
    await input.press('Enter');await page.locator('.login form').evaluate(form=>form.requestSubmit());
    assert.equal(submitted.length,1);assert.equal(submitted[0],opaque);
    releaseLogin();await page.getByRole('alert').filter({hasText:'Access Key was not accepted.'}).waitFor();
    assert.equal(await input.evaluate(n=>document.activeElement===n),true);
    assert.equal(await input.getAttribute('aria-invalid'),'true');assert.deepEqual(await geometry(),baseline);
    assert.equal(await page.locator('.reachability').textContent(),'Service reachable');
    await page.screenshot({path:path.join(out,'login-rejected.png')});
    await page.locator('.login form').evaluate(form=>form.reset());
    assert.equal(await input.inputValue(),'');assert.equal(await input.getAttribute('aria-invalid'),null);
    await button.click();await page.getByRole('alert').filter({hasText:'Access Key was not accepted.'}).waitFor();
    assert.equal(submitted.length,2);assert.equal(submitted[1],'');
    await page.locator('.login form').evaluate(form=>form.reset());
    await page.unroute('**/api/auth/login');
    results.authentication_fixtures={opaque_clipboard:'PASS',pending_duplicate_guard:'PASS',rejection_focus:'PASS',reset:'PASS',stable_geometry:'PASS'};

    health='unreachable';await page.getByText('Service unreachable',{exact:true}).waitFor({timeout:15000});
    assert.equal(await page.locator('.status-square').evaluate(n=>getComputedStyle(n).animationName),'none');
    assert.deepEqual(await geometry(),baseline);
    await page.screenshot({path:path.join(out,'login-unreachable.png')});
    health='reachable';await page.getByText('Service reachable',{exact:true}).waitFor({timeout:15000});
    await page.unroute('**/healthz');results.reachability='PASS: neutral, reachable, unreachable, recovery and reduced motion';

    results.responsive=[];
    for(const viewport of [{width:608,height:720},{width:390,height:844},{width:320,height:568},{width:720,height:360}]){
      await page.setViewportSize(viewport);await page.mouse.move(0,0);await input.blur();
      const size=await page.evaluate(()=>{
        const bounds=n=>{const b=n.getBoundingClientRect();return {left:b.left,top:b.top,right:b.right,bottom:b.bottom};};
        return {width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth,brand:[...document.querySelectorAll('.login-brand>*')].map(bounds),panel:bounds(document.querySelector('.login-panel'))};
      });
      assert.equal(size.overflow,false);assert.ok(size.panel.left>=24&&size.panel.right<=size.width-24);
      for(const item of size.brand)assert.ok(item.left>=24&&item.right<=size.width-24);
      assert.ok(size.brand[0].right<=size.brand[1].left);
      assert.ok(size.brand.every(item=>item.top>=24));
      const mobile=await geometry();assert.equal(mobile.panel.height,268);assert.equal(mobile.field.height,31);
      assert.equal(mobile.field.width,mobile.button.width);assert.ok(mobile.target.height>=44);
      // Clicking the otherwise invisible extension of the field still focuses it.
      await page.locator('.login-key').click({position:{x:10,y:2}});
      assert.equal(await input.evaluate(n=>document.activeElement===n),true);
      await page.screenshot({path:path.join(out,`login-${viewport.width}x${viewport.height}.png`),fullPage:true});
      results.responsive.push({...viewport,panel:mobile.panel});
    }
    await page.setViewportSize({width:1919,height:1034});await page.reload();await input.waitFor();
    assert.equal(await input.inputValue(),'');
    const key=fs.readFileSync(keyPath,'utf8');await input.fill(key);await input.press('Enter');
    await page.getByRole('heading',{name:'dashboard',exact:true}).waitFor();
    results.actual_key_login='PASS';
    for(const endpoint of ['/healthz','/readyz'])assert.equal((await context.request.get(origin+endpoint)).status(),200);
    assert.equal((await context.request.get(origin+'/api/status')).status(),200);
    await page.getByRole('button',{name:'Logout',exact:true}).click();await input.waitFor();
    assert.equal(await input.inputValue(),'');results.logout_clears_field='PASS';
    assert.deepEqual(errors,[]);results.browser_errors=errors;results.status='PASS';
    fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(results,null,2)+'\n');
    console.log(JSON.stringify(results,null,2));
  }finally{
    // Only revoke the probe's own session, including when a later assertion fails.
    try{const response=await context.request.get(origin+'/api/auth/session');if(response.ok()){const session=await response.json();await context.request.post(origin+'/api/auth/logout',{headers:{Origin:origin,'X-CSRF-Token':session.csrf},data:{}});}}catch{}
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
