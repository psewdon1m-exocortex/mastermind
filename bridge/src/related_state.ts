export type RelatedQuery = {path:string;text:string;focus:string;sampled:boolean};
export type RelatedItem = {path:string;title:string;excerpt:string};
export type RelatedResponse = {path:string;items:RelatedItem[];degraded:boolean;sampled:boolean};
export type RelatedState = {query?:RelatedQuery;phase:"idle"|"waiting"|"loading"|"ready"|"error";
  items:RelatedItem[];degraded:boolean};

function utf8(text:string, bytes:number):string {
  const encoded=new TextEncoder().encode(text);
  if(encoded.length<=bytes)return new TextDecoder().decode(encoded);
  // Streaming decode leaves an incomplete final code point out of the sample.
  return new TextDecoder().decode(encoded.subarray(0,bytes),{stream:true});
}

export function contextQuery(path:string,text:string,cursor:number):RelatedQuery {
  cursor=Math.max(0,Math.min(text.length,cursor));
  let sampled=false,body="";
  if(text.length>12000||new TextEncoder().encode(text).length>12000){
    sampled=true;
    // Include the beginning, middle and end; the cursor's neighborhood is separate.
    body=[0,Math.floor(text.length/3),Math.floor(text.length*2/3)]
      .map(start=>utf8(text.slice(start,start+2400),2800)).concat(utf8(text.slice(-700),2800)).join("\n…\n");
  }else body=utf8(text,12000);
  return {path,text:body,focus:utf8(text.slice(Math.max(0,cursor-1200),cursor+600),3600),sampled};
}

type Timer = ReturnType<typeof setTimeout>;
export type Scheduler = {now:()=>number;set:(callback:()=>void,delay:number)=>Timer;clear:(timer:Timer)=>void};
const realScheduler:Scheduler={now:()=>Date.now(),set:(callback,delay)=>setTimeout(callback,delay),clear:timer=>clearTimeout(timer)};

/** One request at a time; a newer buffer or note always wins over an older response. */
export class RelatedController {
  state:RelatedState={phase:"idle",items:[],degraded:false};
  private key="";
  private generation=0;
  private running=false;
  private disposed=false;
  private timer?:Timer;
  private pending?:AbortController;
  private due=0;
  private nextRequest=0;
  constructor(private fetch:(query:RelatedQuery,signal:AbortSignal)=>Promise<RelatedResponse>,
    private changed:(state:RelatedState)=>void,private scheduler:Scheduler=realScheduler){}

  update(query?:RelatedQuery,force=false){
    if(this.disposed)return;
    const key=query?JSON.stringify(query):"";
    if(key===this.key&&!force)return;
    const sameNote=query?.path===this.state.query?.path;
    this.key=key;this.generation++;
    if(this.timer!==undefined)this.scheduler.clear(this.timer);
    this.timer=undefined;
    this.state={query,phase:query?"waiting":"idle",items:sameNote?this.state.items:[],degraded:false};
    this.changed(this.state);
    if(!query){this.pending?.abort();return;}
    this.due=this.scheduler.now()+(force?0:1200);
    this.arm();
  }

  refresh(){if(this.state.query)this.update(this.state.query,true);}

  private arm(){
    if(this.disposed||this.running||!this.state.query)return;
    if(this.timer!==undefined)this.scheduler.clear(this.timer);
    this.timer=this.scheduler.set(()=>{this.timer=undefined;void this.run();},
      Math.max(0,this.due-this.scheduler.now(),this.nextRequest-this.scheduler.now()));
  }

  private async run(){
    const query=this.state.query;
    if(this.disposed||this.running||!query)return;
    this.running=true;
    const generation=this.generation;
    this.pending=new AbortController();
    this.state={...this.state,phase:"loading"};this.changed(this.state);
    try{
      const response=await this.fetch(query,this.pending.signal);
      if(this.disposed||generation!==this.generation)return;
      if(response.path!==query.path||!Array.isArray(response.items))throw new Error("Invalid recommendation response");
      this.state={query,phase:"ready",items:response.items,degraded:response.degraded};this.changed(this.state);
    }catch{
      if(!this.disposed&&generation===this.generation){
        this.state={...this.state,phase:"error"};this.changed(this.state);
      }
    }finally{
      this.running=false;this.pending=undefined;this.nextRequest=this.scheduler.now()+1500;
      if(!this.disposed&&generation!==this.generation)this.arm();
    }
  }

  dispose(){
    this.disposed=true;this.generation++;this.pending?.abort();
    if(this.timer!==undefined)this.scheduler.clear(this.timer);
  }
}
