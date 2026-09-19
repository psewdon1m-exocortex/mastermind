const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {chromium}=require('./lib/browser.cjs');
const origin='http://localhost:18390',out=path.resolve('artifacts/public-editing-20260919');fs.mkdirSync(out,{recursive:true});
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 const browser=await chromium.launch({headless:true}),owner=await browser.newContext({viewport:{width:1920,height:1080},permissions:['clipboard-read','clipboard-write']});
 const a=await browser.newContext({viewport:{width:1440,height:900}}),b=await browser.newContext({viewport:{width:1440,height:900}}),viewer=await browser.newContext();
 const errors=[],results={},name='Shared verification '+crypto.randomBytes(4).toString('hex'),notePath=name+'.md',shares=[];let session,original;
 const pages=await Promise.all([owner.newPage(),a.newPage(),b.newPage(),viewer.newPage()]);const [page,first,second,readOnly]=pages;
 pages.forEach(p=>p.on('pageerror',error=>errors.push(error.message)));
 const api=async(route,method='GET',data)=>{const r=await owner.request.fetch(origin+route,{method,headers:{Origin:origin,...(session?{'X-CSRF-Token':session.csrf}:{})},...(data?{data}:{})});assert.ok(r.ok(),`${method} ${route}: ${r.status()}`);return r.json();};
 const read=()=>api('/api/note?'+new URLSearchParams({path:notePath}));
 async function until(test,timeout=12000){const end=Date.now()+timeout;while(Date.now()<end){if(await test())return;await delay(150);}throw Error('Condition did not become true.');}
 try{
  session=await api('/api/auth/login','POST',{access_key:fs.readFileSync('.local/secrets/core/bootstrap_access_key','utf8')});original=await api('/api/owner/settings');
  await api('/api/owner/settings','PATCH',{revision:original.revision,sidebar:'fixed'});
  await api('/api/notes','POST',{path:notePath,text:`# ${name}\n\nOriginal public paragraph.\n\n@PRIVATE_REFERENCE\n\nLast paragraph.\n`});
  await page.goto(origin+'/shared');await page.getByRole('heading',{name:'shared',exact:true}).waitFor();assert.equal(await page.locator('.nav-row .drag').count(),0);
  await page.locator('[data-nav=shares]').hover();assert.ok(await page.locator('[data-nav=shares] .ordinal').isVisible());assert.equal(await page.locator('.edge-toggle').textContent(),'');
  await page.getByRole('button',{name:'Create Share',exact:true}).click();await page.getByLabel('Note path',{exact:true}).fill(notePath);await page.getByLabel('Access',{exact:true}).selectOption('edit');await page.getByLabel('Password',{exact:true}).fill('1');await page.screenshot({path:path.join(out,'create-share.png')});
  const created=page.waitForResponse(r=>r.url()===origin+'/api/v1/shares'&&r.request().method()==='POST');await page.getByRole('dialog').getByRole('button',{name:'Create share',exact:true}).click();const share=await (await created).json();shares.push(share.share_id);await page.getByRole('dialog').waitFor({state:'detached'});assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),share.url);
  await page.reload();const row=page.locator(`[data-share="${share.share_id}"]`);await row.waitFor();await row.getByRole('button',{name:'Copy link',exact:true}).click();await until(async()=>await page.evaluate(()=>navigator.clipboard.readText())===share.url);results.copy='PASS: create/copy closes overlay; copy remains available after reload';
  for(const p of [first,second]){await p.goto(share.url);await p.getByLabel('Share password',{exact:true}).waitFor();}
  const gate=await first.locator('.gate-group').boundingBox();assert.equal(gate.width,255);assert.equal(await first.locator('h1:visible').count(),0);await first.screenshot({path:path.join(out,'shared-locked.png')});
  await first.getByLabel('Share password').fill('wrong');await first.getByRole('button',{name:'Enter',exact:true}).click();await first.locator('#gateError').getByText('The Share password was not accepted.').waitFor();
  for(const p of [first,second]){await p.getByLabel('Share password').fill('1');await p.getByRole('button',{name:'Enter',exact:true}).click();await p.locator('#surface textarea').first().waitFor();assert.equal(await p.getByRole('button',{name:'Edit',exact:true}).count(),0);assert.equal(await p.locator('h1').textContent(),name);}
  assert.ok(!(await first.locator('#surface').textContent()).includes('PRIVATE_REFERENCE'));await first.screenshot({path:path.join(out,'shared-editor.png')});
  const view=await api('/api/v1/shares','POST',{path:notePath,permission:'view'});shares.push(view.share_id);await readOnly.goto(view.url);await readOnly.locator('#surface').waitFor({state:'visible'});assert.equal(await readOnly.locator('textarea').count(),0);assert.equal(await readOnly.locator('h1').count(),1);results.public_gate='PASS: password 1, rejected password, direct editing and direct read-only view';
  let held=false;
  await first.route('**/api/note',async route=>{if(route.request().method()==='PUT'&&!held){held=true;const response=await route.fetch();await delay(1400);await route.fulfill({response});}else await route.continue();});
  await first.locator('#surface textarea').first().fill('First save.\n\n');await first.getByText('Saving…',{exact:true}).waitFor();await first.locator('#surface textarea').first().fill('Newest edit while saving.\n\n');
  await until(async()=>(await read()).text.includes('Newest edit while saving.'));await first.unroute('**/api/note');await until(async()=>await first.locator('#notice').textContent()==='Changes saved.');results.inflight='PASS: edits made during an in-flight save are retained and saved next';
  await second.locator('#surface textarea').first().fill('Second browser draft.\n\n');const current=await read();await api('/api/note','PUT',{path:notePath,text:current.text.replace('Newest edit while saving.','Owner concurrent edit.'),expected_sha256:current.sha256});
  await second.locator('#conflict').waitFor({state:'visible'});assert.ok((await second.locator('#draft textarea').first().inputValue()).includes('Second browser draft.'));assert.ok((await read()).text.includes('Owner concurrent edit.'));
  assert.ok(!(await second.locator('#conflict').textContent()).includes('PRIVATE_REFERENCE'));await second.screenshot({path:path.join(out,'conflict-review.png')});
  await second.locator('#surface textarea').first().fill('Owner concurrent edit.\nSecond browser draft merged.\n\n');await delay(1200);assert.ok(!(await read()).text.includes('draft merged'));
  await second.getByRole('button',{name:'Save merged changes'}).click();await second.locator('#conflict').waitFor({state:'hidden'});await until(async()=>(await read()).text.includes('draft merged'));
  assert.ok((await read()).text.includes('@PRIVATE_REFERENCE'));await until(async()=>(await first.locator('#surface textarea').first().inputValue()).includes('draft merged'));
  await until(async()=>(await readOnly.locator('#surface').textContent()).includes('draft merged'));results.collisions='PASS: stale write rejected, draft retained, explicit merge, hidden bytes preserved, other pages refresh';
  // Start a read while clean, then type before it returns: polling must not erase input.
  let heldRead=false;await first.route('**/api/note',async route=>{if(route.request().method()==='GET'&&!heldRead){heldRead=true;const response=await route.fetch();await delay(1600);await route.fulfill({response});}else await route.continue();});
  await until(()=>heldRead,7000);await first.locator('#surface textarea').first().fill('Typing during refresh is preserved.\n\n');await until(async()=>(await read()).text.includes('Typing during refresh is preserved.'));await first.unroute('**/api/note');results.poll_race='PASS: background refresh cannot overwrite newly typed text';
  for(const width of [390,720,1440]){await first.setViewportSize({width,height:900});await delay(200);assert.equal(await first.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await first.screenshot({path:path.join(out,`shared-${width}.png`)});}
  await api('/api/v1/shares/'+share.share_id,'PATCH',{revoke:true});await until(async()=>await first.locator('#gate').isVisible(),7000);assert.equal((await a.request.get(share.url+'/api/policy')).status(),404);results.revocation='PASS: open editor loses access after revocation';
  assert.deepEqual(errors,[]);results.browser_errors=[];fs.writeFileSync(path.join(out,'shared-result.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));
 }finally{
  for(const id of shares)await api('/api/v1/shares/'+id,'PATCH',{revoke:true}).catch(()=>{});
  const note=await read().catch(()=>null);if(note)await api('/api/note','DELETE',{path:notePath,expected_sha256:note.sha256}).catch(()=>{});
  if(original){const latest=await api('/api/owner/settings').catch(()=>null);if(latest)await api('/api/owner/settings','PATCH',{revision:latest.revision,sidebar:original.sidebar}).catch(()=>{});}
  if(session)await api('/api/auth/logout','POST',{}).catch(()=>{});await browser.close();
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
