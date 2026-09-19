import {Plugin, MarkdownView, TextFileView, TFile, EditorSuggest, Editor, EditorPosition,
  EditorSuggestContext, EditorSuggestTriggerInfo, Notice, apiVersion, editorLivePreviewField} from "obsidian";
import {createServer, request, IncomingMessage, ServerResponse, Server} from "node:http";
import {readFileSync, writeFileSync, renameSync, openSync, closeSync, fsyncSync, mkdirSync} from "node:fs";
import {dirname} from "node:path";
import {createHash, randomUUID, timingSafeEqual} from "node:crypto";
import {AsyncLocalStorage} from "node:async_hooks";
import {Decoration, DecorationSet, EditorView, ViewPlugin, ViewUpdate, WidgetType} from "@codemirror/view";
import {StateEffect} from "@codemirror/state";
import {MediaBroker, ResourceCard, openResource} from "./resources";
import {Portable} from "./portable";
import {installCommands} from "./commands";
import {NativeLinks} from "./native_links";
import {installRelatedNotes} from "./related";

type Ref = {start: number; end: number; kind: string; target: string; display: string; exists: boolean};
type Suggestion = {name: string; path: string};
type Activity = {id: string; session_id?: string; kind: string; path: string; occurred_at: number};
type EditSession = {id: string; path: string; last_activity_at: number};
type DurableState = {epoch?: string; events: Activity[]; sessions: Record<string, EditSession>};
const referenceEffect = StateEffect.define<DecorationSet>();

class ResourceWidget extends WidgetType {
  card?:ResourceCard;
  constructor(private bridge:MastermindBridge,private kind:string,private target:string){super();}
  eq(other:ResourceWidget){return this.kind===other.kind&&this.target===other.target;}
  toDOM(){const element=document.createElement("span");this.card=new ResourceCard(element,this.bridge,this.kind,this.target);this.card.load();return element;}
  destroy(){this.card?.unload();}
  ignoreEvent(){return true;}
}

function call<T>(url: string, token: string, data?: unknown, timeout = 10000, signal?:AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    const body = data === undefined ? undefined : Buffer.from(JSON.stringify(data));
    const req = request(url, {method: body ? "POST" : "GET", timeout, signal,
      headers: {Authorization: "Bearer " + token, "Content-Type": "application/json",
        ...(body ? {"Content-Length": body.length} : {})}}, res => {
      const parts: Buffer[] = []; let size = 0;
      res.on("data", (chunk: Buffer) => {
        size += chunk.length;
        if (size > 8 * 1024 * 1024) {res.destroy(); reject(new Error("Response limit")); return;}
        parts.push(chunk);
      });
      res.on("end", () => {
        if (res.statusCode !== 200) {
          let message="Core unavailable";
          try{const value=JSON.parse(Buffer.concat(parts).toString("utf8"));
            if(typeof value.error?.message==="string")message=value.error.message.slice(0,500);}catch{}
          reject(new Error(message));return;
        }
        try {resolve(JSON.parse(Buffer.concat(parts).toString("utf8")));}
        catch {reject(new Error("Invalid Core response"));}
      });
    });
    req.on("error", () => reject(new Error("Core unavailable")));
    req.on("timeout", () => {req.destroy(); reject(new Error("Core timeout"));});
    req.end(body);
  });
}

export function utf16Offset(text: string, codepoint: number): number {
  let offset = 0, count = 0;
  for (const character of text) {
    if (count++ >= codepoint) break;
    offset += character.length;
  }
  return offset;
}

