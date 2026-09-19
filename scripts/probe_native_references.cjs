/* Real Obsidian 1.13.7, synthetic fixture only. No credentials or production Vault. */
const {chromium}=require('./lib/browser.cjs');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),artifact=path.join(root,'artifacts/native-references');
const fixture=path.join(root,'.local/native-reference-qualification/vault');
const source='# Source\n\n😀 @Target\n\n@chronos: event-123\n\n@saturn: root/spec.pdf\n\n[[Native]]\n\n`@Excluded`\n\n<!-- @Excluded -->\n\n@Future\n';
const key=(kind,target)=>'mastermind-resource:'+kind+':'+encodeURIComponent(target)+':resource';
fs.mkdirSync(artifact,{recursive:true});

(async()=>{
 const browser=await chromium.connectOverCDP('http://127.0.0.1:19393');
 const result={version:'1.13.7',mode:'portable',checks:[],errors:[]};
 const started=Date.now();
 try{
  const page=browser.contexts()[0].pages()[0];
  page.on('pageerror',error=>result.errors.push(error.message));
  await page.waitForFunction(()=>window.app?.vault?.adapter&&app.workspace?.layoutReady);
  assert.equal(await page.evaluate(()=>app.vault.adapter.getBasePath()),'/qualification/vault');
  const trust=page.getByRole('button',{name:'Trust author and enable plugins',exact:true});
  if(await trust.isVisible())await trust.click();
  await page.keyboard.press('Escape');
  await page.evaluate(async()=>{
    const layout=app.workspace.getLayout();
    layout.main={id:layout.main.id,type:'split',direction:'vertical',children:[{id:'native-source',type:'leaf',
      state:{type:'markdown',state:{file:'Source.md',mode:'source',source:true}}}]};
    layout.active='native-source';
    if(layout.right)layout.right.children=[];
    await app.workspace.changeLayout(layout);
  });
  const ready=()=>page.waitForFunction(()=>{const n=app.plugins.plugins['mastermind-bridge']?.nativeLinks;
    return n?.ready&&!n.diagnostics().running&&!n.diagnostics().dictionary_pending&&n.diagnostics().pending===0&&!n.diagnostics().failure},{},{timeout:30000});
  const check=(name)=>{result.checks.push(name);console.log('PASS '+name)};
  await ready();
  assert.deepEqual(await page.evaluate(()=>Object.keys(app.commands.commands).filter(id=>
    /^mastermind-bridge:open-(graph|backlinks|outgoing)$/.test(id))),[]);
  await page.evaluate(async text=>{
    const renamed=app.vault.getFileByPath('Renamed.md');if(renamed)await app.fileManager.renameFile(renamed,'Target.md');
    for(const name of ['Future.md','Transient.md']){const file=app.vault.getFileByPath(name);if(file)await app.vault.delete(file);}
    await app.vault.modify(app.vault.getFileByPath('Source.md'),text);
    const dual=app.vault.getFileByPath('Dual.md');
    if(dual)await app.vault.modify(dual,'[[Target]] @Target');else await app.vault.create('Dual.md','[[Target]] @Target');
  },source);
  await page.waitForFunction(offset=>app.metadataCache.resolvedLinks['Source.md']?.['Target.md']===1&&
    app.metadataCache.getCache('Source.md')?.links?.some(link=>link.original==='@Target'&&link.position.start.offset===offset),source.indexOf('@Target'));
  await ready();
  let state=await page.evaluate(()=>({resolved:app.metadataCache.resolvedLinks['Source.md'],unresolved:app.metadataCache.unresolvedLinks['Source.md'],
    links:app.metadataCache.getCache('Source.md').links,files:app.vault.getFiles().map(f=>f.path)}));
  assert.equal(state.resolved['Native.md'],1);assert.equal(state.resolved['Target.md'],1);
  assert.ok(await page.evaluate(()=>app.metadataCache.getBacklinksForFile(app.vault.getFileByPath('Target.md')).count()>=3));
  assert.ok(!state.resolved['Excluded.md']);assert.equal(state.unresolved[key('chronos','event-123')],1);
  assert.equal(state.unresolved[key('saturn','root/spec.pdf')],1);
  const at=state.links.find(link=>link.original==='@Target');
  assert.equal(at.position.start.offset,source.indexOf('@Target'));
  assert.equal(at.position.end.offset,source.indexOf('@Target')+7);
  assert.ok(!state.files.some(file=>file.includes('mastermind-resource')));
  assert.equal(fs.readFileSync(path.join(fixture,'Source.md'),'utf8'),source);
  check('Native cache: @note, Chronos, Saturn, Unicode offsets, excluded code/comments, unchanged Markdown');

  await page.evaluate(async()=>{
    for(const type of ['graph','localgraph','backlink','outgoing-link'])for(const leaf of app.workspace.getLeavesOfType(type))leaf.detach();
    const sourceLeaf=app.workspace.getLeaf('tab');await sourceLeaf.openFile(app.vault.getFileByPath('Source.md'));
    await app.workspace.revealLeaf(sourceLeaf);app.workspace.setActiveLeaf(sourceLeaf,{focus:true});
    const graph=app.workspace.getLeaf('tab');await graph.setViewState({type:'graph',active:true});
    const local=app.workspace.getLeaf('split');await local.setViewState({type:'localgraph',group:sourceLeaf,state:{file:'Source.md'},active:true});
    window.nativeReferenceViews={graph,local,sourceLeaf};
    app.workspace.leftSplit.collapse();app.workspace.rightSplit.collapse();
  });
  await page.waitForFunction(()=>nativeReferenceViews.graph.view.renderer.nodes.some(n=>n.id.startsWith('mastermind-resource:')));
  await page.waitForTimeout(500);
  state=await page.evaluate(()=>Object.fromEntries(['graph','local'].map(name=>{const view=nativeReferenceViews[name].view;
    (view.engine||view.dataEngine).setOptions({close:true});return[name,view.renderer.nodes.map(node=>({id:node.id,label:node.getDisplayText(),links:Object.keys(node.forward)}))]})));
  for(const name of ['graph','local']){
    assert.ok(state[name].some(node=>node.id==='Target.md'));
    assert.ok(state[name].some(node=>node.label==='@chronos: event-123'));
    assert.ok(state[name].some(node=>node.label==='@saturn: root/spec.pdf'));
  }
  assert.ok(!state.local.some(node=>node.id==='Excluded.md'));
  await page.screenshot({path:path.join(artifact,'native-graphs.png')});
  check('Native global and local graphs contain custom edges and readable external labels');

  // Exercise native filter semantics and local depth using the actual engine.
  await page.evaluate(()=>nativeReferenceViews.graph.view.dataEngine.setOptions({hideUnresolved:true}));
  assert.equal(await page.evaluate(()=>nativeReferenceViews.graph.view.renderer.nodes.some(n=>n.id.startsWith('mastermind-resource:'))),false);
  await page.evaluate(()=>nativeReferenceViews.graph.view.dataEngine.setOptions({hideUnresolved:false}));
  check('Existing-files filter hides virtual targets without hiding resolved @note edges');

  await page.evaluate(async()=>{
    nativeReferenceViews.sourceLeaf.setGroupMember(null);
    nativeReferenceViews.local.setGroupMember(null);
    nativeReferenceViews.local.detach();
    const target=app.workspace.getLeaf('tab');await target.openFile(app.vault.getFileByPath('Target.md'));
    target.setGroupMember(null);await app.workspace.revealLeaf(target);app.workspace.setActiveLeaf(target,{focus:true});
    const back=app.workspace.getRightLeaf(false);await back.setViewState({type:'backlink',group:null,state:{file:'Target.md'},active:true});
    app.workspace.rightSplit.expand();await app.workspace.revealLeaf(back);
    nativeReferenceViews.back=back;
  });
  await page.waitForFunction(()=>nativeReferenceViews.back.view.contentEl.innerText.includes('@Target'));
  await page.screenshot({path:path.join(artifact,'native-backlinks.png')});
  check('Native Backlinks renders the actual @Target text and source context');
  await page.evaluate(async()=>{
    await nativeReferenceViews.sourceLeaf.openFile(app.vault.getFileByPath('Source.md'));
    await app.workspace.revealLeaf(nativeReferenceViews.sourceLeaf);app.workspace.setActiveLeaf(nativeReferenceViews.sourceLeaf,{focus:true});
    const out=app.workspace.getRightLeaf(true);await out.setViewState({type:'outgoing-link',group:null,state:{file:'Source.md'},active:true});
    await app.workspace.revealLeaf(out);nativeReferenceViews.out=out;
  });
  await page.waitForFunction(()=>nativeReferenceViews.out.view.contentEl.innerText.includes('@saturn: root/spec.pdf'));
  await page.screenshot({path:path.join(artifact,'native-outgoing.png')});
  await page.locator('.outgoing-link-item').filter({hasText:'@chronos: event-123'}).click();
  await page.locator('.modal').getByText('chronos unavailable',{exact:true}).waitFor();
  await page.keyboard.press('Escape');
  await page.locator('.outgoing-link-item').filter({hasText:'@saturn: root/spec.pdf'}).click();
  await page.locator('.modal').getByText('saturn unavailable',{exact:true}).waitFor();
  await page.keyboard.press('Escape');
  check('Native Outgoing Links opens both existing resource modals (offline state expected)');
  const beforeFiles=await page.evaluate(()=>app.vault.getFiles().map(f=>f.path).sort());
  await page.evaluate(link=>nativeReferenceViews.graph.view.renderer.onNodeClick(new MouseEvent('click'),link,'unresolved'),key('chronos','event-123'));
  await page.locator('.modal').getByText('chronos unavailable',{exact:true}).waitFor();await page.keyboard.press('Escape');
  assert.deepEqual(await page.evaluate(()=>app.vault.getFiles().map(f=>f.path).sort()),beforeFiles);
  check('Graph resource activation opens the modal without creating a phantom note');
  await page.evaluate(link=>nativeReferenceViews.sourceLeaf.openLinkText(link,'Source.md'),key('saturn','root/spec.pdf'));
  await page.locator('.modal').getByText('saturn unavailable',{exact:true}).waitFor();await page.keyboard.press('Escape');
  await page.locator('.outgoing-link-item').filter({hasText:'@chronos: event-123'}).click({button:'right'});
  await page.getByText('Open @chronos: event-123',{exact:true}).click();
  await page.locator('.modal').getByText('chronos unavailable',{exact:true}).waitFor();await page.keyboard.press('Escape');
  assert.deepEqual(await page.evaluate(()=>app.vault.getFiles().map(f=>f.path).sort()),beforeFiles);
  check('Direct leaf and context-menu opening preserve the resource behavior');

  await page.evaluate(async()=>{
    await app.workspace.revealLeaf(nativeReferenceViews.sourceLeaf);
    await nativeReferenceViews.sourceLeaf.openFile(app.vault.getFileByPath('Source.md'));
    app.workspace.setActiveLeaf(nativeReferenceViews.sourceLeaf,{focus:true});
    await nativeReferenceViews.sourceLeaf.setViewState({type:'markdown',state:{file:'Source.md',mode:'source',source:true},active:true});
    app.workspace.rightSplit.collapse();
  });
  await page.locator('.workspace-leaf.mod-active .cm-content').click();
  await page.keyboard.press('Control+End');
  for(let i=0;i<6;i++){
    await page.keyboard.type('\nNative save '+i);await page.keyboard.press('Control+s');
    await page.waitForFunction(marker=>app.vault.adapter.read('Source.md').then(text=>text.includes(marker)),'Native save '+i);
  }
  check('Six actual keyboard edits and saves preserve original @ syntax');
  await page.evaluate(async()=>app.fileManager.renameFile(app.vault.getFileByPath('Target.md'),'Renamed.md'));
  await page.waitForFunction(()=>app.metadataCache.resolvedLinks['Source.md']?.['Renamed.md']===1);
  const renamed=await page.evaluate(()=>app.vault.read(app.vault.getFileByPath('Source.md')));
  assert.ok(renamed.includes('@Renamed'));assert.ok(!renamed.includes('@Target'));assert.ok(renamed.includes('`@Excluded`'));
  assert.ok(!renamed.includes('mastermind-resource:'));
  assert.equal(await page.evaluate(()=>app.vault.read(app.vault.getFileByPath('Dual.md'))),'[[Renamed]] @Renamed');
  check('Native rename propagates @ while preserving Markdown and excluded text');
  await page.evaluate(async()=>{await app.vault.create('Future.md','# Future\n');});
  await page.waitForFunction(()=>app.metadataCache.resolvedLinks['Source.md']?.['Future.md']===1);
  await page.evaluate(()=>app.vault.delete(app.vault.getFileByPath('Future.md')));
  await page.waitForFunction(()=>!app.metadataCache.resolvedLinks['Source.md']?.['Future.md']&&app.metadataCache.unresolvedLinks['Source.md']?.Future===1);
  check('Creation resolves existing @ text; deletion retains its broken-link history');

  const bytes=fs.readFileSync(path.join(fixture,'Source.md'),'utf8');
  await page.evaluate(()=>app.plugins.disablePlugin('mastermind-bridge'));
  await page.waitForFunction(()=>!app.metadataCache.resolvedLinks['Source.md']?.['Renamed.md']);
  assert.equal(fs.readFileSync(path.join(fixture,'Source.md'),'utf8'),bytes);
  assert.equal(await page.evaluate(()=>Object.keys(app.metadataCache.unresolvedLinks['Source.md']).some(k=>k.startsWith('mastermind-resource:'))),false);
  assert.equal(await page.evaluate(()=>nativeReferenceViews.graph.view.renderer.nodes.some(n=>n.id.startsWith('mastermind-resource:'))),false);
  await page.evaluate(()=>app.plugins.enablePlugin('mastermind-bridge'));await ready();
  await page.waitForFunction(()=>app.metadataCache.resolvedLinks['Source.md']?.['Renamed.md']===1);
  check('Disable/re-enable restores native caches and reconstructs ephemeral links');
  await page.reload();await ready();
  await page.waitForFunction(()=>app.metadataCache.resolvedLinks['Source.md']?.['Renamed.md']===1);
  assert.equal(fs.readFileSync(path.join(fixture,'Source.md'),'utf8'),bytes);
  check('Editor reload preserves data and rebuilds native references');
  await page.evaluate(async()=>{
    await app.plugins.disablePlugin('mastermind-bridge');
    for(const type of ['mastermind-graph','mastermind-backlinks','mastermind-outgoing']){
      const leaf=app.workspace.getLeaf('tab');await leaf.setViewState({type});
    }
    await app.plugins.enablePlugin('mastermind-bridge');
  });
  await ready();
  await page.waitForFunction(()=>{
    let old=0;app.workspace.iterateAllLeaves(leaf=>{if(leaf.getViewState().type.startsWith('mastermind-'))old++});return old===0;
  });
  assert.ok(await page.evaluate(()=>app.workspace.getLeavesOfType('graph').length>0&&
    app.workspace.getLeavesOfType('backlink').length>0&&app.workspace.getLeavesOfType('outgoing-link').length>0));
  check('Saved custom graph/backlink/outgoing leaves migrate to native views');

  result.diagnostics=await page.evaluate(()=>app.plugins.plugins['mastermind-bridge'].nativeLinks.diagnostics());
  result.elapsed_ms=Date.now()-started;
  assert.deepEqual(result.errors,[]);
  result.status='PASS';
 }catch(error){result.status='FAIL';result.error=error.stack;throw error}
 finally{fs.writeFileSync(path.join(artifact,'result.json'),JSON.stringify(result,null,2)+'\n');await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
