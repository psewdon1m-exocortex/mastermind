import { $, api, dialog, escape, notice, pending, stamp } from './ui.js';
import { confirmAgentAction, openAgentInitialization } from './agent-initialize.js';
import { helperUpdates } from './wyvern.js';

export function gryphonCard(root) {
  const host = $('[data-gryphon]', root);
  let status, closed = false, loading = false, changing = false, challenge, challengeModal, stopInitialization;
  const request = (path = '', options) => api('/api/owner/gryphon' + path, options);
  const bound = () => status?.reachable === true && !!status?.binding;
  function render() {
    if (closed) return;
    const focus = host.contains(document.activeElement)
      ? [...document.activeElement.attributes].find(attribute => attribute.name.startsWith('data-gryphon-'))?.name : undefined;
    const ready = status?.reachable === true, linked = ready && status.connected, bot = status?.bot;
    host.innerHTML = `<div class="settings-group"><h3>Gateway and service function</h3>
      <p>Receive a one-time Crusher code in your private Telegram chat. Bot credentials stay in Gryphon.</p>
      <div class="status-line"><span>${escape(bot ? `${bot.alias}${bot.username ? ' · @' + bot.username : ''}` : 'Gryphon gateway')}</span>
      <span class="${ready ? 'success' : 'danger'}">${ready ? 'Service reachable' : status ? 'Service unavailable' : 'Checking…'}</span></div>
      ${!ready && status ? `<p class="error-message" role="alert">${escape(status.message)}${status.last_known ? ' Displaying the last verified binding.' : ''}</p>` : ''}
      <p class="muted">Last verified: ${escape(stamp(status?.verified_at))}</p><div class="row">
      <button data-gryphon-init ${status?.state === 'NOT_CONFIGURED' ? '' : 'hidden'}>Initialize Gryphon</button>
      <button data-gryphon-link ${!ready || linked || changing ? 'disabled' : ''}>Link Mastermind function</button>
      <button data-gryphon-unlink ${!linked || changing ? 'disabled' : ''}>Unlink Mastermind function</button>
      <button data-gryphon-refresh ${changing ? 'disabled' : ''}>Retry status</button></div></div>
      <div class="settings-group"><h3>Telegram user</h3>
      <p>${status?.binding ? `Telegram ${ready ? 'account linked' : 'binding last verified'} · user ${escape(status.binding.telegramUserId)} · private chat ${escape(status.binding.chatId)}` : 'No Telegram account linked.'}</p>
      ${bound() ? '<p>Commands: <code>/crusher</code>, <code>/crusher_status</code>, <code>/crusher_revoke</code></p>' : ''}
      <div class="row"><button data-gryphon-challenge ${!linked || bound() || changing ? 'disabled' : ''}>${challenge ? 'View link challenge' : 'Link Telegram account'}</button>
      <button data-gryphon-revoke ${!bound() || changing ? 'disabled' : ''}>Revoke Telegram binding</button></div></div>
      <div class="settings-group"><h3>Gryphon version</h3><p>Current installed version: <span>${escape(status?.version || 'Unavailable')}</span></p>
      <button class="action" data-gryphon-update>Check Gryphon for updates</button></div>`;
    $('[data-gryphon-refresh]', host).onclick = () => void refresh();
    $('[data-gryphon-init]', host).onclick = initialize;
    $('[data-gryphon-link]', host).onclick = event => void pending(event.target, linkFunction);
    $('[data-gryphon-unlink]', host).onclick = () => void consequential('connection', 'Unlink Mastermind function',
      'Disconnect Mastermind from this bot and revoke its Telegram-issued Crusher codes and sessions. Other services and owner-created invitations remain available.');
    $('[data-gryphon-revoke]', host).onclick = () => void consequential('binding', 'Revoke Telegram binding',
      'Remove this Telegram account authorization and revoke its Crusher codes and sessions. The bot and other service bindings remain available.');
    $('[data-gryphon-challenge]', host).onclick = event => void pending(event.target, openChallenge);
    $('[data-gryphon-update]', host).onclick = () => helperUpdates('gryphon');
    if (focus) host.querySelector(`[${focus}]`)?.focus({preventScroll: true});
  }
  async function refresh() {
    if (closed || loading || changing) return;
    loading = true;
    try {
      const value = await request();
      if (closed) return;
      status = value;
      if (bound() && challenge) {
        challenge = undefined; challengeModal?.close(true); challengeModal = undefined;
        notice('Telegram account linked to Mastermind.');
      }
      render();
    } catch (error) {
      if (!closed) { status = {...status, reachable: false, last_known: !!status?.verified_at, message: error.message}; render(); }
    } finally { loading = false; }
  }
  async function linkFunction() {
    const {bots} = await request('/bots');
    const available = bots.filter(bot => bot.state === 'ready');
    const modal = dialog('Link Mastermind function', available.length
      ? `<p>Select a registered bot. Telegram account authorization is a separate next step.</p><label>Gryphon bot<select data-bot>${available.map(bot => `<option value="${escape(bot.id)}">${escape(bot.alias)}${bot.username ? ' · @' + escape(bot.username) : ''}</option>`).join('')}</select></label><div class="dialog-footer"><button data-link>Link function</button></div>`
      : '<p>No ready registered bots. Register a bot through authorized Gryphon management, then retry.</p><button data-management>Open gateway management</button>');
    if (available.length) $('[data-link]', modal.element).onclick = event => void pending(event.target, async () => {
      modal.setBusy(true); changing = true;
      try { await request('/connection', {method: 'PUT', body: {botId: $('[data-bot]', modal.element).value}}); modal.setClean(); modal.close(true); notice('Mastermind function linked. Now link your Telegram account.'); }
      catch (error) { modal.error.textContent = error.message; }
      finally { modal.setBusy(false); changing = false; await refresh(); }
    });
    else $('[data-management]', modal.element).onclick = event => void pending(event.target, async () => {
      const {url} = await request('/management'); const target = new URL(url);
      if (target.protocol !== 'https:' || target.username || target.password) throw new Error('Invalid management destination.');
      location.assign(target.href);
    });
  }
  async function consequential(path, title, message) {
    if (!await confirmAgentAction({title, message, confirmLabel: title})) return;
    changing = true; render();
    try { await request('/' + path, {method: 'DELETE'}); challenge = undefined; notice(title + ' completed.'); }
    catch (error) { notice(error.message, true); }
    finally { changing = false; await refresh(); }
  }
  async function openChallenge() {
    if (!challenge || Date.parse(challenge.expiresAt) <= Date.now()) challenge = await request('/link-challenge', {method: 'POST', body: {}});
    const current = challenge; let countdown;
    challengeModal = dialog('Link Telegram account', `<p>Open ${escape(current.botUsername ? '@' + current.botUsername : 'the selected bot')} in a private chat and send:</p>
      <div class="copy-value" tabindex="0">${escape(current.command)}</div><p data-expiry></p><p>Waiting for Gryphon to verify your Telegram identity.</p>
      <div class="dialog-footer"><button data-cancel>Cancel challenge</button><button data-copy>Copy command</button></div>`,
      {dirtyGuard: false, onClose: () => { clearInterval(countdown); challengeModal = undefined; }});
    const modal = challengeModal;
    function tick() {
      const seconds = Math.max(0, Math.ceil((Date.parse(current.expiresAt)-Date.now())/1000));
      $('[data-expiry]', modal.element).textContent = seconds ? `Expires in ${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}` : 'Challenge expired. Close and request a new one.';
      $('[data-copy]', modal.element).disabled = !seconds;
    }
    countdown = setInterval(tick, 1000); tick();
    $('[data-copy]', modal.element).onclick = async () => {
      try { await navigator.clipboard.writeText(current.command); notice('Telegram link command copied.'); }
      catch { modal.error.textContent = 'Select the command above and copy it manually.'; $('.copy-value', modal.element).focus(); }
    };
    $('[data-cancel]', modal.element).onclick = event => void pending(event.target, async () => {
      await request('/link-challenge', {method: 'DELETE'}); challenge = undefined; modal.close(true); render();
    });
    render();
  }
  function initialize() {
    stopInitialization = openAgentInitialization({component: 'Gryphon', service: 'mastermind',
      description: 'Initialize this service client through the local Updater. An existing healthy gateway is reused.',
      profile: 'Bot-function selection and Telegram account authorization are separate next steps.',
      initialize: body => request('/initialize', {method: 'POST', body}),
      observe: id => api('/api/owner/helper-updates/jobs/' + encodeURIComponent(id)),
      recover: async hint => { const {jobs} = await api('/api/owner/helper-updates/jobs'); return jobs.find(job => job.service === 'gryphon-initialization' && (hint?.request_id ? job.request_id === hint.request_id : !['COMPLETED','FAILED'].includes(job.state))); },
      verify: async () => { const value = await request(); return {ready: value.reachable === true && value.enrolled === true, message: 'Gryphon has not verified this service client yet.'}; },
      onComplete: refresh,
    });
  }
  render(); void refresh(); const timer = setInterval(() => { if (!document.hidden) void refresh(); }, 3000);
  return () => { closed = true; clearInterval(timer); challengeModal?.close(true); stopInitialization?.(); challenge = undefined; };
}
