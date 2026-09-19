import {$, api, escape, pending, notice} from './ui.js';

export async function wyvernCard(root) {
  const box = $('[data-wyvern]', root);
  let current;
  const known = value => value === true ? 'Yes' : value === false ? 'No' : 'Unknown';
  async function action(button, run) {
    try { await pending(button, run); }
    catch (error) { if (error.name !== 'AbortError') notice(error.message, true); }
  }
  function bindingSelector(name, fn) {
    const selected = fn.adapter_id ? fn.adapter_id + ':' + fn.profile : '';
    const options = (current.adapters || []).flatMap(adapter => Object.entries(adapter.profiles)
      .filter(([, profile]) => adapter.enabled && (fn.required_capabilities || []).every(cap => profile.capabilities.includes(cap)))
      .map(([profile]) => ({value: adapter.adapter_id + ':' + profile, label: adapter.name + ' / ' + profile})));
    if (selected && !options.some(option => option.value === selected)) {
      options.unshift({value: selected, label: fn.adapter_id + ' / ' + fn.profile + ' (unavailable)'});
    }
    return `<label>${escape(name)}<select data-function="${escape(name)}"><option value="">Not selected</option>${options.map(option => `<option value="${escape(option.value)}" ${option.value === selected ? 'selected' : ''}>${escape(option.label)}</option>`).join('')}</select><span class="muted">${fn.ready ? 'Ready' : 'Not ready'}</span></label>`;
  }
  async function refresh() {
    current = await api('/api/owner/wyvern');
    if (!box.isConnected) return;
    box.innerHTML = `<p>${current.llm_ready ? 'Ready for LLM requests' : 'LLM functions are not ready'}</p>
      <dl><dt>Instance</dt><dd>${escape(current.instance_id || 'Unknown')}</dd><dt>Client</dt><dd>${escape(current.client_id || 'Unknown')}</dd>
      <dt>Transport</dt><dd>${escape(current.mode || 'Unknown')}</dd><dt>Link configured</dt><dd>${known(current.link_configured)}</dd>
      <dt>Gateway reachable</dt><dd>${known(current.reachable)}</dd><dt>Client authenticated</dt><dd>${known(current.client_linked)}</dd>
      <dt>Gateway ready</dt><dd>${known(current.ready)}</dd><dt>Adapter selected</dt><dd>${known(current.adapter_selected)}</dd></dl>
      <form data-wyvern-bindings>${Object.entries(current.functions || {}).map(([name, fn]) => bindingSelector(name, fn)).join('')}${current.reachable ? '<button type="submit">Apply Adapters</button>' : ''}</form>
      <div class="row"><button data-wyvern-refresh>Refresh status</button><button data-wyvern-connect>Connect through Updater</button></div>
      <p class="muted">Create Adapters and manage API keys in the host console: sudo updater tui.</p>`;
    $('[data-wyvern-refresh]', box).onclick = event => action(event.currentTarget, refresh);
    $('[data-wyvern-connect]', box).onclick = event => action(event.currentTarget, async () => {
      const job = await api('/api/owner/wyvern/connect', {method: 'POST', body: {}});
      notice('Wyvern connection accepted: ' + job.id);
      await refresh();
    });
    $('form', box).onsubmit = event => {
      event.preventDefault();
      const button = $('button[type=submit]', box);
      if (!button) return;
      void action(button, async () => {
        const bindings = {};
        for (const select of box.querySelectorAll('[data-function]')) if (select.value) {
          const [adapter_id, profile] = select.value.split(':');
          bindings[select.dataset.function] = {adapter_id, profile};
        }
        await api('/api/owner/wyvern/bindings', {method: 'POST', body: {bindings, expected_revision: current.binding_revision, request_id: crypto.randomUUID()}});
        await refresh();
        notice('Adapter bindings saved.');
      });
    };
  }
  try { await refresh(); }
  catch (error) { if (error.name !== 'AbortError') box.textContent = error.message; }
}
