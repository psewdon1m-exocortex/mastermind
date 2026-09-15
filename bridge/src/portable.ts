import type {App, TFile} from "obsidian";
import {parse, excluded, nameKey, Ref} from "./portable_parser";

const HISTORY=".obsidian/plugins/mastermind-bridge/portable-history.json";
const PRESENTATION=".obsidian/plugins/mastermind-bridge/portable-presentation.json";
const LIMIT=16*1024**2;
type Snapshot={format:string; internal:string[]; saturn:string[]};
const record=(value:unknown):value is Record<string,unknown>=>!!value&&typeof value==="object"&&!Array.isArray(value);
const offset=(text:string,point:number)=>[...text].slice(0,point).join("").length;

/** A standalone adapter. It deliberately has no URL, credentials, fetch or HTTP client. */
export class Portable {
  history=new Set<string>();
  saturn:string[]=[];
  presentation:Record<string,unknown>={};
  cache=new Map<string,{stamp:string; refs:Ref[]}>();
  dictionaryStamp="";
  loaded:Promise<void>;
  pendingSave:Promise<unknown>=Promise.resolve();
  constructor(private app:App){this.loaded=this.load();}
  async load(){
    const adapter=this.app.vault.adapter;
    if(await adapter.exists(HISTORY)){
      const stat=await adapter.stat(HISTORY);if(!stat||stat.size>LIMIT)throw new Error("Portable history exceeds its limit");
      const text=await adapter.read(HISTORY);if(Buffer.byteLength(text)>LIMIT)throw new Error("Portable history exceeds its limit");
      const data:unknown=JSON.parse(text);
      if(!record(data)||data.format!=="mastermind-portable-history/v1"||![data.internal,data.saturn].every(values=>
        Array.isArray(values)&&values.length<=100000&&values.every(value=>typeof value==="string"&&value.length<=1024)))
        throw new Error("Portable history is invalid");
      for(const name of data.internal as string[])this.history.add(name);
      this.saturn=data.saturn as string[];
    }
    if(await adapter.exists(PRESENTATION)){
      const stat=await adapter.stat(PRESENTATION);
      if(stat&&stat.size<=256*1024){const value=JSON.parse(await adapter.read(PRESENTATION));if(record(value))this.presentation=value;}
    }
  }
  inventory(){
    const files=this.app.vault.getMarkdownFiles().filter(file=>!file.path.startsWith(".obsidian/"));
    if(files.length>100000)throw new Error("Portable note inventory exceeds its limit");
    const byName=new Map<string,TFile>(),collisions=new Set<string>();
    for(const file of files){const key=nameKey(file.basename);if(byName.has(key))collisions.add(key);else byName.set(key,file);}
    for(const key of collisions)byName.delete(key);
    const current=Object.assign(Object.create(null),Object.fromEntries([...byName].map(([key,file])=>[key,file.basename]))) as Record<string,string>;
    const stamp=files.map(file=>file.path).sort().join("\0");if(stamp!==this.dictionaryStamp){this.dictionaryStamp=stamp;this.cache.clear();}
    for(const file of files)this.history.add(file.basename);
    return{files,byName,current};
  }
  invalidate(path?:string){if(path)this.cache.delete(path);else{this.cache.clear();this.dictionaryStamp="";}}
  async all(){
    const inventory=this.inventory(),entries:{source:TFile;ref:Ref}[]=[],live=new Set(inventory.files.map(file=>file.path));
    for(const path of this.cache.keys())if(!live.has(path))this.cache.delete(path);
    for(const file of inventory.files){
      if(file.stat.size>8*1024**2)throw new Error("A note exceeds the portable reference limit");
      const stamp=file.stat.mtime+":"+file.stat.size;let item=this.cache.get(file.path);
      if(!item||item.stamp!==stamp){const text=await this.app.vault.cachedRead(file);
        item={stamp,refs:parse(text,inventory.current,[...this.history],this.saturn)};this.cache.set(file.path,item);}
      const unique=new Set<string>();for(const ref of item.refs){const key=ref.kind+"\0"+ref.target;if(unique.has(key))continue;
        unique.add(key);entries.push({source:file,ref});if(entries.length>500000)throw new Error("Portable graph exceeds its edge limit");}
      // Yield between files so opening a large copy does not monopolize the UI.
      if(entries.length%100===0)await new Promise(resolve=>setTimeout(resolve,0));
    }
    return{...inventory,entries};
  }
  async request<T>(route:string,data?:unknown):Promise<T>{
    await this.loaded;
    const input=(data||{}) as Record<string,any>;
    if(route==="/references")return parse(input.text,this.inventory().current,[...this.history],this.saturn) as T;
    if(route==="/suggest"){
      if(excluded(input.text).some(([a,b])=>a<=input.offset&&input.offset<b)||input.query.includes(":"))return [] as T;
      const key=nameKey(input.query),{files}=this.inventory();
      const rank=(file:TFile)=>{const name=nameKey(file.basename);
        if(name.startsWith(key))return 0;if(name.split(/\s+/).some(word=>word.startsWith(key)))return 1;
        if(name.includes(key))return 2;let index=0;for(const c of name)if(c===key[index])index++;return index===key.length?3:4;};
      return files.map(file=>({score:rank(file),name:file.basename,path:file.path})).filter(item=>item.score<4)
        .sort((a,b)=>a.score-b.score||(a.name<b.name?-1:a.name>b.name?1:0)).slice(0,25).map(({name,path})=>({name,path})) as T;
    }
    if(route==="/graph-presentation"){
      const text=JSON.stringify(input);if(Buffer.byteLength(text)>256*1024)throw new Error("Presentation exceeds its limit");
      this.presentation=input;await this.app.vault.adapter.write(PRESENTATION,text);return input as T;
    }
    if(route==="/graph"||route==="/links"){
      const {files,byName,entries}=await this.all();
      if(route==="/links"){
        if(input.direction==="backlinks"){
          const target=this.app.vault.getFileByPath(input.path);if(!target)return [] as T;
          return [...new Map(entries.filter(({ref})=>ref.kind==="internal"&&ref.target===nameKey(target.basename))
            .map(({source})=>[source.path,{path:source.path,name:source.basename,kind:"internal",broken:0}])).values()] as T;
        }
        return entries.filter(({source})=>source.path===input.path).map(({ref})=>{
          const target=ref.kind==="internal"?byName.get(ref.target):undefined;
          return{path:target?.path||null,name:target?.basename||ref.display,kind:ref.kind,target_key:ref.target,broken:ref.exists?0:1};}) as T;
      }
      const edges=new Map<string,[string,string]>(),external:unknown[]=[];let broken=0;
      for(const {source,ref} of entries){
        if(ref.kind!=="internal"){external.push({source:source.path,target_key:ref.target,kind:ref.kind,broken:ref.exists?0:1});continue;}
        if(!ref.exists)broken++;
        const target=byName.get(ref.target);if(!target||source.path===target.path)continue;
        const pair=[source.path,target.path].sort() as [string,string];edges.set(pair.join("\0"),pair);
      }
      return{nodes:files.map(file=>({path:file.path,name:file.basename})),edges:[...edges.values()],external,broken,
        connectedness:files.length>1?Math.round(edges.size/(files.length*(files.length-1)/2)*10000)/100:0,presentation:this.presentation} as T;
    }
    throw new Error("This resource is unavailable in a portable copy");
  }
  async saveHistory(){
    if(this.history.size>100000)throw new Error("Portable history exceeds its limit");
    const snapshot:Snapshot={format:"mastermind-portable-history/v1",internal:[...this.history].sort(),saturn:this.saturn};
    const text=JSON.stringify(snapshot);if(Buffer.byteLength(text)>LIMIT)throw new Error("Portable history exceeds its limit");
    this.pendingSave=this.pendingSave.catch(()=>{}).then(()=>this.app.vault.adapter.write(HISTORY,text));await this.pendingSave;
  }
  async rename(file:TFile,newPath:string,original:()=>Promise<void>){
    await this.loaded;const {current,byName}=this.inventory(),oldKey=nameKey(file.basename),oldName=file.basename;
    const newName=newPath.split("/").pop()!.slice(0,-3),target=byName.get(nameKey(newName));
    if(!newPath.endsWith(".md")||target&&target.path!==file.path)throw new Error("The note basename must stay unique");
    await original();this.history.add(oldName);this.history.add(newName);
    for(const note of this.app.vault.getMarkdownFiles())await this.app.vault.process(note,text=>{
      const refs=parse(text,current,[...this.history],this.saturn).filter(ref=>ref.kind==="internal"&&ref.target===oldKey&&text[offset(text,ref.start)]==="@");
      for(const ref of refs.reverse())text=text.slice(0,offset(text,ref.start))+"@"+newName+text.slice(offset(text,ref.end));return text;
    });
    this.invalidate();await this.saveHistory();
  }
}
