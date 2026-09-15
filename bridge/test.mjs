import {build} from 'esbuild';
import {readFile, mkdir} from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
await mkdir('dist',{recursive:true});
await build({entryPoints:['src/portable_parser.ts'],outfile:'dist/portable-parser.cjs',bundle:true,platform:'node',format:'cjs'});
const {parse}=createRequire(import.meta.url)('./dist/portable-parser.cjs');
const cases=JSON.parse(await readFile('tests/portable-cases.json','utf8'));
for(const [index,item] of cases.entries())assert.deepEqual(parse(item.text,item.current,item.history,item.saturn),item.expected,`Core parity case ${index}: ${item.text}`);
assert.throws(()=>parse('x'.repeat(8*1024**2+1),{}),/limit/);
console.log(`PASS ${cases.length} Core/portable parser parity cases and size bound`);
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
const graph=await portable.request('/graph');assert.equal(graph.connectedness,33.33);assert.equal(graph.broken,1);
assert.equal(graph.external.length,2);assert.deepEqual(graph.edges,[['Branch/Café.md','root.md']]);
assert.deepEqual((await portable.request('/links',{path:'Branch/Café.md',direction:'backlinks'})).map(item=>item.path),['root.md']);
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
console.log('PASS portable graph, backlinks, autocomplete, excluded Markdown, native rename, broken history restart, external unavailable');
