// Real loopback SSH/SFTP transport and the shipped Saturn adapter. Only the
// remote test server withholds a READ response; no adapter or socket is mocked.
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
import {once} from 'node:events';
import {setTimeout as sleep} from 'node:timers/promises';
import {pathToFileURL} from 'node:url';

const require = createRequire('/app/api/package.json');
const storageEntry = require.resolve('@saturn/storage');
const storageRequire = createRequire(storageEntry);
const {Server, utils} = storageRequire('ssh2');
const {SftpStorageAdapter} = await import(pathToFileURL(storageEntry));
const keys = utils.generateKeyPairSync('ed25519');
const fingerprint = 'SHA256:' + crypto.createHash('sha256')
  .update(utils.parseKey(keys.private).getPublicSSH()).digest('base64').replace(/=+$/, '');
const secret = crypto.randomBytes(24).toString('hex');
const passwordFile = '/tmp/sftp-read-stall-password';
await fs.writeFile(passwordFile, secret, {mode: 0o600, flag: 'wx'});
const bytes = crypto.randomBytes(512 * 1024), clients = new Set();
let mode = 'stall', connections = 0, heldReads = 0, adapter;
const server = new Server({hostKeys: [keys.private]}, client => {
  connections++;
  clients.add(client);
  client.on('error', () => undefined);
  client.on('close', () => clients.delete(client));
  client.on('authentication', context => {
    if (context.method === 'password' && context.username === 'qualification' && context.password === secret) context.accept();
    else context.reject();
  });
  client.on('ready', () => client.on('session', accept => {
    accept().on('sftp', acceptSftp => {
      const sftp = acceptSftp();
      sftp.on('OPEN', (id, filename) => {
        assert.equal(filename, '/fixture/source.bin');
        sftp.handle(id, Buffer.from('owned-handle'));
      });
      sftp.on('FSTAT', id => sftp.attrs(id, {size: bytes.length, mode: 0o100600, uid: 1000, gid: 1000, atime: 0, mtime: 0}));
      sftp.on('READ', (id, _handle, offset, length) => {
        if (mode === 'stall' && offset >= 256 * 1024) { heldReads++; return; }
        if (offset >= bytes.length) sftp.status(id, utils.sftp.STATUS_CODE.EOF);
        else sftp.data(id, bytes.subarray(offset, Math.min(offset + length, bytes.length, mode === 'stall' ? 256 * 1024 : bytes.length)));
      });
      sftp.on('CLOSE', id => sftp.status(id, utils.sftp.STATUS_CODE.OK));
    });
  }));
});
try {
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  adapter = new SftpStorageAdapter({host: '127.0.0.1', port: server.address().port,
    username: 'qualification', root: '/fixture', hostFingerprint: fingerprint,
    authMode: 'password_file', passwordFile, operationTimeoutMs: 1200,
    healthTimeoutMs: 1200, maxConnections: 1});
  const started = Date.now(), stream = await adapter.openRead('source.bin');
  await sleep(250); // Attach after the remote already supplied its first bytes.
  let received = 0;
  await assert.rejects(async () => {
    for await (const chunk of stream) received += chunk.length;
  }, /SFTP read idle timeout/);
  const elapsed = Date.now() - started;
  assert.ok(heldReads > 0, 'The server never held a READ after OPEN');
  assert.equal(received, 256 * 1024, 'Early bytes were lost before consumer attachment');
  assert.ok(elapsed >= 1200 && elapsed < 6000, 'Read failed outside its bounded idle deadline');
  mode = 'healthy';
  const recovered = await adapter.openRead('source.bin'), chunks = [];
  for await (const chunk of recovered) chunks.push(chunk);
  assert.deepEqual(Buffer.concat(chunks), bytes);
  assert.equal(connections, 2, 'Broken lease did not create a fresh SSH connection');
  console.log(JSON.stringify({status: 'PASS',transport: 'real loopback SSH/SFTP',
    adapter: storageEntry, after_open_stall_ms: elapsed, early_bytes_preserved: received,
    held_read_requests: heldReads, fresh_connection: true, recovered_bytes: bytes.length,
    recovered_sha256: crypto.createHash('sha256').update(bytes).digest('hex')}));
} finally {
  if (adapter) await adapter.close();
  for (const client of clients) client.end();
  await new Promise(resolve => server.close(resolve));
  await fs.unlink(passwordFile);
}
