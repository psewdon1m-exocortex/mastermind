/* Synthetic indexing benchmark on the same disposable Obsidian as probe_native_references.cjs. */
const {chromium}=require('./lib/browser.cjs');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),fixture=path.join(root,'.local/native-reference-qualification/vault');
const corpus=path.resolve(fixture,'Qualification corpus'),output=path.join(root,'artifacts/native-references/scaling.json');
const count=1000,name=i=>'Qualification '+String(i).padStart(4,'0');
assert.equal(path.dirname(corpus),fixture);

(async()=>{
 const browser=await chromium.connectOverCDP('http://127.0.0.1:19393');
 const page=browser.contexts()[0].pages()[0],result={notes:count};
 try{
  assert.equal(await page.evaluate(()=>app.vault.adapter.getBasePath()),'/qualification/vault');
  assert.ok(!fs.existsSync(corpus),'Do not overwrite an existing corpus');
  await page.evaluate(async()=>{
   const layout=app.workspace.getLayout();
   layout.main={id:layout.main.id,type:'split',direction:'vertical',children:[{id:'scaling-source',type:'leaf',
     state:{type:'markdown',state:{file:'Source.md',mode:'source',source:true}}}]};
   layout.active='scaling-source';if(layout.right)layout.right.children=[];await app.workspace.changeLayout(layout);
  });
  fs.mkdirSync(corpus);
  for(let i=0;i<count;i++)fs.writeFileSync(path.join(corpus,name(i)+'.md'),
    '# '+name(i)+'\n\n😀 @'+name((i+1)%count)+'\n@chronos: event-123\n@saturn: root/spec.pdf\n');
  const started=Date.now();await page.reload();
  const ready=()=>page.waitForFunction(()=>{
   const n=app.plugins.plugins['mastermind-bridge']?.nativeLinks;
   return n?.ready&&!n.diagnostics().running&&!n.diagnostics().dictionary_pending&&!n.diagnostics().pending&&!n.diagnostics().failure;
  },{},{timeout:60000});
  await ready();
  await page.waitForFunction(count=>Object.keys(app.metadataCache.resolvedLinks).filter(p=>
    p.startsWith('Qualification corpus/')&&Object.keys(app.metadataCache.resolvedLinks[p]).length===1).length===count,count,{timeout:60000});
  result.startup_ms=Date.now()-started;
  const before=await page.evaluate(()=>app.plugins.plugins['mastermind-bridge'].nativeLinks.diagnostics());
  result.initial=before;
  const edited=Date.now();
  await page.evaluate(async()=>{
   const file=app.vault.getFileByPath('Qualification corpus/Qualification 0000.md');
   await app.vault.process(file,text=>text.replace('@Qualification 0001','@Qualification 0002'));
  });
  await page.waitForFunction(()=>app.metadataCache.resolvedLinks['Qualification corpus/Qualification 0000.md']?.['Qualification corpus/Qualification 0002.md']===1);
  await ready();result.edit_ms=Date.now()-edited;
  const after=await page.evaluate(()=>app.plugins.plugins['mastermind-bridge'].nativeLinks.diagnostics());
  result.reparsed_notes=after.parsed-before.parsed;assert.equal(result.reparsed_notes,1);
  await page.waitForTimeout(2000);
  assert.equal(await page.evaluate(()=>app.plugins.plugins['mastermind-bridge'].nativeLinks.diagnostics().parsed),after.parsed);
  result.status='PASS';console.log(JSON.stringify(result));
 }catch(error){result.status='FAIL';result.error=error.stack;throw error;}
 finally{
  // This exact directory was created above inside the asserted synthetic Vault.
  if(result.initial&&fs.existsSync(corpus)){fs.rmSync(corpus,{recursive:true});await page.reload();}
  fs.mkdirSync(path.dirname(output),{recursive:true});fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n');
  await browser.close();
 }
})().catch(error=>{console.error(error);process.exitCode=1});
