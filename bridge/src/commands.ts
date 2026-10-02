import {ButtonComponent, Modal, Notice, Setting, TextComponent} from "obsidian";
import type MastermindBridge from "./main";

class NoteCommand extends Modal {
  constructor(private bridge:MastermindBridge,private action:"create"|"delete",private target?:string){super(bridge.app);}
  onOpen(){
    this.titleEl.setText(this.action==="create"?"Create note":"Delete note");
    this.contentEl.addClass("mastermind-command");
    const label=this.action==="create"?"Vault path":"Note";
    let input!:TextComponent;
    new Setting(this.contentEl).setName(label).setClass("mastermind-command-path").addText(component=>{
      input=component.setValue(this.target||"").setPlaceholder("Folder/New note.md").setDisabled(this.action==="delete");
      input.inputEl.setAttribute("aria-label",label);
    });
    if(this.action==="delete")this.contentEl.createEl("p",{text:"Delete this note from the Vault. Existing shared links will show that the note is unavailable."});
    const error=this.contentEl.createDiv({cls:"mastermind-command-error",attr:{role:"alert"}});
    const actions=this.contentEl.createDiv({cls:"mastermind-command-actions"});
    const cancel=new ButtonComponent(actions).setButtonText("Cancel").onClick(()=>this.close());
    const button=new ButtonComponent(actions).setButtonText(this.action==="create"?"Create note":"Delete note");
    if(this.action==="delete")button.setDestructive();else button.setCta();
    button.onClick(async()=>{
      if(button.buttonEl.disabled)return;
      button.setDisabled(true).setButtonText(this.action==="create"?"Creating…":"Deleting…");error.empty();
      try{
        const value=input.getValue(),path=value.endsWith(".md")?value:value+".md";
        const version=this.action==="delete"?await this.bridge.core<{sha256:string}>("/path-version",{path}):undefined;
        new Notice("Mastermind is saving the Vault. The editor will reopen when ready.");
        await this.bridge.core("/note/"+this.action,{path,...(version?{expected_sha256:version.sha256}:{})});this.close();
      }catch(failure){error.setText(failure instanceof Error?failure.message:"The command could not finish.");
        button.setDisabled(false).setButtonText(this.action==="create"?"Create note":"Delete note");}
    });
    if(this.action==="create"){
      input.inputEl.focus();input.inputEl.onkeydown=event=>{
        if(event.key==="Enter"&&!event.isComposing){event.preventDefault();button.buttonEl.click();}
      };
    }else cancel.buttonEl.focus();
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
