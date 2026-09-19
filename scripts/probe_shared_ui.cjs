// Real local Share creation/revocation, plus isolated browser presentation fixtures.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('./lib/browser.cjs');
const origin=process.env.MASTERMIND_URL||'http://localhost:18390';
const out=path.resolve('artifacts/shared-ui-20260919');fs.mkdirSync(out,{recursive:true});
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
  const browser=await chromium.launch({headless:true});
  const context=await browser.newContext({viewport:{width:1920,height:1080},permissions:['clipboard-read','clipboard-write']});
  const page=await context.newPage(),errors=[],results={};let session,created;
  page.on('pageerror',error=>errors.push(error.message));
  async function api(route,method='GET',body){const response=await context.request.fetch(origin+route,{method,headers:{Origin:origin,...(session?{'X-CSRF-Token':session.csrf}:{})},...(body?{data:body}:{})});assert.ok(response.ok(),`${method} ${route}: ${response.status()}`);return response.json();}
  try{
    session=await api('/api/auth/login','POST',{access_key:fs.readFileSync('.local/secrets/core/bootstrap_access_key','utf8')});
    const status=await api('/api/status');results.readiness={state:status.status,runtime:status.runtime?.state,semantic:status.semantic_index};
    await page.goto(origin+'/dashboard');await page.getByRole('heading',{name:'dashboard',exact:true}).waitFor();
    const nav=page.locator('[data-nav=dashboard]');await nav.hover();await delay(180);
    assert.equal(await nav.locator('.ordinal').isVisible(),true);
    assert.equal(await nav.locator('.drag').count(),0);
    results.navigation='PASS: ordinal remains visible with no dot handle';
    for(const size of [16,32,64]){const r=await context.request.get(origin+`/assets/favicon-${size}.png?v=3`);assert.ok(r.ok());const data=await r.body();assert.equal(data.readUInt32BE(16),size);assert.equal(data.readUInt32BE(20),size);assert.ok(data.length<20000);}
    assert.equal(await page.locator('link[rel=icon]').count(),3);results.favicon='PASS: three native PNG sizes; no embedded SVG dependency';
    const notes=await api('/api/notes?limit=1');assert.ok(notes.length);
    await page.getByRole('link',{name:'Shared',exact:true}).click();await page.getByRole('heading',{name:'shared',exact:true}).waitFor();assert.equal(new URL(page.url()).pathname,'/shared');
    await page.getByRole('button',{name:'Create Share',exact:true}).click();await page.getByLabel('Note path',{exact:true}).fill(notes[0].path);
    const accepted=page.waitForResponse(response=>response.url()===origin+'/api/v1/shares'&&response.request().method()==='POST');
    await page.getByRole('dialog').getByRole('button',{name:'Create share',exact:true}).click();created=await (await accepted).json();
    await page.getByRole('dialog').waitFor({state:'detached'});assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),created.url);
    const visitor=await browser.newContext();
    assert.equal((await visitor.request.get(created.url+'/api/policy')).status(),200);
    assert.ok((await visitor.request.post(created.url+'/api/session',{headers:{Origin:origin},data:{}})).ok());
    let row=page.locator(`[data-share="${created.share_id}"]`);await row.waitFor();
    assert.equal(await row.getByRole('button',{name:'Copy link',exact:true}).isDisabled(),false);await row.getByRole('button',{name:'Copy link',exact:true}).click();assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),created.url);
    await row.locator('[data-expand]').click();await row.getByRole('button',{name:'Policy',exact:true}).click();await page.getByLabel('Access',{exact:true}).selectOption('edit');await page.getByRole('button',{name:'Apply policy',exact:true}).click();await page.getByRole('dialog').waitFor({state:'detached'});
    assert.equal((await visitor.request.get(created.url+'/api/note')).status(),401);results.policy='PASS: create/copy and policy edit through UI; previous visitor session invalidated';
    await page.reload();await row.waitFor();
    assert.ok(await row.getByRole('button',{name:'Copy link',exact:true}).isEnabled());await row.getByRole('button',{name:'Copy link',exact:true}).click();await page.getByText('Share link copied to the clipboard.',{exact:true}).waitFor();assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),created.url);
    await row.locator('[data-expand]').click();assert.equal(await row.locator('[data-expand]').getAttribute('aria-expanded'),'true');
    await row.getByRole('button',{name:'Revoke',exact:true}).click();await page.getByRole('button',{name:'Revoke Share',exact:true}).click();
    await row.waitFor({state:'detached'});assert.equal((await visitor.request.get(created.url+'/api/policy')).status(),404);await visitor.close();
    assert.ok(!(await api('/api/v1/shares')).some(item=>item.share_id===created.share_id));created=null;
    results.revocation='PASS: real Share removed from UI and API; anonymous old URL returns 404';
    await page.goto(origin+'/shares');await page.getByRole('heading',{name:'shared',exact:true}).waitFor();assert.equal(new URL(page.url()).pathname,'/shared');
    const fixtures=[{share_id:'a'.repeat(32),path:'Knowledge/Architecture.md',permission:'view',password_required:false,created_at:1789570958,modified_at:1789570958,expires_at:null,size_bytes:61542,target_missing:false,state:'active'},
      {share_id:'b'.repeat(32),path:'Research/Long research note with a descriptive title.md',permission:'edit',password_required:true,created_at:1789560958,modified_at:1789560958,expires_at:1789560959,size_bytes:2048,target_missing:true,state:'expired'}];
    await page.route('**/api/v1/shares?*',route=>route.fulfill({json:fixtures}));await page.reload();await page.locator('[data-share]').first().waitFor();
    const input=page.getByRole('searchbox',{name:'Search shared notes'}),clear=page.getByRole('button',{name:'Clear search'});
    const geometry=()=>input.evaluate(node=>{const box=node.parentElement,icon=box.querySelector('.search-icon'),button=box.querySelector('.clear'),style=getComputedStyle(box);return {inputX:node.offsetLeft,inputW:node.offsetWidth,icon:icon.getBoundingClientRect().width/parseFloat(getComputedStyle(box).getPropertyValue('--grow-x')||1),clearW:button.offsetWidth,gap:style.gap,padding:style.paddingLeft};});
    await page.mouse.move(1100,500);const before=await geometry();assert.equal(before.inputX,42);assert.equal(before.clearW,32);assert.equal(before.gap,'12px');assert.equal(before.padding,'12px');
    await input.fill('  ARCHITECTURE  ');assert.equal(await input.inputValue(),'  ARCHITECTURE  ');assert.equal(await page.locator('[data-share]').count(),1);assert.equal((await geometry()).inputW,before.inputW);await clear.click();assert.equal(await input.inputValue(),'');await input.press('Escape');
    await input.fill('no match');assert.equal(await page.locator('[data-share]').count(),0);assert.ok((await page.locator('[data-count]').textContent()).startsWith('0 of'));await input.press('Escape');assert.equal(await page.locator('[data-share]').count(),2);
    assert.equal(await page.locator('.clear').getAttribute('aria-hidden'),'true');assert.equal(await page.locator('.clear').getAttribute('tabindex'),'-1');
    results.search='PASS: canonical icon/input/clear geometry, stable width, trimmed case-insensitive query, Escape, no-result scope';
    await page.screenshot({path:path.join(out,'shared-closed.png')});
    row=page.locator('[data-share]').first();await row.locator('[data-expand]').focus();await page.keyboard.press('Enter');assert.equal(await row.locator('.shared-metadata>div').count(),6);await page.screenshot({path:path.join(out,'shared-expanded.png')});
    await page.getByRole('button',{name:/Sort by name/}).click();assert.ok((await page.locator('[data-share]').first().textContent()).includes('Architecture.md'));
    for(const width of [390,720,1000,1920]){await page.setViewportSize({width,height:900});await delay(220);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await page.screenshot({path:path.join(out,`shared-${width}.png`)});}
    results.shared_layout='PASS: expandable policies, keyboard control, sorting and four responsive widths';
    await page.setViewportSize({width:1920,height:1080});await page.goto(origin+'/crusher');await page.getByRole('searchbox',{name:'Search submissions'}).waitFor();await page.locator('[data-jobs]').waitFor();
    const crusher=page.getByRole('searchbox',{name:'Search submissions'});await crusher.fill('   COMPLETED  ');await crusher.press('Escape');assert.equal(await crusher.inputValue(),'');assert.equal(await page.locator('.search-icon').count(),1);await page.screenshot({path:path.join(out,'crusher-search.png')});
    // Browser-only notices exercise the presentation contract without fake API successes.
    await page.evaluate(async()=>{const {notice}=await import('/assets/ui.js');document.querySelector('#notices').replaceChildren();for(let n=1;n<=6;n++)notice(`Notification layout check ${n}.`);});
    assert.equal(await page.locator('#notices .notice').count(),5);assert.ok(!(await page.locator('#notices').textContent()).includes('check 1.'));
    const placement=await page.locator('#notices').boundingBox();assert.equal(placement.x,1920-18-410);assert.equal(placement.y,18);
    await page.evaluate(async()=>{(await import('/assets/ui.js')).notice('Error layout check.',true);});
    assert.equal(await page.locator('.notice.error').evaluate(node=>getComputedStyle(node).borderColor),'rgb(248, 61, 61)');
    assert.equal(await page.locator('.notice:not(.error)').first().evaluate(node=>getComputedStyle(node).borderColor),'rgb(98, 255, 140)');
    await page.screenshot({path:path.join(out,'notices.png')});await page.locator('.notice').first().getByRole('button',{name:'Dismiss notification'}).click();assert.equal(await page.locator('.notice').count(),4);await page.mouse.move(500,500);await delay(4700);assert.equal(await page.locator('.notice:not(.error)').count(),0);assert.equal(await page.locator('.notice.error').count(),1);await delay(3400);assert.equal(await page.locator('.notice').count(),0);
    results.notices='PASS: five-item top-right stack, semantic borders, dismiss, success 4.5s/error 8s';
    await page.goto(origin+'/documentation');await page.getByRole('searchbox',{name:'Search documentation'}).fill('Provider readiness');
    await page.waitForFunction(()=>document.querySelectorAll('.doc-section').length===1);
    assert.ok((await page.locator('.doc-section').textContent()).includes('controlled fixtures'));
    results.documentation='PASS: current provider-mode limitation is discoverable in the operator guide';
    assert.deepEqual(errors,[]);results.browser_errors=[];
    fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));
  }finally{
    if(created)await api('/api/v1/shares/'+created.share_id,'PATCH',{revoke:true}).catch(()=>{});
    if(session)await api('/api/auth/logout','POST',{}).catch(()=>{});
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
