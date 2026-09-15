import {ItemView, WorkspaceLeaf} from "obsidian";
import type MastermindBridge from "./main";

type Link = {path?: string; name: string; kind: string; broken: number; target_key: string};
type Node = {path: string; name: string; kind?: string; target?: string; x?: number; y?: number};
type Presentation = {x: number; y: number; zoom: number; internal: boolean; external: boolean;
  positions: Record<string, [number, number]>};
type Graph = {nodes: Node[]; edges: [string, string][]; connectedness: number; broken: number;
  external: {source: string; target_key: string; kind: string}[]; presentation?: Partial<Presentation>};

export class LinksView extends ItemView {
  revision = 0;
  last = "";
  constructor(leaf: WorkspaceLeaf, private bridge: MastermindBridge, private direction: "backlinks"|"outgoing") {super(leaf);}
  getViewType() {return "mastermind-" + this.direction;}
  getDisplayText() {return "Mastermind " + (this.direction === "backlinks" ? "Backlinks" : "Outgoing Links");}
  getIcon() {return this.direction === "backlinks" ? "links-coming-in" : "links-going-out";}
  async onOpen() {
    this.registerEvent(this.app.workspace.on("active-leaf-change", () => void this.refresh()));
    this.registerEvent(this.app.vault.on("modify", () => void this.refresh()));
    this.registerInterval(window.setInterval(() => {if (this.containerEl.checkVisibility()) void this.refresh();}, 5000));
    await this.refresh();
  }
  async refresh() {
    const path = this.app.workspace.getActiveFile()?.path;
    if (!path) {this.contentEl.setText("Open a note to see its links."); return;}
    const revision = ++this.revision;
    try {
      const links = await this.bridge.core<Link[]>("/links", {path, direction: this.direction});
      if (revision !== this.revision) return;
      const key = JSON.stringify([path, links]);
      if (key === this.last) return;
      this.last = key; this.contentEl.empty(); this.contentEl.addClass("mastermind-links-view");
      this.contentEl.createEl("h4", {text: path.split("/").pop()});
      if (!links.length) this.contentEl.createDiv({text: "No links", cls: "mastermind-muted"});
      for (const kind of ["internal", "chronos", "saturn"]) {
        const group = links.filter(link => link.kind === kind);
        if (!group.length) continue;
        this.contentEl.createEl("h5", {text: kind === "internal" ? "Notes" : "External · " + kind});
        for (const link of group) {
          const button = this.contentEl.createEl("button", {text: link.name, cls: "mastermind-link-row"});
          button.toggleClass("is-unresolved", !!link.broken);
          button.title = link.path || link.target_key;
          button.onclick = () => {if (link.kind === "internal" && link.path) void this.app.workspace.openLinkText(link.path, "", false);
            else if (link.kind !== "internal") void this.bridge.openReference({start:0,end:0,kind:link.kind,
              target:link.target_key,display:link.name,exists:!link.broken},path);};
        }
      }
    } catch {this.contentEl.setText("Mastermind Core is unavailable. Your notes remain in Vault."); this.last = "";}
  }
  async onClose() {this.revision++;}
}

// Component circles are an O(N+E) approximate layout. Even a large disconnected
// graph is calculated off the UI thread, with no permanent force-animation loop.
const layoutWorker = `onmessage = ({data}) => {
  const n=data.nodes.length, parent=Array.from({length:n},(_,i)=>i), index=new Map(data.nodes.map((v,i)=>[v.path,i]));
  function find(i){while(parent[i]!==i){parent[i]=parent[parent[i]];i=parent[i];}return i;}
  for(const [a,b] of data.edges){const i=index.get(a),j=index.get(b);if(i!==undefined&&j!==undefined)parent[find(i)]=find(j);}
  const groups=new Map();for(let i=0;i<n;i++){const root=find(i);if(!groups.has(root))groups.set(root,[]);groups.get(root).push(i);}
  const result=new Array(n);let cursor=0;
  for(const group of [...groups.values()].sort((a,b)=>b.length-a.length)){
    const radius=Math.max(60,Math.sqrt(group.length)*28),cx=cursor+radius,cy=radius;
    group.forEach((index,offset)=>{const angle=offset*2.399963229728653,r=Math.sqrt(offset/group.length)*radius;
      result[index]=[cx+Math.cos(angle)*r,cy+Math.sin(angle)*r];});cursor+=radius*2+80;
  }postMessage(result);
};`;

