const test = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const appCode = readFileSync(__dirname + '/../extension/app.js','utf8');
const html = readFileSync(__dirname + '/../extension/app.html','utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve,reject; const promise=new Promise((r,j)=>{resolve=r;reject=j;});return {promise,resolve,reject}; }
// A minimal DOM test double. Runs the actual app script, never a substitute UI.
// It checks startup/event behavior, not CSS or native Firefox widget rendering.
class Element {
  constructor() { this.children=[];this.events={};this.textContent='';this.value='';this.style={};this.dataset={};this.hidden=false;this.disabled=false;this.checked=false;this.open=false;this.clicked=0; const classes=new Set();this.classList={add:x=>classes.add(x),remove:x=>classes.delete(x),toggle:(x,on)=>on?classes.add(x):classes.delete(x)}; }
  remove() {}
  removeAttribute(name) { delete this[name]; }
  append(...xs) { this.children.push(...xs); }
  replaceChildren(...xs) { this.children=xs; }
  addEventListener(type,fn) { this.events[type]=fn; }
  setAttribute(name,value) { this[name]=value; }
  querySelector() { return new Element(); }
  focus() {}
  click() {this.clicked++;}
  showModal() { this.open=true; }
  close() { this.open=false; }
}
async function ui({metadata,source,download,intent={url:'https://mail.test/attachment.pdf'},unlocked=true,profiles=[],precheck,series={enabled:false,inherit:true,assignment:null}}={}) {
  const nodes=new Map([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new Element()]));
  const calls=[],windowEvents={};
  const P={saveSeriesOptions:async value=>Object.assign(series,value),state:async()=>({series,config:{base:'https://archive.test/',profiles,theme:'light'},unlocked,helperAllowed:false}),jobs:()=>[],
    assignmentSuggestions:async()=>[],clearAssignmentHistory:async()=>{},
    precheckSource:async(...args)=>{calls.push(['precheck',...args]);return precheck || {state:'clear',matches:[]};},
    titleHistory:async()=>['Rechnung Strom','Rechnung Wasser'],rememberTitle:async(...args)=>calls.push(['remember-title',...args]),clearTitleHistory:async()=>calls.push('clear-titles'),
    metadata:()=>{calls.push('metadata');return metadata || Promise.resolve({tags:[],correspondents:[],document_types:[],storage_paths:[],warnings:[]});},
    intent:async()=>{calls.push('intent');return intent;},
    sourceURL:async url=>{calls.push(['source',url]);return source ? await source : {id:'file-1',name:'attachment.pdf',size:1234,kind:'web',canDelete:false};},
    chooseFile:async file=>{calls.push(['picker',file.name]);return {id:'picked-'+calls.filter(c=>Array.isArray(c)&&c[0]==='picker').length,name:file.name,size:4321,kind:'picker',canDelete:false};},
    waitForPDFDownload:async(since,name)=>{calls.push(['wait-download',since,name]);return download || {id:9,path:'/tmp/edited-with-notes.pdf',name:'edited-with-notes.pdf'};},
    chooseDownload:async id=>{calls.push(['choose-download',id]);return {id:'download-1',name:'edited-with-notes.pdf',size:4321,kind:'download',canDelete:true};},
    beginBatch:async()=>{calls.push('begin-batch');return 'batch-1';},sealBatch:async id=>calls.push(['seal-batch',id]),
    start:async(...args)=>{calls.push(['start',...args]);return 'job-1';},
    documentAssignment:async(id,base)=>{calls.push(['duplicate-assignment',id,base]);return {tags:[2,3],correspondent:5,document_type:6,storage_path:7,custom_fields:{10:'EUR10',11:false,12:[42,43]}};},
    copyJobLink:async id=>calls.push(['copy-link',id]),
    removeSource:async id=>calls.push(['release',id]),openPage:async()=>{}};
  const location=new URL('moz-extension://test/app.html?compact=1&intent=ticket');
  const ctx={URL,document:{getElementById:id=>nodes.get(id),createElement:()=>new Element(),querySelector:()=>new Element(),querySelectorAll:()=>[],body:new Element(),documentElement:new Element()},
    browser:{runtime:{getManifest:()=>JSON.parse(readFileSync(__dirname+'/../extension/manifest.json','utf8')),getBackgroundPage:async()=>({Paperless:P})},storage:{session:{get:async()=>({}),set:async value=>calls.push(['session-set',value])}}},
    location,history:{replaceState:(_,__,url)=>{location.href=new URL(url,location).href;}},
    matchMedia:()=>({matches:false,addEventListener(){}}),Option:class extends Element {constructor(text,value){super();this.textContent=text;this.value=value;}},
    setInterval:()=>1,setTimeout,clearTimeout,clearInterval(){},console};
  ctx.window={addEventListener:(event,fn)=>{windowEvents[event]=fn;},close(){calls.push('window-close');}};
  vm.createContext(ctx);vm.runInContext(readFileSync(__dirname + '/../extension/pdf-preview.js','utf8'),ctx);vm.runInContext(readFileSync(__dirname + '/../extension/duplicate-preview.js','utf8'),ctx);vm.runInContext(readFileSync(__dirname + '/../extension/keyboard.js','utf8'),ctx);vm.runInContext(readFileSync(__dirname + '/../extension/custom-fields.js','utf8'),ctx);const startup=vm.runInContext(appCode,ctx);
  await tick();return {nodes,calls,startup,P,windowEvents,document:ctx.document};
}
test('incoming PDF is adopted while the metadata API is still waiting',async()=>{
  const metadata=deferred();const h=await ui({metadata:metadata.promise});
  assert.ok(h.calls.some(c=>Array.isArray(c)&&c[0]==='source'),'PDF must not wait for metadata');
  assert.equal(h.nodes.get('files').children.length,1);
  metadata.resolve({tags:[],correspondents:[],document_types:[],storage_paths:[],warnings:[]});await h.startup;
});
test('incoming PDF load has a visible status before its bytes arrive',async()=>{
  const source=deferred();const h=await ui({source:source.promise});
  assert.match(h.nodes.get('source-status')?.textContent || '',/übernommen|geladen/);
  assert.equal(h.nodes.get('send').disabled,true);
  source.resolve({id:'file-1',name:'attachment.pdf',size:1,kind:'web',canDelete:false});await h.startup;await tick();
  assert.equal(h.nodes.get('files').children.length,1);
});
test('a missing transfer ticket produces a visible explanation',async()=>{
  const lost=await ui({intent:null});await lost.startup;
  assert.match(lost.nodes.get('source-status')?.textContent || '',/erneut|abgelaufen|fehlt/);
});
test('source errors stay visible after metadata succeeds, with a retry action',async()=>{
  const metadata=deferred(),source=deferred();const h=await ui({metadata:metadata.promise,source:source.promise});
  source.reject(new Error('PDF-Download fehlgeschlagen (HTTP 401).'));await tick();
  metadata.resolve({tags:[],correspondents:[],document_types:[],storage_paths:[],warnings:['Keine Zusatzliste']});await h.startup;await tick();
  assert.match(h.nodes.get('source-status')?.textContent || '',/HTTP 401/);
  assert.equal(h.nodes.get('retry-source').hidden,false);
});
test('custom date fields render as date-only controls with working shortcuts',async()=>{
  const h=await ui({metadata:Promise.resolve({tags:[],correspondents:[],document_types:[],storage_paths:[],custom_fields:[{id:20,name:'Wiedervorlage',data_type:'date'}],warnings:[]})});
  await h.startup;
  const box=h.nodes.get('custom-fields'),row=box.children[3],input=row.children[1],actions=row.children[2];
  assert.equal(row.hidden,true);
  await box.children[2].children[0].children[0].events.change();
  assert.equal(row.hidden,false);
  assert.equal(input.type,'date');assert.equal(input.step,undefined);
  input.value='2026-01-31';await actions.children[1].events.click();
  assert.equal(input.value,'2026-02-28');
  assert.match(row.children.at(-1).children[1].textContent,/Deck-Karte/);
});
test('PDF viewer starts the annotation-safe download watcher automatically',async()=>{
  const waiting=deferred(),h=await ui({download:waiting.promise,intent:{url:'https://mail.test/edited.pdf',name:'edited.pdf',viewerSource:true}});await h.startup;
  assert.equal(h.calls.filter(c=>Array.isArray(c)&&c[0]==='source').length,1);
  assert.ok(h.calls.some(c=>Array.isArray(c)&&c[0]==='wait-download'&&c[2]==='edited.pdf'));
  assert.equal(h.nodes.get('annotation-choice').hidden,false);
  assert.equal(h.nodes.get('files').children.length,1);
  assert.match(h.nodes.get('source-status').textContent,/bereits ausgewählt/);
  await h.nodes.get('use-original').events.click({});await tick();
  assert.equal(h.calls.filter(c=>Array.isArray(c)&&c[0]==='source').length,1);
  assert.equal(h.nodes.get('files').children.length,1);
  waiting.resolve({id:9,path:'/tmp/ignored.pdf',name:'ignored.pdf'});await tick();
  assert.equal(h.nodes.get('files').children.length,1,'cancelled watcher must not replace the chosen original');
});
test('manually saved annotated file replaces the already selected original',async()=>{
  const waiting=deferred(),h=await ui({download:waiting.promise,intent:{url:'https://mail.test/edited.pdf',viewerSource:true}});await h.startup;
  await h.nodes.get('pick-annotated').events.click({});
  assert.equal(h.nodes.get('file-input').clicked,1);
  await h.nodes.get('file-input').events.change({target:{files:[{name:'edited-with-notes.pdf'}],value:'chosen'}});await tick();
  assert.equal(h.calls.filter(c=>Array.isArray(c)&&c[0]==='source').length,1);
  assert.ok(h.calls.some(c=>Array.isArray(c)&&c[0]==='picker'&&c[1]==='edited-with-notes.pdf'));
  assert.ok(h.calls.some(c=>Array.isArray(c)&&c[0]==='release'&&c[1]==='file-1'));
  assert.equal(h.nodes.get('annotation-choice').hidden,true);
  assert.equal(h.nodes.get('files').children.length,1);
  waiting.resolve({id:9,path:'/tmp/ignored.pdf',name:'ignored.pdf'});
});
test('the next completed Firefox PDF download is selected automatically',async()=>{
  const h=await ui({intent:{url:'https://mail.test/edited.pdf',viewerSource:true}});await h.startup;
  await tick();
  assert.ok(h.calls.some(c=>Array.isArray(c)&&c[0]==='wait-download'));
  assert.ok(h.calls.some(c=>Array.isArray(c)&&c[0]==='choose-download'&&c[1]===9));
  assert.equal(h.calls.filter(c=>Array.isArray(c)&&c[0]==='source').length,1);
  assert.equal(h.nodes.get('annotation-choice').hidden,true);
  assert.equal(h.nodes.get('files').children.length,1);
  assert.ok(h.calls.some(c=>Array.isArray(c)&&c[0]==='release'&&c[1]==='file-1'));
});
test('protected webmail HTML automatically switches to the new PDF download',async()=>{
  const error=Object.assign(new Error('Webmail statt PDF'),{code:'PDF_SOURCE_PROTECTED'});
  const h=await ui({source:Promise.reject(error),intent:{url:'https://webmail.test/inbox'}});await h.startup;await tick();await tick();
  assert.ok(h.calls.some(c=>Array.isArray(c)&&c[0]==='source'));
  assert.ok(h.calls.some(c=>Array.isArray(c)&&c[0]==='wait-download'));
  assert.equal(h.nodes.get('files').children.length,1);
  assert.equal(h.nodes.get('annotation-choice').hidden,true);
  assert.match(h.nodes.get('source-status').textContent,/geschützten Viewer automatisch ausgewählt/);
  assert.equal(h.nodes.get('retry-source').hidden,true);
});
test('Enter selects the exact or first matching tag and clears the search',async()=>{
  const metadata=Promise.resolve({tags:[{id:1,name:'Rechnung',color:'#17541f'},{id:2,name:'Rechtsschutz',color:'#17541f'}],correspondents:[],document_types:[],storage_paths:[],warnings:[]});
  const h=await ui({metadata});await h.startup;
  const search=h.nodes.get('tag-search');search.value='rech';let prevented=false;
  await search.events.keydown({key:'Enter',preventDefault:()=>{prevented=true;}});
  assert.equal(prevented,true);assert.equal(search.value,'');
  assert.equal(h.nodes.get('selected-tags').children[0].textContent,'Rechnung ×');
});
test('compact composer exposes a top quick action synchronized with the main action',async()=>{
  const h=await ui();await h.startup;
  const quick=h.nodes.get('quick-send');
  assert.equal(quick.hidden,false);assert.equal(quick.disabled,false);
  await quick.events.click({});assert.equal(h.nodes.get('send').clicked,1);
});
test('composer registers and seals one batch around all started files',async()=>{
  const h=await ui();await h.startup;
  await h.nodes.get('send').events.click({});await tick();
  const begin=h.calls.indexOf('begin-batch'),start=h.calls.findIndex(call=>Array.isArray(call)&&call[0]==='start'),seal=h.calls.findIndex(call=>Array.isArray(call)&&call[0]==='seal-batch');
  assert.ok(begin>=0&&begin<start&&start<seal);assert.equal(h.calls[start][5],'batch-1');assert.equal(h.calls[seal][1],'batch-1');
});
test('custom field search adds by Enter and removing a field clears its value',async()=>{
  const h=await ui({metadata:Promise.resolve({tags:[],correspondents:[],document_types:[],storage_paths:[],custom_fields:[{id:20,name:'Betrag',data_type:'integer'}],warnings:[]})});await h.startup;
  const box=h.nodes.get('custom-fields'),search=box.children[0],row=box.children[3];
  search.value='bet';await search.events.keydown({key:'Enter',preventDefault(){}});assert.equal(row.hidden,false);
  row.children[1].value='42';await box.children[1].children[0].events.click();
  assert.equal(row.hidden,true);assert.equal(row.children[1].value,'');
});
test('correspondent and document type support search, Enter, and removable single selections',async()=>{
  const h=await ui({metadata:Promise.resolve({tags:[],correspondents:[{id:1,name:'Alpha'},{id:2,name:'Beta'}],document_types:[{id:7,name:'Rechnung'}],storage_paths:[],warnings:[]})});await h.startup;
  for(const [key,query,id] of [['correspondent','bet','2'],['document_type','rech','7']]){
    const search=h.nodes.get(key+'-search');search.value=query;await search.events.input({});
    assert.equal(h.nodes.get(key+'-list').children.length,1);
    await search.events.keydown({key:'Enter',preventDefault(){}});assert.equal(h.nodes.get(key).value,id);
    await h.nodes.get(key+'-selected').children[0].events.click();await tick();assert.equal(h.nodes.get(key).value,'');
  }
});
test('selected tags disappear from available options and return when their chip is removed',async()=>{
  const h=await ui({metadata:Promise.resolve({tags:[{id:1,name:'Eingang'},{id:2,name:'Genehmigung'}],correspondents:[],document_types:[],storage_paths:[],warnings:[]})});await h.startup;
  const search=h.nodes.get('tag-search'),list=h.nodes.get('tag-list'),chips=h.nodes.get('selected-tags');
  search.value='Eingang';await search.events.keydown({key:'Enter',preventDefault(){}});
  assert.equal(chips.children.length,1);assert.equal(list.children.length,1);assert.equal(list.children[0].children[2].textContent,'Genehmigung');
  await chips.children[0].events.click();await tick();assert.equal(chips.children.length,0);assert.equal(list.children.length,2);
});
test('profile changes show public sharing and restore completion; old profiles disable both',async()=>{
  const profiles=[{id:'new',name:'Genehmigung',tags:[],share:{days:30,archive:true},complete_tagging:true},{id:'old',name:'Alt',tags:[]}];
  const h=await ui({profiles});await h.startup;const profile=h.nodes.get('profile');
  profile.value='new';await profile.events.change({});
  assert.equal(h.nodes.get('share-enabled').checked,true);assert.equal(h.nodes.get('share-options').hidden,false);assert.equal(h.nodes.get('share-days').value,'30');assert.equal(h.nodes.get('complete-tagging').checked,true);
  profile.value='old';await profile.events.change({});assert.equal(h.nodes.get('share-enabled').checked,false);assert.equal(h.nodes.get('share-options').hidden,true);assert.equal(h.nodes.get('complete-tagging').checked,false);
});
test('annotation alternatives are collapsed while automatic download monitoring continues',async()=>{
  const wait=deferred(),h=await ui({download:wait.promise,intent:{url:'https://mail.test/a.pdf',viewerSource:true}});await h.startup;
  assert.equal(h.nodes.get('annotation-details').open,false);assert.ok(h.calls.some(c=>Array.isArray(c)&&c[0]==='wait-download'));
  wait.reject(new Error('Download timeout'));await tick();assert.equal(h.nodes.get('annotation-details').open,true);
});
test('title suggestions load and committed input is cached for the current server',async()=>{
  const h=await ui();await h.startup;
  assert.equal(h.nodes.get('title-suggestions').children.length,2);h.nodes.get('title').value='Rechnung Gas';await h.nodes.get('title').events.change({});
  assert.ok(h.calls.some(c=>Array.isArray(c)&&c[0]==='remember-title'&&c[1]==='Rechnung Gas'&&c[2]==='https://archive.test/'));
});
test('date and monetary input display normalized values after leaving the field',async()=>{
  const h=await ui({metadata:Promise.resolve({tags:[],correspondents:[],document_types:[],storage_paths:[],custom_fields:[{id:42,name:'Betrag',data_type:'monetary'}],warnings:[]})});await h.startup;
  const date=h.nodes.get('created');date.value='220826';await date.events.change({});assert.equal(date.value,'22.08.2026');
  const input=h.nodes.get('custom-fields').children[3].children[1];input.value='1489';await input.events.change();assert.equal(input.value,'14.89');await input.events.change();assert.equal(input.value,'14.89');
});
test('title autocomplete marks the first match and Enter accepts it without an arrow key',async()=>{
  const h=await ui();await h.startup;const input=h.nodes.get('title'),list=h.nodes.get('title-suggestions');
  input.value='wass';await input.events.input({});assert.equal(list.hidden,false);assert.equal(list.children[0]['aria-selected'],'true');
  let prevented=false;await input.events.keydown({key:'Enter',preventDefault(){prevented=true;}});
  assert.equal(input.value,'Rechnung Wasser');assert.equal(prevented,true);assert.equal(list.hidden,true);
});
test('title autocomplete uses arrow selection, Escape, and mouse selection',async()=>{
  const h=await ui();await h.startup;const input=h.nodes.get('title'),list=h.nodes.get('title-suggestions'),event=key=>({key,preventDefault(){}});
  input.value='Rechnung';await input.events.input({});await input.events.keydown(event('ArrowDown'));assert.equal(list.children[1]['aria-selected'],'true');
  await input.events.keydown(event('Enter'));assert.equal(input.value,'Rechnung Wasser');
  input.value='Rechnung';await input.events.input({});await input.events.keydown(event('Escape'));assert.equal(list.hidden,true);assert.equal(input.value,'Rechnung');
  await input.events.focus({});await list.children[0].events.click();await tick();assert.equal(input.value,'Rechnung Strom');assert.equal(list.hidden,true);
});
test('calendar and fast date input stay synchronized and retain an optional time',async()=>{
  const h=await ui();await h.startup;const date=h.nodes.get('created'),picker=h.nodes.get('created-picker');
  date.value='220826';await date.events.change({});assert.equal(picker.value,'2026-08-22');
  assert.ok(!html.includes('date-popover'));let opened=0;picker.showPicker=()=>opened++;
  await h.nodes.get('open-calendar').events.click({});assert.equal(opened,1);
  date.value='22.08.2026 14:30';picker.value='2026-09-25';await picker.events.change({});assert.equal(date.value,'25.09.2026 14:30');
});
test('menubar public sharing stays synchronized with the checkbox, expiry and profiles',async()=>{
  const h=await ui({profiles:[{id:'public',name:'Freigabe',tags:[],share:{days:30,archive:false}}]});await h.startup;
  h.nodes.get('share-days').value='7';await h.nodes.get('quick-share').events.click({});assert.equal(h.nodes.get('share-enabled').checked,true);assert.equal(h.nodes.get('quick-share')['aria-pressed'],'true');
  h.nodes.get('share-enabled').checked=false;await h.nodes.get('share-enabled').events.change({});assert.equal(h.nodes.get('quick-share')['aria-pressed'],'false');
  h.nodes.get('profile').value='public';await h.nodes.get('profile').events.change({});assert.equal(h.nodes.get('quick-share').textContent,'Öffentlicher Link: 30 Tage');
});
test('early check does not block filling or sending and cannot restore a submitted file',async()=>{
  const check=deferred(),h=await ui({precheck:check.promise});await h.startup;
  assert.ok(h.calls.some(c=>Array.isArray(c)&&c[0]==='precheck'&&c[1]==='file-1'));
  assert.equal(h.nodes.get('send').disabled,false);h.nodes.get('title').value='Während der Prüfung';
  await h.nodes.get('send').events.click({});assert.ok(h.calls.some(c=>Array.isArray(c)&&c[0]==='start'));
  check.resolve({state:'clear',matches:[]});await tick();assert.equal(h.nodes.get('files').children.length,0);
});
test('early check waits for unlock while leaving the selected file usable',async()=>{
  const h=await ui({unlocked:false});await h.startup;
  assert.equal(h.calls.some(c=>Array.isArray(c)&&c[0]==='precheck'),false);assert.equal(h.nodes.get('files').children.length,1);
  const meta=h.nodes.get('files').children[0].children[1];assert.ok(meta.children.some(n=>n.textContent==='Dublettenprüfung nach dem Entsperren'));
});
test('Ctrl+S triggers send only in composer, ignores repeat and respects disabled button',async()=>{
  const h=await ui();await h.startup;const send=h.nodes.get('send'),event={key:'s',ctrlKey:true,preventDefault(){this.prevented=true;}};
  h.windowEvents.keydown(event);assert.equal(send.clicked,1);assert.equal(event.prevented,true);
  h.windowEvents.keydown({...event,repeat:true});assert.equal(send.clicked,1);
  send.disabled=true;h.windowEvents.keydown(event);assert.equal(send.clicked,1);
  send.disabled=false;h.nodes.get('view-upload').hidden=true;h.windowEvents.keydown(event);assert.equal(send.clicked,1);
  h.nodes.get('view-upload').hidden=false;h.document.querySelectorAll=()=>[{}];h.windowEvents.keydown(event);assert.equal(send.clicked,1);
});
test('Tab zones skip all tag choices in both directions, including from a clicked tag',async()=>{
  const h=await ui();await h.startup;const tags=h.nodes.get('tag-search'),corr=h.nodes.get('correspondent-search');let focused='';
  tags.focus=()=>{focused='tags';};corr.focus=()=>{focused='corr';};
  for(const n of [tags,corr]){n.getClientRects=()=>[{}];n.closest=selector=>selector==='.metadata-card'?{}:null;}
  h.document.querySelectorAll=selector=>selector.includes('data-tab-stop')?[tags,corr]:[];
  const key=(target,shiftKey=false)=>({key:'Tab',target,shiftKey,preventDefault(){this.prevented=true;}});
  const next=key(tags);h.windowEvents.keydown(next);assert.equal(focused,'corr');assert.equal(next.prevented,true);
  h.windowEvents.keydown(key(corr,true));assert.equal(focused,'tags');
  const tag={closest:()=>({}),compareDocumentPosition:node=>node===corr?4:2};h.windowEvents.keydown(key(tag));assert.equal(focused,'corr');
});
test('shortcut recorder captures a combination and allows disabling it',async()=>{
  const h=await ui();await h.startup;const row=h.nodes.get('keyboard-bindings').children[0],input=row.children[1];
  input.events.keydown({key:'Enter',ctrlKey:true,preventDefault(){}});assert.equal(input.value,'Ctrl+Enter');
  await row.children[2].events.click();await tick();assert.equal(input.value,'');
});
test('series mode sends only the first PDF, stays open, retains date, assignment and custom values',async()=>{
  const metadata=Promise.resolve({tags:[{id:1,name:'Rechnung'}],correspondents:[{id:2,name:'Stadtwerke'}],document_types:[{id:3,name:'Rechnung'}],storage_paths:[],custom_fields:[{id:42,name:'Betrag',data_type:'monetary'}],warnings:[]});
  const h=await ui({metadata});await h.startup;
  h.nodes.get('series-mode').checked=true;await h.nodes.get('series-mode').events.change({});
  await h.nodes.get('file-input').events.change({target:{files:[{name:'next.pdf'}],value:'chosen'}});
  h.nodes.get('created').value='220826';await h.nodes.get('created').events.change({});
  h.nodes.get('title').value='Erste Rechnung';h.nodes.get('correspondent').value='2';h.nodes.get('document_type').value='3';
  h.nodes.get('share-enabled').checked=true;h.nodes.get('share-days').value='7';h.nodes.get('complete-tagging').checked=true;
  const box=h.nodes.get('custom-fields'),search=box.children[0];search.value='Betrag';await search.events.keydown({key:'Enter',preventDefault(){}});box.children[3].children[1].value='1489';
  await h.nodes.get('send').events.click({});
  const starts=h.calls.filter(c=>Array.isArray(c)&&c[0]==='start');assert.equal(starts.length,1);assert.equal(starts[0][1],'file-1');assert.equal(starts[0][2].custom_fields['42'],'14.89');
  assert.equal(h.nodes.get('files').children.length,1);assert.equal(h.nodes.get('title').value,'');assert.equal(h.nodes.get('created').value,'22.08.2026');assert.equal(box.children[3].children[1].value,'1489');
  assert.equal(h.nodes.get('correspondent').value,'2');assert.equal(h.nodes.get('share-enabled').checked,true);assert.equal(h.nodes.get('complete-tagging').checked,true);assert.equal(h.calls.includes('window-close'),false);
  h.nodes.get('title').value='Zweite Rechnung';box.children[3].children[1].value='2599';await h.nodes.get('send').events.click({});
  assert.equal(h.calls.filter(c=>Array.isArray(c)&&c[0]==='start').length,2);assert.equal(h.nodes.get('files').children.length,0);assert.equal(h.nodes.get('series-add').hidden,false);
});
test('failed series start retains the current PDF and its typed values',async()=>{
  const h=await ui();await h.startup;h.nodes.get('series-mode').checked=true;h.nodes.get('title').value='Nicht verlieren';h.P.start=async()=>{throw new Error('Start failed');};
  await h.nodes.get('send').events.click({});assert.equal(h.nodes.get('title').value,'Nicht verlieren');assert.equal(h.nodes.get('files').children.length,1);assert.equal(h.nodes.get('send').disabled,false);
});
test('uniform search selects the visibly highlighted result via arrows and Enter',async()=>{
  const h=await ui({metadata:Promise.resolve({tags:[{id:1,name:'Alpha'},{id:2,name:'Beta'}],correspondents:[{id:3,name:'Alpha'},{id:4,name:'Beta'}],document_types:[],storage_paths:[],custom_fields:[{id:5,name:'Alpha',data_type:'string'},{id:6,name:'Beta',data_type:'string'}],warnings:[]})});await h.startup;
  const key=key=>({key,preventDefault(){}}),tags=h.nodes.get('tag-search');await tags.events.keydown(key('ArrowDown'));assert.equal(h.nodes.get('tag-list').children[1]['data-active'],'true');await tags.events.keydown(key('Enter'));assert.match(h.nodes.get('selected-tags').children[0].textContent,/Beta/);
  const corr=h.nodes.get('correspondent-search');await corr.events.keydown(key('ArrowDown'));await corr.events.keydown(key('Enter'));assert.equal(h.nodes.get('correspondent').value,'4');
  const box=h.nodes.get('custom-fields');await box.children[0].events.keydown(key('ArrowDown'));assert.equal(box.children[2].children[1]['data-active'],'true');await box.children[0].events.keydown(key('Enter'));assert.equal(box.children[4].hidden,false);assert.equal(box.children[3].hidden,true);
});
test('assignment suggestions need an explicit click and preserve existing selected tags',async()=>{
  const h=await ui({metadata:Promise.resolve({tags:[{id:1,name:'Eins'},{id:2,name:'Zwei'}],correspondents:[{id:3,name:'Firma'}],document_types:[{id:4,name:'Rechnung'}],storage_paths:[],warnings:[]})});await h.startup;
  h.P.assignmentSuggestions=async()=>[{tags:[2],document_type:4,count:3}];h.nodes.get('tag-search').value='Eins';await h.nodes.get('tag-search').events.keydown({key:'Enter',preventDefault(){}});
  h.nodes.get('correspondent-search').value='Firma';await h.nodes.get('correspondent-search').events.keydown({key:'Enter',preventDefault(){}});await tick();assert.equal(h.nodes.get('document_type').value,'');
  await h.nodes.get('assignment-suggestions').children[0].events.click();await tick();assert.equal(h.nodes.get('document_type').value,'4');assert.equal(h.nodes.get('selected-tags').children.length,2);
});
test('sending a displayed duplicate carries the decision without a second prompt',async()=>{
  const h=await ui({precheck:{state:'duplicate',matches:[{id:42,title:'Vorhanden'}]}});await h.startup;await tick();
  assert.match(h.nodes.get('send').textContent,/Trotz Doublette/);
  assert.match(h.nodes.get('quick-send').textContent,/Trotz Doublette/);
  await h.nodes.get('send').events.click();
  const call=h.calls.find(c=>Array.isArray(c)&&c[0]==='start');assert.deepEqual(Array.from(call[6]),['document:42']);
});

