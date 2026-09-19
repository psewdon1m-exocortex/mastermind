// Read-only UI regression, apart from issuing one expiring Crusher invitation.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('./lib/browser.cjs');
const origin='http://localhost:18390',out=path.resolve('artifacts/ui-refresh-20260919');
fs.mkdirSync(out,{recursive:true});
(async()=>{
  const browser=await chromium.launch({headless:true});let page;
  const results={},errors=[];
  try{
    const context=await browser.newContext({viewport:{width:1920,height:1080},reducedMotion:'reduce'});
    page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
    page.on('console',m=>{if(m.type()==='error'&&m.text().includes('Content Security Policy'))errors.push(m.text());});
    await page.goto(origin+'/dashboard');
    await page.getByLabel('Access Key',{exact:true}).waitFor();
    await page.screenshot({path:path.join(out,'login.png')});
    await page.getByLabel('Access Key',{exact:true}).fill(fs.readFileSync('.local/secrets/core/bootstrap_access_key','utf8'));
    await page.getByRole('button',{name:'Enter service',exact:true}).click();
    await page.getByRole('heading',{name:'dashboard',exact:true}).waitFor();
    await page.waitForFunction(()=>document.querySelector('[data-card="items"] [data-value]')?.textContent!=='Unknown');
    assert.equal(await page.locator('[data-nav="analytics"]').count(),0);
    assert.equal(await page.getByRole('heading',{name:'Service status',exact:true}).count(),0);
    results.cards=await page.locator('[data-card]').evaluateAll(nodes=>nodes.map(n=>({id:n.dataset.card,column:getComputedStyle(n).gridColumn})));
    assert.equal(results.cards.length,8);
    for(const id of ['connectedness','items'])assert.equal(results.cards.find(n=>n.id===id).column,'span 2');
    assert.equal(results.cards.find(n=>n.id==='heatmap').column,'1 / -1');
    assert.equal(results.cards.find(n=>n.id==='crusher_access').column,'span 1');
    const data=await (await context.request.get(origin+'/api/owner/analytics')).json();
    assert.equal(data.items.total,data.items.notes+data.items.attachments);
    results.items=data.items;
    await page.screenshot({path:path.join(out,'dashboard.png'),fullPage:true});
    const access=page.getByRole('button',{name:'Create and copy Crusher access code',exact:true});
    await access.click();await page.getByRole('button',{name:'Copy Crusher access code',exact:true}).waitFor();
    assert.match(await page.locator('[data-access-value]').textContent(),/^\d{6}$/);
    assert.equal(await page.getByRole('dialog').count(),0);results.crusher_access='PASS';
    async function revealNavigation(){if(!await page.locator('.sidebar').evaluate(node=>node.inert))return;if(await page.getByRole('button',{name:'Open navigation',exact:true}).isVisible())await page.getByRole('button',{name:'Open navigation',exact:true}).click();else{await page.mouse.move(600,100);await page.locator('.edge-toggle').hover();}await page.waitForFunction(()=>!document.querySelector('.sidebar').inert);}
    async function nav(label){await revealNavigation();await page.locator('.sidebar').getByRole('link',{name:label,exact:true}).click();await page.getByRole('heading',{name:label.toLowerCase(),exact:true}).waitFor();}
    await nav('Vault');assert.equal(await page.locator('[data-portable]').count(),0);
    await page.getByText('Obsidian connected',{exact:true}).waitFor({timeout:20000});results.vault='PASS';
    await nav('Settings');
    // Exercise actual pointer growth even though the documentation checks use reduced motion.
    await page.emulateMedia({reducedMotion:'no-preference'});
    for(const label of ['Dashboard','Settings']){
      await revealNavigation();
      await page.locator('.nav-row').filter({has:page.getByRole('link',{name:label,exact:true})}).hover();
      await page.waitForTimeout(200);
      const geometry=await page.evaluate(label=>{
        const row=[...document.querySelectorAll('.nav-row')].find(n=>n.querySelector('a').textContent===label);
        const b=row.getBoundingClientRect(),p=row.parentElement.getBoundingClientRect();
        return {top:b.top,bottom:b.bottom,left:b.left,right:b.right,clip:{top:p.top,bottom:p.bottom,left:p.left,right:p.right},transform:getComputedStyle(row).transform};
      },label);
      assert.ok(geometry.top>=geometry.clip.top&&geometry.bottom<=geometry.clip.bottom,JSON.stringify(geometry));
      assert.ok(geometry.left>=geometry.clip.left&&geometry.right<=geometry.clip.right,JSON.stringify(geometry));
      await page.screenshot({path:path.join(out,'hover-'+label.toLowerCase()+'.png')});
    }
    results.navigation_hover='PASS';await page.emulateMedia({reducedMotion:'reduce'});
    await nav('Crusher');assert.equal(await page.locator('[data-access]').count(),0);
    const query=page.getByRole('searchbox',{name:'Search submissions',exact:true});
    await page.waitForFunction(()=>document.querySelector('[data-count]')?.textContent.includes(' of '));
    const before=await page.locator('[data-count]').textContent();
    await query.fill('no-such-source-for-ui-check');assert.equal(await page.locator('.job').count(),0);
    const clear=page.getByRole('button',{name:'Clear search',exact:true});
    assert.equal(await clear.locator('svg').count(),1);
    const searchGeometry=await query.evaluate(n=>({input:getComputedStyle(n).outlineStyle,outer:getComputedStyle(n.parentElement).outlineStyle,field:n.parentElement.offsetHeight}));
    assert.deepEqual(searchGeometry,{input:'none',outer:'none',field:40});
    await page.screenshot({path:path.join(out,'crusher-search.png'),fullPage:true});
    await clear.click();assert.equal(await query.inputValue(),'');await page.waitForFunction(()=>document.activeElement?.matches('input[type=search]'));assert.ok(await query.evaluate(n=>n===document.activeElement));
    assert.equal(await page.locator('[data-count]').textContent(),before);assert.equal(await clear.count(),0);
    await query.fill('again');await query.press('Escape');assert.equal(await query.inputValue(),'');
    await page.evaluate(()=>scrollTo(0,1200));
    assert.ok(Math.abs((await page.locator('.toolbar').boundingBox()).y)<=1,'Submission command bar must remain sticky');
    await page.evaluate(()=>scrollTo(0,0));results.search='PASS';
    await nav('Shared');await nav('Documentation');await page.locator('.doc-section').first().waitFor();
    const topics=await page.locator('.doc-section').count();assert.equal(topics,9);
    const article=page.getByRole('article',{name:'Operator guide',exact:true});
    const toc=page.getByRole('navigation',{name:'Documentation navigation',exact:true});
    const stable=await toc.boundingBox();
    await toc.getByRole('link',{name:'Backup and Restore',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('[data-article="backup"]')?.getAttribute('aria-current')==='location');
    assert.equal(await page.evaluate(()=>scrollY),0);assert.deepEqual(await toc.boundingBox(),stable);
    await article.evaluate(n=>n.scrollTop=n.scrollHeight);
    await page.waitForFunction(()=>document.querySelector('[data-article="logs"]')?.getAttribute('aria-current')==='location');
    assert.equal(await page.locator('[aria-current="location"]').count(),1);
    const docQuery=page.getByRole('searchbox',{name:'Search documentation',exact:true});
    await docQuery.fill('   CREATE ACCESS CODE   ');
    assert.equal(await article.evaluate(n=>n.scrollTop),0);assert.ok(await page.locator('.doc-section').count()>=1);
    assert.ok((await article.textContent()).includes('Create & copy'));
    await docQuery.fill('not-a-real-documentation-topic');await page.getByText('No matching articles. Try another term or clear the search.',{exact:true}).waitFor();
    assert.equal(await page.locator('.docs-group').count(),0);
    await page.getByRole('button',{name:'Clear search',exact:true}).click();assert.equal(await page.locator('.doc-section').count(),topics);
    await article.focus();await article.press('End');await page.waitForTimeout(100);assert.ok(await article.evaluate(n=>n.scrollTop>0));
    await article.press('Home');await page.waitForFunction(()=>document.querySelector('.article').scrollTop===0);
    for(const [width,height] of [[1920,1080],[1280,720],[1000,800],[390,844],[720,420]]){
      await page.setViewportSize({width,height});await page.waitForTimeout(150);
      const size=await page.evaluate(()=>({page:document.documentElement.scrollHeight,height:innerHeight,width:document.documentElement.scrollWidth,viewport:innerWidth,regions:[...document.querySelectorAll('.docs-nav,.article')].map(n=>({height:n.clientHeight,overflow:getComputedStyle(n).overflowY,scrollbar:getComputedStyle(n).scrollbarWidth}))}));
      assert.ok(size.page<=height+1,JSON.stringify(size));assert.ok(size.width<=width,JSON.stringify(size));
      assert.ok(size.regions.every(n=>n.height>70&&n.overflow==='auto'&&n.scrollbar==='none'),JSON.stringify(size));
      if(width<=1000){
        const before=await article.evaluate(n=>n.scrollTop);await toc.hover();await page.mouse.wheel(0,500);await page.waitForTimeout(100);
        assert.ok(await toc.evaluate(n=>n.scrollTop>0));assert.equal(await article.evaluate(n=>n.scrollTop),before);assert.equal(await page.evaluate(()=>scrollY),0);
      }
      await page.screenshot({path:path.join(out,`documentation-${width}x${height}.png`)});
    }
    results.documentation='PASS';
    await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'Open navigation',exact:true}).click();await nav('Dashboard');
    await page.waitForTimeout(300);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.screenshot({path:path.join(out,'dashboard-mobile.png'),fullPage:true});
    await page.goto(origin+'/analytics');await page.getByRole('heading',{name:'dashboard',exact:true}).waitFor();assert.ok(page.url().endsWith('/dashboard'));results.legacy_destination='PASS';
    assert.deepEqual(errors,[]);results.browser_errors=errors;
    fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(results,null,2)+'\n');console.log(JSON.stringify(results,null,2));
  }catch(error){if(page)await page.screenshot({path:path.join(out,'failed.png'),fullPage:true}).catch(()=>{});throw error;}
  finally{
    if(page){
      const response=await page.request.get(origin+'/api/auth/session').catch(()=>null);
      if(response?.ok()){const session=await response.json();await page.request.post(origin+'/api/auth/logout',{headers:{Origin:origin,'X-CSRF-Token':session.csrf}}).catch(()=>{});}
    }
    await browser.close();
  }
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
