import {ItemView, MarkdownView, Notice, TAbstractFile, TFile, WorkspaceLeaf} from "obsidian";
import type MastermindBridge from "./main";
import {contextQuery, RelatedController, RelatedResponse, RelatedState} from "./related_state";

export const RELATED_VIEW="mastermind-related-notes";

export class RelatedNotesView extends ItemView {
  private source?:MarkdownView;
  private controller?:RelatedController;
  private sourceEl?:HTMLElement;
  private statusEl?:HTMLElement;
  private itemsEl?:HTMLElement;
  private refreshEl?:HTMLButtonElement;
  private rendered="";
  private visible=false;
  private refreshed=0;
  constructor(leaf:WorkspaceLeaf,private bridge:MastermindBridge){super(leaf);}
  getViewType(){return RELATED_VIEW;}
  getDisplayText(){return "Related notes";}
  getIcon(){return "lightbulb";}

  async onOpen(){
    this.contentEl.empty();this.contentEl.addClass("mastermind-related");
    const heading=this.contentEl.createDiv({cls:"mastermind-related-heading"});
    heading.createEl("h3",{text:"Related notes"});
    this.refreshEl=heading.createEl("button",{text:"Refresh",attr:{"aria-label":"Refresh related notes"}});
    this.sourceEl=this.contentEl.createDiv({cls:"mastermind-related-source"});
    this.statusEl=this.contentEl.createDiv({cls:"mastermind-related-status",attr:{role:"status","aria-live":"polite"}});
    this.itemsEl=this.contentEl.createEl("ul",{cls:"mastermind-related-list","attr":{"aria-label":"Related notes"}});
    if(this.bridge.portable){
      this.refreshEl.disabled=true;
      this.statusEl.setText("Connect to Mastermind to get suggestions from your note's context. Portable mode does not include this search.");
      return;
    }
    this.controller=new RelatedController((query,signal)=>this.bridge.core<RelatedResponse>("/related-notes",query,signal,25000),
      state=>this.render(state));
    this.refreshEl.onclick=()=>{this.capture();this.controller?.refresh();};
    this.registerEvent(this.app.workspace.on("active-leaf-change",leaf=>{
      if(leaf?.view instanceof MarkdownView)this.source=leaf.view;
      this.capture();
    }));
    this.registerEvent(this.app.workspace.on("file-open",()=>this.capture()));
    this.registerEvent(this.app.workspace.on("editor-change",(_editor,info)=>{
      if(info.file?.path===this.source?.file?.path)this.capture();
    }));
    this.registerEvent(this.app.workspace.on("layout-change",()=>this.capture()));
    const changed=(file:TAbstractFile)=>{if(file===this.source?.file)this.capture();};
    this.registerEvent(this.app.vault.on("modify",changed));
    this.registerEvent(this.app.vault.on("rename",changed));
    this.registerEvent(this.app.vault.on("delete",changed));
    this.registerInterval(window.setInterval(()=>{
      const visible=this.contentEl.isShown()&&!this.bridge.paused;
      if(visible!==this.visible)this.capture();
      if(visible&&Date.now()-this.refreshed>=30000){this.refreshed=Date.now();this.capture();this.controller?.refresh();}
    },1000));
    this.source=this.app.workspace.getActiveViewOfType(MarkdownView)||undefined;
    if(!this.source){
      const file=this.app.workspace.getActiveFile();
      this.source=this.app.workspace.getLeavesOfType("markdown").map(leaf=>leaf.view)
        .find((view):view is MarkdownView=>view instanceof MarkdownView&&view.file===file);
    }
    this.render(this.controller.state);this.capture();
  }

  follow(source:MarkdownView){this.source=source;this.capture();}

