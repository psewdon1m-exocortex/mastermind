import {api, state} from './ui.js';
import {hashFile} from './crusher.js';

const terminal = new Set(['COMPLETED', 'ROLLED_BACK', 'FAILED']);
const node = (tag, text, cls) => { const el = document.createElement(tag); if (text != null) el.textContent = text; if (cls) el.className = cls; return el; };
const button = (text, action) => { const el = node('button', text); el.type = 'button'; el.onclick = action; return el; };
function modal(title, warning = false) {
  const dialog = node('dialog', null, 'exo-update' + (warning ? ' warning-dialog' : ''));
  const heading = node('h2', title); heading.id = 'update-' + crypto.randomUUID();
  dialog.setAttribute('aria-labelledby', heading.id);
  const header = node('header'), close = button('×', () => dialog.close()); close.className = 'close'; close.setAttribute('aria-label', 'Close updates');
  header.append(heading, close); const content = node('div', null, 'exo-update-content'); dialog.append(header, content);
  document.body.append(dialog); dialog.showModal(); close.focus();
  dialog.addEventListener('close', () => dialog.remove(), {once:true});
  return {dialog, content};
}
function meta(values) { const dl = node('dl', null, 'meta'); for (const [key,value] of values) dl.append(node('dt',key),node('dd',value ?? '—')); return dl; }

