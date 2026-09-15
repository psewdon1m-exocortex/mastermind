// Explicit qualification-only preload, never part of a Saturn release image.
import fs from 'node:fs';
import {PostgresFileRepository} from '/app/api/node_modules/@saturn/file-core/dist/index.js';
const name=process.env.MASTERMIND_QUALIFICATION_HOLD;
if(!/^Restart qualification [a-f0-9]{32}\.bin$/.test(name||''))throw new Error('Invalid qualification target');
const marker='/app/data/mastermind-'+name.match(/[a-f0-9]{32}/)[0]+'.held';
const original=PostgresFileRepository.prototype.acquireLocks;
PostgresFileRepository.prototype.acquireLocks=async function(operationId,keys,expiresAt){
  const acquired=await original.call(this,operationId,keys,expiresAt);
  if(acquired && keys.some(key=>key.startsWith('upload-target:')&&key.endsWith(':'+name.toLowerCase())) && !fs.existsSync(marker)){
    fs.writeFileSync(marker,operationId,{flag:'wx',mode:0o600});
    await new Promise(()=>{}); // The independent test controller must SIGKILL us.
  }
  return acquired;
};
