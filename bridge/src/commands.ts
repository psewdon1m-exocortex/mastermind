import {Modal, Notice} from "obsidian";
import type MastermindBridge from "./main";

class NoteCommand extends Modal {
  constructor(private bridge:MastermindBridge,private action:"create"|"delete",private target?:string){super(bridge.app);}
  onOpen(){
    this.titleEl.setText(this.action==="create"?"Create note":"Delete note");
    const label=this.contentEl.createEl("label",{text:this.action==="create"?"Vault path":"Note"});
    const input=label.createEl("input",{type:"text",value:this.target||"",placeholder:"Folder/New note.md"});
    input.disabled=this.action==="delete";input.style.width="100%";
    if(this.action==="delete")this.contentEl.createEl("p",{text:"Delete this note from the Vault. Existing shared links will show that the note is unavailable."});
    const error=this.contentEl.createDiv();error.setAttribute("role","alert");
    const button=this.contentEl.createEl("button",{text:this.action==="create"?"Create note":"Delete note",cls:this.action==="delete"?"mod-warning":"mod-cta"});
    const cancel=this.contentEl.createEl("button",{text:"Cancel"});cancel.onclick=()=>this.close();
    button.onclick=async()=>{
      button.disabled=true;button.setText(this.action==="create"?"Creating…":"Deleting…");error.empty();
      try{
        const path=input.value.endsWith(".md")?input.value:input.value+".md";
        const version=this.action==="delete"?await this.bridge.core<{sha256:string}>("/path-version",{path}):undefined;
        new Notice("Mastermind is saving the Vault. The editor will reopen when ready.");
        await this.bridge.core("/note/"+this.action,{path,...(version?{expected_sha256:version.sha256}:{})});this.close();
      }catch(failure){error.setText(failure instanceof Error?failure.message:"The command could not finish.");button.disabled=false;
        button.setText(this.action==="create"?"Create note":"Delete note");}
    };
    if(this.action==="create"){input.focus();input.onkeydown=event=>{if(event.key==="Enter")button.click();};}
    else cancel.focus();
  }
  onClose(){this.contentEl.empty();}
}

export function installCommands(bridge:MastermindBridge){
  bridge.addCommand({id:"create-note",name:"Create note through Mastermind",callback:()=>new NoteCommand(bridge,"create").open()});
  bridge.addCommand({id:"delete-note",name:"Delete current note through Mastermind",checkCallback:checking=>{
    const file=bridge.app.workspace.getActiveFile();if(!file||file.extension!=="md")return false;
    if(!checking)new NoteCommand(bridge,"delete",file.path).open();return true;
  }});
}
