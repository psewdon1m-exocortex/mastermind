import {MarkdownRenderChild, Modal, Notice} from "obsidian";
import {randomBytes} from "node:crypto";
import {ClientRequest, IncomingMessage, ServerResponse, request} from "node:http";
import type MastermindBridge from "./main";

type Metadata = {kind:string; id?:string; started_at?:string; ended_at?:string|null;
  path?:string; name?:string; type?:string; size_bytes?:number; mime_type?:string; content_type?:string};
type Entry = {path:string; name?:string; type:string; size_bytes:number};

export class MediaBroker {
  capabilities = new Map<string,{path:string; expires:number; streams:Set<ClientRequest>}>();
  responses=0;
  rangeResponses=0;
  transferredBytes=0;
  constructor(private bridge:MastermindBridge) {}
  revoke(token:string){const item=this.capabilities.get(token);for(const stream of item?.streams||[])stream.destroy();this.capabilities.delete(token);}
  issue(path:string) {
    for(const [key,item] of this.capabilities)if(item.expires<Date.now())this.revoke(key);
    if(this.capabilities.size>=32)throw new Error("Close another resource preview first");
    const token=randomBytes(32).toString("hex");
    this.capabilities.set(token,{path,expires:Date.now()+30*60*1000,streams:new Set()});
    return {url:"http://127.0.0.1:8092/media/"+token,revoke:()=>this.revoke(token)};
  }
  handle(req:IncomingMessage,res:ServerResponse):boolean {
    if(!req.url?.startsWith("/media/"))return false;
    const match=/^\/media\/([a-f0-9]{64})$/.exec(req.url),cap=match?this.capabilities.get(match[1]):undefined;
    if(req.method!=="GET"||!cap||cap.expires<=Date.now()){res.writeHead(404).end();return true;}
    const headers:Record<string,string>={Authorization:"Bearer "+this.bridge.token};
    for(const name of ["range","if-range"]){const value=req.headers[name];
      if(Array.isArray(value)||value&&value.length>2048){res.writeHead(400).end();return true;}
      if(value)headers[name]=value;
    }
    const upstream=request(this.bridge.coreUrl+"/internal/bridge/resources/content?"+new URLSearchParams({path:cap.path}),
      {headers,timeout:60000},response=>{
        const code=response.statusCode||502;
        if(![200,206].includes(code)){response.resume();res.writeHead(code===416?416:503).end();return;}
        this.responses++;if(code===206)this.rangeResponses++;
        response.on("data",(chunk:Buffer)=>{this.transferredBytes+=chunk.length;});
        const mime=String(response.headers["content-type"]||"application/octet-stream").split(";",1)[0].toLowerCase();
        const preview=/^(image\/(png|jpeg|webp|gif|svg\+xml)|video\/(mp4|webm|ogg)|audio\/(mpeg|mp4|ogg|wav|webm)|application\/pdf)$/.test(mime);
        const output:Record<string,string|number>={"Content-Type":preview?mime:"application/octet-stream",
          "Content-Disposition":preview?"inline":"attachment", "Cache-Control":"no-store", "Referrer-Policy":"no-referrer",
          "X-Content-Type-Options":"nosniff", "Content-Security-Policy":"default-src 'none'; sandbox", "X-Robots-Tag":"noindex, nofollow, noarchive"};
        for(const name of ["content-length","content-range","accept-ranges","etag"]){const value=response.headers[name];if(typeof value==="string")output[name]=value;}
        res.writeHead(code,output);response.pipe(res);
        res.on("close",()=>response.destroy());response.on("error",()=>res.destroy());
      });
    upstream.on("timeout",()=>upstream.destroy());
    cap.streams.add(upstream);upstream.on("close",()=>cap.streams.delete(upstream));
    upstream.on("error",()=>{if(!res.headersSent)res.writeHead(503).end();else res.destroy();});
    res.on("close",()=>upstream.destroy());upstream.end();return true;
  }
}

