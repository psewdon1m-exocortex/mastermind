// Browser screenshot of the real clean-host native session; no Obsidian DOM access.
const {chromium}=require('./lib/browser.cjs');
const {execFileSync}=require('node:child_process');
const path=require('node:path');
(async()=>{
  const root=path.resolve(__dirname,'..');
  const key=execFileSync('docker',['exec','mastermind-qualification-host','cat','/opt/exocortex/mastermind/secrets/core/bootstrap_access_key'],{encoding:'utf8'});
  const browser=await chromium.launch({headless:true,args:['--host-resolver-rules=MAP mastermind.qualification.test 127.0.0.1:18445']});
  try{
    const context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1600,height:1000}});
    const page=await context.newPage();
    await page.goto('https://mastermind.qualification.test/');
    await page.getByLabel('Access Key',{exact:true}).fill(key);
    await page.getByRole('button',{name:'Enter service',exact:true}).click();
    await page.getByRole('heading',{name:'Dashboard',exact:true}).waitFor();
    await page.locator('.sidebar').getByRole('link',{name:'Vault',exact:true}).click();
    await page.waitForTimeout(4000);
    await page.screenshot({path:path.join(root,'artifacts/host-native-initial.png')});
    if(process.argv.includes('--trust-generated-vault')){
      const inspection=execFileSync('docker',['exec','mastermind-qualification-host','docker','exec','mastermind-runtime-1','python','-c',
        "import json; from pathlib import Path; p=Path('/vault/current'); assert json.loads((p/'.obsidian/community-plugins.json').read_text())==['mastermind-bridge']; assert not list(p.rglob('*.md')); print('OWN_EMPTY_FIXTURE')"],{encoding:'utf8'}).trim();
      if(inspection!=='OWN_EMPTY_FIXTURE')throw Error('Only the generated empty qualification Vault may be trusted by this probe');
      await page.mouse.click(1160,772);
      await page.waitForTimeout(4000);
      const state=await page.evaluate(async()=>{const response=await fetch('/api/status');return response.json();});
      if(!state.runtime?.bridge?.ready)throw Error('Native trust did not produce a ready Bridge');
      await page.screenshot({path:path.join(root,'artifacts/host-native-trusted.png')});
      console.log('PASS native owner trust enabled only the signed Bridge on the empty fixture');
    }
    console.log('Captured the real qualification-host Vault through host Nginx');
  }finally{await browser.close();}
})().catch(error=>{console.error(String(error.message).split('\n')[0]);process.exitCode=1;});