test('composer directly selects public expiry, syncs the toolbar and can turn sharing off',async()=>{
  const h=await ui();await h.startup;
  for(const value of ['7','30','0']){
    await h.nodes.get('share-'+value).events.click({});
    assert.equal(h.nodes.get('share-enabled').checked,true);assert.equal(h.nodes.get('share-days').value,value);
    assert.equal(h.nodes.get('share-'+value)['aria-pressed'],'true');assert.equal(h.nodes.get('share-off')['aria-pressed'],'false');
  }
  await h.nodes.get('share-off').events.click({});assert.equal(h.nodes.get('share-enabled').checked,false);
  assert.equal(h.nodes.get('quick-share').textContent,'Öffentlicher Link: aus');
  await h.nodes.get('share-30').events.click({});await h.nodes.get('send').events.click({});
  const sent=h.calls.find(c=>Array.isArray(c)&&c[0]==='start');assert.equal(sent[2].share.days,30);
});

test('duplicate assignment stays editable and preserves manually selected tags',async()=>{
  const metadata={tags:[{id:1,name:'Manuell'},{id:2,name:'Rechnung'},{id:3,name:'Beleg'}],correspondents:[{id:5,name:'Firma'}],document_types:[{id:6,name:'Rechnung'}],storage_paths:[{id:7,name:'Belege'}],custom_fields:[{id:10,name:'Betrag',data_type:'monetary'},{id:11,name:'Bezahlt',data_type:'boolean'},{id:12,name:'Verknüpfung',data_type:'documentlink'}],warnings:[]};
  const h=await ui({metadata:Promise.resolve(metadata),precheck:{state:'duplicate',matches:[{id:42,title:'Vorhanden',url:'https://archive.test/documents/42/details'}]}});await h.startup;await tick();
  const manual=h.nodes.get('tag-list').children.find(n=>n.children.some(c=>c.textContent==='Manuell')).children[0];manual.checked=true;await manual.events.change({});
  const walk=n=>[n,...n.children.flatMap(walk)];
  for(let i=0;i<2;i++)await walk(h.nodes.get('files')).find(n=>n.textContent==='Zuordnung übernehmen').events.click();
  assert.deepEqual(h.nodes.get('selected-tags').children.map(n=>n.textContent),['Manuell ×','Rechnung ×','Beleg ×'],h.nodes.get('notice').textContent);
  assert.equal(h.nodes.get('correspondent').value,'5');assert.equal(h.nodes.get('document_type').value,'6');assert.equal(h.nodes.get('storage_path').value,'7');
  assert.equal(walk(h.nodes.get('custom-fields')).find(n=>n.id==='custom-field-10').value,'EUR10.00');
  assert.equal(walk(h.nodes.get('custom-fields')).find(n=>n.id==='custom-field-11').value,'false');
  assert.equal(walk(h.nodes.get('custom-fields')).find(n=>n.id==='custom-field-12').value,'42, 43');
  const remove=h.nodes.get('selected-tags').children.find(n=>n.textContent==='Rechnung ×');await remove.events.click();
  assert.deepEqual(h.nodes.get('selected-tags').children.map(n=>n.textContent),['Manuell ×','Beleg ×']);
  assert.equal(h.calls.filter(c=>Array.isArray(c)&&c[0]==='start').length,0);
});

