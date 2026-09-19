// Run after `node node_modules/playwright/cli.js install chromium firefox`.
// Uses the served worker and its actual CSP; no network interception or upload.
const assert=require('node:assert/strict'),crypto=require('node:crypto'),fs=require('node:fs'),path=require('node:path');
const {chromium,firefox}=require('./lib/browser.cjs');
const origin=process.env.MASTERMIND_URL||'http://localhost:18390';
const sizes=[0,1,55,56,63,64,65,1024**2-1,1024**2,1024**2+1,3*1024**2+17];
const expected=sizes.map(size=>crypto.createHash('sha256').update(Buffer.from(Uint8Array.from({length:size},(_,i)=>i%251))).digest('hex'));
(async()=>{
  const results={};
  for(const [name,engine]of Object.entries({chromium,firefox})){
    const browser=await engine.launch({headless:true});
    try{
      const page=await browser.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
      const response=await page.request.get(origin+'/assets/hash-worker.js');assert.ok(response.ok());
      const csp=response.headers()['content-security-policy'];assert.ok(csp.includes("script-src 'self'"));assert.ok(csp.includes("default-src 'none'"));
      await page.goto(origin+'/crusher');
      const actual=await page.evaluate(async sizes=>{
        const {hashFile}=await import('/assets/crusher.js');const values=[];
        for(const size of sizes){const bytes=Uint8Array.from({length:size},(_,i)=>i%251),progress=[];const hash=await hashFile(new File([bytes],'binary-данные.bin',{type:'application/octet-stream'}),p=>progress.push(p));values.push({hash,progress});}
        const controller=new AbortController();controller.abort();let cancelled;
        try{await hashFile(new File(['sample'],'cancelled.txt'),()=>{},controller.signal);}catch(error){cancelled=error.name;}
        const active=new AbortController();let stopped;
        try{await hashFile(new File([new Uint8Array(8*1024**2)],'cancelled-large.bin'),()=>active.abort(),active.signal);}catch(error){stopped=error.name;}
        return {values,cancelled,stopped};
      },sizes);
      assert.deepEqual(actual.values.map(value=>value.hash),expected);assert.equal(actual.cancelled,'AbortError');assert.equal(actual.stopped,'AbortError');
      for(const [index,value]of actual.values.entries()){if(sizes[index])assert.equal(value.progress.at(-1),1);assert.ok(value.progress.every((p,i)=>p>0&&p<=1&&(!i||p>=value.progress[i-1])));}
      assert.deepEqual(errors,[]);results[name]={version:browser.version(),sha256_vectors:sizes.length,progress:'PASS',cancellation:'PASS',browser_errors:errors};
    }finally{await browser.close();}
  }
  const out=path.resolve('artifacts/hashing-fix');fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'hashing.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
