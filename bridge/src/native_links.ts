import {apiVersion, CachedMetadata, Component, LinkCache, Notice, setIcon, TFile, WorkspaceLeaf} from "obsidian";
import type MastermindBridge from "./main";
import {parse, Ref} from "./portable_parser";

type Dictionary = {current: Record<string,string>; history: string[]; saturn: string[]};
type Entry = {links: LinkCache[]; native: CachedMetadata; combined: CachedMetadata};
type NativeCache = MastermindBridge["app"]["metadataCache"] & {resolveLinks(path:string):void};
const PREFIX = "mastermind-resource:";

export function resourceLink(ref: Pick<Ref,"kind"|"target">): string {
  // Encode delimiters used by Obsidian, and keep .md from being stripped by its resolver.
  return PREFIX + ref.kind + ":" + encodeURIComponent(ref.target) + ":resource";
}

export function resourceReference(link: string): Ref | undefined {
  const match = /^mastermind-resource:(chronos|saturn):(.*):resource$/.exec(link);
  if (!match) return;
  try {
    const target = decodeURIComponent(match[2]);
    if (!target || target.length > 4096) return;
    return {start:0,end:0,kind:match[1],target,display:"@"+match[1]+": "+target,exists:true};
  } catch {return;}
}

export function nativeReferences(text:string, refs:Ref[]): LinkCache[] {
  const offsets=[0];
  for(const character of text)offsets.push(offsets[offsets.length-1]+character.length);
  const lines=[0];for(let i=0;i<text.length;i++)if(text[i]==="\n")lines.push(i+1);
  const point=(offset:number)=>{
    let low=0,high=lines.length;
    while(low+1<high){const middle=(low+high)>>>1;if(lines[middle]<=offset)low=middle;else high=middle;}
    return{offset,line:low,col:offset-lines[low]};
  };
  return refs.filter(ref=>text[offsets[ref.start]]==="@").map(ref=>({
    link:ref.kind==="internal"?ref.display:resourceLink(ref),
    original:text.slice(offsets[ref.start],offsets[ref.end]),displayText:ref.display,
    position:{start:point(offsets[ref.start]),end:point(offsets[ref.end])}
  }));
}

/** Ephemeral augmentation of native link reads. Never writes synthetic links/files or raw caches. */
export class NativeLinks extends Component {
  private cache:NativeCache;
  private originalGet:NativeCache["getCache"];
  private entries=new Map<string,Entry>();
  private pending=new Set<string>();
  private dictionary?:Dictionary;
  private dictionaryStamp="";
  private dictionaryLoading=false;
  private dictionaryDirty=true;
  private revision=0;
  private running=false;
  private stopped=false;
  private flushTimer?:ReturnType<typeof setTimeout>;
  private viewTimer?:ReturnType<typeof setTimeout>;
  private graphLeaves=new WeakSet<WorkspaceLeaf>();
  private observed=new WeakSet<HTMLElement>();
  private patchedNodePrototypes=new WeakSet<object>();
  ready=false;
  failure="";
  parsed=0;
  parseMs=0;
  dictionaryRequests=0;

  constructor(private bridge:MastermindBridge){
    super();this.cache=bridge.app.metadataCache as NativeCache;this.originalGet=this.cache.getCache;
  }

