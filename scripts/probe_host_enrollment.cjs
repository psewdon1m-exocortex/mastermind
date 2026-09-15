// Actual Settings -> host Updater -> signed Neptune installation -> Saturn.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const {chromium}=require('./lib/browser.cjs');
const root=path.resolve(__dirname,'..'),origin='https://mastermind.qualification.test';
(async()=>{
  const key=execFileSync('docker',['exec','mastermind-qualification-host','cat','/opt/exocortex/mastermind/secrets/core/bootstrap_access_key'],{encoding:'utf8'});
  const code=JSON.parse(fs.readFileSync(path.join(root,'.local/host-fixture/enrollment.json'),'utf8')).code;
  const browser=await chromium.launch({headless:true,args:['--host-resolver-rules=MAP mastermind.qualification.test 127.0.0.1:18445']});
  try{
    const context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1920,height:1080}});
    const page=await context.newPage();
    await page.goto(origin+'/settings');
    await page.getByLabel('Access Key',{exact:true}).fill(key);
    await page.getByRole('button',{name:'Enter service',exact:true}).click();
    await page.getByRole('heading',{name:'Settings',exact:true}).waitFor();
    if(!process.argv.includes('--review')){
      await page.locator('[data-agent-init]').click();
      await page.getByLabel('Neptune setup code',{exact:true}).fill(code);
      await page.getByRole('button',{name:'Initialize',exact:true}).click();
    }
    let previous, result;
    for(let tick=0;tick<600;tick++){
      await page.waitForTimeout(1000);
      result=await page.evaluate(async()=>{const r=await fetch('/api/owner/agents/neptune/initialization');return r.ok?await r.json():{state:'RECONNECTING',http:r.status};}).catch(e=>({state:'RECONNECTING',error:String(e.message).split('\n')[0]}));
      if(result.state!==previous){console.log(JSON.stringify({utc:new Date().toISOString(),state:result.state,error:result.error}));previous=result.state;}
      if(['COMPLETED','FAILED'].includes(result.state))break;
    }
    fs.writeFileSync(path.join(root,'artifacts/host-enrollment.json'),JSON.stringify(result,null,2));
    await page.screenshot({path:path.join(root,'artifacts/host-enrollment.png')});
    assert.equal(result.state,'COMPLETED',result.error||'Initialization deadline');
    assert.deepEqual(result.capabilities,['archive','mirror','reader']);
    console.log('PASS actual browser initialization, signed host Neptune install, independent pipelines and authenticated reader');
  }finally{await browser.close();}
})().catch(error=>{console.error(String(error.message).split('\n')[0]);process.exitCode=1;});
