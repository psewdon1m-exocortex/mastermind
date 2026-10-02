// Minimal DOM contract for isolated browser tests. This is not the Obsidian
// implementation and must never be described as a native/theme qualification.
HTMLElement.prototype.createEl=function(tag,options={}){
  const element=this.ownerDocument.createElement(tag);
  if(options.text!==undefined)element.textContent=options.text;
  if(options.cls)element.className=options.cls;
  for(const [key,value] of Object.entries(options.attr||{}))element.setAttribute(key,value);
  this.append(element);return element;
};
HTMLElement.prototype.createDiv=function(options){return this.createEl('div',options);};
HTMLElement.prototype.setText=function(text){this.textContent=text;};
HTMLElement.prototype.empty=function(){this.replaceChildren();};
HTMLElement.prototype.addClass=function(name){this.classList.add(name);};
HTMLElement.prototype.toggleClass=function(name,on){this.classList.toggle(name,on);};
HTMLElement.prototype.isShown=function(){return this.checkVisibility();};

export class ButtonComponent {
  constructor(container){this.buttonEl=container.createEl('button');this.buttonEl.type='button';}
  setButtonText(text){this.buttonEl.textContent=text;return this;}
  setDisabled(disabled){this.buttonEl.disabled=disabled;return this;}
  setCta(){return this.setClass('mod-cta');}
  setDestructive(){return this.setClass('mod-destructive');}
  setClass(name){this.buttonEl.classList.add(name);return this;}
  onClick(callback){this.buttonEl.addEventListener('click',callback);return this;}
}
export class TextComponent {
  constructor(container){this.inputEl=container.createEl('input');this.inputEl.type='text';}
  setValue(value){this.inputEl.value=value;return this;}
  getValue(){return this.inputEl.value;}
  setPlaceholder(text){this.inputEl.placeholder=text;return this;}
  setDisabled(disabled){this.inputEl.disabled=disabled;return this;}
}
export class Setting {
  constructor(container){
    this.settingEl=container.createDiv({cls:'setting-item'});
    this.infoEl=this.settingEl.createDiv({cls:'setting-item-info'});
    this.nameEl=this.infoEl.createDiv({cls:'setting-item-name'});
    this.controlEl=this.settingEl.createDiv({cls:'setting-item-control'});
  }
  setName(text){this.nameEl.textContent=text;return this;}
  setClass(name){this.settingEl.classList.add(name);return this;}
  addText(callback){callback(new TextComponent(this.controlEl));return this;}
}
export class Modal {
  constructor(app){
    this.app=app;this.modalEl=document.body.createDiv({cls:'modal'});
    this.titleEl=this.modalEl.createEl('h2');this.contentEl=this.modalEl.createDiv({cls:'modal-content'});
  }
  setTitle(text){this.titleEl.setText(text);}
  open(){this.onOpen();}
  close(){this.onClose();this.modalEl.remove();}
}
export class ItemView {
  constructor(leaf){this.app=leaf.app;this.contentEl=document.querySelector('#related');}
}
export class MarkdownRenderChild {
  constructor(element){this.containerEl=element;}
  load(){this.onload();}
  unload(){this.onunload();}
}
export class Notice {constructor(text){(window.notices??=[]).push(text);}}
export class TAbstractFile {}
export class TFile extends TAbstractFile {}
export class MarkdownView {}
export class WorkspaceLeaf {}
