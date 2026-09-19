// Isolated owner Settings probe. Never rotates credentials or touches the real Vault.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('./lib/browser.cjs');
const origin=process.env.CONTEXT_PROBE_ORIGIN||'http://localhost:18392';
const output=path.resolve('artifacts/context-indexing-ui');fs.mkdirSync(output,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1050}}),page=await context.newPage();
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const login=await context.request.post(origin+'/api/auth/login',{headers:{Origin:origin},data:{access_key:fs.readFileSync('.local/secrets/core/bootstrap_access_key','utf8')}});
  assert.equal(login.status(),200);const session=await login.json();
  await page.goto(origin+'/settings');const card=page.locator('[data-card="context_indexing"]');
  await card.locator('[name="template_path"]').waitFor();
  assert.equal(await card.locator('input[readonly]').inputValue(),'root/crusher');
  await card.scrollIntoViewIfNeeded();
  await card.locator('[name="template_path"]').fill('draft.md');
  await card.getByRole('button',{name:'Refresh status and revision',exact:true}).click();
  assert.equal(await card.locator('[name="template_path"]').inputValue(),'draft.md');
  await card.locator('[data-pick="template_path"]').click();
  const modal=page.getByRole('dialog');await modal.locator('[data-path="root/templates/example crusher.md"]').click();
  assert.equal(await card.locator('[name="template_path"]').inputValue(),'root/templates/example crusher.md');
  await card.getByRole('button',{name:'Validate draft',exact:true}).click();
  await page.getByText('Changed fields are valid.',{exact:true}).waitFor();
  const api=async(method,data)=>page.evaluate(async({method,data,csrf})=>{const r=await fetch('/api/owner/context-indexing/settings',{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},...(data?{body:JSON.stringify(data)}:{})});const value=await r.json();if(!r.ok)throw new Error(method+': '+r.status+' '+value.error?.code);return value;},{method,data,csrf:session.csrf});
  const before=await api('GET');await api('PATCH',{expected_revision:before.revision,operation_id:require('node:crypto').randomUUID(),retrieval:{curator_enabled:true}});
  await card.locator('[name="fallback_note"]').fill('root/pool.md');
  await card.getByRole('button',{name:'Apply',exact:true}).click();
  await card.locator('[data-error]').filter({hasText:/changed|revision|refresh/i}).waitFor();
  assert.equal(await card.locator('[name="fallback_note"]').inputValue(),'root/pool.md');
  await card.getByRole('button',{name:'Refresh status and revision',exact:true}).click();
  await card.getByRole('button',{name:'Apply',exact:true}).click();
  await page.getByText('Obsidian & search settings saved.',{exact:true}).waitFor();
  assert.equal((await api('GET')).retrieval.curator_enabled,false);
  while(await page.getByRole('button',{name:'Dismiss notification'}).count())await page.getByRole('button',{name:'Dismiss notification'}).first().click();
  await card.screenshot({path:path.join(output,'wide.png')});
  await page.setViewportSize({width:390,height:844});await card.scrollIntoViewIfNeeded();
  assert.ok(await card.evaluate(node=>node.scrollWidth<=node.clientWidth+1),'Settings card must not overflow');
  await card.screenshot({path:path.join(output,'narrow.png')});
  assert.deepEqual(errors,[]);fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({status:'PASS',checks:['combined card','readonly output','draft preserved','real note picker','server validation','concurrent revision conflict','explicit rebase','mobile width','no browser exceptions']},null,2));
  console.log('PASS: context-indexing owner Settings, conflict, picker, draft, responsive layout.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
