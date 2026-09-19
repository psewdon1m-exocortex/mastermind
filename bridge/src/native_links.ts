import {apiVersion, CachedMetadata, Component, LinkCache, Menu, Notice, setIcon, TFile, WorkspaceLeaf} from "obsidian";
import type MastermindBridge from "./main";
import {parse} from "./portable_parser";
import {nativeReferences, resourceReference} from "./native_projection";

type Dictionary = {current: Record<string,string>; history: string[]; saturn: string[]};
type Entry = {links: LinkCache[]; native: CachedMetadata; combined: CachedMetadata};
type NativeCache = MastermindBridge["app"]["metadataCache"] & {
  resolveLinks(path:string):void;
  getBacklinksForFile(file:TFile):{add(path:string,link:LinkCache):void};
};
type NativeWorkspace = MastermindBridge["app"]["workspace"] & {
  handleLinkContextMenu(menu:Menu,link:string,source:string,...rest:unknown[]):boolean;
};
type NativeLeaf = WorkspaceLeaf & {openLinkText(link:string,source:string,options?:unknown):Promise<void>};
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
  private dictionaryTimer?:ReturnType<typeof setTimeout>;
  private viewTimer?:ReturnType<typeof setTimeout>;
  private patchedRenderers=new WeakSet<object>();
  private observers=new Map<WorkspaceLeaf,{element:HTMLElement;observer:MutationObserver}>();
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
    if(apiVersion!=="1.13.7"||typeof this.cache.resolveLinks!=="function"||
      typeof this.cache.getBacklinksForFile!=="function"||
      typeof (WorkspaceLeaf.prototype as NativeLeaf).openLinkText!=="function"){
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
    const backlinks=cache.getBacklinksForFile;
    const getBacklinks:typeof backlinks=function(this:NativeCache,file){
      const result=backlinks.call(this,file);
      // Leave iterateAllRefs/raw caches alone: the native rename writer only understands native syntax.
      for(const [path,entry] of self.entries){
        if(self.originalGet.call(this,path)!==entry.native)continue;
        for(const link of entry.links)if(this.getFirstLinkpathDest(link.link,path)===file)result.add(path,link);
      }
      return result;
    };
    cache.getBacklinksForFile=getBacklinks;
    this.register(()=>{if(cache.getBacklinksForFile===getBacklinks)cache.getBacklinksForFile=backlinks;});
    const workspace=this.bridge.app.workspace as NativeWorkspace,open=workspace.openLinkText;
    const openReference:typeof open=function(this:typeof workspace,link,source,...options){
      const ref=resourceReference(link);
      if(ref)return self.bridge.openReference(ref,source);
      return open.call(this,link,source,...options);
    };
    workspace.openLinkText=openReference;
    this.register(()=>{if(workspace.openLinkText===openReference)workspace.openLinkText=open;});
    const leafPrototype=WorkspaceLeaf.prototype as NativeLeaf,leafOpen=leafPrototype.openLinkText;
    const openInLeaf:typeof leafOpen=function(this:WorkspaceLeaf,link,source,...options){
      const ref=resourceReference(link);
      if(ref&&this.view.app===self.bridge.app)return self.bridge.openReference(ref,source);
      return leafOpen.call(this,link,source,...options);
    };
    leafPrototype.openLinkText=openInLeaf;
    this.register(()=>{if(leafPrototype.openLinkText===openInLeaf)leafPrototype.openLinkText=leafOpen;});
    const contextMenu=workspace.handleLinkContextMenu;
    const resourceMenu:typeof contextMenu=function(this:NativeWorkspace,menu,link,source,...rest){
      const ref=resourceReference(link);if(!ref)return contextMenu.call(this,menu,link,source,...rest);
      menu.addItem(item=>item.setTitle("Open "+ref.display).setIcon(ref.kind==="chronos"?"clock":"file-box")
        .onClick(()=>void self.bridge.openReference(ref,source)));
      return true;
    };
    workspace.handleLinkContextMenu=resourceMenu;
    this.register(()=>{if(workspace.handleLinkContextMenu===resourceMenu)workspace.handleLinkContextMenu=contextMenu;});
    this.registerEvent(cache.on("changed",file=>this.enqueue(file.path)));
    const changed=()=>{
      this.dictionaryDirty=true;this.revision++;
      if(this.dictionaryTimer)clearTimeout(this.dictionaryTimer);
      this.dictionaryTimer=setTimeout(()=>{this.dictionaryTimer=undefined;void this.loadDictionary();},250);
    };
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
    workspace.onLayoutReady(()=>{if(!this.stopped){void this.migrateViews();void this.loadDictionary();this.scheduleViews();}});
  }

  private async migrateViews(){
    const native:Record<string,string>={"mastermind-graph":"graph","mastermind-backlinks":"backlink","mastermind-outgoing":"outgoing-link"};
    const changes:Promise<void>[]=[];
    this.bridge.app.workspace.iterateAllLeaves(leaf=>{
      const state=leaf.getViewState(),type=native[state.type];
      if(type)changes.push(leaf.setViewState({type,state:{file:this.bridge.app.workspace.getActiveFile()?.path}}));
    });
    await Promise.all(changes);
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
        }catch{
          if(this.entries.delete(path)){this.cache.resolveLinks(path);this.cache.trigger("resolve",file);}
          this.failure="A note could not be indexed";
        }
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
    const live=new Set<WorkspaceLeaf>();
    this.bridge.app.workspace.iterateAllLeaves(leaf=>{
      const view=leaf.view as typeof leaf.view & {renderer?:any;engine?:any;dataEngine?:any;contentEl:HTMLElement};
      const engine=view.engine||view.dataEngine;
      if(["graph","localgraph"].includes(view.getViewType())&&view.renderer&&engine){
        const prototype=Object.getPrototypeOf(view.renderer);
        if(!this.patchedRenderers.has(prototype)){
          this.patchedRenderers.add(prototype);
          const original=prototype.setData,self=this;
          const setData=function(this:any,...args:any[]){
            const result=original.apply(this,args);self.labelNodes(this);return result;
          };
          prototype.setData=setData;
          this.register(()=>{if(prototype.setData===setData)prototype.setData=original;});
        }
        this.labelNodes(view.renderer);engine.render();
      }
      if(view.getViewType()==="outgoing-link"){
        const element=view.contentEl;
        if(!element)return; // A restored/deferred native leaf has no content until it is loaded.
        live.add(leaf);
        const previous=this.observers.get(leaf);
        if(previous?.element!==element){
          previous?.observer.disconnect();
          const observer=new MutationObserver(()=>this.labelOutgoing(element));
          observer.observe(element,{childList:true,subtree:true});this.observers.set(leaf,{element,observer});
        }
        this.labelOutgoing(element);
      }
    });
    for(const [leaf,{observer}] of this.observers)if(!live.has(leaf)){observer.disconnect();this.observers.delete(leaf);}
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
      if(label.textContent!==ref.display)label.setText(ref.display);
      const row=label.closest<HTMLElement>(".outgoing-link-item")!;
      row.setAttribute("aria-label",ref.display);row.title=ref.display;
      const icon=row.querySelector<HTMLElement>(".tree-item-icon");if(icon)setIcon(icon,ref.kind==="chronos"?"clock":"file-box");
    }
  }

  diagnostics(){return{ready:this.ready,failure:this.failure,notes:this.entries.size,pending:this.pending.size,
    running:this.running,dictionary_pending:this.dictionaryLoading||!!this.dictionaryTimer,
    parsed:this.parsed,parse_ms:this.parseMs,dictionary_requests:this.dictionaryRequests};}

  onunload(){
    this.stopped=true;this.revision++;this.ready=false;
    for(const {observer} of this.observers.values())observer.disconnect();this.observers.clear();
    if(this.flushTimer)clearTimeout(this.flushTimer);if(this.viewTimer)clearTimeout(this.viewTimer);
    if(this.dictionaryTimer)clearTimeout(this.dictionaryTimer);
    // Component restores methods after onunload. Empty projection now makes the remaining reads native.
    const paths=[...this.entries.keys()];this.entries.clear();this.pending.clear();
    for(const path of paths){const file=this.bridge.app.vault.getFileByPath(path);
      if(file){this.cache.resolveLinks(path);this.cache.trigger("resolve",file);}}
    this.bridge.app.workspace.iterateAllLeaves(leaf=>{
      const view=leaf.view as typeof leaf.view & {engine?:any;dataEngine?:any};
      if(["graph","localgraph"].includes(view.getViewType()))(view.engine||view.dataEngine)?.render();
    });
  }
}