// The shared layout, with streaming file IO for a multi-GiB three-component head.
// No Blob/ArrayBuffer copy of the complete ZIP is made in the browser or API.
export function openGroupUpdates({rollback = false} = {}) {
  document.querySelectorAll('dialog.exo-update').forEach(el => el.close());
  const focus = document.activeElement, view = modal(rollback ? 'Previous version' : 'Updates');
  let closed = false, timer, discovery, target, record, checking = false, busy = false, error = '', connection = '';
  let file, checkedHash, saved = false, hashing = false, measured, lastTerminal, warning, renderKey;
  const active = () => Boolean(record?.phase && !terminal.has(record.phase));
  const version = () => rollback ? target?.version : discovery?.available_version;
  async function perform(action) {
    if (busy) return; busy = true; error = ''; render();
    try { await action(); } catch (failure) { error = failure.message; }
    finally { busy = false; render(); }
  }
  function render() {
    if (closed) return;
    const key = JSON.stringify([discovery,target,record?.request_id,record?.phase,record?.job_state,record?.progress,record?.error,record?.job_message,record?.download_consumed,record?.download_complete,record?.recovery_uploading,checking,busy,error,connection,file?.name,checkedHash,saved,hashing,measured]);
    if (key === renderKey) return; renderKey = key;
    const focused = view.content.contains(document.activeElement) ? document.activeElement : null;
    const identity = focused && [focused.tagName, focused.getAttribute('aria-label'), focused.textContent, focused.type];
    const c = view.content; c.replaceChildren();
    c.append(meta([['Installed', discovery?.installed_version ?? 'Checking…'], ['Updater', discovery ? 'Available' : 'Checking…'], ['Registry', discovery ? 'Checked' : 'Unavailable']]));
    const discoveryBox = node('section', null, 'box'); discoveryBox.append(node('h3','Discovery'));
    discoveryBox.append(node('p', checking ? 'Checking for updates…' : rollback ? target?.available ? 'Previous version: ' + target.version : 'No verified previous version is available.' : discovery?.update_available ? 'Mastermind ' + discovery.available_version + ' is available.' : discovery ? 'No new updates are available.' : 'Release discovery is unavailable.'));
    discoveryBox.append(node('p', 'Core, Runtime and Worker use one signed release. A full backup must be saved on your computer before installation.', 'muted'));
    const actions = node('div',null,'actions'), again = button('Check again', () => void check()); again.disabled = checking || busy || active(); actions.append(again);
    if ((rollback && target?.available) || (!rollback && discovery?.update_available)) {
      const install = button((rollback ? 'Return to ' : 'Install ') + version(), backupWarning);
      install.disabled = checking || busy || active() || (!rollback && !discovery.compatible); actions.append(install);
      if (!rollback && !discovery.compatible) discoveryBox.append(node('p','The signed component profile or saved-copy protocol is incompatible.','error'));
    }
    c.append(discoveryBox, actions);
    if (record?.phase) {
      const status = node('section',null,'box job'); status.setAttribute('aria-live','polite');
      status.append(meta([['State',record.job_state || record.phase],['Job',record.job_id || record.request_id],['Message',record.job_message || record.error || (record.phase === 'WAITING_SAVED' ? 'Save and verify the backup before installing.' : 'Status refreshes automatically.')]]));
      const progress = node('progress'); progress.max = 1; progress.setAttribute('aria-label','Update progress');
      const value = record.progress;
      if (typeof measured === 'number') progress.value = measured;
      else if (value?.mode === 'determinate' && value.total > 0 && value.completed >= 0 && value.completed <= value.total) progress.value = value.completed / value.total;
      else if (['COMPLETED','ROLLED_BACK'].includes(record.phase)) progress.value = 1;
      status.append(progress);
      if (hashing) status.append(node('p','Checking the selected ZIP · ' + Math.round((measured || 0)*100) + '%'));
      if (['WAITING_SAVED','DOWNLOADING'].includes(record.phase) || (['FAILED','ROLLBACK_FAILED'].includes(record.job_state) && record.error === 'UPDATE_RECOVERY_REQUIRED')) savedControls(status);
      if (connection) status.append(node('p', connection,'error'));
      c.append(status);
    }
    const fault = node('p',error,'error'); fault.setAttribute('role','alert'); c.append(fault);
    if (identity) [...c.querySelectorAll('button,input,a')].find(el => el.tagName === identity[0] && el.getAttribute('aria-label') === identity[1] && el.textContent === identity[2] && el.type === identity[3])?.focus();
  }
  function savedControls(c) {
    const recovery = ['FAILED','ROLLBACK_FAILED'].includes(record.job_state) && record.error === 'UPDATE_RECOVERY_REQUIRED';
    if (recovery) c.append(node('p','Recovery requires the original ZIP saved before this interrupted update. Select it below; current writers remain paused.','error'));
    c.append(node('p','The server copy is deleted when the download ends, including an interrupted transfer. Installation verifies the file you select below.','muted'));
    if (!record.download_consumed && record.phase === 'WAITING_SAVED') {
      const link = node('a','Download backup'); link.href = '/api/owner/updates/' + record.request_id + '/backup'; link.download = 'mastermind-backup.zip'; c.append(link);
    }
    if (record.download_consumed && !record.download_complete) c.append(node('p','Download interrupted. Cancel this preparation and create a fresh backup.','error'));
    if (record.download_complete || recovery) {
      const label = node('label',null,'saved'), input = node('input'); input.type = 'checkbox'; input.checked = saved;
      input.onchange = () => { saved = input.checked; render(); }; label.append(input,node('span','I have saved the ZIP on my computer.')); c.append(label);
      const picker = node('input'); picker.type = 'file'; picker.accept = '.zip'; picker.setAttribute('aria-label','Select the saved backup ZIP'); picker.disabled = busy || hashing;
      picker.onchange = async () => {
        file = picker.files[0]; checkedHash = undefined; error = '';
        if (!file) return;
        if (file.size !== record.size) { error = 'Select the exact backup created for this update.'; render(); return; }
        hashing = true; measured = 0; render();
        try {
          checkedHash = await hashFile(file, value => { measured = value; render(); }, new AbortController().signal);
          if (checkedHash !== record.sha256) { checkedHash = undefined; error = 'The selected ZIP checksum differs from this backup.'; }
        } catch (failure) { error = failure.message; }
        finally { hashing = false; measured = undefined; render(); }
      };
      c.append(picker);
      if (file) c.append(node('p',file.name + (checkedHash ? ' · checksum verified' : ' · not verified')));
      const install = button(recovery ? 'Recover previous version' : (rollback ? 'Return to ' : 'Install ') + record.version, () => perform(async () => {
        const response = await fetch('/api/owner/updates/' + record.request_id + '/saved-backup', {
          method:'PUT', credentials:'same-origin', body:file,
          headers:{'X-CSRF-Token':state.session.csrf,'Content-Type':'application/zip','X-Update-Saved':'1','X-Content-SHA256':checkedHash}
        });
        const result = await response.json(); if (!response.ok) throw Error(result.error?.message || 'Saved backup transfer failed. Reopen this panel to check its status.');
        record = result; file = undefined; checkedHash = undefined; saved = false;
      }));
      install.disabled = busy || hashing || record.recovery_uploading || !saved || !checkedHash; c.append(install);
    }
    if (recovery) return;
    const cancel = button('Cancel preparation', () => perform(async () => { record = await api('/api/owner/updates/' + record.request_id + '/cancel',{method:'POST',body:{}}); }));
    cancel.disabled = busy || hashing || record.phase === 'DOWNLOADING'; c.append(cancel);
  }
  function backupWarning() {
    if (warning) return;
    warning = modal((rollback ? 'Return to ' : 'Install ') + version(), true);
    const current = warning;
    const box = node('section',null,'warning'); box.append(node('h3','Save a backup before continuing'),node('p','A full encrypted ZIP will be prepared under the writer lock. Download it, confirm it is saved, and select that file. Installation remains locked until its checksum is verified.'));
    const create = button('Create backup', () => {
      current.dialog.close();
      void perform(async () => { record = await api('/api/owner/updates' + (rollback ? '/rollback' : ''), {method:'POST',body:rollback ? {job_id:target.job_id} : {version:version()}}); });
    });
    const actions = node('div',null,'actions'); actions.append(button('Cancel',()=>current.dialog.close()),create); current.content.append(box,actions);
    current.dialog.addEventListener('close',()=>{warning=undefined;},{once:true});
  }
  async function check() {
    if (checking || closed) return; checking=true; error=''; render();
    try { discovery = await api('/api/owner/updates/check',{method:'POST',body:{}}); if (rollback) target = await api('/api/owner/updates/rollback'); }
    catch (failure) { discovery=undefined; error=failure.message; }
    finally { checking=false; render(); }
  }
  async function observe() {
    if (closed) return;
    try {
      record = await api('/api/owner/updates'); connection='';
      if (terminal.has(record.phase) && lastTerminal !== record.request_id + record.phase) { lastTerminal = record.request_id + record.phase; await check(); }
    } catch (failure) { connection = 'Connection interrupted. Reconnecting… ' + failure.message; }
    render(); if (!closed) timer=setTimeout(observe,1500);
  }
  view.dialog.addEventListener('close',()=>{closed=true;clearTimeout(timer);warning?.dialog.close();if(focus?.isConnected)focus.focus();},{once:true});
  void check(); void observe();
  return {close:()=>view.dialog.close()};
}