  onload(){
    // These native internals were qualified on the exact bundled version. Do not guess on upgrades.
    if(apiVersion!=="1.13.7"||typeof this.cache.resolveLinks!=="function"){
      this.failure="Native reference integration requires qualified Obsidian 1.13.7";
      new Notice(this.failure);return;
    }
    const cache=this.cache,self=this;
    const get:NativeCache["getCache"]=function(this:NativeCache,path){
      const native=self.originalGet.call(this,path),entry=self.entries.get(path);
      // A new native cache invalidates old offsets immediately, before asynchronous reindexing.
      return native&&entry?.native===native?entry.combined:native;
    };
    cache.getCache=get;
    this.register(()=>{if(cache.getCache===get)cache.getCache=this.originalGet;});
    const resolve=cache.getFirstLinkpathDest;
    const resolveReference:typeof resolve=function(this:NativeCache,link,source){
      return resourceReference(link)?null:resolve.call(this,link,source);
    };
    cache.getFirstLinkpathDest=resolveReference;
    this.register(()=>{if(cache.getFirstLinkpathDest===resolveReference)cache.getFirstLinkpathDest=resolve;});
    const workspace=this.bridge.app.workspace,open=workspace.openLinkText;
    const openReference:typeof open=function(this:typeof workspace,link,source,...options){
      const ref=resourceReference(link);
      if(ref)return self.bridge.openReference(ref,source);
      return open.call(this,link,source,...options);
    };
    workspace.openLinkText=openReference;
    this.register(()=>{if(workspace.openLinkText===openReference)workspace.openLinkText=open;});
    this.registerEvent(cache.on("changed",file=>this.enqueue(file.path)));
    const changed=()=>{this.dictionaryDirty=true;this.revision++;void this.loadDictionary();};
    this.registerEvent(this.bridge.app.vault.on("create",file=>{if(file instanceof TFile&&file.extension==="md")changed();}));
    this.registerEvent(this.bridge.app.vault.on("delete",file=>{
      this.entries.delete(file.path);this.pending.delete(file.path);
      if(file instanceof TFile&&file.extension==="md")changed();
    }));
    this.registerEvent(this.bridge.app.vault.on("rename",(file,oldPath)=>{
      for(const path of this.entries.keys())if(path===oldPath||path.startsWith(oldPath+"/"))this.entries.delete(path);
      changed();
    }));
    this.registerEvent(workspace.on("layout-change",()=>this.scheduleViews()));
    this.registerInterval(window.setInterval(()=>void this.loadDictionary(),10000));
    workspace.onLayoutReady(()=>{if(!this.stopped){void this.loadDictionary();this.scheduleViews();}});
  }

  private async loadDictionary(){
    if(this.stopped||this.dictionaryLoading)return;
    this.dictionaryLoading=true;
    try{
      this.dictionaryRequests++;
      const dictionary=await this.bridge.core<Dictionary>("/reference-dictionary");
      if(this.stopped)return;
      const stamp=JSON.stringify(dictionary);
      if(this.dictionaryDirty||stamp!==this.dictionaryStamp){
        this.dictionaryDirty=false;this.dictionaryStamp=stamp;this.dictionary=dictionary;this.revision++;
        for(const file of this.bridge.app.vault.getMarkdownFiles())this.pending.add(file.path);
        this.schedule();
      }
      this.failure="";
    }catch{this.failure="Reference dictionary unavailable";}
    finally{this.dictionaryLoading=false;}
  }

  private enqueue(path:string){this.pending.add(path);this.schedule();}
  private schedule(){
    if(this.stopped||this.flushTimer||this.running||!this.dictionary)return;
    this.flushTimer=setTimeout(()=>{this.flushTimer=undefined;void this.flush();},100);
  }

  private async flush(){
    if(this.stopped||!this.dictionary)return;
    this.running=true;
    try{
      let turn=performance.now();
      while(this.pending.size&&!this.stopped){
        const path=this.pending.values().next().value!;this.pending.delete(path);
        const file=this.bridge.app.vault.getFileByPath(path),native=this.originalGet.call(this.cache,path);
        if(!file||file.extension!=="md"||!native){this.entries.delete(path);continue;}
        const revision=this.revision,stamp=file.stat.mtime+":"+file.stat.size;
        try{
          if(file.stat.size>8*1024**2)throw new Error("Reference note size limit");
          const text=await this.bridge.app.vault.cachedRead(file);
          if(this.stopped)return;
          if(revision!==this.revision||native!==this.originalGet.call(this.cache,path)||stamp!==file.stat.mtime+":"+file.stat.size){
            this.pending.add(path);continue;
          }
          const started=performance.now(),{current,history,saturn}=this.dictionary;
          const links=text.includes("@")?nativeReferences(text,parse(text,current,history,saturn)):[];
          this.parseMs+=performance.now()-started;this.parsed++;
          const previous=this.entries.get(path);
          if(links.length)this.entries.set(path,{links,native,combined:{...native,links:[...(native.links||[]),...links]}});
          else this.entries.delete(path);
          if(links.length||previous){this.cache.resolveLinks(path);this.cache.trigger("resolve",file);}
        }catch{this.entries.delete(path);this.failure="A note could not be indexed";}
        if(performance.now()-turn>12){await new Promise(resolve=>setTimeout(resolve,0));turn=performance.now();}
      }
      this.ready=true;this.scheduleViews();
    }finally{this.running=false;this.schedule();}
  }

