import type {App, TFile} from "obsidian";
import {parse, excluded, nameKey} from "./portable_parser";

const HISTORY=".obsidian/plugins/mastermind-bridge/portable-history.json";
const LIMIT=16*1024**2;
type Snapshot={format:string; internal:string[]; saturn:string[]};
const record=(value:unknown):value is Record<string,unknown>=>!!value&&typeof value==="object"&&!Array.isArray(value);
const offset=(text:string,point:number)=>[...text].slice(0,point).join("").length;

/** A standalone adapter. It deliberately has no URL, credentials, fetch or HTTP client. */
export class Portable {
  history=new Set<string>();
  saturn:string[]=[];
  private inventoryCache?:{files:TFile[];byName:Map<string,TFile>;current:Record<string,string>};
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
  }
  inventory(){
    if(this.inventoryCache)return this.inventoryCache;
    const files=this.app.vault.getMarkdownFiles().filter(file=>!file.path.startsWith(".obsidian/"));
    if(files.length>100000)throw new Error("Portable note inventory exceeds its limit");
    const byName=new Map<string,TFile>(),collisions=new Set<string>();
    for(const file of files){const key=nameKey(file.basename);if(byName.has(key))collisions.add(key);else byName.set(key,file);}
    for(const key of collisions)byName.delete(key);
    const current=Object.assign(Object.create(null),Object.fromEntries([...byName].map(([key,file])=>[key,file.basename]))) as Record<string,string>;
    for(const file of files)this.history.add(file.basename);
    return this.inventoryCache={files,byName,current};
  }
  invalidate(){this.inventoryCache=undefined;}
  async request<T>(route:string,data?:unknown):Promise<T>{
    await this.loaded;
    const input=(data||{}) as Record<string,any>;
    if(route==="/reference-dictionary")return{current:this.inventory().current,history:[...this.history].sort(),saturn:this.saturn} as T;
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
