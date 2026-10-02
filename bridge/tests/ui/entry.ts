import {installCommands} from '../../src/commands';
import {RelatedNotesView} from '../../src/related';
import {ResourceCard} from '../../src/resources';
import {TFile} from 'obsidian';

// The production UI is exercised with in-memory service responses. Never load
// a real Vault, credentials, or Chronos/Saturn data in this fixture.
const host=window as any;
const calls:any[]=[],commands:any[]=[];
const file=Object.assign(new TFile(),{path:'Notes/Example.md',extension:'md'});
let pendingResolve:(value:unknown)=>void;
const bridge:any={portable:true,app:{workspace:{getActiveFile:()=>file},vault:{getFileByPath:()=>file}},
  addCommand:(command:any)=>commands.push(command),
  core:async(route:string,data:any)=>{
    calls.push({route,data});
    if(route==='/path-version')return {sha256:'fixture-version'};
    if(host.failRequest)throw new Error('Fixture request failed');
    if(host.holdRequest)return new Promise(resolve=>{pendingResolve=resolve;});
    return {};
  }};
installCommands(bridge);
const related=new RelatedNotesView({app:bridge.app} as any,bridge);
await related.onOpen();
const items=[{title:'Двигатели и приводы — a long related note title',path:'root/'+('Длинная папка/').repeat(8)+'Двигатели.md',
  excerpt:'An evidence excerpt that remains legible while recommendations update. '.repeat(8),reason:'Shared topic: propulsion'}];
host.fixture={calls,commands,related,items,
  open:(action:string)=>{const command=commands.find(item=>item.id===action+'-note');
    if(command.callback)command.callback();else command.checkCallback(false);},
  resolve:()=>{host.holdRequest=false;pendingResolve?.({});},
  render:(phase='ready')=>(related as any).render({phase,query:{path:'root/Example.md'},items}),
  resource:async(kind:string,scenario='loaded')=>{
    const container=document.querySelector('#resource') as HTMLElement;container.empty();container.addClass('mastermind-resource');
    let fail=scenario==='retry';
    const card=new ResourceCard(container,{core:async(route:string,data:any)=>{
      calls.push({route,data});if(fail){fail=false;throw new Error('Fixture unavailable');}
      if(route.startsWith('/resources?'))return {entries:[{path:'root/folder/file.txt',name:'A long resource filename '.repeat(4),type:'file',size_bytes:5}],
        next_cursor:route.includes('cursor=')?null:'next'};
      return kind==='chronos'?{kind,started_at:'2026-10-01T10:00:00Z',ended_at:null}:
        {kind,type:scenario==='folder'?'folder':'file',name:'Resource',size_bytes:8};
    },media:{issue:()=>({url:'about:blank',revoke:()=>{}})},app:bridge.app} as any,kind,'root/folder');
    host.resourceCard?.onunload();host.resourceCard=card;await card.refresh();return card.state;
  }};
host.fixture.render();
document.querySelector('#reference')!.innerHTML='<span class="mastermind-reference">@Example</span> <span class="mastermind-reference is-unresolved">@Missing</span>';
