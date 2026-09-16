const test=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const code=readFileSync(__dirname+'/../extension/popup.js','utf8');
const html=readFileSync(__dirname+'/../extension/popup.html','utf8');
class Element {
  constructor(tag='div'){this.tag=tag;this.textContent='';this.children=[];this.dataset={};this.classList={add(){},remove(){}};}
  addEventListener(name,fn){this[name]=fn;}
  querySelector(selector){return this.children.find(n=>n.className===selector.slice(1));}
  remove() {}
  append(...xs){this.children.push(...xs);}
  replaceChildren(...xs){this.children=xs;}
  setAttribute(k,v){this[k]=v;}
  removeAttribute(k){delete this[k];}
  get text(){return this.textContent+this.children.map(x=>x.text).join(' ');}
  find(text){if(this.textContent===text)return this;for(const c of this.children){const found=c.find(text);if(found)return found;}}
}
async function popup(jobs,extra={}){
  const nodes=new Map([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new Element()]));const decisions=[],copies=[],windowEvents={};
  const P={state:async()=>({config:{theme:'light'},unlocked:true,busy:jobs.some(j=>j.busy)}),jobs:()=>jobs,
    jobThumbnail:extra.jobThumbnail|| (async()=>null),
    acknowledgeJob:async id=>{jobs.find(j=>j.id===id).unread=false;},
    copyJobLink:async id=>{copies.push(id);jobs.find(j=>j.id===id).linkCopied=true;},
    copyShareLink:async id=>copies.push('share:'+id),
    createJobShare:async(id,options)=>{decisions.push(['share',id,options]);jobs.find(j=>j.id===id).shareURL='https://archive.test/share/new';},
    retryDeck:async(id,allow=false)=>decisions.push([id,allow]),
    decideDuplicate:async(id,accept)=>{decisions.push([id,accept]);jobs.find(j=>j.id===id).state=accept?'uploading':'cancelled';}};
  const tiles=()=>{const walk=n=>[n,...n.children.flatMap(walk)];return walk(nodes.get('popup-jobs')).filter(n=>n.className==='job-thumbnail');};
  const ctx={URL:{createObjectURL:()=> 'blob:thumbnail',revokeObjectURL(){}},browser:{runtime:{getBackgroundPage:async()=>({Paperless:P})}},document:{querySelectorAll:tiles,querySelector:()=>tiles().find(n=>!n.dataset.zoomDismissed),getElementById:id=>nodes.get(id),createElement:t=>new Element(t),documentElement:new Element()},matchMedia:()=>({matches:false}),setInterval:()=>1,setTimeout,clearTimeout,window:{addEventListener(name,fn){windowEvents[name]=fn;},close(){},confirm:()=>true}};
  vm.createContext(ctx);vm.runInContext(readFileSync(__dirname+'/../extension/pdf-preview.js','utf8'),ctx);vm.runInContext(readFileSync(__dirname+'/../extension/duplicate-preview.js','utf8'),ctx);await vm.runInContext(code,ctx);return {nodes,decisions,copies,windowEvents};
}
test('popup displays completed import, original cleanup warning and document link until read',async()=>{
  const h=await popup([{id:'j',name:'Rechnung.pdf',state:'success',busy:false,unread:true,cleanupWarning:true,message:'In Paperless archiviert. Original bleibt erhalten.',documentURL:'https://archive.test/documents/12/details'}]);
  const list=h.nodes.get('popup-jobs');assert.ok(list.find('Archiviert · Original erhalten'));
  assert.equal(list.find('In Paperless öffnen').href,'https://archive.test/documents/12/details');
  await list.find('Link kopieren').onclick();assert.deepEqual(h.copies,['j']);
  assert.ok(h.nodes.get('popup-jobs').find('Paperless-Link automatisch kopiert · mit Strg+V einfügen.'));
  assert.match(h.nodes.get('job-summary').textContent,/1 archiviert/);
  await list.find('Als gelesen markieren').onclick();assert.equal(list.find('Als gelesen markieren'),undefined);
});
test('popup keeps duplicate decisions in the job and passes explicit Yes or No',async()=>{
  for(const accept of [false,true]){
    const h=await popup([{id:'j',name:'Rechnung.pdf',state:'duplicate',busy:false,message:'Identische Datei gefunden.',duplicates:[{id:42,title:'Vorhanden',url:'https://archive.test/documents/42/details'}]}]);
    const list=h.nodes.get('popup-jobs');assert.ok(list.find('Entscheidung erforderlich'));
    await list.find(accept?'Ja, trotzdem übernehmen':'Nein, nicht übernehmen').onclick();
    assert.deepEqual(h.decisions,[['j',accept]]);
  }
});
test('popup exposes Paperless and Deck links and a separate Deck retry',async()=>{
  const h=await popup([{id:'j',name:'Bescheid.pdf',state:'success',busy:false,deckWarning:true,deckUncertain:false,message:'In Paperless archiviert. Deck offen.',documentURL:'https://archive.test/documents/12/details',deckLinks:[{name:'Wiedervorlage',url:'https://cloud.test/apps/deck/#/board/1/card/9'}]}]);
  const list=h.nodes.get('popup-jobs');
  assert.ok(list.find('Archiviert · Deck offen'));
  assert.equal(list.find('In Paperless öffnen').href,'https://archive.test/documents/12/details');
  assert.equal(list.find('Deck: Wiedervorlage').href,'https://cloud.test/apps/deck/#/board/1/card/9');
  await list.find('Deck erneut prüfen').onclick();
  assert.deepEqual(h.decisions,[['j',false]]);
});
test('popup exposes public links separately from internal document links',async()=>{
  const h=await popup([{id:'j',name:'Rechnung.pdf',state:'success',busy:false,linkCopied:true,shareURL:'https://archive.test/share/approval',documentURL:'https://archive.test/documents/12/details'}]);
  const list=h.nodes.get('popup-jobs');assert.equal(list.find('Öffentliches Dokument öffnen').href,'https://archive.test/share/approval');
  await list.find('Öffentlichen Link kopieren').onclick();assert.deepEqual(h.copies,['share:j']);
  assert.ok(list.find('Öffentlicher Link automatisch kopiert · mit Strg+V einfügen.'));
});
test('popup creates and copies public links directly for all three durations',async()=>{
  for(const [label,days] of [['7 Tage',7],['30 Tage',30],['Unbefristet',0]]){
    const h=await popup([{id:'j',name:'Rechnung.pdf',state:'success',busy:false,documentId:12,documentURL:'https://archive.test/documents/12/details'}]);
    const list=h.nodes.get('popup-jobs');assert.ok(list.find('Öffentlicher Link:'));
    for(const text of ['7 Tage','30 Tage','Unbefristet'])assert.ok(list.find(text));
    const chosen=list.find(label),pending=chosen.onclick();
    for(const text of ['7 Tage','30 Tage','Unbefristet'])assert.equal(list.find(text).disabled,true);
    await list.find('7 Tage').onclick();await pending;
    assert.equal(h.decisions.length,1);assert.equal(h.decisions[0][0],'share');assert.equal(h.decisions[0][1],'j');assert.equal(h.decisions[0][2].days,days);assert.equal(h.decisions[0][2].archive,false);
    assert.ok(h.nodes.get('popup-jobs').find('Öffentlichen Link kopieren'));
  }
});

