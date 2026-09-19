// Compile the supplied artwork into browser-sized icons. No external renderer
// or runtime SVG subresources are needed by the tab icon.
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('./lib/browser.cjs');
(async()=>{
  const directory=path.resolve(__dirname,'../src/mastermind/web');
  const source='data:image/png;base64,'+fs.readFileSync(path.join(directory,'brand-mark.png')).toString('base64');
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage();
    const icons=await page.evaluate(async source=>{
      const image=new Image();image.src=source;await image.decode();
      const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;
      const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(image,0,0);
      const pixels=ctx.getImageData(0,0,canvas.width,canvas.height).data;
      let left=canvas.width,top=canvas.height,right=0,bottom=0;
      for(let y=0;y<canvas.height;y++)for(let x=0;x<canvas.width;x++)if(pixels[(y*canvas.width+x)*4+3]>32){left=Math.min(left,x);top=Math.min(top,y);right=Math.max(right,x);bottom=Math.max(bottom,y);}
      const w=right-left+1,h=bottom-top+1,results={};
      for(const dimension of [16,32,64]){
        const output=document.createElement('canvas');output.width=output.height=dimension;
        const paint=output.getContext('2d'),scale=(dimension-2)/Math.max(w,h);
        paint.imageSmoothingEnabled=true;paint.imageSmoothingQuality='high';paint.translate(dimension/2,dimension/2);
        // Turn the preceding 180-degree rendition a further 180 degrees.
        // This returns to the supplied artwork orientation, without margins.
        paint.rotate(0);paint.drawImage(image,left,top,w,h,-w*scale/2,-h*scale/2,w*scale,h*scale);
        results[dimension]=output.toDataURL('image/png').split(',')[1];
      }
      return results;
    },source);
    for(const [size,data] of Object.entries(icons))fs.writeFileSync(path.join(directory,`favicon-${size}.png`),Buffer.from(data,'base64'));
    console.log('Built 16, 32 and 64 px tab icons from the supplied artwork.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
