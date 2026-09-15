const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {execFileSync}=require('node:child_process');
(async()=>{
  const root=path.resolve(__dirname,'..'),origin='http://localhost:18390';
  const login=await fetch(origin+'/api/auth/login',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json'},
    body:JSON.stringify({access_key:fs.readFileSync(path.join(root,'.local/secrets/core/bootstrap_access_key'),'utf8')})});
  assert.equal(login.status,200);const csrf=(await login.json()).csrf,cookie=login.headers.getSetCookie().map(c=>c.split(';')[0]).join('; ');
  const headers={Origin:origin,Cookie:cookie,'Content-Type':'application/json','X-CSRF-Token':csrf};
  async function call(route,data,method='POST',extra={}){
    const response=await fetch(origin+route,{method,headers:{...headers,...extra},...(data?{body:JSON.stringify(data)}:{})});
    const result=await response.json();if(response.status!==200)throw Error(route+' '+response.status+' '+JSON.stringify(result));return result;
  }
  async function ready(){for(let i=0;i<90;i++){const state=await call('/api/status',null,'GET');
    if(state.runtime?.bridge?.ready&&state.runtime.startup_allowed)return;await new Promise(resolve=>setTimeout(resolve,500));}throw Error('Runtime did not become ready');}
  const stamp=Date.now(),folder='Native folder '+stamp,moved='Moved folder '+stamp,note='Native topic '+stamp,links='Native attachment links '+stamp;
  await ready();await call('/api/notes',{path:folder+'/'+note+'.md',text:'# '+note+'\n'});await ready();
  // Generated fixture setup only; production mutations use the coordinator. No other job runs here.
  const bytes=crypto.randomBytes(256*1024),sha=crypto.createHash('sha256').update(bytes).digest('hex');
  execFileSync('docker',['exec','-i','mastermind-development-runtime-1','python','-c',
    "from pathlib import Path; import sys; p=Path('/vault/current')/sys.argv[1]; (p/'Empty/deep').mkdir(parents=True); (p/'attachment.bin').write_bytes(sys.stdin.buffer.read())",folder],{input:bytes});
  await call('/api/notes',{path:links+'.md',text:'![['+folder+'/attachment.bin]]\n\n[['+folder+'/'+note+']]\n\n@'+note+'\n'});await ready();
  const shared=await call('/api/v1/shares',{path:folder+'/'+note+'.md',permission:'view'});
  const attachment=await call('/api/note/rename',{old_path:folder+'/attachment.bin',new_path:folder+'/renamed.bin',expected_sha256:sha});
  assert.equal(attachment.sha256,sha);await ready();
  let content=await call('/api/note?path='+encodeURIComponent(links+'.md'),null,'GET');
  assert.ok(content.text.includes('renamed.bin')&&!content.text.includes('attachment.bin'),'Native attachment link propagation missing');
  const version=await call('/internal/bridge/path-version',{path:folder},'POST',{Authorization:'Bearer '+fs.readFileSync(path.join(root,'.local/secrets/core/bridge_token'),'utf8')});
  const result=await call('/api/note/rename',{old_path:folder,new_path:moved,expected_sha256:version.sha256});
  assert.equal(result.path,moved);await ready();
  content=await call('/api/note?path='+encodeURIComponent(links+'.md'),null,'GET');
  assert.ok(!content.text.includes(folder+'/'),'Native folder link propagation missing');
  assert.ok(content.text.includes('@'+note),'Folder move changed the note basename reference');
  const listing=await call('/api/v1/shares',null,'GET');
  assert.equal(listing.find(item=>item.share_id===shared.share_id).path,moved+'/'+note+'.md');
  const probe=JSON.parse(execFileSync('docker',['exec','mastermind-development-runtime-1','python','-c',
    "from pathlib import Path; import sys,hashlib,json; p=Path('/vault/current')/sys.argv[1]; print(json.dumps({'sha':hashlib.file_digest((p/'renamed.bin').open('rb'),'sha256').hexdigest(),'empty':(p/'Empty/deep').is_dir(),'old':(Path('/vault/current')/sys.argv[2]).exists()}))",moved,folder],{encoding:'utf8'}));
  assert.deepEqual(probe,{sha,empty:true,old:false});
  console.log(JSON.stringify({native_attachment_rename:'PASS',native_folder_move:'PASS',native_link_propagation:'PASS',unchanged_attachment_sha:'PASS',empty_directories:'PASS',share_path:'PASS'}));
})().catch(error=>{console.error(error.message);process.exitCode=1;});
