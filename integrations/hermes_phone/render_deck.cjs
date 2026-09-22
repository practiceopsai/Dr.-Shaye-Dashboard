// Content is data; never evaluate model output as JavaScript.
const fs = require('fs');
const PptxGenJS = require('pptxgenjs');
const [source, destination] = process.argv.slice(2);
const content = JSON.parse(fs.readFileSync(source, 'utf8'));
const deck = new PptxGenJS();
deck.layout = 'LAYOUT_WIDE'; deck.author = 'Eli'; deck.title = content.title;
deck.subject = 'Source-backed research'; deck.lang = 'en-US';
const colors = {dark:'22392F', cream:'F5F3EA', accent:'B5CB87', muted:'5E6D62'};
function page(title, dark=false) {
  const slide = deck.addSlide(); slide.background = {color:dark?colors.dark:colors.cream};
  slide.addText(title,{x:.65,y:.55,w:12,h:1.2,fontFace:'Georgia',fontSize:32,
    color:dark?colors.cream:colors.dark,margin:0,breakLine:false,fit:'shrink'});
  slide.addText('ELI  /  RESEARCH BRIEF',{x:.65,y:6.85,w:9,h:.2,fontFace:'Calibri',fontSize:10,
    color:dark?colors.accent:colors.muted,margin:0});
  slide.addText(String(deck._slides.length),{x:12,y:6.85,w:.6,h:.2,fontSize:10,color:dark?colors.accent:colors.muted,margin:0});
  return slide;
}
const title = page(content.title,true);
title.addShape(deck.ShapeType.rect,{x:.65,y:2.2,w:.9,h:.9,line:{color:colors.accent},fill:{color:colors.accent}});
title.addText('01',{x:.65,y:2.4,w:.9,h:.4,align:'center',fontSize:22,bold:true,color:colors.dark,margin:0});
title.addText(content.summary,{x:2,y:2.2,w:10.2,h:3.6,fontFace:'Calibri',fontSize:22,color:colors.cream,margin:0,fit:'shrink',valign:'top'});
for (const [index, section] of content.sections.entries()) {
  const slide=page(section.heading);
  if(index%2===0) {
    slide.addShape(deck.ShapeType.rect,{x:.65,y:2.1,w:1.2,h:1.2,line:{color:colors.dark},fill:{color:colors.dark}});
    slide.addText(String(index+1).padStart(2,'0'),{x:.65,y:2.45,w:1.2,h:.5,fontFace:'Georgia',fontSize:28,color:colors.accent,align:'center',margin:0});
    slide.addText(section.text,{x:2.25,y:2.1,w:10.3,h:4.1,fontFace:'Calibri',fontSize:22,color:colors.dark,margin:0,fit:'shrink',valign:'top',paraSpaceAfterPt:12});
  } else {
    const panelHeight=section.text.length<400?2.6:4.3;
    slide.addShape(deck.ShapeType.rect,{x:.65,y:2,w:12,h:panelHeight,line:{color:colors.dark},fill:{color:colors.dark}});
    slide.addText(section.text,{x:1.15,y:2.45,w:11,h:panelHeight-.9,fontFace:'Calibri',fontSize:22,color:colors.cream,margin:0,fit:'shrink',valign:'top',paraSpaceAfterPt:12});
  }
}
for (let start=0;start<content.sources.length;start+=5) {
  const slide=page('Sources',true);
  content.sources.slice(start,start+5).forEach((item,index)=>{
    slide.addText(item.title,{x:.8,y:1.95+index*.9,w:11.5,h:.35,fontSize:16,bold:true,color:colors.accent,margin:0,fit:'shrink'});
    slide.addText(item.url,{x:.8,y:2.32+index*.9,w:11.5,h:.3,fontSize:12,color:colors.cream,margin:0,hyperlink:{url:item.url},fit:'shrink'});
  });
}
deck.writeFile({fileName:destination}).catch(error=>{process.stderr.write(error.message);process.exitCode=1;});