const seriesCatalog={tags:[{id:1,name:'Akte'},{id:2,name:'Weiterer Kontext'}],correspondents:[{id:3,name:'Gericht'}],document_types:[{id:4,name:'Beschluss'}],storage_paths:[{id:5,name:'Akten'}],custom_fields:[{id:10,name:'Aktenzeichen',data_type:'string'},{id:11,name:'Betrag',data_type:'monetary'},{id:12,name:'Erledigt',data_type:'boolean'},{id:13,name:'Anzahl',data_type:'integer'},{id:14,name:'Verweise',data_type:'documentlink'}],warnings:[]};
function seriesFixture(overrides={}) {return {enabled:true,inherit:true,assignment:{tags:[1],correspondent:3,document_type:4,storage_path:5,created:new Date(2026,8,11,14,30).toISOString(),custom_fields:{10:'99 C 35/26',11:'EUR10',12:false,13:0,14:[42,43]},complete_tagging:true},...overrides};}
function findField(h,id) {const walk=node=>node.id==='custom-field-'+id?node:node.children.map(walk).find(Boolean);return walk(h.nodes.get('custom-fields'));}
test('a new series window inherits all last accepted classification values and remains editable',async()=>{
 const series=seriesFixture(),h=await ui({series,metadata:Promise.resolve(seriesCatalog)});await h.startup;
 assert.equal(h.nodes.get('series-mode').checked,true);assert.equal(h.nodes.get('series-inherit').checked,true);
 assert.equal(h.nodes.get('title').value,'');assert.equal(h.nodes.get('created').value,'11.09.2026 14:30');assert.equal(h.nodes.get('created-picker').value,'2026-09-11');
 for(const [key,value] of [['correspondent','3'],['document_type','4'],['storage_path','5']])assert.equal(h.nodes.get(key).value,value);
 assert.equal(findField(h,10).value,'99 C 35/26');assert.equal(findField(h,11).value,'EUR10.00');assert.equal(findField(h,12).value,'false');assert.equal(findField(h,13).value,'0');assert.equal(findField(h,14).value,'42, 43');
 assert.equal(h.nodes.get('complete-tagging').checked,true);assert.equal(h.nodes.get('share-enabled').checked,false);assert.equal(h.nodes.get('delete-local').checked,false);
 const search=h.nodes.get('tag-search');search.value='Weiterer Kontext';await search.events.keydown({key:'Enter',preventDefault(){}});findField(h,10).value='99 C 36/26';h.nodes.get('title').value='Neue Verfügung';
 await h.nodes.get('send').events.click({});const sent=h.calls.find(c=>Array.isArray(c)&&c[0]==='start')[2];assert.deepEqual([...sent.tags],[1,2]);assert.equal(sent.custom_fields[10],'99 C 36/26');assert.equal(sent.custom_fields[12],false);assert.equal(sent.custom_fields[13],0);assert.equal(series.assignment.custom_fields[10],'99 C 35/26');
});
test('disabled inheritance does not fill a new window and clears classification for the next queued PDF',async()=>{
 const h=await ui({series:seriesFixture({inherit:false}),metadata:Promise.resolve(seriesCatalog)});await h.startup;
 assert.equal(h.nodes.get('correspondent').value,'');assert.equal(findField(h,10).value,'');
 h.nodes.get('correspondent').value='3';h.nodes.get('document_type').value='4';h.nodes.get('complete-tagging').checked=true;h.nodes.get('created').value='11.09.2026';findField(h,10).value='Akte';
 await h.nodes.get('file-input').events.change({target:{files:[{name:'next.pdf'}],value:'selected'}});
 await h.nodes.get('send').events.click({});assert.equal(h.nodes.get('correspondent').value,'');assert.equal(h.nodes.get('document_type').value,'');assert.equal(findField(h,10).value,'');assert.equal(h.nodes.get('complete-tagging').checked,false);assert.equal(h.nodes.get('created').value,'11.09.2026');
});
test('explicit launch profile takes priority over the previous series assignment',async()=>{
 const h=await ui({series:seriesFixture(),metadata:Promise.resolve(seriesCatalog),profiles:[{id:'chosen',name:'Kontext',tags:[2],document_type:4}],intent:{url:'https://mail.test/attachment.pdf',profileId:'chosen'}});await h.startup;
 assert.equal(h.nodes.get('profile').value,'chosen');assert.equal(findField(h,10).value,'');assert.equal(h.nodes.get('correspondent').value,'');assert.equal(h.nodes.get('selected-tags').children.length,1);assert.match(h.nodes.get('selected-tags').children[0].textContent,/Weiterer Kontext/);
});
test('late metadata cannot overwrite manual work or restore across a changed login',async()=>{
 for(const changedSession of [false,true]) {
  const metadata=deferred(),h=await ui({series:seriesFixture(),metadata:metadata.promise});
  if(changedSession){const prior=h.P.state;h.P.state=async()=>({...await prior(),previewRevision:2});}
  else {h.nodes.get('assignment-card').events.input();h.nodes.get('created').value='12.09.2026';}
  metadata.resolve(seriesCatalog);await h.startup;assert.equal(findField(h,10).value,'');assert.equal(h.nodes.get('correspondent').value,'');
  if(!changedSession)assert.equal(h.nodes.get('created').value,'12.09.2026');
 }
});
test('removed catalog IDs are skipped with a visible explanation while valid values survive',async()=>{
 const series=seriesFixture();series.assignment.tags.push(999);series.assignment.document_type=999;series.assignment.custom_fields[999]='removed';
 const h=await ui({series,metadata:Promise.resolve(seriesCatalog)});await h.startup;
 assert.equal(h.nodes.get('selected-tags').children.length,1);assert.equal(h.nodes.get('document_type').value,'');assert.equal(findField(h,10).value,'99 C 35/26');assert.match(h.nodes.get('notice').textContent,/teilweise übernommen/);
});
