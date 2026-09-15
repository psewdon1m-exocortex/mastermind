// Real browser interactions against the local service group. Synthetic source data only.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {chromium}=require('./lib/browser.cjs');
const root=path.resolve(__dirname,'..'),origin='http://localhost:18390',out=path.join(root,'artifacts/shell-workflows');fs.mkdirSync(out,{recursive:true});
const scratch=path.join(root,'.local/shell-workflows');fs.mkdirSync(scratch,{recursive:true});
const key=fs.readFileSync(path.join(root,'.local/secrets/core/bootstrap_access_key'),'utf8');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
  const browser=await chromium.launch({headless:true});let page,context,csrf,activeKey=key;const errors=[],results=new Proxy({}, {set(target,key,value){target[key]=value;console.log(JSON.stringify({check:key,result:value}));return true;}});
  try{
    context=await browser.newContext({viewport:{width:1920,height:1080},acceptDownloads:true,permissions:['clipboard-read','clipboard-write']});
    page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
    page.on('console',e=>{if(e.type()==='error'&&e.text().includes('Content Security Policy'))errors.push(e.text());});
    async function login(){await page.goto(origin+'/settings');await page.getByLabel('Access Key',{exact:true}).waitFor();await page.getByLabel('Access Key',{exact:true}).fill(activeKey);await page.getByRole('button',{name:'Enter service',exact:true}).click();await page.getByRole('heading',{name:'Settings',exact:true}).waitFor();csrf=(await(await context.request.get(origin+'/api/auth/session')).json()).csrf;for(let i=0;i<120;i++){const response=await context.request.get(origin+'/api/status');if(response.ok()&&(await response.json()).status==='HEALTHY')return;await sleep(500);}throw Error('Canonical startup readiness did not settle');}
    async function api(route,method='GET',data){const response=await context.request.fetch(origin+route,{method,data,headers:{Origin:origin,'X-CSRF-Token':csrf},timeout:180000});assert.equal(response.status(),200,route+' HTTP '+response.status());return response.json();}
    async function nav(name){await page.locator('.sidebar').getByRole('link',{name,exact:true}).click();await page.getByRole('heading',{name,exact:true}).waitFor();}
    await login();const initial=await api('/api/owner/settings');
    await page.locator('[data-hex]').fill('#62FF8C');await page.locator('[data-hex]').dispatchEvent('input');assert.equal((await api('/api/owner/settings')).accent,initial.accent);
    await page.getByRole('button',{name:'Apply color',exact:true}).click();await page.getByText('Accent saved.',{exact:true}).waitFor();assert.equal((await api('/api/owner/settings')).accent,'#62FF8C');
    await page.getByRole('button',{name:'Reorder Appearance',exact:true}).focus();await page.keyboard.press('Alt+ArrowDown');
    await page.waitForFunction(()=>document.querySelector('.grid').firstElementChild.dataset.card==='security');
    await page.reload();await page.getByRole('button',{name:'Reorder Appearance',exact:true}).waitFor();assert.equal(await page.locator('.grid>section').first().getAttribute('data-card'),'security');
    await page.getByRole('button',{name:'Reorder Appearance',exact:true}).focus();await page.keyboard.press('Alt+ArrowUp');await page.waitForFunction(()=>document.querySelector('.grid').firstElementChild.dataset.card==='appearance');
    await page.getByRole('button',{name:'Reset color',exact:true}).click();await page.getByRole('button',{name:'Apply color',exact:true}).click();await page.getByText('Accent saved.',{exact:true}).waitFor();
    await page.getByLabel('Keep sidebar open',{exact:true}).uncheck();await page.waitForFunction(()=>document.querySelector('.sidebar').inert);assert.equal((await api('/api/owner/settings')).sidebar,'auto');
    await page.getByLabel('Keep sidebar open',{exact:true}).check();await page.waitForFunction(()=>!document.querySelector('.sidebar').inert);results.settings_persistence='PASS';
    await page.getByRole('button',{name:'Change Access Key',exact:true}).click();assert.equal(await page.locator('#app').evaluate(n=>n.inert),true);
    await page.getByLabel('Current Access Key',{exact:true}).fill('unsaved fixture');await page.keyboard.press('Escape');await page.getByText('This form contains unsaved input.',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Discard input and close',exact:true}).click();assert.equal(await page.locator('#app').evaluate(n=>n.inert),false);
    assert.equal(await page.evaluate(()=>document.activeElement.textContent),'Change Access Key');
    await page.getByRole('button',{name:'Change Access Key',exact:true}).click();
    for(let i=0;i<12;i++){await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>!!document.activeElement.closest('[role=dialog]')),true);}
    const header=await page.locator('.dialog-header h2').boundingBox();await page.mouse.move(header.x+20,header.y+10);await page.mouse.down();await page.mouse.move(0,0);await page.mouse.up();const bounds=await page.locator('[role=dialog]').boundingBox();assert.ok(bounds.x>=8&&bounds.y>=8);
    await page.keyboard.press('Escape');results.dialog_keyboard='PASS';
    const notePath='Shell workflow '+crypto.randomBytes(4).toString('hex')+'.md',original='Public paragraph.\n\n@root\n\nLast paragraph.\n';
    await api('/api/notes','POST',{path:notePath,text:original});
    const event=page.waitForEvent('download',{timeout:120000});await page.getByRole('button',{name:'Create and download snapshot',exact:true}).click();const download=await event,zip=path.join(scratch,'backup.zip');await download.saveAs(zip);
    const backup=(await api('/api/owner/operations')).find(x=>x.kind==='backup'&&x.state==='COMPLETED');assert.equal(crypto.createHash('sha256').update(fs.readFileSync(zip)).digest('hex'),backup.sha256);
    await page.getByRole('button',{name:'Close dialog',exact:true}).click();
    const note=await api('/api/note?'+new URLSearchParams({path:notePath}));await api('/api/note','PUT',{path:notePath,text:'Changed after backup.\n',expected_sha256:note.sha256});
    await page.locator('#restore-file').setInputFiles(zip);await page.getByRole('button',{name:'Restore this snapshot',exact:true}).waitFor({timeout:120000});
    const staged=(await api('/api/owner/operations')).find(x=>x.kind==='restore'&&x.state==='AWAITING_CONFIRMATION');assert.ok(staged);
    await page.getByRole('button',{name:'Close dialog',exact:true}).click();await page.locator('[data-op-review="'+staged.id+'"]').click();await page.getByRole('button',{name:'Restore this snapshot',exact:true}).waitFor();
    await page.getByRole('button',{name:'Restore this snapshot',exact:true}).click();await page.getByRole('button',{name:'Restore snapshot',exact:true}).click();
    for(let i=0;i<120;i++){if((await context.request.get(origin+'/api/auth/session')).status()===401)break;await sleep(500);}
    await login();assert.equal((await api('/api/owner/operations/'+staged.id)).state,'COMPLETED');assert.equal((await api('/api/note?'+new URLSearchParams({path:notePath}))).text,original);results.browser_backup_restore='PASS';
    await nav('Shares');await page.getByRole('button',{name:'Create Share',exact:true}).click();await page.getByLabel('Note path',{exact:true}).fill(notePath);await page.getByLabel('Permission',{exact:true}).selectOption('edit');
    await page.getByLabel('Password action',{exact:true}).selectOption('replace');await page.getByLabel('New Share password',{exact:true}).fill('Browser share 123!');
    await page.locator('[role=dialog]').getByRole('button',{name:'Create Share',exact:true}).click();await page.locator('.copy-value').waitFor();const shareUrl=await page.locator('.copy-value').textContent();
    await page.getByRole('button',{name:'Copy',exact:true}).click();assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),shareUrl);
    await page.evaluate(()=>{navigator.clipboard.writeText=async()=>{throw Error('Clipboard unavailable in this fixture');};});
    await page.getByRole('button',{name:'Copy',exact:true}).click();await page.getByText('Clipboard is unavailable. Select the complete value above and copy it manually.',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Close dialog',exact:true}).click();await page.reload();await page.getByRole('searchbox',{name:'Search Shares',exact:true}).fill(notePath);
    const row=page.locator('[data-share]').filter({hasText:notePath}).first();await row.waitFor();assert.equal(await row.getByRole('button',{name:'Copy URL',exact:true}).isDisabled(),true);
    const visitor=await browser.newContext(),sharedPage=await visitor.newPage();await sharedPage.goto(shareUrl);await sharedPage.getByLabel('Share password',{exact:true}).fill('Browser share 123!');await sharedPage.getByRole('button',{name:'Unlock',exact:true}).click();await sharedPage.getByRole('button',{name:'Edit',exact:true}).click();
    const editable=sharedPage.locator('#surface textarea');await editable.last().fill('\nVisitor workflow saved.\n');await sharedPage.getByRole('button',{name:'Save changes',exact:true}).click();await sharedPage.getByText('Changes saved.',{exact:true}).waitFor();assert.ok((await api('/api/note?'+new URLSearchParams({path:notePath}))).text.includes('@root'));
    await page.bringToFront();await row.getByRole('button',{name:'Revoke',exact:true}).click();await page.getByRole('button',{name:'Revoke Share',exact:true}).click();
    // The click dispatches an asynchronous mutation; verify its visible receipt
    // before probing revocation from the independent visitor session.
    await row.getByText('revoked',{exact:true}).waitFor();
    assert.equal((await visitor.request.get(shareUrl+'/api/policy')).status(),404);await visitor.close();results.shares_clipboard_public='PASS';
    await nav('Crusher');await page.getByLabel('Source text',{exact:true}).fill('SHELL_BROWSER_FIXTURE: Source material about links and hierarchical knowledge.');await page.getByRole('button',{name:'Submit source',exact:true}).click();await page.getByText('Source accepted.',{exact:true}).first().waitFor({timeout:30000});
    let job;for(let i=0;i<160;i++){job=(await api('/api/v1/crusher/jobs?limit=100'))[0];if(['COMPLETED','FAILED'].includes(job.state))break;await sleep(500);}assert.equal(job.state,'COMPLETED',JSON.stringify(job));assert.ok(!Object.hasOwn(job,'result')&&!Object.hasOwn(job,'path'));results.crusher_owner_ui='PASS';
    await nav('Vault');await page.getByRole('button',{name:'Fullscreen',exact:true}).click();await page.waitForFunction(()=>!!document.fullscreenElement);await page.getByRole('button',{name:'Exit fullscreen',exact:true}).click();await page.waitForFunction(()=>!document.fullscreenElement);await page.getByRole('button',{name:'Reconnect',exact:true}).click();results.vault_toolbar='PASS';
    await nav('Settings');const logsEvent=page.waitForEvent('download',{timeout:30000});await page.getByRole('button',{name:'Download archived logs',exact:true}).click();const logs=await logsEvent;assert.match(logs.suggestedFilename(),/^mastermind-logs-\d{8}T\d{6}Z.zip$/);await page.getByRole('button',{name:'Close dialog',exact:true}).click();results.logs_download='PASS';
    await page.screenshot({path:path.join(out,'settings-final.png'),fullPage:true});
    assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({...results,browser_errors:errors},null,2));console.log(JSON.stringify(results));
  }catch(error){if(page)await page.screenshot({path:path.join(out,'failed.png'),fullPage:true}).catch(()=>{});throw error;}
  finally{await browser.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
