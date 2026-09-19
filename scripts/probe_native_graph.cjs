const {chromium} = require('./lib/browser.cjs');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
  const root=path.resolve(__dirname,'..'),origin='http://localhost:18390';
  const browser=await chromium.launch({headless:true});
  try {
    const context=await browser.newContext({viewport:{width:1440,height:1000}});
    const response=await context.request.post(origin+'/api/auth/login',{data:{access_key:fs.readFileSync(path.join(root,'.local/secrets/core/bootstrap_access_key'),'utf8')},headers:{Origin:origin}});
    assert.equal(response.status(),200);
    const page=await context.newPage();await page.goto(origin+'/runtime/index.html?autoconnect=1&path=runtime/websockify&resize=remote');
    await page.waitForTimeout(3500);
    await page.mouse.click(720,250);await page.keyboard.press('Escape');await page.keyboard.press('Control+p');
    await page.keyboard.type('Open graph view',{delay:45});await page.waitForTimeout(700);await page.keyboard.press('Enter');
    await page.waitForTimeout(2500);
    const status=()=>page.evaluate(async()=>(await fetch('/api/status')).json());
    const first=await status(),graph=first.runtime.bridge.graphs.find(g=>g.visible);
    assert.ok(graph?.nodes>0,'The native graph has no nodes');assert.equal(graph.type,'graph');
    const references=first.runtime.bridge.native_references;
    assert.ok(references.ready&&!references.failure&&!references.pending,'The native reference index is not ready');
    await page.screenshot({path:path.join(root,'artifacts/runtime-native-graph.png')});
    await page.waitForTimeout(1500);
    const second=(await status()).runtime.bridge.native_references;
    assert.equal(second.parsed,references.parsed,'Idle references keep reparsing');
    await page.keyboard.press('Control+o');await page.keyboard.type('Runtime test',{delay:40});await page.keyboard.press('Enter');
    await page.waitForTimeout(1000);
    const hidden=(await status()).runtime.bridge.native_references;
    await page.waitForTimeout(1500);
    const final=(await status()).runtime.bridge.native_references;
    assert.equal(final.parsed,hidden.parsed);
    console.log(JSON.stringify({native_graph:'PASS',idle_reparse:'NONE',graph}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
