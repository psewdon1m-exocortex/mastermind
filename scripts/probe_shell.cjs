// Browser evidence against the real local Core, Runtime, Worker and neighboring services.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('./lib/browser.cjs');
(async()=>{
  const root=path.resolve(__dirname,'..'),origin=process.env.SHELL_ORIGIN||'http://localhost:18390';
  const output=path.join(root,'artifacts/shell');fs.mkdirSync(output,{recursive:true});
  const browser=await chromium.launch({headless:true});
  try{const context=await browser.newContext({viewport:{width:1920,height:1080},acceptDownloads:true});
    const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
    page.on('console',message=>{if(message.type()==='error'&&message.text().includes('Content Security Policy'))errors.push(message.text());});
    await page.goto(origin+'/');await page.getByLabel('Access Key',{exact:true}).waitFor();await page.screenshot({path:path.join(output,'login.png')});
    await page.getByLabel('Access Key',{exact:true}).fill(fs.readFileSync(path.join(root,'.local/secrets/core/bootstrap_access_key'),'utf8'));
    await page.getByRole('button',{name:'Enter service',exact:true}).click();await page.getByRole('heading',{name:'dashboard',exact:true}).waitFor();
    await page.waitForTimeout(3500);await page.screenshot({path:path.join(output,'dashboard.png')});
    for(const view of ['Shared','Crusher','Settings','Documentation']){
      await page.locator('.sidebar').getByRole('link',{name:view,exact:true}).click();await page.getByRole('heading',{name:view.toLowerCase(),exact:true}).waitFor();await page.waitForTimeout(1000);
      await page.screenshot({path:path.join(output,view.toLowerCase()+'.png'),fullPage:view==='Settings'});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,view+' desktop horizontal overflow');
    }
    assert.ok((await page.getByRole('article').textContent()).includes('Access Key'));
    await page.getByRole('searchbox',{name:'Search documentation',exact:true}).fill('restore');
    assert.ok(await page.locator('[data-article]').count()>0);await page.getByRole('button',{name:'Clear search',exact:true}).click();
    await page.setViewportSize({width:390,height:844});await page.waitForTimeout(300);
    await page.getByRole('button',{name:'Open navigation',exact:true}).click();await page.screenshot({path:path.join(output,'mobile-navigation.png')});
    await page.locator('.sidebar').getByRole('link',{name:'Settings',exact:true}).click();await page.waitForTimeout(1000);await page.screenshot({path:path.join(output,'mobile-settings.png'),fullPage:true});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'mobile horizontal overflow');
    assert.deepEqual(errors,[]);console.log(JSON.stringify({navigation:'PASS',desktop:'PASS',mobile:'PASS',documentation_search:'PASS',browser_errors:errors}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
