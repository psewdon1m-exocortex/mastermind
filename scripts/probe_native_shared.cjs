// Bounded native Obsidian versus public-editor collision, using one disposable note.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const {chromium}=require('./lib/browser.cjs');
const origin='http://localhost:18390',out=path.resolve('artifacts/public-editing-20260919');
fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true}),owner=await browser.newContext({viewport:{width:1600,height:1000}}),visitor=await browser.newContext();
 let session,share,nativeOpened=false;const name='Native share check '+crypto.randomBytes(4).toString('hex'),notePath=name+'.md';let native,publicPage;
 const api=async(route,method='GET',data)=>{const r=await owner.request.fetch(origin+route,{method,headers:{Origin:origin,...(session?{'X-CSRF-Token':session.csrf}:{})},...(data?{data}:{})});assert.ok(r.ok(),`${route}: ${r.status()}`);return r.json();};
 const read=()=>api('/api/note?'+new URLSearchParams({path:notePath}));
 const checkpoint=async name=>{await native.screenshot({path:path.join(out,name+'.png')});if(process.argv.includes('--inspect')){console.log(name);await new Promise(resolve=>{process.stdin.resume();process.stdin.once('data',()=>{process.stdin.pause();resolve();});});}};
 try{
  session=await api('/api/auth/login','POST',{access_key:fs.readFileSync('.local/secrets/core/bootstrap_access_key','utf8')});await api('/api/notes','POST',{path:notePath,text:`# ${name}\n\nBase note for simultaneous editing.\n\n@PRIVATE_REFERENCE\n`});share=await api('/api/v1/shares','POST',{path:notePath,permission:'edit'});
  native=await owner.newPage();await native.goto(origin+'/runtime/index.html?autoconnect=1&path=runtime/websockify&resize=remote');await native.locator('canvas:visible').first().waitFor();await native.waitForTimeout(2600);
  await native.mouse.click(500,400);await native.keyboard.press('Escape');await native.keyboard.press('Control+o');await native.waitForTimeout(400);await native.keyboard.type(name,{delay:2});await native.waitForTimeout(600);await checkpoint('native-search');
  await native.keyboard.press('Control+Enter');nativeOpened=true;await native.waitForTimeout(900);await checkpoint('native-note');
  publicPage=await visitor.newPage();await publicPage.goto(share.url);await publicPage.locator('#surface textarea').first().waitFor();await publicPage.clock.install();await publicPage.clock.pauseAt(new Date());
  await publicPage.locator('#surface textarea').first().fill('Visitor simultaneous draft.\n\n');
  await native.bringToFront();await native.mouse.click(530,220);await native.keyboard.press('Control+End');await native.keyboard.type('\nNative simultaneous change.\n',{delay:1});await native.waitForTimeout(150);await checkpoint('native-dirty');
  await publicPage.clock.runFor(1200);await publicPage.locator('#conflict').waitFor({state:'visible',timeout:15000});
  const current=await read();assert.ok(current.text.includes('Native simultaneous change.'));assert.ok(!current.text.includes('Visitor simultaneous draft.'));assert.ok(current.text.includes('@PRIVATE_REFERENCE'));assert.ok((await publicPage.locator('#draft textarea').first().inputValue()).includes('Visitor simultaneous draft.'));
  await publicPage.screenshot({path:path.join(out,'native-conflict.png')});const result={native:'PASS: real VNC/Obsidian edit',collision:'PASS: native bytes retained, stale public draft preserved for explicit merge',protected_content:'PASS'};fs.writeFileSync(path.join(out,'native-result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
 }finally{
  if(publicPage)await publicPage.close();if(nativeOpened){await native.bringToFront();await native.keyboard.press('Control+w').catch(()=>{});}if(native)await native.close();
  if(share)await api('/api/v1/shares/'+share.share_id,'PATCH',{revoke:true}).catch(()=>{});const note=await read().catch(()=>null);if(note)await api('/api/note','DELETE',{path:notePath,expected_sha256:note.sha256}).catch(()=>{});
  if(session)await api('/api/auth/logout','POST',{}).catch(()=>{});await browser.close();
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
