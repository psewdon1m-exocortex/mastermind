// Actual browser drags against the production card, reorder and CSS code.
// The HTTP settings store and card bodies are isolated fixtures; no live settings change.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require('./lib/browser.cjs');
const out=path.resolve('artifacts/reorder'),web=path.resolve('src/mastermind/web');
const initial=['appearance','security','backup','timezone'];
let saved,requests,delay=0,failure=false;
const reset=()=>{saved={revision:0,accent:'#00a8ff',orders:{settings:[...initial],dashboard:['a','b','c','d'],navigation:['a','b','c']}};requests=[];delay=0;failure=false;};
const html=`<!doctype html><html><head><link rel="stylesheet" href="/assets/shell.css"></head><body>
<main id="content" class="settings-page"><div class="grid settings-grid"></div></main><div id="notices"></div>
<script type="module">
import {state,card,reorder} from '/assets/ui.js';
state.prefs=await (await fetch('/api/owner/settings')).json();
const grid=document.querySelector('.grid');
const layout=new URLSearchParams(location.search).get('layout')||'settings';
if(layout==='settings'){
grid.innerHTML=['appearance','security','backup','timezone'].map((id,i)=>card(id,id,
  '<label>Fixture input<input value="Unchanged text"></label><div style="height:'+([240,100,1000,120][i])+'px"></div>',{wide:true})).join('');
grid.querySelectorAll('.card').forEach(card=>card.classList.add('settings-card'));
reorder(grid,'settings');
}else{
 document.querySelector('#content').classList.remove('settings-page');
 if(layout==='dashboard'){
  grid.innerHTML=['a','b','c','d'].map(id=>card(id,id,'<input value="Dashboard input">',{quarter:true})).join('');
  reorder(grid,'dashboard');
 }else{
  grid.className='nav-list';grid.style.width='320px';
  grid.innerHTML=['a','b','c'].map(id=>'<div class="nav-row" data-nav="'+id+'" draggable="true"><a href="#'+id+'">'+id+'</a><span class="ordinal"></span></div>').join('');
  reorder(grid,'navigation','[data-nav]',true);
 }
}
window.fixtureReady=true;
</script></body></html>`;

