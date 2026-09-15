const {chromium}=require('C:/Users/pc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
  const root=path.resolve(__dirname,'..'),origin='http://localhost:18390',browser=await chromium.launch({headless:true});
  let owner,csrf,share;
  try{
    owner=await browser.newContext();
    const login=await owner.request.post(origin+'/api/auth/login',{data:{access_key:fs.readFileSync(path.join(root,'.local/secrets/core/bootstrap_access_key'),'utf8')},headers:{Origin:origin}});
    assert.equal(login.status(),200);csrf=(await login.json()).csrf;
    const headers={Origin:origin,'X-CSRF-Token':csrf},notePath='Shared browser.md';
    const source='---\nprivate: HIDDEN_FRONTMATTER_CANARY\n---\n\nPublic introduction.\n\n@HIDDEN_TARGET_CANARY\n\nFinal paragraph.\n';
    const current=await owner.request.get(origin+'/api/note',{params:{path:notePath}});
    const written=current.status()===200?await owner.request.put(origin+'/api/note',{headers,data:{path:notePath,text:source,expected_sha256:(await current.json()).sha256}}):await owner.request.post(origin+'/api/notes',{headers,data:{path:notePath,text:source}});
    assert.equal(written.status(),200);
    const issued=await owner.request.post(origin+'/api/v1/shares',{headers,data:{path:notePath,permission:'edit'}});
    assert.equal(issued.status(),200);share=await issued.json();
    const visitor=await browser.newContext({viewport:{width:1440,height:1000}}),page=await visitor.newPage();
    const requests=[],errors=[];page.on('request',r=>requests.push(r.url()));page.on('pageerror',e=>errors.push(e.message));
    await page.goto(share.url);await page.getByRole('button',{name:'Edit',exact:true}).waitFor({state:'visible'});
    assert.ok(!(await page.content()).includes('HIDDEN_'));
    await page.getByRole('button',{name:'Edit',exact:true}).click();
    const fields=page.locator('#surface textarea');assert.ok(await fields.count()>0);
    let target=-1;for(let i=0;i<await fields.count();i++)if((await fields.nth(i).inputValue()).includes('Final paragraph'))target=i;
    assert.ok(target>=0);await fields.nth(target).fill('\nBrowser visitor change.\n');
    await page.getByRole('button',{name:'Save changes'}).click();await page.getByText('Changes saved.',{exact:true}).waitFor();
    let note=await (await owner.request.get(origin+'/api/note',{params:{path:notePath}})).json();
    assert.ok(note.text.includes('Browser visitor change.')&&note.text.includes('HIDDEN_FRONTMATTER_CANARY')&&note.text.includes('@HIDDEN_TARGET_CANARY'));
    // Conflict against a real Core/Obsidian quiesce boundary retains only the visitor's safe draft.
    await fields.nth(target).fill('\nUnsaved visitor draft.\n');
    const ownerEdit=await owner.request.put(origin+'/api/note',{headers,data:{path:notePath,text:note.text.replace('Public introduction.','Owner concurrent change.'),expected_sha256:note.sha256}});
    assert.equal(ownerEdit.status(),200);
    await page.getByRole('button',{name:'Save changes'}).click();await page.locator('#conflict').waitFor({state:'visible'});
    assert.ok((await page.locator('#draft textarea').evaluateAll(nodes=>nodes.map(n=>n.value))).some(v=>v.includes('Unsaved visitor draft')));
    assert.ok(!(await page.content()).includes('HIDDEN_'));
    await page.screenshot({path:path.join(root,'artifacts/shared-desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(root,'artifacts/shared-mobile.png'),fullPage:true});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Mobile page overflows horizontally');
    assert.equal((await visitor.request.get(origin+'/api/notes')).status(),401);
    assert.ok(requests.every(u=>u.startsWith(share.url)), 'Public page requested a resource outside its Share');
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({shared_browser:'PASS',real_native_commit:'PASS',protected_bytes:'PRESERVED',conflict:'SAFE_DRAFT_RETAINED',owner_scope:'DENIED',mobile_overflow:false,requests:requests.length}));
  }finally{
    if(share&&owner)await owner.request.patch(origin+'/api/v1/shares/'+share.share_id,{headers:{Origin:origin,'X-CSRF-Token':csrf},data:{revoke:true}});
    await browser.close();
  }
})().catch(error=>{console.error(error.message);process.exitCode=1;});
