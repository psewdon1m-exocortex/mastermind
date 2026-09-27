import { $, api, state } from './ui.js';
import { mountWyvernConnection } from './wyvern-connection.js';
import { openUpdateOverlay } from './update-overlay.js';

export function helperUpdates(component) {
  return openUpdateOverlay({ component, service: 'mastermind', base: '/api/owner/helper-updates',
    headers: () => ({'X-CSRF-Token': state.session?.csrf || ''}) });
}
export function wyvernCard(root) {
  const status = () => api('/api/owner/wyvern');
  let widget;
  widget = mountWyvernConnection($('[data-wyvern]', root), {service: 'mastermind', status,
    bind: body => api('/api/owner/wyvern/bindings', {method: 'POST', body})});
  return () => widget.close();
}
