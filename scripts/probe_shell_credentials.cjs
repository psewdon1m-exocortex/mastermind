const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('./lib/browser.cjs');
const root=path.resolve(__dirname,'..'),origin='http://localhost:18390',key=fs.readFileSync(path.join(root,'.local/secrets/core/bootstrap_access_key'),'utf8');
(async()=>{
  const browser=await chromium.launch({headless:true});let active=key,csrf,context;
  try{
    context=await browser.newContext({viewport:{width:1440,height:1000}});const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
    async function login(c,value){const r=await c.request.post(origin+'/api/auth/login',{headers:{Origin:origin},data:{access_key:value}});assert.equal(r.status(),200,'Generated owner login');return (await r.json()).csrf;}
    csrf=await login(context,key);const other=await browser.newContext();await login(other,key);
    await page.goto(origin+'/settings');await page.getByRole('button',{name:'Change Access Key',exact:true}).click();
    await page.getByLabel('Current Access Key',{exact:true}).fill(key);
    const next=' \r\nOpaque e\u0301 🔑\t '+Date.now()+' ';
    // Deterministic clipboard payload: exercise the browser's paste path rather
    // than textarea.fill(), which normalizes CRLF before the application sees it.
    async function paste(label,value){await page.getByLabel(label,{exact:true}).evaluate((input,value)=>{const data=new DataTransfer();data.setData('text/plain',value);input.dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));},value);}
    await paste('New Access Key',next);await paste('Confirm new Access Key',next+'x');
    await page.locator('[role=dialog]').getByRole('button',{name:'Change Access Key',exact:true}).click();await page.getByText('The new values do not match exactly.',{exact:true}).waitFor();assert.equal((await other.request.get(origin+'/api/auth/session')).status(),200);
    await page.getByLabel('Confirm new Access Key',{exact:true}).fill('');await paste('Confirm new Access Key',next);
    const reply=page.waitForResponse(r=>r.url()===origin+'/api/auth/rotate'&&r.request().method()==='POST');
    await page.locator('[role=dialog]').getByRole('button',{name:'Change Access Key',exact:true}).click();const response=await reply;assert.equal(response.status(),200);
    active=response.request().postDataJSON().new_access_key;csrf=(await response.json()).csrf;
    assert.ok(active===next,'The exact opaque clipboard bytes were not preserved');assert.equal((await other.request.get(origin+'/api/auth/session')).status(),401);assert.equal((await context.request.get(origin+'/api/auth/session')).status(),200);
    await page.getByText('Access Key changed. Other sessions ended.',{exact:true}).waitFor();
    assert.deepEqual(errors,[]);console.log(JSON.stringify({opaque_unicode_crlf_paste:'PASS',mismatch_no_rotation:'PASS',other_session_revoked:'PASS',current_session_retained:'PASS'}));
  }finally{
    if(context&&active!==key){const response=await context.request.post(origin+'/api/auth/rotate',{headers:{Origin:origin,'X-CSRF-Token':csrf},data:{current_access_key:active,new_access_key:key,confirm_access_key:key}});assert.equal(response.status(),200,'Restore the generated local bootstrap identity');}
    await browser.close();
  }
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
