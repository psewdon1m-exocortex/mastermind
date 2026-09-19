/* Real Obsidian + Core retrieval + local E5; only the explicitly marked synthetic Vault. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('./lib/browser.cjs');
const work=path.resolve(process.argv[2]),output=path.resolve('artifacts/related-notes');
assert.equal(JSON.parse(fs.readFileSync(path.join(work,'fixture.json'),'utf8')).fixture,'mastermind-related-notes/v1');
fs.mkdirSync(output,{recursive:true});
const status=async()=>{const response=await fetch('http://127.0.0.1:18495/fixture/status');assert.equal(response.status,200);return response.json();};

(async()=>{
 const browser=await chromium.connectOverCDP('http://127.0.0.1:19394');
 const report={schema:'mastermind.related-notes.native.v1',checks:[],errors:[],fixture:work,
  limitations:['Synthetic Vault; actual Obsidian and E5, with offline fixture coordination. No live service deployment.']};
 const check=name=>{report.checks.push(name);console.log('PASS '+name);};
 const page=browser.contexts()[0].pages()[0];
 page.on('pageerror',error=>report.errors.push(error.message));
 try{
  await page.waitForFunction(()=>window.app?.workspace?.layoutReady);
  assert.equal(await page.evaluate(()=>app.vault.adapter.getBasePath()),'/qualification/core/vault/current');
  const trust=page.getByRole('button',{name:'Trust author and enable plugins',exact:true});
  if(await trust.isVisible())await trust.click();
  await page.waitForFunction(()=>app.plugins.plugins['mastermind-bridge']?.ready);
  await page.evaluate(()=>{
    window.relatedQueries=[];
    const bridge=app.plugins.plugins['mastermind-bridge'],original=bridge.core.bind(bridge);
    bridge.core=(route,data,...rest)=>{
      if(route==='/related-notes')relatedQueries.push({at:Date.now(),...data});
      return original(route,data,...rest);
    };
  });
  await page.evaluate(async()=>{
    const layout=app.workspace.getLayout();
    layout.main={id:layout.main.id,type:'split',direction:'vertical',children:[{id:'related-draft',type:'leaf',
      state:{type:'markdown',state:{file:'Draft.md',mode:'source',source:true}}}]};
    layout.active='related-draft';if(layout.right)layout.right.children=[];
    await app.workspace.changeLayout(layout);
    window.relatedSource=app.workspace.getLeavesOfType('markdown')[0];
    app.workspace.setActiveLeaf(relatedSource,{focus:true});
    app.commands.executeCommandById('mastermind-bridge:open-related-notes');
  });
  const panel=page.locator('.mastermind-related');
  await panel.waitFor({state:'visible'});
  const ready=()=>page.waitForFunction(()=>app.workspace.getLeavesOfType('mastermind-related-notes')[0]?.view.controller?.state.phase==='ready',{}, {timeout:35000});
  const titles=()=>panel.locator('.mastermind-related-item strong').allTextContents();
  await ready();
  let names=await titles();
  assert.ok(names.includes('Aircraft designers')&&names.includes('Composite materials'),JSON.stringify(names));
  assert.ok(!names.includes('Draft')&&!names.includes('Garden'),JSON.stringify(names));
  report.aviation=names;
  await page.screenshot({path:path.join(output,'aviation.png')});
  check('Native sidebar shows relevant ordinary notes through the actual Core endpoint and E5');

  const before=(await status()).requests;
  await page.locator('[data-type="markdown"] .cm-content').click();
  await page.keyboard.press('Control+a');
  await page.keyboard.type('Garden soil irrigation, flowers and vegetable plants.',{delay:12});
  await page.waitForFunction(()=>app.workspace.getLeavesOfType('mastermind-related-notes')[0]?.view.controller?.state.query?.text.includes('Garden soil'));
  await ready();names=await titles();
  assert.equal(names[0],'Garden');assert.ok(!names.includes('Composite materials'),JSON.stringify(names));
  assert.equal((await status()).requests-before,1,'Typing should coalesce into one request');
  report.gardening=names;
  await page.screenshot({path:path.join(output,'gardening.png')});
  check('Actual keyboard edits replace aviation suggestions with gardening after one debounced request');

  // Different vocabulary/language exercises the semantic channel beyond literal matching.
  await page.evaluate(()=>relatedSource.view.editor.setValue('Проектирование летательных аппаратов: как инженеры снижают массу крыла и повышают прочность конструкции?'));
  await page.waitForFunction(()=>app.workspace.getLeavesOfType('mastermind-related-notes')[0]?.view.controller?.state.query?.text.includes('Проектирование'));
  await ready();names=await titles();
  assert.ok(names.includes('Composite materials'),JSON.stringify(names));
  report.cross_language=names;check('Russian context retrieves the English aerospace material through real semantic search');

  await panel.getByRole('button',{name:'Open Composite materials',exact:true}).click();
  await page.waitForFunction(()=>relatedSource.view.file?.path==='Composite materials.md');
  await ready();assert.ok(!(await titles()).includes('Composite materials'));
  check('Suggestion activation opens the note and recommendations follow the new source');

  await page.evaluate(()=>app.workspace.rightSplit.collapse());
  await page.waitForTimeout(1600);
  const hiddenBefore=(await status()).requests;
  await page.evaluate(()=>relatedSource.view.editor.setValue('A synthetic edit while the suggestions pane is hidden.'));
  await page.waitForTimeout(3500);assert.equal((await status()).requests,hiddenBefore);
  check('Collapsed sidebar stops background recommendation requests');
  await page.evaluate(()=>app.workspace.revealLeaf(app.workspace.getLeavesOfType('mastermind-related-notes')[0]));
  await page.evaluate(()=>relatedSource.view.editor.setValue(''));
  await panel.getByText('Start writing to discover related notes.',{exact:true}).waitFor();
  assert.equal(await panel.locator('.mastermind-related-item').count(),0);
  check('An empty buffer immediately clears suggestions');

  await page.evaluate(async()=>{
    await relatedSource.openFile(app.vault.getFileByPath('Draft.md'));
    relatedSource.view.editor.setValue('Aircraft designers and airplane wing materials');
    app.workspace.setActiveLeaf(relatedSource,{focus:true});
  });
  await ready();
  await page.evaluate(()=>{window.relatedOldUrl=app.plugins.plugins['mastermind-bridge'].coreUrl;app.plugins.plugins['mastermind-bridge'].coreUrl='http://127.0.0.1:1';});
  await panel.getByRole('button',{name:'Refresh related notes',exact:true}).click();
  await panel.getByText('Could not update suggestions. Try Refresh.',{exact:true}).waitFor();
  await page.evaluate(()=>{app.plugins.plugins['mastermind-bridge'].coreUrl=relatedOldUrl;});
  await panel.getByRole('button',{name:'Refresh related notes',exact:true}).click();await ready();
  check('Connection failure is visible and Refresh recovers');
  assert.deepEqual(report.errors,[]);
  report.status='PASS';report.search=(await status()).search;
 }finally{
  report.queries=await page.evaluate(()=>window.relatedQueries||[]).catch(()=>[]);
  await page.screenshot({path:path.join(output,'last-state.png')}).catch(()=>{});
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));
  await browser.close();
 }
 console.log(JSON.stringify({status:report.status,checks:report.checks.length,errors:report.errors}));
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
