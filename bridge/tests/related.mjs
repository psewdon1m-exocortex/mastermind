import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {createRequire} from 'node:module';
await build({entryPoints:['src/related_state.ts'],outfile:'dist/related-state.cjs',bundle:true,platform:'node',format:'cjs'});
const {RelatedController,contextQuery}=createRequire(import.meta.url)('../dist/related-state.cjs');
const settle=async()=>{await Promise.resolve();await Promise.resolve();};
function fixture(){
  let now=0,next=0;const timers=new Map(),requests=[],states=[];
  const clock={now:()=>now,set:(callback,delay)=>{timers.set(++next,{at:now+delay,callback});return next;},clear:id=>timers.delete(id)};
  const controller=new RelatedController((query,signal)=>new Promise((resolve,reject)=>requests.push({query,signal,resolve,reject})),
    state=>states.push(structuredClone(state)),clock);
  const advance=async delta=>{now+=delta;for(const [id,timer] of [...timers])if(timer.at<=now){timers.delete(id);timer.callback();}await settle();};
  return {controller,requests,states,advance};
}
const query=(text,path='Draft.md')=>contextQuery(path,text,text.length);
const response=(path,title)=>({path,items:[{path:title+'.md',title,excerpt:title+' context'}],degraded:false,sampled:false});

{
  const {controller,requests,advance}=fixture();
  for(const text of ['air','aircraft','aircraft wings']){controller.update(query(text));await advance(300);}
  assert.equal(requests.length,0);await advance(1200);assert.equal(requests.length,1);
  assert.equal(requests[0].query.text,'aircraft wings');
  controller.update(query('garden plants'));await advance(5000);assert.equal(requests.length,1,'No concurrent request during an edit');
  requests[0].resolve(response('Draft.md','Aircraft'));await settle();
  assert.equal(controller.state.items.length,0,'Stale buffer response must not render');
  await advance(1500);assert.equal(requests.length,2);
  requests[1].resolve(response('Draft.md','Garden'));await settle();
  assert.equal(controller.state.items[0].title,'Garden');
  controller.update(query('garden plants'));await advance(10000);assert.equal(requests.length,2,'Unchanged context must not loop');
  controller.dispose();
}
{
  const {controller,requests,advance}=fixture();
  controller.update(query('aircraft'));await advance(1200);
  controller.update(query('gardening','Other.md'));await advance(2000);
  requests[0].resolve(response('Draft.md','Wrong note'));await settle();
  assert.equal(controller.state.items.length,0);await advance(1500);
  requests[1].resolve(response('Other.md','Garden'));await settle();assert.equal(controller.state.items[0].title,'Garden');
  controller.update();await advance(60000);assert.equal(requests.length,2,'Hidden or blank view must stop requests');
  assert.equal(controller.state.items.length,0);
  controller.dispose();
}
{
  const {controller,requests,advance,states}=fixture();
  controller.update(query('aircraft'));await advance(1200);
  controller.dispose();const count=states.length;
  assert.ok(requests[0].signal.aborted);requests[0].resolve(response('Draft.md','Late'));await settle();
  await advance(10000);assert.equal(states.length,count,'No updates after unload');
}
{
  const {controller,requests,advance}=fixture();
  controller.update(query('aircraft'));await advance(1200);requests[0].reject(new Error('unavailable'));await settle();
  assert.equal(controller.state.phase,'error');controller.refresh();await advance(1500);
  requests[1].resolve(response('Draft.md','Recovered'));await settle();assert.equal(controller.state.items[0].title,'Recovered');
  controller.dispose();
}
{
  const long='FIRST '+('🚀 самолёты '.repeat(12000))+' FINAL';
  const sample=contextQuery('Unicode.md',long,long.length);
  assert.ok(sample.sampled);assert.ok(sample.text.includes('FIRST')&&sample.text.includes('FINAL'));
  assert.ok(Buffer.byteLength(sample.text)<=16384&&Buffer.byteLength(sample.focus)<=4096);
  assert.ok(!/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(sample.text+sample.focus));
  assert.ok(!contextQuery('Short.md','Airplane wings',8).sampled);
}
console.log('PASS related notes: debounce, single flight, stale note/buffer rejection, hide/unload, retry, Unicode context bounds');
