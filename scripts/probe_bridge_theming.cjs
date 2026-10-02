/* Isolated Chromium regression tests of production Bridge UI/CSS. The small
   Obsidian DOM shim is NOT evidence of qualification in real Obsidian themes. */
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
const {build}=require('../bridge/node_modules/esbuild');
const {chromium}=require('./lib/browser.cjs');
const root=path.resolve(__dirname,'..'),fixture=path.join(root,'bridge/tests/ui');
const output=path.join(root,'artifacts/bridge-theming');
const report={schema:'mastermind.bridge.theming.v1',checks:[],limitations:[
  'Synthetic light/dark host tokens and a minimal Obsidian DOM shim; no actual Obsidian or community-theme qualification.',
  'No live Vault or external service calls; Chronos/Saturn responses are in-memory UI fixtures.'
]};
const check=name=>{report.checks.push(name);console.log('PASS '+name);};

(async()=>{
  await fs.mkdir(output,{recursive:true});
  const bundle=await build({entryPoints:[path.join(fixture,'entry.ts')],bundle:true,write:false,format:'esm',platform:'browser',plugins:[{
    name:'isolated-host',setup(build){
      build.onResolve({filter:/^obsidian$/},()=>({path:path.join(fixture,'obsidian.mjs')}));
      build.onResolve({filter:/^node:/},args=>({path:args.path,namespace:'offline'}));
      build.onLoad({filter:/.*/,namespace:'offline'},()=>({contents:
        'export const randomBytes = () => {throw new Error("No native network in UI fixture")}; export const request = randomBytes;'}));
    }
  }]});
  const browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1040,height:850}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',route=>route.abort());
  const style=async(selector,properties)=>page.locator(selector).first().evaluate((el,properties)=>{
    const css=getComputedStyle(el);return Object.fromEntries(properties.map(name=>[name,css.getPropertyValue(name)]));
  },properties);
  const card=page.locator('.mastermind-related-item');
  try{
    await page.setContent('<main id="workspace"><section id="resource-column"><button id="unrelated">Native control</button>'+
      '<input id="unrelated-input" aria-label="Native input"><div id="reference"></div><div id="resource"></div></section><aside id="related"></aside></main>');
    await page.addStyleTag({content:await fs.readFile(path.join(fixture,'theme.css'),'utf8')});
    const nativeBefore=await style('#unrelated',['color','background-color','border-radius','font-family','box-shadow']);
    const inputBefore=await style('#unrelated-input',['color','background-color','width','font-family']);
    await page.addStyleTag({content:await fs.readFile(path.join(root,'bridge/styles.css'),'utf8')});
    await page.addScriptTag({type:'module',content:bundle.outputFiles[0].text});
    await page.waitForFunction(()=>window.fixture);
    assert.deepEqual(await style('#unrelated',Object.keys(nativeBefore)),nativeBefore);
    assert.deepEqual(await style('#unrelated-input',Object.keys(inputBefore)),inputBefore);
    check('Plugin stylesheet leaves unrelated native controls unchanged');

    for(const [theme,surface,text,muted] of [['light','rgb(245, 245, 245)','rgb(34, 34, 34)','rgb(85, 85, 85)'],
      ['dark','rgb(48, 48, 48)','rgb(238, 238, 238)','rgb(204, 204, 204)']]){
      await page.evaluate(theme=>document.body.className='theme-'+theme,theme);
      await page.evaluate(()=>fixture.resource('chronos'));
      for(const selector of ['.mastermind-related-item','.mastermind-resource']){
        assert.deepEqual(await style(selector,['background-color','color']),{'background-color':surface,color:text});
      }
      assert.equal((await style('.mastermind-related-excerpt',['color'])).color,muted);
      const ready=await style('.mastermind-related-list',['opacity']);
      await page.evaluate(()=>fixture.render('loading'));
      assert.deepEqual(await style('.mastermind-related-list',['opacity']),ready);
      assert.equal(await page.locator('.mastermind-related-list').getAttribute('aria-busy'),'true');
      assert.match(await page.locator('.mastermind-related-status').innerText(),/Finding related/);
      await page.evaluate(()=>fixture.render());
      await page.screenshot({path:path.join(output,theme+'.png')});
      check(theme+' host tokens update existing recommendations/resources; busy text keeps its contrast');
    }

    await page.evaluate(()=>{
      for(const name of ['--interactive-accent','--text-accent','--link-color'])document.body.style.setProperty(name,'rgb(0, 180, 120)');
    });
    assert.equal((await style('.mastermind-related-item strong',['color'])).color,'rgb(0, 180, 120)');
    assert.equal((await style('.mastermind-reference',['color'])).color,'rgb(0, 180, 120)');
    await card.hover();assert.equal((await style('.mastermind-related-item',['border-color']))['border-color'],'rgb(0, 180, 120)');
    await page.locator('.mastermind-related-heading button').focus();await page.keyboard.press('Tab');
    assert.equal(await card.evaluate(el=>el.matches(':focus-visible')),true);
    assert.equal((await style('.mastermind-related-item',['outline-color']))['outline-color'],'rgb(0, 180, 120)');
    check('Live accent changes reach titles, references, hover and keyboard focus without remounting');

    await page.mouse.move(0,0);
    // Insert before the plugin stylesheet to verify inheritance, not stylesheet order.
    await page.evaluate(()=>{
      const snippet=document.createElement('style');snippet.id='snippet';snippet.textContent=`body {
        --mm-surface-raised: rgb(40, 60, 70); --mm-text: rgb(240, 245, 250);
        --mm-radius: 13px; --mm-card-padding: 18px; --mm-card-shadow: none;
        --mm-line-height: 2; --mm-excerpt-lines: 5; --mm-font-interface: monospace;
      }`;document.head.prepend(snippet);
    });
    assert.deepEqual(await style('.mastermind-related-item',['background-color','color','border-radius','padding-top','box-shadow','font-family']),{
      'background-color':'rgb(40, 60, 70)',color:'rgb(240, 245, 250)','border-radius':'13px','padding-top':'18px','box-shadow':'none','font-family':'monospace'});
    assert.equal((await style('.mastermind-resource',['background-color']))['background-color'],'rgb(40, 60, 70)');
    assert.equal((await style('.mastermind-related-excerpt',['-webkit-line-clamp']))['-webkit-line-clamp'],'5');
    await page.addStyleTag({content:'.mastermind-related {--mm-surface-raised: rgb(60, 40, 70);}'});
    assert.equal((await style('.mastermind-related-item',['background-color']))['background-color'],'rgb(60, 40, 70)');
    assert.equal((await style('.mastermind-resource',['background-color']))['background-color'],'rgb(40, 60, 70)');
    check('Body snippets work before plugin CSS; component overrides remain local');

    await page.evaluate(()=>{
      document.querySelector('#workspace').style.gridTemplateColumns='minmax(0, 1fr) 220px';
      for(const [name,value] of Object.entries({'--font-ui-medium':'24px','--font-ui-small':'22px','--font-ui-smaller':'20px'}))document.body.style.setProperty(name,value);
    });
    await page.evaluate(()=>fixture.resource('saturn','folder'));
    for(const selector of ['#related','.mastermind-related-heading','.mastermind-related-item','.mastermind-resource']){
      assert.equal(await page.locator(selector).first().evaluate(el=>el.scrollWidth<=el.clientWidth+1),true,selector+' must not overflow at 220px/large text');
    }
    assert.equal(await page.locator('.mastermind-link-row').evaluate(el=>{
      const css=getComputedStyle(el),bounds=el.getBoundingClientRect(),parent=el.parentElement.getBoundingClientRect();
      return css.textOverflow==='ellipsis'&&css.overflow==='hidden'&&bounds.left>=parent.left&&bounds.right<=parent.right;
    }),true,'Resource filenames truncate inside their card');
    for(const selector of ['.mastermind-related-heading button','.mastermind-link-row','.mastermind-resource-actions button']){
      assert.equal(await page.locator(selector).first().evaluate(el=>el.scrollHeight<=el.clientHeight+1),true,selector+' must not clip enlarged text vertically');
    }
    await page.screenshot({path:path.join(output,'narrow-large-text.png')});
    check('220px sidebar, long Unicode paths and larger fonts fit without horizontal overflow');

    await page.evaluate(()=>{fixture.calls.length=0;fixture.open('create');});
    const input=page.getByRole('textbox',{name:'Vault path',exact:true});
    assert.equal(await input.evaluate(el=>el===document.activeElement),true);
    assert.equal(await input.evaluate(el=>el.hasAttribute('style')),false);
    await input.fill('Tests/Новая нота');
    await input.dispatchEvent('keydown',{key:'Enter',isComposing:true});
    assert.equal(await page.evaluate(()=>fixture.calls.length),0,'IME confirmation must not submit');
    await page.evaluate(()=>window.holdRequest=true);
    await input.press('Enter');await input.press('Enter');
    assert.equal(await page.evaluate(()=>fixture.calls.length),1,'Repeated Enter must not duplicate a write');
    assert.deepEqual(await page.evaluate(()=>fixture.calls[0]),{route:'/note/create',data:{path:'Tests/Новая нота.md'}});
    await page.evaluate(()=>fixture.resolve());
    await page.locator('.modal').waitFor({state:'detached'});
    check('Native-component create dialog keeps focus, IME input and one write per submission');

    await page.evaluate(()=>{fixture.open('create');window.failRequest=true;});
    await page.getByRole('textbox',{name:'Vault path',exact:true}).fill('Retry.md');
    await page.getByRole('button',{name:'Create note',exact:true}).click();
    await page.getByRole('alert').filter({hasText:'Fixture request failed'}).waitFor();
    assert.equal(await page.getByRole('button',{name:'Create note',exact:true}).isEnabled(),true);
    await page.setViewportSize({width:320,height:850});
    for(const selector of ['.modal','.mastermind-command','.mastermind-command-path','.mastermind-command-actions']){
      assert.equal(await page.locator(selector).evaluate(el=>el.scrollWidth<=el.clientWidth+1),true,selector+' modal overflow');
    }
    await page.screenshot({path:path.join(output,'dialog-narrow-error.png')});
    await page.evaluate(()=>window.failRequest=false);
    await page.getByRole('button',{name:'Create note',exact:true}).click();
    await page.locator('.modal').waitFor({state:'detached'});
    await page.setViewportSize({width:1040,height:850});
    await page.evaluate(()=>{fixture.calls.length=0;fixture.open('delete');});
    assert.equal(await page.getByRole('textbox',{name:'Note',exact:true}).isDisabled(),true);
    assert.equal(await page.getByRole('button',{name:'Cancel',exact:true}).evaluate(el=>el===document.activeElement),true);
    await page.getByRole('button',{name:'Delete note',exact:true}).click();
    await page.locator('.modal').waitFor({state:'detached'});
    assert.deepEqual(await page.evaluate(()=>fixture.calls),[
      {route:'/path-version',data:{path:'Notes/Example.md'}},
      {route:'/note/delete',data:{path:'Notes/Example.md',expected_sha256:'fixture-version'}}]);
    await page.evaluate(()=>{fixture.calls.length=0;fixture.open('delete');});
    await page.getByRole('button',{name:'Cancel',exact:true}).click();
    assert.equal(await page.evaluate(()=>fixture.calls.length),0);
    check('Modal errors recover, narrow layout fits, delete preserves version checks and Cancel does not write');

    await page.evaluate(()=>{fixture.calls.length=0;return fixture.resource('saturn','retry');});
    await page.getByRole('button',{name:'Retry',exact:true}).click();
    await page.getByRole('button',{name:'Download',exact:true}).waitFor();
    await page.getByRole('button',{name:'Download',exact:true}).click();
    await page.waitForFunction(()=>notices.includes('Download is ready in the Vault toolbar.'));
    assert.equal(await page.getByRole('button',{name:'Download',exact:true}).isEnabled(),true);
    await page.locator('.mastermind-resource-actions').getByRole('button',{name:'Refresh',exact:true}).click();
    await page.waitForFunction(()=>fixture.calls.filter(call=>call.route==='/external/open').length===3);
    await page.evaluate(()=>fixture.resource('saturn','folder'));
    await page.getByRole('button',{name:'Load more',exact:true}).click();
    await page.waitForFunction(()=>document.querySelectorAll('.mastermind-link-row').length===2);
    assert.equal(await page.getByRole('button',{name:'Load more',exact:true}).count(),0);
    assert.ok((await page.evaluate(()=>fixture.calls)).some(call=>call.route==='/external/download'&&call.data.target==='root/folder'));
    assert.ok((await page.evaluate(()=>fixture.calls)).some(call=>call.route.includes('cursor=next')));
    check('Resource Retry, Download, Refresh and pagination retain their service calls');
    assert.deepEqual(errors,[]);report.status='PASS';
  }catch(error){report.status='FAIL';report.error=error.stack;throw error;}
  finally{
    await fs.writeFile(path.join(output,'result.json'),JSON.stringify(report,null,2)+'\n');
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