  private capture(){
    if(!this.controller)return;
    this.visible=this.contentEl.isShown()&&!this.bridge.paused;
    const active=this.app.workspace.getActiveViewOfType(MarkdownView);
    if(active)this.source=active;
    const file=this.source?.file;
    if(!this.visible||!file||this.app.vault.getFileByPath(file.path)!==file
        ||!this.app.workspace.getLeavesOfType("markdown").some(leaf=>leaf===this.source?.leaf)){
      this.controller.update();
      if(this.bridge.paused)this.statusEl?.setText("Suggestions are paused while the Vault is busy.");
      return;
    }
    const text=this.source!.getViewData();
    const offset=this.source!.editor?.posToOffset(this.source!.editor.getCursor())??text.length;
    if(!text.trim()){
      this.controller.update();this.sourceEl?.setText(file.basename);
      this.statusEl?.setText("Start writing to discover related notes.");return;
    }
    const query=contextQuery(file.path,text,offset);
    // Repeated workspace events with the same context do not reset the debounce.
    const previous=this.controller.state.query;
    if(previous?.path===query.path&&previous.text===query.text&&previous.sampled===query.sampled
        &&previous.focus===query.focus)return;
    this.refreshed=Date.now();this.controller.update(query);
  }

  private render(state:RelatedState){
    this.sourceEl?.setText(state.query?.path??"No note selected");
    const busy=state.phase==="waiting"||state.phase==="loading";
    this.contentEl.toggleClass("is-updating",busy);
    this.itemsEl?.setAttribute("aria-busy",String(busy));
    if(this.refreshEl)this.refreshEl.disabled=state.phase==="loading"||!state.query;
    const messages={idle:"Open a note to discover related ideas.",waiting:"Updating suggestions…",loading:"Finding related notes…",
      ready:state.items.length?(state.degraded?"Suggestions may be incomplete while search is catching up.":"Suggested from this note's content."):
        "No sufficiently related notes found. Keep writing or try again later.",error:"Could not update suggestions. Try Refresh."};
    this.statusEl?.setText(messages[state.phase]+(state.query?.sampled&&state.phase==="ready"?" Based on excerpts from this long note.":""));
    const rendered=JSON.stringify(state.items);
    if(rendered===this.rendered)return;
    this.rendered=rendered;this.itemsEl?.empty();
    for(const item of state.items){
      const row=this.itemsEl!.createEl("li");
      const button=row.createEl("button",{cls:"mastermind-related-item",attr:{"aria-label":"Open "+item.title}});
      button.createEl("strong",{text:item.title});
      button.createEl("span",{text:item.path,cls:"mastermind-related-path"});
      if(item.reason)button.createEl("span",{text:item.reason,cls:"mastermind-related-reason"});
      button.createEl("span",{text:item.excerpt,cls:"mastermind-related-excerpt"});
      button.onclick=async event=>{
        const file=this.app.vault.getFileByPath(item.path);
        if(!(file instanceof TFile)){new Notice("This note is no longer available.");this.controller?.refresh();return;}
        try{
          const leaf=event.ctrlKey||event.metaKey?this.app.workspace.getLeaf("tab"):
            (this.source?.leaf??this.app.workspace.getLeaf(false));
          await leaf.openFile(file);await this.app.workspace.revealLeaf(leaf);
        }catch{new Notice("The related note could not be opened.");}
      };
    }
  }

  async onClose(){this.controller?.dispose();this.contentEl.empty();}
  onunload(){this.controller?.dispose();}
}

export function installRelatedNotes(bridge:MastermindBridge){
  bridge.registerView(RELATED_VIEW,leaf=>new RelatedNotesView(leaf,bridge));
  const open=async()=>{
    const source=bridge.app.workspace.getActiveViewOfType(MarkdownView);
    let leaf=bridge.app.workspace.getLeavesOfType(RELATED_VIEW)[0];
    if(!leaf){const right=bridge.app.workspace.getRightLeaf(false);if(!right)return;leaf=right;await leaf.setViewState({type:RELATED_VIEW,active:true});}
    await bridge.app.workspace.revealLeaf(leaf);
    if(source&&leaf.view instanceof RelatedNotesView)leaf.view.follow(source);
  };
  bridge.addCommand({id:"open-related-notes",name:"Open related notes",callback:open});
  bridge.addRibbonIcon("lightbulb","Related notes",()=>{void open();});
  bridge.register(()=>{for(const leaf of bridge.app.workspace.getLeavesOfType(RELATED_VIEW))leaf.detach();});
}
