export const state={session:null,prefs:null,route:'dashboard',viewController:null};
export const $=(query,root=document)=>root.querySelector(query);
export const $$=(query,root=document)=>[...root.querySelectorAll(query)];
export const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const humanBytes=n=>n==null?'Unknown':n>=1073741824?(n/1073741824).toFixed(1)+' GiB':n>=1048576?(n/1048576).toFixed(1)+' MiB':n.toLocaleString()+' B';
export const stamp=n=>n?new Date(n*1000).toLocaleString():'Never verified';
export const duration=n=>`${Math.floor(n/86400)}d ${Math.floor(n%86400/3600)}h ${Math.floor(n%3600/60)}m ${Math.floor(n%60)}s`;
export function notice(message,error=false){const node=document.createElement('div');node.className='notice'+(error?' error':'');node.textContent=message;$('#notices').replaceChildren(node);setTimeout(()=>node.remove(),7000);}
export async function api(route,{method='GET',body,headers={},signal=state.viewController?.signal,allow401=false}={}){
  const response=await fetch(route,{method,credentials:'same-origin',signal,headers:{...(body!==undefined?{'Content-Type':'application/json'}:{}),
    ...(state.session&&method!=='GET'?{'X-CSRF-Token':state.session.csrf}:{}),...headers},...(body!==undefined?{body:JSON.stringify(body)}:{})});
  const data=await response.json();if(!response.ok){const error=new Error(data.error?.message||'Request could not be completed.');error.code=data.error?.code;error.status=response.status;
    if(response.status===401&&state.session&&!allow401){state.session=null;document.dispatchEvent(new Event('session-expired'));}throw error;}return data;
}
export function bind(root,event,selector,handler){const listener=async e=>{const target=e.target.closest(selector);if(!target||!root.contains(target))return;
  try{await handler(e,target);}catch(error){if(error.name!=='AbortError')notice(error.message,true);}};root.addEventListener(event,listener);return()=>root.removeEventListener(event,listener);}
