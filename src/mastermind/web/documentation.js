import {$,$$,api,escape,search,wireSearch} from './ui.js';

export async function documentation(root){
  const articles=await api('/api/owner/documentation');
  if(!root.isConnected)return()=>{};
  document.documentElement.classList.add('documentation-open');
  root.classList.add('documentation-container');
  root.innerHTML=`<div class="docs"><nav class="docs-nav" aria-label="Documentation navigation" tabindex="0">${search('Search documentation','Find topic')}<div data-articles></div></nav><article class="article" aria-label="Operator guide" tabindex="0"></article></div>`;
  const nav=$('.docs-nav',root),content=$('.article',root),destinations=$('[data-articles]',root);
  let matches=[],frame=0,closed=false;
  const searchable=articles.map(item=>{
    const body=document.createElement('div');body.innerHTML=item.html;
    return {item,text:[item.title,item.summary,...item.keywords,body.textContent].join(' ').toLocaleLowerCase()};
  });
  function currentSection(){
    if(closed||!matches.length)return;
    const sections=$$('.doc-section',content),line=content.getBoundingClientRect().top+30;
    let current=sections[0];
    for(const section of sections)if(section.getBoundingClientRect().top<=line+1)current=section;
    const maximum=content.scrollHeight-content.clientHeight;
    if(maximum>1&&content.scrollTop>=maximum-1)current=sections.at(-1);
    for(const link of $$('[data-article]',nav)){
      const active=link.dataset.article===current.dataset.topic;
      link.classList.toggle('active',active);
      if(active)link.setAttribute('aria-current','location');else link.removeAttribute('aria-current');
    }
  }
  function schedule(){cancelAnimationFrame(frame);frame=requestAnimationFrame(currentSection);}
  function filter(query){
    const needle=query.trim().toLocaleLowerCase(),navTop=nav.scrollTop;
    matches=searchable.filter(entry=>entry.text.includes(needle)).map(entry=>entry.item);
    content.scrollTop=0;
    const groups=[...new Set(matches.map(item=>item.group))];
    destinations.innerHTML=groups.map(group=>`<section class="docs-group"><h2>${escape(group)}</h2>${matches.filter(item=>item.group===group).map(item=>`<a href="#${item.id}" data-article="${item.id}" aria-controls="doc-${item.id}">${escape(item.title)}</a>`).join('')}</section>`).join('');
    content.innerHTML=`<header class="guide-header"><p class="guide-kicker">Mastermind · ${escape(articles[0].version)} · Operator guide</p><h2>Using Mastermind</h2><p>Manage your knowledge base, submit sources and operate the service. Search this guide or choose a topic to move through it.</p></header>${matches.length?matches.map(item=>`<section class="doc-section" id="doc-${item.id}" data-topic="${item.id}" aria-labelledby="heading-${item.id}"><h3 id="heading-${item.id}" tabindex="-1">${escape(item.title)}</h3><p class="doc-summary">${escape(item.summary)}</p>${item.html}</section>`).join(''):'<p class="docs-empty" role="status">No matching articles. Try another term or clear the search.</p>'}`;
    for(const table of $$('table',content)){const wrapper=document.createElement('div');wrapper.className='doc-table';wrapper.tabIndex=0;table.before(wrapper);wrapper.append(table);}
    nav.scrollTop=navTop;content.scrollTop=0;currentSection();schedule();
  }
  function jump(id,animate=true){
    const section=$$('.doc-section',content).find(item=>item.dataset.topic===id);
    if(!section)return;
    const top=section.getBoundingClientRect().top-content.getBoundingClientRect().top+content.scrollTop-30;
    content.scrollTo({top:Math.max(0,top),behavior:animate&&!matchMedia('(prefers-reduced-motion: reduce)').matches?'smooth':'instant'});
    currentSection();
  }
  wireSearch($('.search-box',nav),filter);
  nav.addEventListener('click',event=>{
    const link=event.target.closest('[data-article]');if(!link)return;
    event.preventDefault();jump(link.dataset.article);
  });
  content.addEventListener('scroll',schedule,{passive:true});
  const observer=new ResizeObserver(schedule);observer.observe(content);
  filter('');
  if(location.hash)jump(location.hash.slice(1),false);
  document.fonts.ready.then(schedule);
  return()=>{closed=true;observer.disconnect();cancelAnimationFrame(frame);document.documentElement.classList.remove('documentation-open');};
}