test('archived job automatically loads a passive PDF thumbnail',async()=>{
  const calls=[];const h=await popup([{id:'j',name:'Rechnung.pdf',state:'success',documentId:12,documentURL:'https://archive.test/documents/12/details'}],{jobThumbnail:async id=>{calls.push(id);return {};}});
  await new Promise(r=>setImmediate(r));
  const top=h.nodes.get('popup-jobs').children[0].children[0],preview=top.children.find(n=>n.className==='job-thumbnail');
  assert.equal(preview.tag,'div');assert.equal(preview.onclick,undefined);assert.equal(preview.children[0].src,'blob:thumbnail');
  preview.children[0].onload();assert.equal(preview.hidden,false);assert.deepEqual(calls,['j']);
});

test('thumbnail failure is visible while the archived job remains usable',async()=>{
  const h=await popup([{id:'j',name:'PDF',state:'success',documentId:12,documentURL:'https://archive.test/documents/12/details'}],{jobThumbnail:async()=>{throw new Error('HTTP 403');}});
  await new Promise(r=>setImmediate(r));
  assert.ok(h.nodes.get('popup-jobs').find('PDF-Vorschau nicht verfügbar: HTTP 403'));
  assert.ok(h.nodes.get('popup-jobs').find('In Paperless öffnen'));
});

test('hover preview shares the loaded image, supports dismissal and never needs a click',async()=>{
  let reads=0;
  const h=await popup([{id:'j',name:'Rechnung.pdf',state:'success',documentId:12,documentURL:'https://archive.test/documents/12/details'}],{jobThumbnail:async()=>{reads++;return {};}});
  await new Promise(r=>setImmediate(r));
  const preview=h.nodes.get('popup-jobs').children[0].children[0].children.find(n=>n.className==='job-thumbnail');
  preview.children[0].onload();const zoom=preview.children.find(n=>n.className==='thumbnail-zoom');
  assert.equal(zoom.children[0].src,'blob:thumbnail');assert.equal(preview.onclick,undefined);
  let prevented=false;h.windowEvents.keydown({key:'Escape',preventDefault(){prevented=true;},stopPropagation(){}});
  assert.equal(prevented,true);assert.equal(preview.dataset.zoomDismissed,'true');
  preview.onmouseleave();assert.equal(preview.dataset.zoomDismissed,undefined);
  await h.nodes.get('popup-jobs').find('Link kopieren').onclick();assert.equal(reads,1);
});
