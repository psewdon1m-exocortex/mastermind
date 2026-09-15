const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
(async () => {
  const root = path.resolve(__dirname, '..'), origin = 'http://localhost:18390';
  const login = await fetch(origin+'/api/auth/login', {method:'POST', headers:{Origin:origin,'Content-Type':'application/json'},
    body:JSON.stringify({access_key:fs.readFileSync(path.join(root,'.local/secrets/core/bootstrap_access_key'),'utf8')})});
  assert.equal(login.status,200);
  const csrf = (await login.json()).csrf;
  const cookie = login.headers.getSetCookie().map(c=>c.split(';')[0]).join('; ');
  const call = async (route, data, method='POST') => {
    const response = await fetch(origin+route, {method, headers:{Origin:origin,Cookie:cookie,
      'Content-Type':'application/json','X-CSRF-Token':csrf}, ...(data?{body:JSON.stringify(data)}:{})});
    const result = await response.json();
    if (response.status!==200) throw new Error(route+' '+response.status+' '+JSON.stringify(result));
    return result;
  };
  const stamp = Date.now(), old = 'Rename source '+stamp, next='Rename target '+stamp, referring='Rename links '+stamp;
  await call('/api/notes',{path:old+'.md',text:'#main\nSource body\n'});
  await new Promise(r=>setTimeout(r,3000));
  const text = 'Native [['+old+']] and @'+old+'\n\n`@'+old+'`\n\n<!-- @'+old+' -->\n';
  await call('/api/notes',{path:referring+'.md',text});
  await new Promise(r=>setTimeout(r,4000));
  const source = await call('/api/note?path='+encodeURIComponent(old+'.md'),null,'GET');
  const renamed = await call('/api/note/rename',{old_path:old+'.md',new_path:next+'.md',expected_sha256:source.sha256});
  assert.equal(renamed.path,next+'.md');
  const after = await call('/api/note?path='+encodeURIComponent(referring+'.md'),null,'GET');
  assert.ok(after.text.includes('[['+next+']]'), 'Native wiki propagation missing');
  assert.ok(after.text.includes('and @'+next+'\n'), '@ propagation missing');
  assert.ok(after.text.includes('`@'+old+'`'), 'Code changed');
  assert.ok(after.text.includes('<!-- @'+old+' -->'), 'Comment changed');
  console.log(JSON.stringify({native_rename:'PASS',native_links:'PASS',custom_references:'PASS',code_and_comments:'PASS'}));
})().catch(error=>{console.error(error.message);process.exitCode=1;});
