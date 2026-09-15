import MarkdownIt from "markdown-it";
import inventory from "./unicode-fold.json";

const fold=inventory.mapping as Record<string,string>,md=new MarkdownIt("commonmark",{html:true});
export type Ref={start:number;end:number;kind:string;target:string;display:string;exists:boolean};
const rawFold=(value:string)=>[...value].map(c=>fold[c]||c).join("");
export const nameKey=(value:string)=>rawFold(value.normalize("NFC"));
const character=(text:string,pos:number)=>pos<text.length?String.fromCodePoint(text.codePointAt(pos)!):"";
const left=(text:string,pos:number)=>pos===0||(/[\s\p{P}]/u.test([...text.slice(Math.max(0,pos-2),pos)].at(-1)||"")&&!/[.\-_\\]/.test(text[pos-1]));
const right=(text:string,pos:number)=>pos===text.length||(/\s/u.test(character(text,pos))||/\p{P}/u.test(character(text,pos))&&text[pos]!=="_");
const escaped=(text:string,pos:number)=>{let n=0;while(pos>0&&text[--pos]==="\\")n++;return n%2===1;};

export function excluded(text:string):[number,number][]{
  const spans:[number,number][]=[],front=/^---\r?\n[\s\S]*?\r?\n(?:---|\.\.\.)(?:\r?\n|$)/.exec(text);
  if(front)spans.push([0,front[0].length]);
  const offsets=[0];for(const line of text.matchAll(/\r\n|\r|\n/g))offsets.push(line.index+line[0].length);
  for(const token of md.parse(text,{}))if(["fence","code_block","html_block"].includes(token.type)&&token.map)
    spans.push([offsets[token.map[0]]??text.length,offsets[token.map[1]]??text.length]);
  for(const match of text.matchAll(/<!--[\s\S]*?(?:-->|$)/g))spans.push([match.index,match.index+match[0].length]);
  for(const match of text.matchAll(/(?<!`)(`+)(?!`)/g)){
    if(spans.some(([a,b])=>a<=match.index&&match.index<b))continue;
    const tail=text.slice(match.index+match[0].length),closing=new RegExp("(?<!`)"+match[0]+"(?!`)").exec(tail);
    if(closing)spans.push([match.index,match.index+match[0].length+closing.index+closing[0].length]);
  }
  for(const match of text.matchAll(/<[^>\n]+>/g))spans.push([match.index,match.index+match[0].length]);
  return spans;
}

export function parse(text:string,current:Record<string,string>,history:string[]=[],saturn:string[]=[]):Ref[]{
  if(Buffer.byteLength(text)>8*1024**2)throw new Error("Note exceeds portable reference limit");
  const chars=text.split("");for(const [a,b] of excluded(text))for(let i=a;i<b;i++)if(chars[i]!=="\n")chars[i]="\0";
  const visible=chars.join(""),found:Ref[]=[],occupied:[number,number][]=[],positions=new Uint32Array(text.length+1);
  let index=0,point=0;for(const c of text){positions[index]=point;index+=c.length;positions[index]=++point;}
  const add=(start:number,end:number,kind:string,target:string,display:string,exists:boolean)=>found.push({start:positions[start],end:positions[end],kind,target,display,exists});
  for(const match of visible.matchAll(/(!?)\[\[([^\]\r\n]+)\]\]/g)){
    if(escaped(text,match.index))continue;
    let target=match[2].split("|",1)[0].split("#",1)[0].split("^",1)[0].trim().split("/").pop()||"";
    if(target.toLowerCase().endsWith(".md"))target=target.slice(0,-3);if(!target)continue;
    add(match.index,match.index+match[0].length,"internal",nameKey(target),target,Object.hasOwn(current,nameKey(target)));
    occupied.push([match.index,match.index+match[0].length]);
  }
  const names:Record<string,string>=Object.assign(Object.create(null),Object.fromEntries(history.map(name=>[nameKey(name),name])),current);
  const ordered=Object.values(names).map(display=>({display,wanted:nameKey(display),initial:rawFold(character(display,0).normalize("NFD"))[0]}))
    .sort((a,b)=>[...b.wanted].length-[...a.wanted].length);
  for(const match of visible.matchAll(/@/g)){
    const start=match.index;if(escaped(text,start)||!left(text,start)||occupied.some(([a,b])=>a<=start&&start<b))continue;
    const namespace=/^@([a-z]+):/.exec(visible.slice(start));
    if(namespace){
      if(!["chronos","saturn"].includes(namespace[1]))continue;
      const external=/^@([a-z]+):[ \t]+([^\s<>]+)/.exec(visible.slice(start));if(!external)continue;
      let target=external[2],end=start+external[0].length;
      if(external[1]==="saturn"){
        const beginning=start+external[0].length-target.length;
        for(const path of [...saturn].sort((a,b)=>b.length-a.length))if(visible.startsWith(path,beginning)&&right(visible,beginning+path.length)){
          target=path;end=beginning+path.length;break;
        }
        if(target!=="root"&&!target.startsWith("root/"))continue;
      }
      add(start,end,external[1],target,text.slice(start,end),external[1]==="chronos"||saturn.includes(target));continue;
    }
    const initial=rawFold(character(visible,start+1).normalize("NFD"))[0];
    for(const {display,wanted,initial:beginning} of ordered){
      if(initial!==beginning)continue;
      let matched=false;
      for(let end=start+1;end<Math.min(visible.length,start+2+wanted.length*6+16);){
        end+=String.fromCodePoint(visible.codePointAt(end)!).length;
        const part=nameKey(visible.slice(start+1,end));
        if(part===wanted&&right(visible,end)){add(start,end,"internal",wanted,display,Object.hasOwn(current,wanted));matched=true;break;}
        if(part.length>wanted.length+2||part.includes("\0")||part.includes("\n"))break;
      }
      if(matched)break;
    }
  }
  return found.sort((a,b)=>a.start-b.start);
}