export async function pending(button,action){if(button.disabled)return;const label=button.textContent,width=button.style.width;button.style.width=button.offsetWidth+'px';button.disabled=true;button.setAttribute('aria-busy','true');button.textContent='Working…';try{return await action();}finally{button.textContent=label;button.style.width=width;button.disabled=false;button.removeAttribute('aria-busy');}}
export function search(label='Search',placeholder=''){return `<label class="search-box"><span class="sr-only">${escape(label)}</span><input type="search" placeholder="${escape(placeholder||label)}" aria-label="${escape(label)}"><button type="button" class="clear" aria-label="Clear search" hidden>×</button></label>`;}
export function wireSearch(root,handler){const input=$('input[type=search]',root),clear=$('.clear',root);const update=()=>{clear.hidden=!input.value;handler(input.value);};input.addEventListener('input',update);clear.addEventListener('click',()=>{input.value='';update();input.focus();});input.addEventListener('keydown',e=>{if(e.key==='Escape'&&input.value){e.stopPropagation();input.value='';update();}});return input;}
export function card(id,title,body,{wide=false,quarter=false}={}){return `<section class="card${wide?' wide':''}${quarter?' quarter':''}" data-card="${id}"><header class="card-header"><span class="ordinal"></span><h2>${escape(title)}</h2></header>${handle(title)}<div class="card-body">${body}</div></section>`;}
export function handle(label){return `<button type="button" class="drag" draggable="true" aria-label="Reorder ${escape(label)}" title="Drag, or use Alt + Arrow Up / Down"><span class="dots" aria-hidden="true"><i></i><i></i><i></i><i></i></span></button>`;}
export async function preferences(change){function apply(result){state.prefs=result;document.documentElement.style.setProperty('--accent',result.accent);document.dispatchEvent(new Event('preferences-changed'));return result;}try{return apply(await api('/api/owner/settings',{method:'PATCH',body:{revision:state.prefs.revision,...change}}));}catch(error){if(error.code==='SETTINGS_CONFLICT')apply(await api('/api/owner/settings'));throw error;}}
export function reorder(root,key,selector='[data-card]'){
  const attr=selector==='[data-nav]'?'nav':'card';let dragged=null;
  const items=()=>$$(selector,root);function apply(order){for(const id of order){const node=items().find(item=>item.dataset[attr]===id);if(node)root.append(node);}items().forEach((item,index)=>{const n=$('.ordinal',item);if(n)n.textContent=String(index+1).padStart(2,'0');});}
  apply(state.prefs.orders[key]);
  async function persist(order,focus){try{await preferences({orders:{[key]:order}});apply(order);notice(`Order saved. ${focus} is item ${order.indexOf(focus)+1}.`);}catch(error){apply(state.prefs.orders[key]);throw error;}}
  bind(root,'keydown','.drag',async(e,target)=>{if(!e.altKey||!['ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();const row=target.closest(selector),id=row.dataset[attr],order=items().map(item=>item.dataset[attr]),index=order.indexOf(id),next=index+(e.key==='ArrowUp'?-1:1);if(next<0||next>=order.length)return;[order[index],order[next]]=[order[next],order[index]];await persist(order,id);target.focus();});
  root.addEventListener('dragstart',e=>{const h=e.target.closest('.drag');if(!h)return;dragged=h.closest(selector);e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',dragged.dataset[attr]);});
  root.addEventListener('dragover',e=>{const item=e.target.closest(selector);if(!dragged||!item||dragged===item)return;e.preventDefault();items().forEach(node=>delete node.dataset.drop);const b=item.getBoundingClientRect();item.dataset.drop=e.clientY<b.y+b.height/2?'before':'after';});
  bind(root,'drop',selector,async(e,target)=>{e.preventDefault();if(!dragged||target===dragged)return;const id=dragged.dataset[attr],order=items().map(item=>item.dataset[attr]).filter(v=>v!==id),at=order.indexOf(target.dataset[attr]);order.splice(at+(target.dataset.drop==='after'?1:0),0,id);items().forEach(node=>delete node.dataset.drop);dragged=null;await persist(order,id);});
  root.addEventListener('dragend',()=>{dragged=null;items().forEach(node=>delete node.dataset.drop);});
}
let activeDialog=null;
export function closeDialogs(){activeDialog?.close(true);}
export function dialog(title,body,{onClose=()=>{},dirtyGuard=true}={}){
  closeDialogs();
  const previous=document.activeElement,overlay=document.createElement('div');overlay.className='overlay';overlay.innerHTML=`<section class="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title"><header class="dialog-header"><h2 id="dialog-title">${escape(title)}</h2><button type="button" aria-label="Close dialog">×</button></header><div class="dialog-body">${body}<p class="error-message" role="alert"></p></div></section>`;
  $('#overlay-root').replaceChildren(overlay);$('#app').inert=true;const panel=$('.dialog',overlay),error=$('.error-message',overlay);let dirty=false,busy=false,closed=false;panel.addEventListener('input',()=>dirty=true);
  function close(force=false){if(closed)return;if(busy&&!force){error.textContent='This step is still running. Its status will be available in Settings.';return;}
    if(dirty&&dirtyGuard&&!force){error.textContent='This form contains unsaved input.';if(!$('.discard',panel)){const discard=document.createElement('button');discard.className='discard danger';discard.textContent='Discard input and close';discard.onclick=()=>close(true);error.after(discard);}return;}
    closed=true;overlay.remove();window.removeEventListener('resize',clamp);$('#app').inert=false;activeDialog=null;onClose();if(previous?.isConnected)previous.focus();}
  $('.dialog-header button',panel).onclick=()=>close();overlay.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close();}if(e.key==='Tab'){const controls=$$('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex="0"]',panel).filter(n=>n.getClientRects().length);if(!controls.length){e.preventDefault();return;}const first=controls[0],last=controls.at(-1);if(e.shiftKey&&document.activeElement===first){last.focus();e.preventDefault();}else if(!e.shiftKey&&document.activeElement===last){first.focus();e.preventDefault();}}});
  const header=$('.dialog-header',panel);let drag=null;header.addEventListener('pointerdown',e=>{if(e.target.closest('button'))return;const b=panel.getBoundingClientRect();drag={x:e.clientX,y:e.clientY,left:b.left,top:b.top};header.setPointerCapture(e.pointerId);});header.addEventListener('pointermove',e=>{if(!drag)return;panel.style.position='fixed';panel.style.margin='0';panel.style.left=Math.max(8,Math.min(innerWidth-panel.offsetWidth-8,drag.left+e.clientX-drag.x))+'px';panel.style.top=Math.max(8,Math.min(innerHeight-panel.offsetHeight-8,drag.top+e.clientY-drag.y))+'px';});header.addEventListener('pointerup',()=>drag=null);header.addEventListener('pointercancel',()=>drag=null);
  function clamp(){if(panel.style.position!=='fixed')return;const b=panel.getBoundingClientRect();panel.style.left=Math.max(8,Math.min(innerWidth-panel.offsetWidth-8,b.left))+'px';panel.style.top=Math.max(8,Math.min(innerHeight-panel.offsetHeight-8,b.top))+'px';}
  window.addEventListener('resize',clamp);
  requestAnimationFrame(()=>{if(panel.isConnected)($('input:not([disabled]),textarea:not([disabled]),select:not([disabled])',panel)||$('.dialog-header button',panel)).focus();});
  activeDialog={element:panel,error,close,setBusy:value=>{busy=value;},setClean:()=>dirty=false};return activeDialog;
}
export function confirmation(title,description,action,buttonText='Confirm'){
  const modal=dialog(title,`<p>${escape(description)}</p><div class="dialog-footer"><button type="button" data-cancel>Cancel</button><button type="button" data-confirm class="danger">${escape(buttonText)}</button></div>`,{dirtyGuard:false});
  $('[data-cancel]',modal.element).onclick=()=>modal.close();$('[data-confirm]',modal.element).onclick=async e=>{await pending(e.target,async()=>{modal.setBusy(true);try{await action();modal.close(true);}catch(error){modal.error.textContent=error.message;}finally{modal.setBusy(false);}});};return modal;
}
export function copyDialog(title,value,description='Keep this value. It will not be shown again after this session.'){
  const modal=dialog(title,`<p>${escape(description)}</p><div class="copy-value" tabindex="0">${escape(value)}</div><button type="button" data-copy>Copy</button>`,{dirtyGuard:false});
  $('[data-copy]',modal.element).onclick=async e=>{if(!e.isTrusted||!document.hasFocus())return;try{if(!navigator.clipboard||!window.isSecureContext)throw Error();await navigator.clipboard.writeText(value);modal.error.textContent='';notice('Copied.');}catch{modal.error.textContent='Clipboard is unavailable. Select the complete value above and copy it manually.';$('.copy-value',modal.element).focus();}};return modal;
}
export function download(url){const anchor=document.createElement('a');anchor.href=url;anchor.download='';document.body.append(anchor);anchor.click();anchor.remove();}
export function poll(action,interval=3000){let stopped=false,timer;async function tick(){if(stopped)return;try{if(!document.hidden)await action();}catch(error){if(error.name!=='AbortError')notice(error.message,true);}if(!stopped)timer=setTimeout(tick,interval);}tick();return()=>{stopped=true;clearTimeout(timer);};}
// Textarea display normalizes CRLF. Preserve the exact clipboard value separately;
// incremental keyboard edits map display offsets back into the original opaque string.
export function opaqueInput(input){let raw='',display='';const normalize=value=>value.replace(/\r\n?/g,'\n');
  function offset(index){let r=0,d=0;while(r<raw.length&&d<index){r+=raw[r]==='\r'&&raw[r+1]==='\n'?2:1;d++;}return r;}
  input.addEventListener('paste',e=>{const value=e.clipboardData?.getData('text/plain');if(value===undefined)return;e.preventDefault();const start=input.selectionStart,end=input.selectionEnd;raw=raw.slice(0,offset(start))+value+raw.slice(offset(end));display=normalize(raw);input.value=display;const caret=start+normalize(value).length;input.setSelectionRange(caret,caret);input.dispatchEvent(new Event('input',{bubbles:true}));});
  input.addEventListener('input',()=>{const next=input.value;if(next===display)return;let first=0;while(first<display.length&&first<next.length&&display[first]===next[first])first++;let tail=0;while(tail<display.length-first&&tail<next.length-first&&display[display.length-1-tail]===next[next.length-1-tail])tail++;raw=raw.slice(0,offset(first))+next.slice(first,next.length-tail)+raw.slice(offset(display.length-tail));display=next;});
  return {value:()=>raw,reset:()=>{raw=display=input.value='';}};
}

// The same absolute growth in both dimensions; offsets exclude transforms.
function growth(event){const target=event.target.closest?.('button,.nav-row,.hoverable');if(!target||target.matches('.drag,.day,.clear,.edge-toggle')||target.closest('.nav-bottom,.dialog-header'))return;const node=target.closest('.nav-row')||target,w=node.offsetWidth,h=node.offsetHeight;if(!w||!h)return;const g=Math.min(w,h)*.05;node.style.setProperty('--grow-x',(w+g)/w);node.style.setProperty('--grow-y',(h+g)/h);const b=node.getBoundingClientRect(),p=node.parentElement.getBoundingClientRect();node.style.transformOrigin=(Math.abs(b.left-p.left)<4?'left':Math.abs(b.right-p.right)<4?'right':'center')+' center';node.classList.add('hover-scale');}
document.addEventListener('pointerover',growth);document.addEventListener('focusin',growth);
