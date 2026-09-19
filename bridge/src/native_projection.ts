import type {LinkCache} from "obsidian";
import type {Ref} from "./portable_parser";

const PREFIX = "mastermind-resource:";

export function resourceLink(ref: Pick<Ref,"kind"|"target">): string {
  // Encode delimiters used by Obsidian, and keep .md from being stripped by its resolver.
  return PREFIX + ref.kind + ":" + encodeURIComponent(ref.target) + ":resource";
}

export function resourceReference(link: string): Ref | undefined {
  const match = /^mastermind-resource:(chronos|saturn):(.*):resource$/.exec(link);
  if (!match) return;
  try {
    const target = decodeURIComponent(match[2]);
    if (!target || target.length > 4096) return;
    return {start:0,end:0,kind:match[1],target,display:"@"+match[1]+": "+target,exists:true};
  } catch {return;}
}

export function nativeReferences(text:string, refs:Ref[]): LinkCache[] {
  // Only retain requested endpoints, not one array entry for every character in a large note.
  const endpoints=[...new Set(refs.flatMap(ref=>[ref.start,ref.end]))].sort((a,b)=>a-b);
  const points=new Map<number,{offset:number;line:number;col:number}>();
  let point=0,offset=0,line=0,column=0;
  for(const end of endpoints){
    while(point<end&&offset<text.length){
      const code=text.codePointAt(offset)!,size=code>0xffff?2:1;
      if(code===10){line++;column=0;}else column+=size;
      offset+=size;point++;
    }
    points.set(end,{offset,line,col:column});
  }
  return refs.filter(ref=>text[points.get(ref.start)!.offset]==="@").map(ref=>{
    const start=points.get(ref.start)!,end=points.get(ref.end)!;
    return{link:ref.kind==="internal"?ref.display:resourceLink(ref),
      original:text.slice(start.offset,end.offset),displayText:ref.display,position:{start,end}};
  });
}
