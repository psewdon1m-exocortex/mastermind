import { $, api } from './ui.js';
import { mountWyvernConnection } from './wyvern-connection.js';
export function wyvernCard(root) {
  const status = () => api('/api/owner/wyvern');
  let widget;
  widget = mountWyvernConnection($('[data-wyvern]', root), {service: 'mastermind', status,
    bind: body => api('/api/owner/wyvern/bindings', {method: 'POST', body})});
  return () => widget.close();
}
