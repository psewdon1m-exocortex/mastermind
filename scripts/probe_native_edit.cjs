const {chromium} = require('C:/Users/pc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
(async () => {
  const root = path.resolve(__dirname, '..');
  const browser = await chromium.launch({headless: true});
  try {
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}});
  const origin = 'http://localhost:18390';
  const login = await context.request.post(origin + '/api/auth/login', {
    data: {access_key: fs.readFileSync(path.join(root, '.local/secrets/core/bootstrap_access_key'), 'utf8')},
    headers: {Origin: origin}
  });
  if (login.status() !== 200) throw new Error('Login failed: ' + login.status());
  const csrf = (await login.json()).csrf;
  const page = await context.newPage();
  await page.goto(origin + '/runtime/index.html?autoconnect=1&path=runtime/websockify&resize=remote');
  await page.waitForTimeout(3500);
  const created = await page.evaluate(async ({csrf}) => {
    const response = await fetch('/api/notes', {method: 'POST', headers: {'Content-Type':'application/json','X-CSRF-Token':csrf},
      body: JSON.stringify({path:'Runtime test.md',text:'#main\nNative editor qualification\n'})});
    return {status:response.status, body:await response.json()};
  }, {csrf});
  console.log('Programmatic create through verified pause:', created.status);
  if (![200,409].includes(created.status)) throw new Error('Create failed: ' + created.body.error?.code);
  await page.waitForTimeout(5000);
  // Focus the remote application, close native settings, and use the real quick switcher.
  await page.mouse.click(720, 250);
  await page.keyboard.press('Escape');
  await page.keyboard.press('Control+o');
  await page.waitForTimeout(700);
  await page.keyboard.type('Runtime test', {delay:80});
  await page.keyboard.press('Enter');
  await page.waitForTimeout(1200);
  await page.keyboard.press('Control+End');
  await page.keyboard.press('Enter');
  await page.keyboard.type('Native keyboard marker', {delay:35});
  await page.waitForTimeout(3000);
  const read = await page.evaluate(async () => (await fetch('/api/note?path=Runtime%20test.md')).json());
  console.log('Native keyboard persisted:', read.text?.includes('Native keyboard marker') === true);
  await page.screenshot({path:path.join(root,'artifacts/runtime-native-edit.png')});
  if (!read.text?.includes('Native keyboard marker')) throw new Error('Native keyboard text was not persisted');
  } finally {await browser.close();}
})().catch(error => {console.error(error.message); process.exitCode=1;});
