const {chromium} = require('C:/Users/pc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
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
    await page.keyboard.type('Open Mastermind Graph',{delay:45});await page.waitForTimeout(700);await page.keyboard.press('Enter');
    await page.waitForTimeout(2500);
    const status=()=>page.evaluate(async()=>(await fetch('/api/status')).json());
    const first=await status(),graph=first.runtime.bridge.graphs.find(g=>g.visible);
    assert.ok(graph?.nodes>0,'The native graph has no nodes');assert.ok(graph.render_count>0,'The native graph was not drawn');
    await page.screenshot({path:path.join(root,'artifacts/runtime-native-graph.png')});
    await page.waitForTimeout(1500);
    const second=(await status()).runtime.bridge.graphs.find(g=>g.visible);
    assert.equal(second.render_count,graph.render_count,'Idle graph keeps redrawing');
    await page.keyboard.press('Control+o');await page.keyboard.type('Runtime test',{delay:40});await page.keyboard.press('Enter');
    await page.waitForTimeout(1000);
    const hidden=(await status()).runtime.bridge.graphs;
    await page.waitForTimeout(1500);
    const final=(await status()).runtime.bridge.graphs;
    for(let i=0;i<hidden.length;i++)if(!hidden[i].visible)assert.equal(final[i].render_count,hidden[i].render_count);
    console.log(JSON.stringify({native_graph:'PASS',idle_redraw:'NONE',graph}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
