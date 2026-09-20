// Real Gryphon with a deterministic Telegram transport. No real bot or user is contacted.
import fs from 'node:fs';
import http from 'node:http';
import {randomBytes} from 'node:crypto';
import {GryphonGateway} from '/gryphon/dist/gateway.js';
import {GryphonRepository} from '/gryphon/dist/repository.js';
import {createClientServer, listenUnix, listenTcp} from '/gryphon/dist/http.js';
if (process.env.MASTERMIND_GRYPHON_FIXTURE !== 'isolated-synthetic-v1') throw Error('Isolated fixture only');
const config = {version: '0.1.4-fixture', dataDirectory: '/tmp/gryphon', publicOrigin: 'https://gryphon.invalid',
  clientsDirectory: '/clients', providerTimeoutMs: 3000, webhookMaxBytes: 8192, webhookMaxConnections: 2};
fs.mkdirSync(config.dataDirectory, {recursive: true});
const repository = new GryphonRepository('/tmp/gryphon/state.sqlite');
const sent = [], menus = [];
const transportFactory = () => ({
  getMe: async () => ({id: '100000', isBot: true, username: 'mastermind_fixture_bot'}),
  setWebhook: async () => {}, setCommands: async value => {menus.push(value);},
  sendMessage: async value => {sent.push(value);}, answerCallbackQuery: async () => {},
});
// Only Register origin discovery is replaced: the adapter itself is reached over real HTTP.
const adapterDispatcher = async (connection, token, envelope) => {
  const result = await fetch(connection.adapterUrl, {method: 'POST', redirect: 'error',
    headers: {Authorization: 'Bearer '+token, 'Content-Type': 'application/json'}, body: JSON.stringify(envelope), signal: AbortSignal.timeout(8000)});
  if (!result.ok) throw Error('Adapter HTTP '+result.status);
  return result.json();
};
const gateway = new GryphonGateway({repository, config, pepper: randomBytes(32), transportFactory, adapterDispatcher});
const {bot} = await gateway.connectBot({alias: 'local-fixture', botToken: '100000:'+randomBytes(24).toString('base64url')});
await listenUnix(createClientServer(gateway), '/run/gryphon/client.sock', 0o660);
const control = http.createServer(async (request, response) => {
  try {
    if (request.method === 'GET' && request.url === '/status') {
      response.writeHead(200, {'Content-Type': 'application/json'}); response.end(JSON.stringify({sent, menus})); return;
    }
    if (request.method !== 'POST' || request.url !== '/event') {response.writeHead(404); response.end(); return;}
    let raw = ''; for await (const chunk of request) {raw += chunk; if (raw.length > 8192) throw Error('Fixture body limit');}
    const update = JSON.parse(raw);
    const result = gateway.acceptUpdate(bot.webhookKey, bot.webhookSecret, update);
    await gateway.drain();
    response.writeHead(200, {'Content-Type': 'application/json'}); response.end(JSON.stringify({result, sent, menus}));
  } catch {response.writeHead(500); response.end('Fixture operation failed');}
});
await listenTcp(control, '0.0.0.0', 18497);
setInterval(() => {void gateway.drain();}, 250).unref();
