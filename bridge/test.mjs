import {build} from 'esbuild';
import {readFile, mkdir} from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
await import('./tests/related.mjs');
await mkdir('dist',{recursive:true});
await build({entryPoints:['src/portable_parser.ts'],outfile:'dist/portable-parser.cjs',bundle:true,platform:'node',format:'cjs'});
const {parse}=createRequire(import.meta.url)('./dist/portable-parser.cjs');
const cases=JSON.parse(await readFile('tests/portable-cases.json','utf8'));
for(const [index,item] of cases.entries())assert.deepEqual(parse(item.text,item.current,item.history,item.saturn),item.expected,`Core parity case ${index}: ${item.text}`);
assert.throws(()=>parse('x'.repeat(8*1024**2+1),{}),/limit/);
console.log(`PASS ${cases.length} Core/portable parser parity cases and size bound`);
await build({entryPoints:['src/native_projection.ts'],outfile:'dist/native-projection.cjs',bundle:true,platform:'node',format:'cjs'});
const {nativeReferences,resourceLink,resourceReference}=createRequire(import.meta.url)('./dist/native-projection.cjs');
for(const item of cases){
  const expected=item.expected.filter(ref=>[...item.text][ref.start]==='@');
  const links=nativeReferences(item.text,item.expected);
  assert.equal(links.length,expected.length);
  for(const [index,link] of links.entries()){
    const ref=expected[index],start=[...item.text].slice(0,ref.start).join('').length,end=[...item.text].slice(0,ref.end).join('').length;
    assert.equal(link.original,item.text.slice(start,end));
    for(const [side,offset] of [['start',start],['end',end]]){
      assert.deepEqual(link.position[side],{offset,line:item.text.slice(0,offset).split('\n').length-1,
        col:offset-item.text.lastIndexOf('\n',offset-1)-1});
    }
  }
}
for(const kind of ['chronos','saturn'])for(const target of ['id-123','root/a # b.md','root/日本語 😀.pdf','root/a%20b','root/a:resource']){
  const link=resourceLink({kind,target});assert.ok(!link.includes('#')&&!link.endsWith('.md'));
  assert.equal(resourceReference(link).target,target);assert.equal(resourceReference(link).kind,kind);
}
for(const invalid of ['Target.md','mastermind-resource:unknown:x:resource','mastermind-resource:saturn:%ZZ:resource'])assert.equal(resourceReference(invalid),undefined);
console.log('PASS native UTF-16 positions for every grammar fixture and external target round trips');
await build({entryPoints:['src/portable.ts'],outfile:'dist/portable.cjs',bundle:true,platform:'node',format:'cjs'});
const {Portable}=createRequire(import.meta.url)('./dist/portable.cjs');
const contents=new Map([
  ['root.md','#main\n@Café [[Café]] @Deleted @chronos: opaque-id @saturn: root/my file.pdf'],
  ['Branch/Café.md','#key\n@root'],['Unconnected.md','plain text'],
  ['.obsidian/plugins/mastermind-bridge/portable-history.json',JSON.stringify({format:'mastermind-portable-history/v1',internal:['Deleted'],saturn:['root/my file.pdf']})]
]);
const files=[...contents].filter(([path])=>path.endsWith('.md')).map(([path,text])=>({path,basename:path.split('/').pop().slice(0,-3),extension:'md',stat:{mtime:1,size:Buffer.byteLength(text)}}));
const app={vault:{adapter:{exists:async path=>contents.has(path),stat:async path=>({size:Buffer.byteLength(contents.get(path))}),
  read:async path=>contents.get(path),write:async(path,text)=>{contents.set(path,text);}},getMarkdownFiles:()=>files,
  getFileByPath:path=>files.find(file=>file.path===path),cachedRead:async file=>contents.get(file.path),
  process:async(file,fn)=>{contents.set(file.path,fn(contents.get(file.path)));file.stat.mtime++;}}};
const portable=new Portable(app);
const dictionary=await portable.request('/reference-dictionary');
assert.equal(dictionary.current['café'],'Café');assert.ok(dictionary.history.includes('Deleted'));
assert.deepEqual(dictionary.saturn,['root/my file.pdf']);
assert.equal(portable.inventory(),portable.inventory(),'Unchanged inventories should be reused');
for(const route of ['/graph','/links','/graph-presentation'])await assert.rejects(portable.request(route),/unavailable/);
assert.deepEqual(await portable.request('/suggest',{text:'`@Ca`',offset:1,query:'Ca'}),[]);
assert.deepEqual(await portable.request('/suggest',{text:'@Ca',offset:0,query:'Ca'}),[{name:'Café',path:'Branch/Café.md'}]);
await assert.rejects(portable.request('/external',{kind:'saturn',target:'root/my file.pdf'}),/unavailable/);
const target=files[1];await portable.rename(target,'Branch/New name.md',async()=>{
  contents.set('Branch/New name.md',contents.get(target.path));contents.delete(target.path);target.path='Branch/New name.md';target.basename='New name';
  // Emulate the native FileManager's wiki rename. The portable adapter handles only @.
  contents.set('root.md',contents.get('root.md').replace('[[Café]]','[[New name]]'));
});
assert.match(contents.get('root.md'),/@New name \[\[New name\]\]/);
const restarted=new Portable(app);assert.deepEqual((await restarted.request('/references',{text:'@Deleted @Café @New name'})).map(ref=>ref.exists),[false,false,true]);
assert.ok([...contents.keys()].every(path=>path.endsWith('.md')||path.startsWith('.obsidian/plugins/mastermind-bridge/')));
console.log('PASS portable dictionary, inventory reuse, autocomplete, native rename, broken history restart, external unavailable');