  private scheduleViews(){
    if(this.stopped||this.viewTimer)return;
    this.viewTimer=setTimeout(()=>{this.viewTimer=undefined;this.updateViews();},100);
  }

  private updateViews(){
    this.bridge.app.workspace.iterateAllLeaves(leaf=>{
      const view=leaf.view as typeof leaf.view & {renderer?:any;engine?:any;dataEngine?:any;contentEl:HTMLElement};
      const engine=view.engine||view.dataEngine;
      if(["graph","localgraph"].includes(view.getViewType())&&view.renderer&&engine){
        if(!this.graphLeaves.has(leaf)){
          this.graphLeaves.add(leaf);
          const renderer=view.renderer,original=renderer.setData,self=this;
          const setData=function(this:any,...args:any[]){
            const result=original.apply(this,args);self.labelNodes(this);return result;
          };
          renderer.setData=setData;
          this.register(()=>{if(renderer.setData===setData)renderer.setData=original;});
        }
        this.labelNodes(view.renderer);engine.render();
      }
      if(view.getViewType()==="outgoing-link"){
        const element=view.contentEl;
        if(!this.observed.has(element)){
          this.observed.add(element);
          const observer=new MutationObserver(()=>this.labelOutgoing(element));
          observer.observe(element,{childList:true,subtree:true});this.register(()=>observer.disconnect());
        }
        this.labelOutgoing(element);
      }
    });
  }

  private labelNodes(renderer:any){
    for(const node of renderer.nodes||[]){
      const ref=resourceReference(node.id);
      if(!ref)continue;
      const prototype=Object.getPrototypeOf(node);
      if(!this.patchedNodePrototypes.has(prototype)){
        this.patchedNodePrototypes.add(prototype);
        const original=prototype.getDisplayText;
        const display=function(this:any){return resourceReference(this.id)?.display||original.call(this);};
        prototype.getDisplayText=display;
        this.register(()=>{if(prototype.getDisplayText===display)prototype.getDisplayText=original;});
      }
      if(node.text)node.text.text=ref.display;
    }
  }

  private labelOutgoing(element:HTMLElement){
    for(const label of element.querySelectorAll<HTMLElement>(".outgoing-link-item .tree-item-inner-text")){
      const ref=resourceReference(label.textContent||"");if(!ref)continue;
      label.setText(ref.display);
      const row=label.closest<HTMLElement>(".outgoing-link-item")!;
      row.setAttribute("aria-label",ref.display);row.title=ref.display;
      const icon=row.querySelector<HTMLElement>(".tree-item-icon");if(icon)setIcon(icon,ref.kind==="chronos"?"clock":"file-box");
    }
  }

  diagnostics(){return{ready:this.ready,failure:this.failure,notes:this.entries.size,pending:this.pending.size,
    parsed:this.parsed,parse_ms:this.parseMs,dictionary_requests:this.dictionaryRequests};}

  onunload(){
    this.stopped=true;this.revision++;this.ready=false;
    if(this.flushTimer)clearTimeout(this.flushTimer);if(this.viewTimer)clearTimeout(this.viewTimer);
    // Component restores methods after onunload. Empty projection now makes the remaining reads native.
    const paths=[...this.entries.keys()];this.entries.clear();this.pending.clear();
    for(const path of paths){const file=this.bridge.app.vault.getFileByPath(path);
      if(file){this.cache.resolveLinks(path);this.cache.trigger("resolve",file);}}
  }
}