export class ResourceCard extends MarkdownRenderChild {
  static active=new Set<ResourceCard>();
  generation=0;
  state="loading";
  observer?:IntersectionObserver;
  inViewport=false;
  revoke?:()=>void;
  timer?:ReturnType<typeof setTimeout>;
  constructor(element:HTMLElement,private bridge:MastermindBridge,private kind:string,private target:string) {super(element);}
  onload(){ResourceCard.active.add(this);this.containerEl.addClass("mastermind-resource");this.containerEl.setText("Loading "+this.kind+"…");
    this.observer=new IntersectionObserver(entries=>{this.inViewport=entries.some(entry=>entry.isIntersecting);
      if(this.inViewport&&this.state==="loading")void this.refresh();});this.observer.observe(this.containerEl);}
  onunload(){ResourceCard.active.delete(this);this.generation++;this.observer?.disconnect();this.revoke?.();if(this.timer)clearTimeout(this.timer);
    for(const media of this.containerEl.querySelectorAll("video,audio")){(media as HTMLMediaElement).pause();media.removeAttribute("src");(media as HTMLMediaElement).load();}}
  diagnostics(){
    const image=this.containerEl.querySelector("img"),video=this.containerEl.querySelector("video"),audio=this.containerEl.querySelector("audio");
    return {kind:this.kind,state:this.state,visible:this.containerEl.checkVisibility(),image_ready:image?image.complete&&image.naturalWidth>0:undefined,
      video_ready:video?.readyState,video_time:video?.currentTime,audio_ready:audio?.readyState,pdf:Boolean(this.containerEl.querySelector("iframe"))};
  }
  async refresh(){
    const generation=++this.generation;
    this.state="fetching";
    if(this.timer)clearTimeout(this.timer);
    this.revoke?.();this.containerEl.empty();this.containerEl.setText("Loading "+this.kind+"…");
    try{
      const metadata=await this.bridge.core<Metadata>("/external/open",{kind:this.kind,target:this.target});
      if(generation!==this.generation)return;
      this.state="loaded";
      const element=this.containerEl;element.empty();
      element.createEl("strong",{text:this.kind==="chronos"?"Chronos":metadata.name||this.target.split("/").pop()||"Saturn"});
      if(this.kind==="chronos"){
        for(const [label,value] of [["Start",metadata.started_at],["End",metadata.ended_at]])
          element.createDiv({text:label+"  "+(value?new Date(value).toLocaleString():"—")});
        this.timer=setTimeout(()=>{if(this.inViewport)void this.refresh();else this.state="loading";},30000);return;
      }
      if(metadata.type==="folder"){
        await this.list(this.target,null,generation);return;
      }
      element.createDiv({text:((metadata.size_bytes||0)/1024**2).toFixed(2)+" MiB",cls:"mastermind-muted"});
      const media=this.bridge.media.issue(this.target);this.revoke=media.revoke;
      const mime=(metadata.mime_type||metadata.content_type||"").split(";",1)[0].toLowerCase();
      if(/^image\/(png|jpeg|webp|gif|svg\+xml)$/.test(mime)){
        const image=element.createEl("img",{attr:{src:media.url,alt:metadata.name||"Saturn image",loading:"lazy"}});
        image.onclick=()=>openResource(this.bridge,this.kind,this.target);
      }else if(/^video\/(mp4|webm|ogg)$/.test(mime)){
        element.createEl("video",{attr:{src:media.url,controls:"",preload:"metadata"}});
      }else if(/^audio\/(mpeg|mp4|ogg|wav|webm)$/.test(mime)){
        element.createEl("audio",{attr:{src:media.url,controls:"",preload:"metadata"}});
      }else if(mime==="application/pdf"){
        element.createEl("iframe",{attr:{src:media.url,title:metadata.name||"Saturn PDF",sandbox:"allow-scripts allow-same-origin"}});
      }
      const download=element.createEl("button",{text:"Download"});
      download.onclick=()=>{download.disabled=true;void this.bridge.core("/external/download",{target:this.target})
        .then(()=>new Notice("Download is ready in the Vault toolbar."))
        .catch(()=>new Notice("Could not prepare this download."))
        .finally(()=>{download.disabled=false;});};
      const refresh=element.createEl("button",{text:"Refresh"});refresh.onclick=()=>void this.refresh();
    }catch{
      if(generation!==this.generation)return;
      this.state="unavailable";
      this.containerEl.empty();this.containerEl.createDiv({text:this.kind+" unavailable"});
      this.containerEl.createDiv({text:this.target,cls:"mastermind-muted"});
      const retry=this.containerEl.createEl("button",{text:"Retry"});retry.onclick=()=>void this.refresh();
      this.timer=setTimeout(()=>{if(this.inViewport)void this.refresh();else this.state="loading";},30000);
    }
  }
  async list(path:string,cursor:string|null,generation:number){
    const parameters=new URLSearchParams({path,limit:"100"});if(cursor)parameters.set("cursor",cursor);
    const result=await this.bridge.core<{entries:Entry[];next_cursor:string|null}>("/resources?"+parameters);
    if(generation!==this.generation)return;
    for(const entry of result.entries){const button=this.containerEl.createEl("button",{
      text:(entry.type==="folder"?"▸ ":"")+(entry.name||entry.path.split("/").pop()),cls:"mastermind-link-row"});
      button.onclick=()=>openResource(this.bridge,"saturn",entry.path);
    }
    if(result.next_cursor){const more=this.containerEl.createEl("button",{text:"Load more"});
      more.onclick=()=>{more.remove();void this.list(path,result.next_cursor,generation).catch(()=>new Notice("Saturn listing is unavailable."));};}
  }
}

export function openResource(bridge:MastermindBridge,kind:string,target:string){
  class ResourceModal extends Modal {
    card?:ResourceCard;
    onOpen(){this.setTitle(kind==="chronos"?"Chronos":"Saturn");this.card=new ResourceCard(this.contentEl,bridge,kind,target);this.card.load();}
    onClose(){this.card?.unload();}
  }
  new ResourceModal(bridge.app).open();
}
