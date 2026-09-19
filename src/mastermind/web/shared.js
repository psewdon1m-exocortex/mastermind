import {$,api,escape,stamp,search,wireSearch,bind,pending,dialog,confirmation,notice} from './ui.js';

// Raw capabilities are intentionally kept only in this authenticated tab.
export const shareCapabilities=new Map();
const shortDate=value=>value?new Date(value*1000).toLocaleString('en-GB',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}):'Unavailable';
const size=value=>value==null?'Unavailable':value>=1024?(value/1024).toLocaleString('en-GB',{maximumFractionDigits:1})+' KiB':value+' B';

export async function shares(root){
  root.innerHTML=`<div class="toolbar shared-toolbar" role="toolbar" aria-label="Shared controls">${search('Search shared notes')}<div class="shared-tools"><span data-count role="status">Loading…</span><button data-create>Create Share</button><button data-previous disabled>Previous</button><button data-next disabled>Next</button></div></div>
    <div class="shared-head"><div class="shared-column-heads"><button data-sort="name" aria-label="Sort by name">Name <span data-sort-mark="name" aria-hidden="true">↕</span></button><button data-sort="modified" aria-label="Sort by modified date">Modified <span data-sort-mark="modified" aria-hidden="true">↓</span></button><span>Access</span></div><span></span></div>
    <div class="shared-list" data-shares aria-label="Shared notes"></div>`;
  let records=[],offset=0,query='',sorting='modified',direction=-1;const expanded=new Set();
  const permission=item=>item.permission==='edit'?'Edit':'View';
  const status=item=>item.target_missing?'Note missing':item.state==='expired'?'Expired':'Active';
  const details=item=>[['Password',item.password_required?'On':'Off'],['Shared since',stamp(item.created_at)],['Expires at',item.expires_at?stamp(item.expires_at):'None'],['Size',size(item.size_bytes)],['Access',permission(item)],['Status',status(item)]];
  function render(){
    const needle=query.trim().toLocaleLowerCase('en-US');
    const list=records.filter(item=>item.state!=='revoked'&&[item.path,item.share_id,shortDate(item.modified_at),...details(item).flat()].join(' ').toLocaleLowerCase('en-US').includes(needle));
    list.sort((a,b)=>direction*(sorting==='name'?a.path.localeCompare(b.path,'en',{sensitivity:'base'}):(a.modified_at??0)-(b.modified_at??0))||b.created_at-a.created_at||a.share_id.localeCompare(b.share_id));
    $('[data-count]',root).textContent=`${list.length} of ${records.length} on page ${offset/100+1}`;
    for(const key of ['name','modified']){$(`[data-sort-mark="${key}"]`,root).textContent=sorting===key?(direction===1?'↑':'↓'):'↕';$(`[data-sort="${key}"]`,root).setAttribute('aria-label',`Sort by ${key==='name'?'name':'modified date'}${sorting===key?', currently '+(direction===1?'ascending':'descending'):''}`);}
    $('[data-shares]',root).innerHTML=list.length?list.map(item=>{
      const open=expanded.has(item.share_id),canCopy=shareCapabilities.has(item.share_id),id=escape(item.share_id),name=escape(item.path.split('/').at(-1));
      return `<article class="shared-item${open?' expanded':''}" data-share="${id}"><div class="shared-row"><button class="shared-toggle" data-expand aria-expanded="${open}" aria-controls="share-details-${id}" aria-label="Details for ${escape(item.path)}"><strong title="${escape(item.path)}">${name}</strong><time>${escape(shortDate(item.modified_at))}</time><span class="accent">${permission(item)}</span></button><button class="shared-copy" data-copy >Copy link</button></div>
        <div class="shared-details" id="share-details-${id}" ${open?'':'hidden'}><dl class="shared-metadata">${details(item).map(([key,value])=>`<div><dt>${key}</dt><dd>${escape(value)}</dd></div>`).join('')}</dl><p class="shared-path">${escape(item.path)}</p><div class="shared-link-value" ${canCopy?'':'hidden'}><label>Share link<input readonly value="${escape(shareCapabilities.get(item.share_id)||'')}" aria-label="Share link"></label></div><div class="shared-footer"><p>This link opens only this note. Linked notes and resources remain unavailable.</p><div class="row-actions"><button data-edit>Policy</button><button class="danger" data-revoke>Revoke</button></div></div></div></article>`;
    }).join(''):'<p class="empty">No matching shared notes on this page.</p>';
    $('[data-previous]',root).disabled=!offset;$('[data-next]',root).disabled=records.length<100;
  }
  async function refresh(){
    records=await api('/api/v1/shares?limit=100&offset='+offset);
    if(!records.length&&offset){offset=Math.max(0,offset-100);records=await api('/api/v1/shares?limit=100&offset='+offset);}
    if(root.isConnected)render();
  }
  wireSearch($('.search-box',root),value=>{query=value;render();});
  bind(root,'click','[data-sort]',(e,b)=>{direction=sorting===b.dataset.sort?-direction:b.dataset.sort==='name'?1:-1;sorting=b.dataset.sort;render();});
  let paging=false;
  async function turnPage(delta){if(paging)return;paging=true;const previous=offset;for(const control of root.querySelectorAll('[data-previous],[data-next]')){control.disabled=true;control.setAttribute('aria-busy','true');}try{offset=Math.max(0,offset+delta);await refresh();}catch(error){offset=previous;throw error;}finally{paging=false;for(const control of root.querySelectorAll('[data-previous],[data-next]'))control.removeAttribute('aria-busy');$('[data-previous]',root).disabled=!offset;$('[data-next]',root).disabled=records.length<100;}}
  bind(root,'click','[data-previous]',()=>turnPage(-100));
  bind(root,'click','[data-next]',()=>turnPage(100));
  bind(root,'click','[data-expand]',(e,b)=>{
    const item=b.closest('[data-share]'),id=item.dataset.share,open=!expanded.has(id);
    if(open)expanded.add(id);else expanded.delete(id);
    item.classList.toggle('expanded',open);b.setAttribute('aria-expanded',String(open));$('.shared-details',item).hidden=!open;
  });
  function copyPromise(result,event){
    if(!event.isTrusted||!window.isSecureContext||!document.hasFocus()||!navigator.clipboard)return Promise.resolve(false);
    try{if(navigator.clipboard.write&&typeof ClipboardItem!=='undefined')return navigator.clipboard.write([new ClipboardItem({'text/plain':result.then(value=>new Blob([value.url],{type:'text/plain'}))})]).then(()=>true,()=>false);}catch{}
    return Promise.resolve(false);
  }
  bind(root,'click','[data-copy]',async(event,button)=>{
    const id=button.closest('[data-share]').dataset.share;
    await pending(button,async()=>{const result=api('/api/v1/shares/'+id+'/link');const copied=copyPromise(result,event);const {url}=await result;shareCapabilities.set(id,url);const success=await copied;
      if(!success){expanded.add(id);render();const field=$(`[data-share="${id}"] .shared-link-value input`,root);field.focus();field.select();}
      notice(success?'Share link copied to the clipboard.':'Clipboard unavailable. Select and copy the Share link.',!success);
    });
  });
  bind(root,'click','[data-revoke]',(e,b)=>{
    const id=b.closest('[data-share]').dataset.share,item=records.find(value=>value.share_id===id);
    confirmation('Revoke Share',`Revoke the link for ${item.path}? This link and all its visitor sessions will stop working, and it will disappear from Shared. The note remains in the Vault. This action cannot be undone.`,async()=>{
      await api('/api/v1/shares/'+id,{method:'PATCH',body:{revoke:true}});shareCapabilities.delete(id);expanded.delete(id);await refresh();notice('Share revoked and removed from Shared.');
    },'Revoke Share');
  });
  async function edit(item){
    const creating=!item,modal=dialog(creating?'Create Share':'Share — '+item.path.split('/').at(-1),`<form class="share-form"><p>Share this note. Expiry and password are optional.</p>${creating?'<label>Note path<input name="path" required placeholder="Folder/Note.md" list="share-notes"><datalist id="share-notes"></datalist></label>':''}<label>Access<select name="permission" aria-label="Access"><option value="view">View</option><option value="edit">Edit</option></select></label><label>Expires<input name="expires" type="datetime-local" aria-label="Expires"></label><label>Password<input name="password" type="password" autocomplete="new-password" placeholder="${creating?'Off':'Leave empty to keep current password'}"></label>${item?.password_required?'<label class="inline"><input type="checkbox" name="remove_password">Remove password</label>':''}<div class="dialog-footer"><button type="button" data-cancel>Cancel</button><button type="submit">${creating?'Create share':'Apply policy'}</button></div></form>`);
    const form=$('form',modal.element);$('[data-cancel]',form).onclick=()=>modal.close();
    if(item){form.elements.permission.value=item.permission;if(item.expires_at){const date=new Date(item.expires_at*1000);form.elements.expires.value=new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16);}}
    if(creating){form.elements.path.oninput=()=>{$('#dialog-title',modal.element).textContent=form.elements.path.value?'Share — '+form.elements.path.value.split('/').at(-1):'Create Share';};api('/api/notes?limit=500').then(notes=>{if(modal.element.isConnected)$('#share-notes',modal.element).innerHTML=notes.map(note=>`<option value="${escape(note.path)}"></option>`).join('');}).catch(()=>{if(modal.element.isConnected)modal.error.textContent='Suggestions unavailable. Enter the exact note path.';});}
    form.onsubmit=async event=>{event.preventDefault();await pending($('button[type=submit]',form),async()=>{
      modal.setBusy(true);try{
        const data={permission:form.elements.permission.value};if(creating)data.path=form.elements.path.value;
        if(creating||form.elements.expires.value!==form.elements.expires.defaultValue)data.expires_at=form.elements.expires.value?new Date(form.elements.expires.value).getTime()/1000:null;
        if(creating||form.elements.password.value)data.password=form.elements.password.value||null;if(form.elements.remove_password?.checked)data.password=null;
        const request=api('/api/v1/shares'+(creating?'':'/'+item.share_id),{method:creating?'POST':'PATCH',body:data});
        const copying=creating?copyPromise(request,event):null;const result=await request;
        let copied=false;if(creating){shareCapabilities.set(result.share_id,result.url);copied=await copying;if(!copied)expanded.add(result.share_id);}
        modal.close(true);await refresh();
        notice(creating?(copied?'Share created and copied to the clipboard.':'Share created. Clipboard unavailable: use Copy link or select the link in its details.'):'Share policy updated.',creating&&!copied);
      }catch(error){modal.error.textContent=error.message;}finally{modal.setBusy(false);}
    });};
    form.elements.expires.defaultValue=form.elements.expires.value;
  }
  bind(root,'click','[data-create]',()=>edit(null));bind(root,'click','[data-edit]',(e,b)=>edit(records.find(item=>item.share_id===b.closest('[data-share]').dataset.share)));
  await refresh();return()=>{};
}
