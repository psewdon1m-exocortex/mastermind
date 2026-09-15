// Execute each package's declared tests inside the already-built clean replay.
// pnpm's deployment stage retains a production install state; invoking its run
// shortcut can prune dev tools. Execute the pinned Vitest/TypeScript CLIs directly.
import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import assert from 'node:assert/strict';
const root='/workspace';
const outputs=[];
for(const group of ['apps','packages'])for(const entry of fs.readdirSync(path.join(root,group)).sort()){
  const cwd=path.join(root,group,entry),file=path.join(cwd,'package.json');if(!fs.existsSync(file))continue;
  const pkg=JSON.parse(fs.readFileSync(file,'utf8')),script=pkg.scripts?.test;
  if(!script)continue;
  assert.ok(['vitest run','vitest run --passWithNoTests'].includes(script),'Unreviewed test script: '+pkg.name);
  console.log('PACKAGE '+pkg.name);
  const result=spawnSync(process.execPath,[path.join(root,'node_modules/vitest/vitest.mjs'),...script.split(' ').slice(1)],{cwd,stdio:'inherit',timeout:180000});
  assert.equal(result.status,0,'Package test failure: '+pkg.name);
  if(pkg.scripts.typecheck){
    const check=pkg.scripts.typecheck;assert.equal(check,'tsc --noEmit -p tsconfig.json','Unreviewed typecheck: '+pkg.name);
    const typed=spawnSync(process.execPath,[path.join(root,'node_modules/typescript/bin/tsc'),'--noEmit','-p','tsconfig.json'],{cwd,stdio:'inherit',timeout:180000});
    assert.equal(typed.status,0,'Typecheck failed: '+pkg.name);
  }
  outputs.push(pkg.name);
}
console.log(JSON.stringify({status:'PASS',packages:outputs}));
