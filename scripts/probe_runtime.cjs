const {chromium} = require('C:/Users/pc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
(async () => {
  const root = path.resolve(__dirname, '..');
  const browser = await chromium.launch({headless: true});
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}});
  const origin = 'http://localhost:18390';
  const login = await context.request.post(origin + '/api/auth/login', {
    data: {access_key: fs.readFileSync(path.join(root, '.local/secrets/core/bootstrap_access_key'), 'utf8')},
    headers: {Origin: origin}
  });
  console.log('Owner login status:', login.status());
  const page = await context.newPage();
  page.on('websocket', socket => console.log('WebSocket path:', new URL(socket.url()).pathname + new URL(socket.url()).search));
  page.on('pageerror', error => console.log('Browser error:', error.message.slice(0, 300)));
  await page.goto(origin + '/runtime/index.html?autoconnect=1&path=runtime/websockify&resize=remote', {waitUntil: 'domcontentloaded'});
  await page.waitForTimeout(7000);
  if (process.argv.includes('--trust-generated-vault')) {
    // Coordinates from runtime-first.png; only used against this generated empty test Vault.
    await page.mouse.click(878, 558);
    await page.waitForTimeout(3500);
  }
  console.log('Runtime page:', (await page.locator('body').innerText()).slice(-1200));
  await page.screenshot({path: path.join(root, 'artifacts/runtime-first.png')});
  console.log('Screenshot saved: artifacts/runtime-first.png');
  await browser.close();
})().catch(error => {console.error(error.message); process.exitCode=1;});
