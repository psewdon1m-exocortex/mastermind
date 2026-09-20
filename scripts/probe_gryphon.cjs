// Full GUI -> Gryphon link -> bot command -> Crusher session -> revoke qualification.
const assert = require('node:assert/strict'), fs = require('node:fs');
require('node:dns').setDefaultResultOrder('ipv4first');
const {chromium} = require('./lib/browser.cjs');
const origin = 'http://localhost:18496', gateway = 'http://localhost:18497';
const directory = process.env.MASTERMIND_GRYPHON_FIXTURE_DIR;
if (!directory) throw Error('Provide the isolated fixture credential directory');
const key = fs.readFileSync(directory+'/bootstrap_access_key','utf8');
const event = (id, text, user=12345) => ({update_id:id, message:{message_id:id,
  chat:{id:user,type:'private'},from:{id:user,is_bot:false,first_name:'Fixture'},text}});
async function send(value) {const r=await fetch(gateway+'/event',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});assert.equal(r.status,200);return r.json();}
(async()=>{
 for(let attempt=0;attempt<40;attempt++) {
  try { if((await fetch(origin+'/readyz')).ok && (await fetch(gateway+'/status')).ok) break; }
  catch {}
  if(attempt===39) throw Error('Fixture did not become ready');
  await new Promise(resolve=>setTimeout(resolve,250));
 }
 const browser=await chromium.launch({headless:true});
 try {
  const owner=await browser.newContext({viewport:{width:1440,height:1100}}), page=await owner.newPage(), errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const login=await owner.request.post(origin+'/api/auth/login',{headers:{Origin:origin},data:{access_key:key}});
  assert.equal(login.status(),200); const csrf=(await login.json()).csrf;
  const mutate=(path,data,method='POST')=>owner.request.fetch(origin+path,{method,headers:{Origin:origin,'X-CSRF-Token':csrf},...(data?{data}:{})});
  await page.goto(origin+'/settings');
  const card=page.locator('[data-card="gryphon"]');await card.getByRole('button',{name:'Link Mastermind function',exact:true}).waitFor();
  await card.getByRole('button',{name:'Link Mastermind function',exact:true}).click();
  await page.getByRole('button',{name:'Link function',exact:true}).click();
  await card.getByRole('button',{name:'Link Telegram account',exact:true}).click();
  await page.locator('.copy-value').waitFor();const command=await page.locator('.copy-value').innerText();assert.match(command,/^\/link /);
  await send(event(1,command));
  await page.getByText('Telegram account linked · user 12345 · private chat 12345',{exact:true}).waitFor();
  await card.scrollIntoViewIfNeeded(); fs.mkdirSync('artifacts/gryphon',{recursive:true}); await card.screenshot({path:'artifacts/gryphon/settings-linked.png'});
  await card.getByRole('button',{name:'Retry status',exact:true}).focus();
  await page.waitForTimeout(3300);
  assert.equal(await page.locator(':focus').getAttribute('data-gryphon-refresh'),'');
  await page.setViewportSize({width:390,height:844});
  await card.scrollIntoViewIfNeeded();
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await card.screenshot({path:'artifacts/gryphon/settings-mobile.png'});
  await page.setViewportSize({width:1440,height:1100});
  const initial=(await send(event(2,'/crusher'))).sent; const message=initial.find(item=>/Mastermind Crusher code:/.test(item.text));assert.ok(message);
  const code=/code: ([0-9]{6})/.exec(message.text)[1];assert.ok(message.text.includes(origin+'/crusher\n'));assert.ok(!message.text.includes('?code='));
  const replay=await send(event(2,'/crusher'));assert.equal(replay.sent.filter(item=>/Mastermind Crusher code:/.test(item.text)).length,1);
  const foreign=await send(event(3,'/crusher',99999));assert.equal(foreign.sent.filter(item=>/Mastermind Crusher code:/.test(item.text)).length,1);
  const guest=await browser.newContext(), crusher=await guest.newPage();await crusher.goto(origin+'/crusher');
  const activation=crusher.waitForResponse(response=>response.url().endsWith('/api/v1/crusher/sessions')&&response.request().method()==='POST');
  await crusher.getByRole('textbox',{name:/code/i}).fill(code);await crusher.getByRole('button',{name:'Enter',exact:true}).click();
  const token=(await (await activation).json()).token;assert.ok(token);
  await crusher.getByText('Source links',{exact:true}).waitFor();
  await crusher.getByLabel('Source files',{exact:true}).setInputFiles({name:'telegram-fixture.txt',mimeType:'text/plain',buffer:Buffer.from('Synthetic Telegram access qualification. No external AI provider is called.')});
  await crusher.waitForFunction(()=>document.querySelector('[data-submit-status]')?.textContent==='1 source accepted.' || document.querySelector('.crusher-drop-panel .error-message')?.textContent);
  assert.equal(await crusher.locator('.crusher-drop-panel .error-message').innerText(),'');
  assert.equal((await (await guest.request.get(origin+'/api/v1/crusher/jobs',{headers:{Authorization:'Bearer '+token}})).json()).length,1);
  await crusher.screenshot({path:'artifacts/gryphon/crusher-unlocked.png'});
  assert.equal((await guest.request.post(origin+'/api/v1/crusher/sessions',{data:{code}})).status(),401);
  assert.equal((await guest.request.get(origin+'/api/owner/gryphon')).status(),401);
  assert.equal((await guest.request.get(origin+'/api/v1/crusher/jobs',{headers:{Authorization:'Bearer '+token}})).status(),200);
  const ownerInvitation=await mutate('/api/v1/crusher/access',{});assert.equal(ownerInvitation.status(),200);
  const ownerCode=(await ownerInvitation.json()).code;
  await send(event(4,'/crusher_status'));
  await send(event(5,'/crusher_revoke'));
  assert.equal((await guest.request.get(origin+'/api/v1/crusher/jobs',{headers:{Authorization:'Bearer '+token}})).status(),401);
  const record=await guest.request.post(origin+'/api/v1/crusher/sessions',{data:{code:ownerCode}});assert.equal(record.status(),200);
  await crusher.reload();await crusher.getByRole('textbox',{name:/code/i}).waitFor();
  await card.getByRole('button',{name:'Revoke Telegram binding',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Revoke Telegram binding',exact:true}).click();
  await card.getByText('No Telegram account linked.',{exact:true}).waitFor();
  const denied=await send(event(6,'/crusher'));assert.equal(denied.sent.filter(item=>/Mastermind Crusher code:/.test(item.text)).length,1);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'PASS',checks:['GUI function link','private Telegram binding','one-use code','duplicate delivery','foreign user denied','guest UI unlock','source file accepted','Vault/owner isolation','status','scoped revoke','binding revoke','keyboard focus','mobile layout'],telegram:'controlled transport; real Gryphon and Mastermind processes'}));
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