class NoteSuggest extends EditorSuggest<Suggestion> {
  pending?:AbortController;
  constructor(private bridge: MastermindBridge) {super(bridge.app);}
  onTrigger(cursor: EditorPosition, editor: Editor): EditorSuggestTriggerInfo | null {
    const before = editor.getLine(cursor.line).slice(0, cursor.ch);
    const at = before.lastIndexOf("@");
    if (at < 0 || (at > 0 && (!/[\s\p{P}]/u.test(before[at-1]) || /[.\-_\\]/.test(before[at-1])))) return null;
    const query = before.slice(at + 1);
    if (query.includes("@") || query.length > 200) return null;
    return {start: {line: cursor.line, ch: at}, end: cursor, query};
  }
  async getSuggestions(context: EditorSuggestContext): Promise<Suggestion[]> {
    this.pending?.abort();this.pending=new AbortController();
    try {return await this.bridge.core<Suggestion[]>("/suggest", {query: context.query,
      text: context.editor.getValue(), offset: context.editor.posToOffset(context.start)},this.pending.signal);}
    catch {return [];}
  }
  renderSuggestion(item: Suggestion, element: HTMLElement) {
    element.createDiv({text: item.name});
    element.createDiv({text: item.path, cls: "suggestion-note"});
  }
  selectSuggestion(item: Suggestion) {
    if (this.context) this.context.editor.replaceRange("@" + item.name, this.context.start, this.context.end);
    this.close();
  }
  close(){this.pending?.abort();super.close();}
}

export default class MastermindBridge extends Plugin {
  token = "";
  coreUrl = process.env.MASTERMIND_CORE_URL || "http://core:18390";
  statePath = process.env.MASTERMIND_BRIDGE_STATE || "";
  state: DurableState = {events: [], sessions: {}};
  paused = false;
  overlay?: HTMLElement;
  overlays = new Map<Document, HTMLElement>();
  documents = new Set<Document>();
  composing = new Set<Document>();
  server?: Server;
  lastGesture = 0;
  draining = false;
  ready = false;
  statusElement?: HTMLElement;
  nativeContext = new AsyncLocalStorage<string>();
  nativeOperation?: string;
  nativeRename?: typeof this.app.fileManager.renameFile;
  nativeWrites = new Set<Promise<unknown>>();
  activePath?: string;
  media=new MediaBroker(this);
  portable?:Portable;
  nativeLinks?:NativeLinks;

  core<T>(route: string, data?: unknown, signal?:AbortSignal, timeout=10000): Promise<T> {
    if(this.portable)return this.portable.request<T>(route,data);
    return call<T>(this.coreUrl + "/internal/bridge" + route, this.token, data,timeout,signal);
  }