(async()=>{
 reset();fs.mkdirSync(out,{recursive:true});
 const server=http.createServer(async(req,res)=>{
  if(req.url==='/api/owner/settings'){
   if(req.method==='PATCH'){
    let text='';for await(const chunk of req)text+=chunk;
    const data=JSON.parse(text);requests.push(data);await new Promise(resolve=>setTimeout(resolve,delay));
    if(failure){res.writeHead(503,{'Content-Type':'application/json'});res.end(JSON.stringify({error:{message:'Fixture save unavailable'}}));return;}
    if(data.revision!==saved.revision){res.writeHead(409,{'Content-Type':'application/json'});res.end(JSON.stringify({error:{code:'SETTINGS_CONFLICT',message:'Fixture revision conflict'}}));return;}
    saved={...saved,revision:saved.revision+1,orders:{...saved.orders,...data.orders}};
   }
   res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify(saved));return;
  }
  if(req.url.startsWith('/assets/')){
   const name=req.url.slice(8);
   if(!['ui.js','shell.css'].includes(name)){res.writeHead(404);res.end();return;}
   res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':'text/css');res.end(fs.readFileSync(path.join(web,name)));return;
  }
  res.setHeader('Content-Type','text/html');res.end(html);
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const origin='http://127.0.0.1:'+server.address().port;
 let browser;const report={checks:[],errors:[],boundary:'Production UI modules and styles; synthetic cards and settings HTTP store. No live deployment.'};
 try{
  browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  page.on('pageerror',error=>report.errors.push(error.message));
  const boot=async layout=>{reset();await page.setViewportSize({width:1440,height:1000});await page.goto(origin+'/?layout='+(layout||'settings'));await page.waitForFunction(()=>window.fixtureReady);};
  const order=()=>page.locator('[data-card]').evaluateAll(nodes=>nodes.map(node=>node.dataset.card));
  const start=async id=>{const handle=page.locator('[data-card="'+id+'"] > .drag');await handle.scrollIntoViewIfNeeded();const b=await handle.boundingBox();await page.mouse.move(b.x+b.width/2,b.y+b.height/2);await page.mouse.down();await page.mouse.move(b.x+b.width/2-12,b.y+b.height/2+12,{steps:5});};
  const move=async(x,y)=>{await page.mouse.move(x,y,{steps:10});await page.mouse.move(x,y);};
  const settled=()=>page.waitForFunction(()=>!document.querySelector('.grid').hasAttribute('aria-busy'));
  const check=async(name,action,layout)=>{await boot(layout);try{await action();report.checks.push({name,status:'PASS'});}catch(error){report.checks.push({name,status:'FAIL',error:error.message});if(!process.argv.includes('--baseline'))throw error;}finally{await page.mouse.up();}};

  await check('Drop in the gap between settings cards',async()=>{
   const a=await page.locator('[data-card="security"]').boundingBox(),b=await page.locator('[data-card="backup"]').boundingBox();
   await start('appearance');await move(a.x+100,(a.y+a.height+b.y)/2);await page.mouse.up();
   await page.waitForTimeout(180);assert.deepEqual(await order(),['security','appearance','backup','timezone']);
   assert.equal(requests.length,1);await page.reload();await page.waitForFunction(()=>window.fixtureReady);assert.deepEqual(await order(),saved.orders.settings);
  });
  await check('Insertion marker remains visible in Settings',async()=>{
   const b=await page.locator('[data-card="security"]').boundingBox();
   await start('appearance');await move(b.x+120,b.y+40);
   const marker=page.locator('[data-drop]');assert.equal(await marker.count(),1);
   const visible=await marker.evaluate(node=>getComputedStyle(node).boxShadow!=='none'||getComputedStyle(node,'::after').content!=='none');
   assert.ok(visible,'Settings overrides the insertion marker');
   await page.screenshot({path:path.join(out,'insertion.png')});
   await page.keyboard.press('Escape');await page.mouse.up();assert.equal(requests.length,0);
   assert.equal(await marker.count(),0);
  });
  await check('Drop on a card and preserve input contents',async()=>{
   await page.locator('[data-card="appearance"] input').fill('Unsaved edit');
   const b=await page.locator('[data-card="security"]').boundingBox();
   await start('appearance');await move(b.x+100,b.y+b.height-30);await page.mouse.up();await page.waitForTimeout(180);
   assert.deepEqual(await order(),['security','appearance','backup','timezone']);
   assert.deepEqual(await page.locator('input').evaluateAll(nodes=>nodes.map(node=>node.value)),['Unchanged text','Unsaved edit','Unchanged text','Unchanged text']);
  });
  if(!process.argv.includes('--baseline')){
   await check('Move upward and save keyboard reordering',async()=>{
    const b=await page.locator('[data-card="appearance"]').boundingBox();
    await start('security');await move(b.x+100,b.y+25);await page.mouse.up();await page.waitForTimeout(180);
    assert.deepEqual(await order(),['security','appearance','backup','timezone']);
    await page.locator('[data-card="security"] > .drag').press('Alt+ArrowDown');await settled();
    assert.deepEqual(await order(),initial);assert.equal(requests.length,2);
   });
   await check('Slow save gives immediate feedback and prevents overlapping writes',async()=>{
    delay=400;const handle=page.locator('[data-card="appearance"] > .drag');
    await handle.press('Alt+ArrowDown');assert.deepEqual(await order(),['security','appearance','backup','timezone']);
    await handle.press('Alt+ArrowDown');await settled();assert.equal(requests.length,1);
    assert.deepEqual(await order(),saved.orders.settings);
   });
   await check('Failed save restores the saved order and reports the error',async()=>{
    failure=true;await page.locator('[data-card="appearance"] > .drag').press('Alt+ArrowDown');await settled();
    await page.getByRole('alert').filter({hasText:'Fixture save unavailable'}).waitFor();
    assert.deepEqual(await order(),initial);
   });
   await check('Canceled drag outside the grid does not save',async()=>{
    await start('appearance');await move(2,600);await page.mouse.up();assert.equal(requests.length,0);
    assert.equal(await page.locator('[data-drop]').count(),0);assert.deepEqual(await order(),initial);
   });
   await check('Drop after the visible portion of a tall card',async()=>{
    const b=await page.locator('[data-card="backup"]').boundingBox();assert.ok(b.y+b.height>1000);
    await start('appearance');await move(b.x+100,950);await page.mouse.up();await page.waitForTimeout(180);
    assert.deepEqual(await order(),['security','backup','appearance','timezone']);
   });
   await check('Dragging near the viewport edge scrolls long settings',async()=>{
    await start('appearance');await move(700,998);
    await page.waitForFunction(()=>scrollY>50,{},{timeout:4000});
    await page.keyboard.press('Escape');await page.mouse.up();assert.equal(requests.length,0);
   });
   await check('Narrow layout accepts the gap between cards',async()=>{
    await page.setViewportSize({width:390,height:1000});
    const a=await page.locator('[data-card="security"]').boundingBox(),b=await page.locator('[data-card="backup"]').boundingBox();
    await start('appearance');await move(90,(a.y+a.height+b.y)/2);await page.mouse.up();await page.waitForTimeout(180);
    assert.deepEqual(await order(),['security','appearance','backup','timezone']);
   });
   await check('Concurrent settings change restores the current server order',async()=>{
    saved={...saved,revision:1,orders:{...saved.orders,settings:[...initial].reverse()}};
    await page.locator('[data-card="appearance"] > .drag').press('Alt+ArrowDown');await settled();
    await page.getByRole('alert').filter({hasText:'Fixture revision conflict'}).waitFor();
    assert.deepEqual(await order(),saved.orders.settings);
   });
   await check('Dashboard cards reorder across columns',async()=>{
    const b=await page.locator('[data-card="c"]').boundingBox();await start('a');await move(b.x+b.width-25,b.y+75);
    assert.equal(await page.locator('[data-card="c"]').getAttribute('data-drop'),'right');
    await page.mouse.up();await page.waitForTimeout(180);assert.deepEqual(await order(),['b','c','a','d']);
   },'dashboard');
   await check('Navigation rows retain direct drag and keyboard support',async()=>{
    const row=page.locator('[data-nav="a"]'),target=page.locator('[data-nav="c"]'),b=await target.boundingBox();
    await row.dragTo(target,{targetPosition:{x:100,y:b.height-5}});await page.waitForTimeout(180);
    assert.deepEqual(saved.orders.navigation,['b','c','a']);
    await row.locator('a').press('Alt+ArrowUp');await page.waitForTimeout(180);
    assert.deepEqual(saved.orders.navigation,['b','a','c']);
   },'navigation');
  }
  assert.deepEqual(report.errors,[]);
 }finally{
  await browser?.close();await new Promise(resolve=>server.close(resolve));
  fs.writeFileSync(path.join(out,process.argv.includes('--baseline')?'baseline.json':'report.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
