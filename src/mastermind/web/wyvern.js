import { $, api, state } from './ui.js';
import { mountWyvernConnection } from './wyvern-connection.js';
import { openAgentInitialization } from './agent-initialize.js';
import { openUpdateOverlay } from './update-overlay.js';

export function helperUpdates(component) {
  return openUpdateOverlay({ component, service: 'mastermind', base: '/api/owner/helper-updates',
    headers: () => ({'X-CSRF-Token': state.session?.csrf || ''}) });
}
export function wyvernCard(root) {
  const status = () => api('/api/owner/wyvern');
  let widget;
  const initialize = () => openAgentInitialization({ component: 'Wyvern', service: 'mastermind',
    description: 'Initialize the scoped client connection. An existing shared gateway is reused.',
    profile: 'Adapter selection is separate. Initialization sends no model request.',
    initialize: body => api('/api/owner/wyvern/connect', {method: 'POST', body}),
    observe: id => api('/api/owner/helper-updates/jobs/' + encodeURIComponent(id)),
    recover: async hint => {
      const { jobs } = await api('/api/owner/helper-updates/jobs');
      return jobs.find(job => job.service === 'wyvern-installation' &&
        (hint?.request_id ? job.request_id === hint.request_id : !['COMPLETED','FAILED'].includes(job.state)));
    },
    verify: async () => { const value = await status(); return {ready: value.reachable === true && value.client_linked === true, message: 'This client has not yet been verified by the gateway.'}; },
    onComplete: () => widget.refresh(),
  });
  widget = mountWyvernConnection($('[data-wyvern]', root), {service: 'mastermind', status, initialize,
    bind: body => api('/api/owner/wyvern/bindings', {method: 'POST', body}),
    management: () => api('/api/owner/wyvern/management'), update: () => helperUpdates('wyvern')});
  return () => widget.close();
}