export class GraphView extends ItemView {
  canvas?: HTMLCanvasElement;
  list?: HTMLElement;
  summary?: HTMLElement;
  data?: Graph;
  nodes: Node[] = [];
  edges: [string,string][] = [];
  points = new Map<string, Node>();
  cells = new Map<string, Node[]>();
  presentation: Presentation = {x:30,y:30,zoom:1,internal:true,external:true,positions:{}};
  query = "";
  worker?: Worker;
  workerUrl?: string;
  frame = 0;
  renderTimer?: ReturnType<typeof setTimeout>;
  saveTimer?: ReturnType<typeof setTimeout>;
  lastRender = 0;
  renderCount = 0;
  renderMs = 0;
  layoutMs = 0;
  revision = 0;
  drag?: {x:number;y:number;node?:Node;moved:boolean};
  constructor(leaf: WorkspaceLeaf, private bridge: MastermindBridge) {super(leaf);}
  getViewType() {return "mastermind-graph";}
  getDisplayText() {return "Mastermind Graph";}
  getIcon() {return "git-fork";}
  async onOpen() {
    this.contentEl.empty(); this.contentEl.addClass("mastermind-graph-view");
    const controls = this.contentEl.createEl("details"); controls.createEl("summary", {text:"Presentation"});
    const search = controls.createEl("input", {type:"search",placeholder:"Filter notes and resources"});
    search.setAttribute("aria-label","Filter graph"); search.oninput=()=>{this.query=search.value.toLocaleLowerCase();this.project();};
    for (const key of ["internal","external"] as const) {
      const label=controls.createEl("label"), check=label.createEl("input",{type:"checkbox"});check.checked=true;
      label.append(key === "internal" ? " Notes" : " External resources");
      check.onchange=()=>{this.presentation[key]=check.checked;this.project();this.save();};
    }
    const reset=controls.createEl("button",{text:"Reset view"});
    reset.onclick=()=>{this.presentation={x:30,y:30,zoom:1,internal:true,external:true,positions:{}};this.project();this.save();};
    this.summary=this.contentEl.createDiv({cls:"mastermind-muted"});
    this.canvas=this.contentEl.createEl("canvas"); this.canvas.tabIndex=0;
    this.canvas.setAttribute("aria-label","Knowledge graph. Arrow keys pan, plus and minus zoom. Notes are also listed below.");
    this.list=this.contentEl.createDiv({cls:"mastermind-graph-list"});
    const resize=new ResizeObserver(()=>this.schedule());resize.observe(this.canvas);this.register(()=>resize.disconnect());
    const visible=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting))this.schedule();});
    visible.observe(this.canvas);this.register(()=>visible.disconnect());
    this.registerDomEvent(this.canvas,"wheel",event=>{
      event.preventDefault(); const p=this.position(event);
      const zoom=Math.max(.1,Math.min(10,this.presentation.zoom*Math.exp(-event.deltaY*.001)));
      const factor=zoom/this.presentation.zoom;
      this.presentation.x=p.x-(p.x-this.presentation.x)*factor;
      this.presentation.y=p.y-(p.y-this.presentation.y)*factor;
      this.presentation.zoom=zoom;this.schedule();this.save();
    },{passive:false});
    this.registerDomEvent(this.canvas,"pointerdown",event=>{
      const p=this.position(event);this.drag={...p,node:this.hit(p.x,p.y),moved:false};this.canvas!.setPointerCapture(event.pointerId);
    });
    this.registerDomEvent(this.canvas,"pointermove",event=>{
      if(!this.drag)return;const p=this.position(event),dx=p.x-this.drag.x,dy=p.y-this.drag.y;
      if(Math.abs(dx)+Math.abs(dy)>1)this.drag.moved=true;
      if(this.drag.node){this.drag.node.x!+=dx/this.presentation.zoom;this.drag.node.y!+=dy/this.presentation.zoom;}
      else {this.presentation.x+=dx;this.presentation.y+=dy;}
      this.drag.x=p.x;this.drag.y=p.y;this.schedule();
    });
    this.registerDomEvent(this.canvas,"pointerup",()=>{
      const drag=this.drag;this.drag=undefined;if(!drag)return;
      if(drag.node&&!drag.moved)void this.openNode(drag.node);
      if(drag.node&&drag.moved&&!drag.node.kind&&Object.keys(this.presentation.positions).length<2000)
        this.presentation.positions[drag.node.path]=[drag.node.x!,drag.node.y!];
      this.rebuildCells();this.save();
    });
    this.registerDomEvent(this.canvas,"keydown",event=>{
      if(["ArrowLeft","ArrowRight","ArrowUp","ArrowDown","+","-","="].includes(event.key))event.preventDefault();else return;
      if(event.key==="ArrowLeft")this.presentation.x-=30;if(event.key==="ArrowRight")this.presentation.x+=30;
      if(event.key==="ArrowUp")this.presentation.y-=30;if(event.key==="ArrowDown")this.presentation.y+=30;
      if(event.key==="+"||event.key==="=")this.presentation.zoom=Math.min(10,this.presentation.zoom*1.1);
      if(event.key==="-")this.presentation.zoom=Math.max(.1,this.presentation.zoom/1.1);this.schedule();this.save();
    });
    this.registerInterval(window.setInterval(()=>{if(this.containerEl.checkVisibility())void this.refresh();},10000));
    await this.refresh(true);
  }
  async refresh(initial=false) {
    try {
      const data=await this.bridge.core<Graph>("/graph");
      if(initial&&data.presentation)this.presentation={...this.presentation,...data.presentation};
      const comparable=(value:Graph)=>JSON.stringify([value.nodes,value.edges,value.external]);
      if(this.data&&comparable(this.data)===comparable(data))return;
      this.data=data;this.summary?.setText(data.nodes.length+" notes · "+data.edges.length+" internal edges · "+
        data.connectedness.toFixed(2)+"% connectedness · "+data.broken+" broken links");this.project();
    }catch{this.summary?.setText("Mastermind Core is unavailable. Showing the last graph.");}
  }
  project() {
    if(!this.data)return;
    const nodes=new Map<string,Node>();
    if(this.presentation.internal)for(const node of this.data.nodes)nodes.set(node.path,{...node});
    const edges:[string,string][]=[...this.data.edges];
    if(this.presentation.external)for(const ref of this.data.external){
      const key="external:"+ref.kind+":"+ref.target_key;
      nodes.set(key,{path:key,name:ref.kind+": "+ref.target_key,kind:ref.kind,target:ref.target_key});edges.push([ref.source,key]);
    }
    const matching=[...nodes.values()].filter(node=>!this.query||node.name.toLocaleLowerCase().includes(this.query));
    this.nodes=matching.slice(0,5000);
    this.points=new Map(this.nodes.map(node=>[node.path,node]));
    this.edges=edges.filter(([a,b])=>this.points.has(a)&&this.points.has(b)).slice(0,20000);
    this.list?.empty();
    if(matching.length>5000)this.list?.createDiv({text:"Showing 5,000 matching nodes. Refine the filter to explore the rest."});
    for(const node of this.nodes.slice(0,200)){
      const button=this.list!.createEl("button",{text:node.name,cls:"mastermind-link-row"});button.onclick=()=>void this.openNode(node);
    }
    if(this.nodes.length>200)this.list?.createDiv({text:"Showing the first 200 entries. Use the filter to find any note."});
    this.worker?.terminate();if(this.workerUrl)URL.revokeObjectURL(this.workerUrl);
    this.workerUrl=URL.createObjectURL(new Blob([layoutWorker],{type:"text/javascript"}));this.worker=new Worker(this.workerUrl);
    const revision=++this.revision;
    const layoutStarted=performance.now();
    this.worker.onmessage=event=>{if(revision!==this.revision)return;this.layoutMs=performance.now()-layoutStarted;
      this.nodes.forEach((node,index)=>{const position=this.presentation.positions[node.path]||event.data[index];
        [node.x,node.y]=position;});this.rebuildCells();this.schedule();this.worker?.terminate();};
    this.worker.postMessage({nodes:this.nodes,edges:this.edges});
  }
  position(event:MouseEvent){const box=this.canvas!.getBoundingClientRect();return{x:event.clientX-box.left,y:event.clientY-box.top};}
  rebuildCells(){this.cells.clear();for(const node of this.nodes){const key=Math.floor(node.x!/40)+":"+Math.floor(node.y!/40);
    if(!this.cells.has(key))this.cells.set(key,[]);this.cells.get(key)!.push(node);}}
  hit(x:number,y:number){x=(x-this.presentation.x)/this.presentation.zoom;y=(y-this.presentation.y)/this.presentation.zoom;
    const cx=Math.floor(x/40),cy=Math.floor(y/40),radius=12/this.presentation.zoom,range=Math.ceil(radius/40);
    for(let i=cx-range;i<=cx+range;i++)for(let j=cy-range;j<=cy+range;j++)for(const node of this.cells.get(i+":"+j)||[])
      if(Math.hypot(node.x!-x,node.y!-y)<=radius)return node;
  }
  schedule(){if(this.frame||this.renderTimer||!this.canvas?.checkVisibility())return;
    const delay=Math.max(0,34-(performance.now()-this.lastRender));
    this.renderTimer=setTimeout(()=>{this.renderTimer=undefined;this.frame=requestAnimationFrame(()=>{this.frame=0;this.draw();});},delay);
  }
  draw(){const canvas=this.canvas;if(!canvas?.checkVisibility())return;this.lastRender=performance.now();this.renderCount++;
    const box=canvas.getBoundingClientRect(),dpr=Math.min(2,window.devicePixelRatio||1),ctx=canvas.getContext("2d")!;
    canvas.width=Math.min(4096,Math.round(box.width*dpr));canvas.height=Math.min(4096,Math.round(box.height*dpr));
    const style=getComputedStyle(canvas);ctx.scale(dpr,dpr);ctx.clearRect(0,0,box.width,box.height);
    ctx.translate(this.presentation.x,this.presentation.y);ctx.scale(this.presentation.zoom,this.presentation.zoom);
    ctx.strokeStyle=style.getPropertyValue("--background-modifier-border");ctx.lineWidth=1/this.presentation.zoom;ctx.beginPath();
    for(const [a,b]of this.edges){const source=this.points.get(a)!,target=this.points.get(b)!;
      if(source.x===undefined||target.x===undefined)continue;ctx.moveTo(source.x,source.y!);ctx.lineTo(target.x,target.y!);}ctx.stroke();
    ctx.font=(12/this.presentation.zoom)+"px "+style.getPropertyValue("--font-interface");
    for(const node of this.nodes){if(node.x===undefined)continue;
      const sx=node.x*this.presentation.zoom+this.presentation.x,sy=node.y!*this.presentation.zoom+this.presentation.y;
      if(sx < -200||sx>box.width+200||sy < -30||sy>box.height+30)continue;
      ctx.fillStyle=style.getPropertyValue(node.kind?"--text-muted":"--interactive-accent");ctx.beginPath();
      ctx.arc(node.x,node.y!,4/Math.sqrt(this.presentation.zoom),0,Math.PI*2);ctx.fill();
      if(this.nodes.length<=300||this.presentation.zoom>=1.4){ctx.fillStyle=style.getPropertyValue("--text-normal");
        ctx.fillText(node.name.length>60?node.name.slice(0,59)+"…":node.name,node.x+8/this.presentation.zoom,node.y!+4/this.presentation.zoom);}
    }
    this.renderMs=performance.now()-this.lastRender;
  }
  diagnostics(){return{nodes:this.nodes.length,edges:this.edges.length,render_count:this.renderCount,
    render_ms:this.renderMs,layout_ms:this.layoutMs,visible:this.canvas?.checkVisibility()||false};}
  async openNode(node:Node){if(!node.kind)await this.app.workspace.openLinkText(node.path,"",true);
    else await this.bridge.openReference({start:0,end:0,kind:node.kind,target:node.target!,display:node.name,exists:true},"");}
  save(){if(this.saveTimer)clearTimeout(this.saveTimer);this.saveTimer=setTimeout(()=>{
    void this.bridge.core("/graph-presentation",this.presentation).catch(()=>this.summary?.setText("Presentation changes are not saved while Core is unavailable."));
  },500);}
  async onClose(){this.revision++;this.worker?.terminate();if(this.workerUrl)URL.revokeObjectURL(this.workerUrl);
    if(this.frame)cancelAnimationFrame(this.frame);if(this.renderTimer)clearTimeout(this.renderTimer);if(this.saveTimer)clearTimeout(this.saveTimer);}
}
