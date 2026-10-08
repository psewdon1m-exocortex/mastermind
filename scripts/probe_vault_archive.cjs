/* Real HTTP/UI backup round-trip against a marked synthetic Core only. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('./lib/browser.cjs');
const root=path.resolve(__dirname,'..'),work=path.resolve(process.argv[2]||'');
assert.ok(work.startsWith(path.join(root,'.local','qualification')+path.sep));
const fixture=JSON.parse(fs.readFileSync(path.join(work,'fixture.json'),'utf8'));
assert.equal(fixture.fixture,'mastermind-vault-archive/v1');
assert.match(fixture.origin,/^http:\/\/127\.0\.0\.1:\d+$/);
const output=path.join(root,'artifacts/vault-archive');fs.mkdirSync(output,{recursive:true});

(async()=>{
  const browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000},acceptDownloads:true}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const report={checks:[],limitations:['Real Core HTTP and filesystem; offline Runtime coordination, no native Obsidian.']};
  const check=name=>{report.checks.push(name);console.log('PASS '+name);};
  const login=async()=>{
    await page.goto(fixture.origin+'/login');
    await page.getByLabel('Access Key',{exact:true}).fill('synthetic-vault-archive-key');
    await page.getByRole('button',{name:'Enter service',exact:true}).click();
    await page.getByRole('heading',{name:'dashboard',exact:true}).waitFor();
  };
  const close=()=>page.getByRole('button',{name:'Close dialog',exact:true}).click();
  const request=(route,method='GET',body)=>page.evaluate(async({route,method,body})=>{
    const {api}=await import('/assets/ui.js');return api(route,{method,body});
  },{route,method,body});
  const select=async(file)=>{
    await page.getByRole('button',{name:'Restore Vault ZIP',exact:true}).click();
    await page.getByRole('dialog').getByText('The archive is inspected before any replacement.',{exact:false}).waitFor();
    await page.locator('#restore-file').setInputFiles(file);
  };
  try{
    await login();
    await page.locator('.sidebar').getByRole('link',{name:'Settings',exact:true}).click();
    const card=page.locator('[data-card="backup"]');
    await card.getByRole('button',{name:'Download Vault ZIP',exact:true}).waitFor();
    assert.equal(await card.getByRole('button',{name:'Restore ZIP snapshot',exact:true}).count(),1);
    await card.scrollIntoViewIfNeeded();await card.screenshot({path:path.join(output,'backup-card.png')});
    const fetchDownload=async(label,name)=>{
      const promise=page.waitForEvent('download');
      await card.getByRole('button',{name:label,exact:true}).click();
      const download=await promise;assert.equal(await download.failure(),null);
      await download.saveAs(path.join(work,name));await close();
    };
    await fetchDownload('Download Vault ZIP','vault.zip');
    await fetchDownload('Create and download snapshot','recovery.zip');
    check('Both manual exports download through the Settings card without leaving the page');
    await select(path.join(work,'recovery.zip'));
    await page.getByRole('alert').filter({hasText:'INVALID_VAULT_ARCHIVE'}).waitFor();
    assert.equal(fs.readFileSync(path.join(work,'data/vault/current/root/root.md'),'utf8'),'#main\n[[Birds]]\n');
    await close();
    check('Encrypted recovery ZIP cannot be mistaken for a plain Vault; rejected upload leaves files intact');

    const current=await request('/api/note?path=root/root.md');
    await request('/api/note','PUT',{path:'root/root.md',text:'Changed after download',expected_sha256:current.sha256});
    await page.evaluate(async()=>{const {preferences}=await import('/assets/ui.js');await preferences({accent:'#FF51B0'});});
    await select(path.join(work,'vault.zip'));
    await page.getByRole('button',{name:'Restore this Vault',exact:true}).waitFor();
    assert.match(await page.getByRole('dialog').innerText(),/2 notes/);
    assert.equal(fs.readFileSync(path.join(work,'data/vault/current/root/root.md'),'utf8'),'Changed after download');
    await page.getByRole('dialog').screenshot({path:path.join(output,'inspection.png')});
    await page.getByRole('button',{name:'Restore this Vault',exact:true}).click();
    await page.getByRole('button',{name:'Cancel',exact:true}).click();
    assert.equal(fs.readFileSync(path.join(work,'data/vault/current/root/root.md'),'utf8'),'Changed after download');
    const ops=await request('/api/owner/operations');
    const inspected=ops.find(op=>op.kind==='vault_restore'&&op.state==='AWAITING_CONFIRMATION');
    assert.ok(inspected);
    await page.reload();
    await page.locator('[data-op-review="'+inspected.id+'"]').click();
    await page.getByRole('button',{name:'Restore this Vault',exact:true}).click();
    await page.getByRole('button',{name:'Restore Vault',exact:true}).click();
    await page.waitForFunction(async()=>{const response=await fetch('/api/auth/session');return response.status===401;});
    await login();
    const result=await request('/api/owner/operations/'+inspected.id);
    assert.equal(result.state,'COMPLETED');
    const restored=await request('/api/note?path=root/root.md');
    assert.equal(restored.text,'#main\n[[Birds]]\n');
    const prefs=await request('/api/owner/settings');
    assert.equal(prefs.accent,'#FF51B0');
    check('Inspection and Cancel do not write; Review resumes the Vault operation; confirmed restore replaces files and retains Shell preferences');
    check('Restore ends the old session; the current Access Key still signs in after completion');

    await page.locator('.sidebar').getByRole('link',{name:'Settings',exact:true}).click();
    await page.setViewportSize({width:390,height:844});
    await card.scrollIntoViewIfNeeded();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    const first=await card.getByRole('button',{name:'Create and download snapshot',exact:true}).boundingBox();
    const second=await card.getByRole('button',{name:'Download Vault ZIP',exact:true}).boundingBox();
    assert.ok(second.y>=first.y+first.height);
    await card.screenshot({path:path.join(output,'backup-card-mobile.png')});
    check('Paired actions stack without horizontal overflow on mobile');
    assert.deepEqual(errors,[]);report.status='PASS';
  }catch(error){report.status='FAIL';report.error=error.stack;throw error;}
  finally{fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(report,null,2)+'\n');await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
