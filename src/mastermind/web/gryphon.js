import { $, api, dialog, escape, notice } from './ui.js';
import { confirmAgentAction } from './agent-initialize.js';

export function gryphonCard(root) {
  const host = $('[data-gryphon]', root);
  let status, closed = false, loading = false, changing = false;
  const request = (path = '', options) => api('/api/owner/gryphon' + path, options);

  function render() {
    if (closed) return;
    const ready = status?.reachable === true;
    const applied = ready && status.connected && !!status.binding;
    host.innerHTML = `<div class="settings-group gryphon-binding-group"><h3>Gryphon bot binding</h3>
      <p>Gryphon owns the Telegram connection, service receives only service-scoped commands.</p>
      <div class="gryphon-status-rows">
        <div class="status-line"><span>Local Gryphon agent:</span><span class="${ready ? 'success' : 'danger'}">${status ? 'Reachability' : 'Checking'}<i class="security-status-square" aria-hidden="true"></i></span></div>
        <div class="status-line"><span>Applied connection:</span><span class="${applied ? 'success' : 'danger'}">Reachability<i class="security-status-square" aria-hidden="true"></i></span></div>
      </div>
      ${!ready && status ? `<p class="error-message" role="alert">${escape(status.message || 'Gryphon is unavailable.')}${status.last_known ? ' Last verified registration retained.' : ''}</p>` : ''}
      <p class="gryphon-applied">Applied connection: <strong>${escape(status?.connected ? status.bot?.alias || 'unknown' : 'none')}</strong></p>
      <button type="button" class="action gryphon-choice-action" data-gryphon-choice ${!ready || changing ? 'disabled' : ''}>${status?.connected ? 'Change Gryphon function' : 'Link Gryphon function'}</button>
    </div>`;
    $('[data-gryphon-choice]', host).onclick = () => void openChoices();
  }

  async function refresh() {
    if (closed || loading || changing) return;
    loading = true;
    try {
      const value = await request();
      if (!closed) { status = value; render(); }
    } catch (error) {
      if (!closed) { status = {...status, reachable: false, last_known: !!status?.verified_at, message: error.message}; render(); }
    } finally { loading = false; }
  }

  async function openChoices() {
    try {
      const {bots} = await request('/bots');
      const available = bots.filter(bot => bot.state === 'ready' || bot.id === status?.bot?.id);
      const selectedId = status?.connected ? status.bot?.id : null;
      const selected = available.find(bot => bot.id === selectedId);
      const modal = dialog('Gryphon Connection', `<p class="gryphon-choice-intro">Select a connection already applied through Gryphon</p>
        <div class="gryphon-choice-layout"><div class="gryphon-choice-list">${available.length
          ? available.map(bot => `<button type="button" class="gryphon-choice${bot.id === selectedId ? ' is-selected' : ''}" data-bot-id="${escape(bot.id)}" aria-pressed="${bot.id === selectedId}" ${bot.state !== 'ready' ? 'disabled' : ''}><span class="gryphon-choice-check" aria-hidden="true"></span>${escape(bot.username ? '@' + bot.username : bot.alias)}</button>`).join('')
          : '<p>No paired bots are available. Register and pair one with sudo updater tui.</p>'}</div>
          ${selected ? `<div class="gryphon-adapter-config"><strong>Active adapter config:</strong><span>Bot: ${escape(selected.alias)}</span><span>${escape(selected.username ? 'Telegram: @' + selected.username : 'Telegram account paired in Gryphon')}</span><span>Mastermind function: active</span></div>` : ''}
        </div>${status?.connected ? '<button type="button" class="gryphon-unlink-action" data-gryphon-unlink>Unlink all adapters</button>' : ''}`, {dirtyGuard: false});
      modal.element.classList.add('gryphon-choice-overlay');
      modal.element.querySelectorAll('[data-bot-id]').forEach(button => {
        button.onclick = async () => {
          if (button.dataset.botId === status?.bot?.id && status?.binding) return;
          changing = true; modal.setBusy(true);
          modal.element.querySelectorAll('[data-bot-id]').forEach(item => { item.disabled = true; });
          try {
            await request('/connection', {method: 'PUT', body: {botId: button.dataset.botId}});
            modal.close(true);
            notice('Mastermind function and paired Telegram account linked.');
          } catch (error) {
            modal.error.textContent = error.message;
            modal.element.querySelectorAll('[data-bot-id]').forEach(item => { item.disabled = item.dataset.botId !== status?.bot?.id && !available.some(bot => bot.id === item.dataset.botId && bot.state === 'ready'); });
          } finally { changing = false; modal.setBusy(false); await refresh(); }
        };
      });
      const unlink = $('[data-gryphon-unlink]', modal.element);
      if (unlink) unlink.onclick = async () => {
        if (!await confirmAgentAction({title: 'Unlink service function', message: 'Disconnect Mastermind from this bot and revoke its Telegram-issued Crusher codes and sessions. Other services remain connected.', confirmLabel: 'Unlink function'})) return;
        changing = true;
        try { await request('/connection', {method: 'DELETE'}); notice('Mastermind function unlinked from Gryphon.'); }
        catch (error) { notice(error.message, true); }
        finally { changing = false; await refresh(); }
      };
    } catch (error) { notice(error.message, true); }
  }

  render(); void refresh();
  const timer = setInterval(() => { if (!document.hidden) void refresh(); }, 3000);
  return () => { closed = true; clearInterval(timer); };
}
