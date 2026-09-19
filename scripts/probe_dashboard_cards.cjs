// Live UI checks. One real invitation is consumed; failure/expiry cases use fixtures.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('./lib/browser.cjs');
const origin='http://localhost:18390',out=path.resolve('artifacts/dashboard-cards-20260919');
fs.mkdirSync(out,{recursive:true});
(async()=>{
  const browser=await chromium.launch({headless:true});
  const context=await browser.newContext({viewport:{width:1920,height:1080},permissions:['clipboard-read','clipboard-write']});
  const page=await context.newPage(),errors=[],results={};let created=0;
  page.on('pageerror',e=>errors.push(e.message));
  page.on('console',message=>{if(message.type()==='error'&&message.text().includes('Content Security Policy'))errors.push(message.text());});
  page.on('request',request=>{if(request.method()==='POST'&&request.url().endsWith('/api/v1/crusher/access'))created++;});
  try{
    await page.goto(origin+'/login');await page.getByLabel('Access Key',{exact:true}).fill(fs.readFileSync('.local/secrets/core/bootstrap_access_key','utf8'));
    await page.getByRole('button',{name:'Enter service',exact:true}).click();await page.getByRole('heading',{name:'dashboard',exact:true}).waitFor();
    await page.evaluate(()=>document.fonts.ready);
    const brand=await page.locator('.brand strong').evaluate(n=>({text:n.textContent,breaks:n.querySelectorAll('br').length,width:n.clientWidth,scroll:n.scrollWidth,whiteSpace:getComputedStyle(n).whiteSpace}));
    assert.equal(brand.text,'Mastermind');assert.equal(brand.breaks,0);assert.equal(brand.whiteSpace,'nowrap');assert.ok(brand.scroll<=brand.width);results.brand=brand;
    assert.equal(await page.locator('link[rel=icon]').count(),3);
    for(const size of [16,32,64]){const icon=await context.request.get(origin+`/assets/favicon-${size}.png?v=2`);assert.ok(icon.ok());assert.ok(icon.headers()['content-type'].startsWith('image/png'));const png=await icon.body();assert.equal(png.readUInt32BE(16),size);assert.equal(png.readUInt32BE(20),size);assert.ok(png.length<20000);}
    results.favicon='PASS: browser-sized PNG icons without embedded image dependencies';
    const card=page.locator('[data-card="crusher_access"]'),button=card.locator('[data-access]');
    await card.scrollIntoViewIfNeeded();await page.mouse.move(0,0);await page.waitForTimeout(180);
    assert.equal((await card.boundingBox()).height,166);assert.equal(await card.locator('.card-header').count(),0);
    await card.screenshot({path:path.join(out,'crusher-rest.png')});
    results.hover={};
    for(const id of ['heatmap','crusher_access']){
      const target=page.locator(`[data-card="${id}"]`);await target.scrollIntoViewIfNeeded();await page.mouse.move(0,0);await page.waitForTimeout(180);
      const before=await target.boundingBox();await target.hover({position:{x:15,y:70}});await page.waitForTimeout(190);
      const after=await target.boundingBox();assert.ok(after.width>before.width);assert.ok(after.height>before.height);
      const css=await target.evaluate(n=>({border:getComputedStyle(n).borderTopColor,accent:getComputedStyle(document.documentElement).getPropertyValue('--accent').trim(),background:getComputedStyle(n).backgroundColor}));
      assert.equal(css.background,'rgb(17, 17, 17)');
      const handle=await target.locator(':scope > .drag').boundingBox();assert.ok(handle.width<40);assert.ok(after.x+after.width-handle.x-handle.width<3);
      results.hover[id]={before,after,handle};
    }
    await card.locator('.drag').hover();await card.screenshot({path:path.join(out,'crusher-handle-hover.png')});
    // Pressing the reorder handle must not create an invitation.
    await card.locator('.drag').click();assert.equal(created,0);
    await button.click();await page.waitForFunction(()=>document.querySelector('[data-access-detail]').textContent.startsWith('Copied'));
    const code=await card.locator('[data-access-value]').textContent();assert.match(code,/^\d{6}$/);
    assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),code);assert.equal(created,1);assert.equal(await page.getByRole('dialog').count(),0);
    await button.press('Enter');await page.waitForFunction(()=>!document.querySelector('[data-access]').disabled);
    assert.equal(created,1);assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),code);
    const visitor=await browser.newContext();
    try{const response=await visitor.request.post(origin+'/api/v1/crusher/sessions',{headers:{Origin:origin},data:{code}});assert.equal(response.status(),200);}finally{await visitor.close();}
    results.live_invitation='PASS: create, copy, keyboard recopy without regeneration, visitor activation';

    // Reload clears raw capability memory. Fixture data keeps screenshots non-sensitive.
    await page.reload();await button.waitFor();let fixtureCalls=0,release;
    const delayed=new Promise(resolve=>release=resolve);
    await page.route('**/api/v1/crusher/access',async route=>{fixtureCalls++;await delayed;await route.fulfill({contentType:'application/json',body:JSON.stringify({code:'012345',expires_at:Date.now()/1000+1800})});});
    await page.evaluate(()=>{navigator.clipboard.write=async()=>{throw Error('Denied');};navigator.clipboard.writeText=async()=>{throw Error('Denied');};});
    await button.click();await page.getByText('Creating…',{exact:true}).waitFor();assert.equal(await button.isDisabled(),true);
    await button.evaluate(n=>n.click());assert.equal(fixtureCalls,1);release();
    await page.waitForFunction(()=>document.querySelector('[data-access-detail]').textContent.startsWith('Copy failed'));
    assert.equal(await card.locator('[data-access-value]').textContent(),'012345');assert.equal(await button.isEnabled(),true);
    await card.locator('[data-access-value]').selectText();assert.equal(await page.evaluate(()=>getSelection().toString()),'012345');
    await button.click();await page.waitForFunction(()=>!document.querySelector('[data-access]').disabled);assert.equal(fixtureCalls,1);
    await card.screenshot({path:path.join(out,'crusher-copy-denied.png')});results.clipboard_denied='PASS: complete selectable value, retry, no new code';
    await page.locator('.sidebar').getByRole('link',{name:'Settings',exact:true}).click();await page.getByRole('heading',{name:'settings',exact:true}).waitFor();
    await page.locator('.sidebar').getByRole('link',{name:'Dashboard',exact:true}).click();await button.waitFor();assert.equal(await card.locator('[data-access-value]').textContent(),'012345');
    results.navigation_retains_code='PASS';

    await page.unroute('**/api/v1/crusher/access');await page.reload();await button.waitFor();
    await page.route('**/api/v1/crusher/access',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({code:'987654',expires_at:Date.now()/1000+2})}));
    await button.click();await page.waitForFunction(()=>document.querySelector('[data-access-detail]').textContent.startsWith('Code expired'),{},{timeout:7000});
    assert.equal(await card.locator('[data-access-value]').textContent(),'Create & copy');results.expiry='PASS';
    await page.unroute('**/api/v1/crusher/access');
    await page.route('**/api/v1/crusher/access',route=>route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({error:{message:'At most ten unconsumed Crusher codes can be active.'}})}));
    await button.click();await page.waitForFunction(()=>document.querySelector('[data-access-detail]').textContent.includes('Could not create'));
    assert.equal(await button.isEnabled(),true);results.server_failure='PASS';
    await page.unroute('**/api/v1/crusher/access');
    await page.reload();await button.waitFor();await page.screenshot({path:path.join(out,'dashboard.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});await card.scrollIntoViewIfNeeded();await page.mouse.move(0,0);await page.waitForTimeout(190);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    assert.ok((await card.locator('.drag').boundingBox()).width<40);await card.screenshot({path:path.join(out,'crusher-mobile.png')});results.mobile='PASS';
    assert.deepEqual(errors,[]);results.browser_errors=[];results.status='PASS';
    fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(results,null,2)+'\n');console.log(JSON.stringify(results,null,2));
  }finally{
    try{const response=await context.request.get(origin+'/api/auth/session');if(response.ok()){const session=await response.json();await context.request.post(origin+'/api/auth/logout',{headers:{Origin:origin,'X-CSRF-Token':session.csrf},data:{}});}}catch{}
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