  async onload() {
    this.paused=process.env.MASTERMIND_START_PAUSED==="1";
    const tokenFile = process.env.MASTERMIND_BRIDGE_TOKEN_FILE;
    if (!tokenFile&&!this.statePath){this.portable=new Portable(this.app);await this.portable.loaded;}
    else if(!tokenFile||!this.statePath)throw new Error("Mastermind Bridge runtime configuration is incomplete");
    if(tokenFile)this.token = readFileSync(tokenFile, "utf8");
    if(!this.portable){
    try {this.state = JSON.parse(readFileSync(this.statePath, "utf8"));}
    catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw new Error("Bridge state requires recovery");
    }
    }
    this.statusElement = this.addStatusBarItem();
    this.statusElement.addClass("mastermind-status");
    this.statusElement.setText(this.portable?"Mastermind · portable copy":"Mastermind · connecting");
    if(this.portable){
      const original=this.app.fileManager.renameFile.bind(this.app.fileManager);
      const portableRename:typeof original=async(file,path)=>{
        if(file instanceof TFile&&file.extension==="md")return this.portable!.rename(file,path,()=>original(file,path));
        await original(file,path);this.portable!.invalidate();await this.portable!.saveHistory();
      };
      this.app.fileManager.renameFile=portableRename;
      this.register(()=>{if(this.app.fileManager.renameFile===portableRename)this.app.fileManager.renameFile=original;});
      const remember=(file:unknown)=>{
        if(file instanceof TFile&&file.extension==="md")this.portable!.history.add(file.basename);
        this.portable!.invalidate();void this.portable!.saveHistory().catch(()=>new Notice("Portable reference history could not be saved."));
      };
      this.registerEvent(this.app.vault.on("create",remember));
      this.registerEvent(this.app.vault.on("delete",remember));
      this.registerEvent(this.app.vault.on("rename",remember));
    }else{this.installManagedRename();installCommands(this);}
    this.nativeLinks=this.addChild(new NativeLinks(this));
    installRelatedNotes(this);
    const registerDocument = (doc: Document) => {
      if (this.documents.has(doc)) return;
      this.documents.add(doc);
      const gesture = (event: Event) => {
      if (this.paused) {event.preventDefault(); event.stopImmediatePropagation(); return;}
      if (event.isTrusted) this.lastGesture = Date.now();
      };
      for (const name of ["beforeinput", "keydown", "pointerdown", "paste", "drop"] as const) {
        this.registerDomEvent(doc, name, gesture, {capture: true});
      }
      this.registerDomEvent(doc, "compositionstart", () => this.composing.add(doc));
      this.registerDomEvent(doc, "compositionend", () => this.composing.delete(doc));
      if (this.paused) this.freeze("Vault is paused while Mastermind saves a consistent state.");
    };
    registerDocument(document);
    this.registerEvent(this.app.workspace.on("window-open", (_workspaceWindow, win) => registerDocument(win.document)));
    this.registerEvent(this.app.workspace.on("editor-change", (_editor, info) => {
      if (this.portable || this.paused || Date.now()-this.lastGesture > 1500 || !info.file) return;
      const path = info.file.path;
      const session = this.state.sessions[path] || {id: randomUUID(), path, last_activity_at: Date.now()/1000};
      session.last_activity_at = Date.now()/1000;
      this.state.sessions[path] = session;
      this.persist();
    }));
    this.registerEvent(this.app.workspace.on("active-leaf-change", () => {
      const next = this.app.workspace.getActiveFile()?.path;
      if (!this.paused && this.activePath && this.activePath !== next) this.closeEditSession(this.activePath);
      this.activePath = next;
    }));
    this.registerEvent(this.app.workspace.on("layout-change", () => {
      if (this.paused) return;
      const opened = new Set<string>();
      this.app.workspace.iterateAllLeaves(leaf => {
        if (leaf.view instanceof TextFileView && leaf.view.file) opened.add(leaf.view.file.path);
      });
      for (const path of Object.keys(this.state.sessions)) if (!opened.has(path)) this.closeEditSession(path);
    }));
    this.registerEvent(this.app.vault.on("create", file => {
      if (!this.portable && file instanceof TFile && file.extension === "md" && !this.paused && Date.now()-this.lastGesture < 1500) {
        this.state.events.push({id: randomUUID(), kind: "CREATE", path: file.path, occurred_at: Date.now()/1000});
        this.persist();
      }
    }));
    this.registerEditorSuggest(new NoteSuggest(this));
    this.registerHoverLinkSource("mastermind-bridge", {display: "Mastermind", defaultMod: true});
    this.registerMarkdownPostProcessor(async (element, context) => {
      const nodes: Text[] = [];
      const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        const node = walker.currentNode as Text;
        if (node.data.includes("@") && !node.parentElement?.closest("a,code,pre,script,style,.mastermind-reference")) nodes.push(node);
      }
      for (const node of nodes) {
        try {
          const text = node.data;
          const refs = await this.references(text);
          if (!node.isConnected || node.data !== text) continue;
          const fragment = document.createDocumentFragment(); let offset = 0;
          for (const ref of refs) {
            const start = utf16Offset(text, ref.start), end = utf16Offset(text, ref.end);
            fragment.append(text.slice(offset, start));
            const link = document.createElement("span");
            link.className = "internal-link mastermind-reference" + (ref.exists ? "" : " is-unresolved");
            link.textContent = text.slice(start, end);
            link.tabIndex = 0; link.setAttribute("role", "link");
            link.onclick = () => void this.openReference(ref, context.sourcePath);
            link.onkeydown = event => {if (event.key === "Enter") void this.openReference(ref, context.sourcePath);};
            link.onmouseenter = event => this.hover(ref, link, event, context.sourcePath);
            fragment.append(link); offset = end;
            if(ref.kind!=="internal"){
              const card=document.createElement("span");fragment.append(card);
              context.addChild(new ResourceCard(card,this,ref.kind,ref.target));
            }
          }
          fragment.append(text.slice(offset)); node.replaceWith(fragment);
        } catch { /* Offline references remain readable literal Markdown. */ }
      }
    });
    const bridge = this;
    this.registerEditorExtension(ViewPlugin.fromClass(class {
      decorations: DecorationSet = Decoration.none;
      timer?: ReturnType<typeof setTimeout>;
      generation = 0;
      constructor(public view: EditorView) {this.schedule();}
      update(update: ViewUpdate) {
        this.decorations = this.decorations.map(update.changes);
        for (const transaction of update.transactions) for (const effect of transaction.effects) {
          if (effect.is(referenceEffect)) this.decorations = effect.value;
        }
        if (update.docChanged || update.viewportChanged) this.schedule();
      }
      schedule() {
        if (this.timer) clearTimeout(this.timer);
        const generation = ++this.generation;
        this.timer = setTimeout(async () => {
          const text = this.view.state.doc.toString();
          try {
            const refs = await bridge.references(text);
            if (generation !== this.generation || text !== this.view.state.doc.toString()) return;
            const ranges=refs.map(ref => Decoration.mark({
              class: "internal-link mastermind-reference" + (ref.exists ? "" : " is-unresolved"),
              attributes: {"data-mastermind-reference": JSON.stringify(ref)}
            }).range(utf16Offset(text, ref.start), utf16Offset(text, ref.end)));
            if(this.view.state.field(editorLivePreviewField,false))for(const ref of refs){
              if(ref.kind!=="internal")ranges.push(Decoration.widget({widget:new ResourceWidget(bridge,ref.kind,ref.target),side:1})
                .range(utf16Offset(text,ref.end)));
            }
            const decorations = Decoration.set(ranges, true);
            this.view.dispatch({effects: referenceEffect.of(decorations)});
          } catch {
            if (generation === this.generation) this.view.dispatch({effects: referenceEffect.of(Decoration.none)});
          }
        }, 250);
      }
      destroy() {if (this.timer) clearTimeout(this.timer); this.generation++;}
    }, {decorations: value => value.decorations, eventHandlers: {
      mousedown(event) {
        const target = (event.target as HTMLElement).closest<HTMLElement>("[data-mastermind-reference]");
        if (target && (event.ctrlKey || event.metaKey)) {
          event.preventDefault();
          void bridge.openReference(JSON.parse(target.dataset.mastermindReference!), bridge.app.workspace.getActiveFile()?.path || "");
          return true;
        }
        return false;
      }
    }}));
    if(!this.portable){
      this.registerInterval(window.setInterval(() => void this.drain(), 1000));
      this.server = createServer((req, res) => {void this.handle(req, res);});
      this.server.listen(8092, "127.0.0.1");
    }
    this.app.workspace.onLayoutReady(() => {this.ready = true;
      if(this.portable){this.portable.inventory();void this.portable.saveHistory().catch(()=>new Notice("Portable history could not be saved."));}
      void this.drain();});
  }

  async references(text: string): Promise<Ref[]> {
    const refs = await this.core<Ref[]>("/references", {text});
    return refs.filter(ref => text[utf16Offset(text, ref.start)] === "@");
  }

  installManagedRename() {
    const adapter = this.app.vault.adapter;
    const originalRename = this.app.fileManager.renameFile.bind(this.app.fileManager);
    this.nativeRename = originalRename;
    const bridge = this;
    const managedRename: typeof originalRename = async (file, newPath) => {
      if (bridge.nativeContext.getStore()) return originalRename(file, newPath);
      if (bridge.paused) throw new Error("Vault is paused");
      const version = await call<{sha256:string}>(bridge.coreUrl+"/internal/bridge/path-version",bridge.token,{path:file.path},180000);
      await call(bridge.coreUrl + "/internal/bridge/rename", bridge.token,
        {old_path: file.path, new_path: newPath, expected_sha256: version.sha256}, 180000);
    };
    this.app.fileManager.renameFile = managedRename;
    this.register(() => {if (this.app.fileManager.renameFile === managedRename) this.app.fileManager.renameFile = originalRename;});

    const write = adapter.write.bind(adapter), rename = adapter.rename.bind(adapter);
    const process = adapter.process.bind(adapter), append = adapter.append.bind(adapter);
    const writeBinary = adapter.writeBinary.bind(adapter);
    const managedWrite: typeof write = async (path, data, options) => {
      if (!bridge.nativeOperation || path.startsWith(".obsidian/")) return write(path, data, options);
      if (bridge.nativeContext.getStore() !== bridge.nativeOperation) throw new Error("Vault is paused for rename");
      const action = (async () => {
        const before = await adapter.exists(path) ? await adapter.read(path) : null;
        await bridge.core("/native-intent", {operation_id: bridge.nativeOperation,
          writes: [{path, text: data}], expected: {[path]: before === null ? null : createHash("sha256").update(before).digest("hex")}});
        await write(path, data, options);
      })();
      bridge.nativeWrites.add(action);
      try {await action;} finally {bridge.nativeWrites.delete(action);}
    };
    const managedAdapterRename: typeof rename = async (oldPath, newPath) => {
      if (!bridge.nativeOperation) return rename(oldPath, newPath);
      if (bridge.nativeContext.getStore() !== bridge.nativeOperation) throw new Error("Vault is paused for rename");
      if (await adapter.exists(newPath)) throw new Error("Rename destination exists");
      await call(bridge.coreUrl+"/internal/bridge/native-intent",bridge.token,{operation_id: bridge.nativeOperation,
        move:[oldPath,newPath]},180000);
      await rename(oldPath, newPath);
    };
    adapter.write = managedWrite;
    adapter.rename = managedAdapterRename;
    const managedProcess: typeof process = async (path, fn, options) => {
      if (!bridge.nativeOperation || path.startsWith(".obsidian/")) return process(path, fn, options);
      if (bridge.nativeContext.getStore() !== bridge.nativeOperation) throw new Error("Vault is paused for rename");
      const action = (async () => {
        const before = await adapter.read(path), after = fn(before);
        await bridge.core("/native-intent", {operation_id: bridge.nativeOperation, writes: [{path, text: after}],
          expected: {[path]: createHash("sha256").update(before).digest("hex")}});
        return process(path, current => {
          if (current !== before) throw new Error("A concurrent writer changed this note");
          return after;
        }, options);
      })();
      bridge.nativeWrites.add(action);
      try {return await action;} finally {bridge.nativeWrites.delete(action);}
    };
    const managedAppend: typeof append = async (path, data, options) => {
      if (!bridge.nativeOperation) return append(path, data, options);
      await managedProcess(path, before => before+data, options);
    };
    const managedBinary: typeof writeBinary = async (path, data, options) => {
      if (!bridge.nativeOperation) return writeBinary(path, data, options);
      if (!path.endsWith(".md")) throw new Error("Unexpected binary write during native rename");
      const text = new TextDecoder("utf-8", {fatal: true}).decode(data);
      await managedWrite(path, text, options);
    };
    adapter.process = managedProcess; adapter.append = managedAppend; adapter.writeBinary = managedBinary;
    this.register(() => {if (adapter.write === managedWrite) adapter.write = write;
      if (adapter.rename === managedAdapterRename) adapter.rename = rename;
      if (adapter.process === managedProcess) adapter.process = process;
      if (adapter.append === managedAppend) adapter.append = append;
      if (adapter.writeBinary === managedBinary) adapter.writeBinary = writeBinary;});
  }

  async runNativeRename(data: {operation_id: string; old_path: string; new_path: string}) {
    if (!this.paused || this.nativeOperation || !this.nativeRename) throw new Error("Rename barrier is not prepared");
    // This is a documented native option, not a replacement native link parser.
    const configPath = ".obsidian/app.json";
    const config = JSON.parse(await this.app.vault.adapter.read(configPath));
    if (config.alwaysUpdateLinks !== true) throw new Error("Enable Automatically update internal links in Obsidian Settings");
    const file = this.app.vault.getAbstractFileByPath(data.old_path);
    if (!file) throw new Error("Source note is unavailable");
    this.nativeOperation = data.operation_id;
    try {
      await this.nativeContext.run(data.operation_id, () => this.nativeRename!(file, data.new_path));
      while (this.nativeWrites.size) await Promise.all([...this.nativeWrites]);
      for(const [path,session] of Object.entries(this.state.sessions)){
        if(path===data.old_path||path.startsWith(data.old_path+"/")){
          delete this.state.sessions[path];session.path=data.new_path+path.slice(data.old_path.length);
          this.state.sessions[session.path]=session;
        }
      }
      this.persist();
      return {renamed: true};
    } catch (error) {throw error;}
  }

  closeEditSession(path: string) {
    const session = this.state.sessions[path];
    if (!session) return;
    this.state.events.push({id: session.id, session_id: session.id, kind: "EDIT", path,
      occurred_at: session.last_activity_at});
    delete this.state.sessions[path];
    this.persist();
  }

  async openReference(ref: Ref, source: string) {
    if (ref.kind === "internal") {
      if (ref.exists) await this.app.workspace.openLinkText(ref.display, source, false);
      else new Notice("This note is unavailable.");
    } else {
      openResource(this,ref.kind,ref.target);
    }
  }

  hover(ref: Ref, target: HTMLElement, event: MouseEvent, source: string) {
    if (ref.kind === "internal") this.app.workspace.trigger("hover-link", {
      event, source: "mastermind-bridge", hoverParent: this, targetEl: target,
      linktext: ref.display, sourcePath: source,
    });
  }

  persist() {
    if(this.portable)return;
    const text = JSON.stringify(this.state);
    if (Buffer.byteLength(text) > 10*1024*1024) {
      this.freeze("Activity queue is full. Waiting for Mastermind Core.");
      throw new Error("Activity queue full");
    }
    mkdirSync(dirname(this.statePath), {recursive: true, mode: 0o700});
    const temporary = this.statePath + ".tmp";
    writeFileSync(temporary, text, {mode: 0o600});
    const fd = openSync(temporary, "r+"); fsyncSync(fd); closeSync(fd);
    renameSync(temporary, this.statePath);
  }

  async drain() {
    if(this.portable)return;
    if (this.draining) return;
    this.draining = true;
    try {
      const now = Date.now()/1000;
      for (const [path, session] of Object.entries(this.state.sessions)) {
        if (now-session.last_activity_at >= 300) {
          this.closeEditSession(path);
        }
      }
      this.persist();
      const batch = this.state.events.slice(0, 100);
      const response = await this.core<{reset: boolean; epoch: string}>("/events", {
        epoch: this.state.epoch, events: batch, sessions: Object.values(this.state.sessions), version: this.manifest.version});
      if (response.reset) {
        // First connection adopts the identity; a restore discards the obsolete Runtime queue.
        if (this.state.epoch) this.state = {events: [], sessions: {}};
        this.state.epoch = response.epoch;
        this.persist();
        return;
      }
      const ids = new Set(batch.map(event => event.id));
      this.state.events = this.state.events.filter(event => !ids.has(event.id));
      this.persist(); this.statusElement?.setText("Mastermind · connected");
    } catch {this.statusElement?.setText("Mastermind · offline, activity queued");}
    finally {this.draining = false;}
  }

  freeze(message: string) {
    this.paused = true;
    for (const doc of this.documents) {
      if (!doc.defaultView || doc.defaultView.closed) {this.documents.delete(doc); continue;}
      let overlay = this.overlays.get(doc);
      if (!overlay) {overlay = doc.body.createDiv({cls: "mastermind-pause"}); this.overlays.set(doc, overlay);}
      overlay.setText(message);
    }
  }

  unfreeze() {
    this.paused = false;
    this.nativeOperation = undefined;
    for (const overlay of this.overlays.values()) overlay.remove();
    this.overlays.clear();
  }

  async quiesce() {
    if ([...this.composing].some(doc => doc.defaultView && !doc.defaultView.closed)) {
      throw new Error("An input composition is still active");
    }
    this.freeze("Vault is paused while Mastermind saves a consistent state.");
    try {
      const views: TextFileView[] = [];
      this.app.workspace.iterateAllLeaves(leaf => {if (leaf.view instanceof TextFileView) views.push(leaf.view);});
      const values = new Map<string, string>();
      for (const view of views) {
        if (!view.file) continue;
        const value = view.getViewData();
        if (values.has(view.file.path) && values.get(view.file.path) !== value) throw new Error("Conflicting editor buffers");
        values.set(view.file.path, value);
      }
      const save = async () => {for (const view of views) await view.save();};
      if (this.nativeOperation) await this.nativeContext.run(this.nativeOperation, save);
      else await save();
      for (const [path, value] of values) {
        const file = this.app.vault.getFileByPath(path);
        if (!file || await this.app.vault.read(file) !== value) throw new Error("Unsaved buffer");
      }
      this.persist();
      return {buffers_verified: true, version: this.manifest.version, activity: {
        epoch: this.state.epoch, events: [...this.state.events], sessions: Object.values(this.state.sessions)}};
    } catch (error) {
      this.unfreeze();
      throw error;
    }
  }

  async handle(req: IncomingMessage, res: ServerResponse) {
    if(this.media.handle(req,res))return;
    const actual = Buffer.from(req.headers.authorization || ""), expected = Buffer.from("Bearer " + this.token);
    if (actual.length !== expected.length || !timingSafeEqual(actual, expected)) {res.writeHead(401).end(); return;}
    try {
      let body = "";
      for await (const chunk of req) {
        body += chunk.toString("utf8");
        if (Buffer.byteLength(body) > 64*1024) throw new Error("Body limit");
      }
      const data = body ? JSON.parse(body) : {};
      let result: unknown;
      if (req.url === "/status" && req.method === "GET") {
        const graphs: unknown[]=[];
        this.app.workspace.iterateAllLeaves(leaf=>{
          const view=leaf.view as typeof leaf.view & {renderer?:{nodes:unknown[];links:unknown[]}};
          if(["graph","localgraph"].includes(view.getViewType()))graphs.push({type:view.getViewType(),
            nodes:view.renderer?.nodes.length||0,edges:view.renderer?.links.length||0,visible:view.containerEl.isShown()});
        });
        result = {ready: this.ready, version: this.manifest.version, protocol_version: 1, obsidian_version: apiVersion, paused: this.paused,
          activity_pending: this.state.events.length, graphs, native_references:this.nativeLinks?.diagnostics(),
          resources:[...ResourceCard.active].map(card=>card.diagnostics()),
          media:{responses:this.media.responses,range_responses:this.media.rangeResponses,transferred_bytes:this.media.transferredBytes}};
      }
      else if (req.url === "/quiesce" && req.method === "POST") result = await this.quiesce();
      else if (req.url === "/unfreeze" && req.method === "POST") {this.unfreeze(); result = {resumed: true};}
      else if (req.url === "/native-rename" && req.method === "POST") result = await this.runNativeRename(data);
      else if (req.url === "/open" && req.method === "POST") {
        const file = this.app.vault.getFileByPath(data.path);
        if (!file) throw new Error("Note unavailable");
        await this.app.workspace.getLeaf(false).openFile(file); result = {opened: true};
      } else {res.writeHead(404).end(); return;}
      res.writeHead(200, {"Content-Type": "application/json", "Cache-Control": "no-store"}).end(JSON.stringify(result));
    } catch {res.writeHead(423, {"Content-Type": "application/json"}).end('{"error":"VAULT_BUSY"}');}
  }

  onunload() {this.ready = false; this.persist(); this.server?.close(); this.unfreeze();
    for(const token of this.media.capabilities.keys())this.media.revoke(token);}
}
