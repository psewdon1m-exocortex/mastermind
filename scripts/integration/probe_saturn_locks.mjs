// Run on stdin in the actual Saturn test container; generated local database only.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {setTimeout as wait} from 'node:timers/promises';
import {Database} from '/app/api/node_modules/@saturn/database/dist/index.js';

const environment=JSON.parse(fs.readFileSync('/fixture/saturn-env.json','utf8'));
const holder=new Database(environment.DATABASE_URL,{maintenanceBarrier:true,max:3});
const recovery=new Database(environment.DATABASE_URL,{maintenanceBarrier:true,max:3});
const inspector=new Database(environment.DATABASE_URL,{max:2});
const id=randomUUID(), key='mastermind-qualification:'+id;
let release;
const gate=new Promise(resolve=>{release=resolve;});
let entered;
const acquired=new Promise(resolve=>{entered=resolve;});
try{
  await inspector.withSql(sql=>sql`INSERT INTO operation_locks(lock_key,operation_id,expires_at) VALUES(${key},${id},now()+interval '6 hours')`);
  const protectedWork=holder.withSharedMaintenance(async()=>{entered();await gate;});
  await acquired;
  let finished=false;
  const attempt=recovery.reconcileInactiveFileLocks().then(()=>{finished=true;});
  for(let tries=0;tries<100;tries++){
    const rows=await inspector.withSql(sql=>sql`SELECT count(*)::int AS count FROM pg_locks WHERE locktype='advisory' AND objid=1397967206 AND NOT granted`);
    if(rows[0].count>0)break;
    assert.ok(tries<99,'Exclusive recovery never reached PostgreSQL');await wait(20);
  }
  assert.equal(finished,false,'Recovery crossed an active shared maintenance barrier');
  assert.equal((await inspector.withSql(sql=>sql`SELECT count(*)::int AS count FROM operation_locks WHERE lock_key=${key}`))[0].count,1);
  release();await protectedWork;await attempt;
  assert.equal((await inspector.withSql(sql=>sql`SELECT count(*)::int AS count FROM operation_locks WHERE lock_key=${key}`))[0].count,0);
  console.log(JSON.stringify({actual_postgresql:true,active_writer_preserved:'PASS',exclusive_recovery_waited:'PASS',orphan_lease_removed:'PASS'}));
}finally{
  release();
  await inspector.withSql(sql=>sql`DELETE FROM operation_locks WHERE lock_key=${key}`);
  await Promise.all([holder.close(),recovery.close(),inspector.close()]);
}
