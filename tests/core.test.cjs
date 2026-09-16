const test = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const {webcrypto,createHash} = require('node:crypto');
const coreCode = readFileSync(__dirname + '/../extension/core.js', 'utf8');
const backgroundCode = readFileSync(__dirname + '/../extension/background.js', 'utf8');
const task = '11111111-2222-4333-8444-555555555555';
const pdf = new Blob(['%PDF-1.4\nTest document\n%%EOF'], {type:'application/pdf'});
function context(fetcher = fetch) {
  const ctx = {URL,Blob,FormData,TextDecoder,TextEncoder,btoa,Uint8Array,AbortSignal,crypto:webcrypto,fetch:fetcher,console,structuredClone,setTimeout,clearTimeout};
  vm.createContext(ctx);vm.runInContext(readFileSync(__dirname + '/../extension/keyboard.js','utf8'),ctx);vm.runInContext(readFileSync(__dirname + '/../extension/custom-fields.js','utf8'),ctx);vm.runInContext(coreCode,ctx);vm.runInContext(readFileSync(__dirname + '/../extension/nextcloud.js','utf8'),ctx); return ctx;
}
const C = context().Core;
test('custom date shortcuts use calendar dates without time or DST drift', () => {
  const F=context().CustomFields;
  assert.equal(F.shiftDate('2026-01-31','month'),'2026-02-28');
  assert.equal(F.shiftDate('2028-01-31','month'),'2028-02-29');
  assert.equal(F.shiftDate('2026-03-08','4w'),'2026-04-05');
  assert.equal(F.shiftDate('2026-10-25','6w'),'2026-12-06');
  assert.equal(F.shiftDate('','4w',new Date(2026,8,8,23,30)),'2026-10-06');
  assert.throws(()=>F.shiftDate('2026-02-30','4w'),/Kalenderdatum/);
});
test('Paperless custom field types normalize to their API value shapes', () => {
  const F=context().CustomFields;
  const cases=[
    [{data_type:'string'},' Text ',' Text '],
    [{data_type:'longtext'},'Mehr\nText','Mehr\nText'],
    [{data_type:'url'},'https://example.test/a','https://example.test/a'],
    [{data_type:'date'},'2026-10-06','2026-10-06'],
    [{data_type:'boolean'},'false',false],
    [{data_type:'integer'},'0',0],
    [{data_type:'float'},'12,5',12.5],
    [{data_type:'monetary'},'EUR123,4','EUR123.40'],
    [{data_type:'select',extra_data:{select_options:[{id:'option-1'}]}},'option-1','option-1'],
    [{data_type:'documentlink'},'12, 34 12',[12,34]]
  ];
  for(const [field,input,expected] of cases){
    const actual=F.normalize(field,input);
    assert.deepEqual(Array.isArray(actual)?Array.from(actual):actual,expected);
  }
  assert.throws(()=>F.normalize({data_type:'url'},'javascript:alert(1)'),/Webadresse/);
});
test('API requests stay within the configured server and subpath', () => {
  assert.equal(C.baseURL('https://archive.test/paperless'), 'https://archive.test/paperless/');
  assert.throws(()=>C.baseURL('http://archive.test'));
  assert.throws(()=>C.baseURL('https://user:pass@archive.test'));
  assert.throws(()=>C.apiURL('https://archive.test/paperless/', 'https://evil.test/api/tags/'));
  assert.throws(()=>C.apiURL('https://archive.test/paperless/', '/elsewhere/api/tags/'));
});
test('multipart upload repeats tag IDs and never sends cookies or follows redirects', async () => {
  const api = new C.API('https://archive.test/', async()=>'test-key', async (url, init) => {
    assert.equal(url,'https://archive.test/api/documents/post_document/');
    assert.equal(init.credentials,'omit');assert.equal(init.redirect,'error');
    assert.equal(init.headers.Authorization,'Token test-key');
    assert.deepEqual(init.body.getAll('tags'),['2','7']);
    assert.equal(init.body.get('document_type'),'4');assert.equal(init.body.get('title'),'Rechnung');
    assert.equal(await init.body.get('document').text(),await pdf.text());
    assert.equal(init.headers['Content-Type'],undefined);
    return Response.json(task);
  });
  assert.equal(await api.upload(pdf,'Rechnung.pdf',{tags:[2,7,2,-1],document_type:4,title:' Rechnung '}),task);
});
test('all tag pages loaded, foreign pagination blocked before credential transmission', async () => {
  const seen=[];
  const api=new C.API('https://archive.test/',async()=>'test',async(url)=>{
    seen.push(url);return Response.json(seen.length===1?{results:[{id:1}],next:'https://archive.test/api/tags/?page=2'}:{results:[{id:2}],next:null});
  });
  assert.equal((await api.list('tags')).length,2);
  let calls=0;
  const bad=new C.API('https://archive.test/',async()=>'test',async()=>{calls++;return Response.json({results:[],next:'https://evil.test/api/tags/'});});
  await assert.rejects(bad.list('tags'));assert.equal(calls,1);
});
test('only matching SUCCESS with a document ID permits completion', () => {
  for (const item of [{task_id:'other',status:'SUCCESS',related_document:'1'},{task_id:task,status:'SUCCESS'},{task_id:task,status:'STARTED',related_document:'1'}]) assert.equal(C.taskState([item],task).state,'pending');
  assert.equal(C.taskState([{task_id:task,status:'FAILURE',related_document:'1'}],task).state,'failed');
  assert.equal(C.taskState({results:[{task_id:task,status:'SUCCESS',related_document:'12'}]},task).documentId,12);
  assert.throws(()=>C.taskID('<html>login</html>'));
});
test('PDF header validated; HTML and zero-byte files rejected', async () => {
  await C.checkPDF(pdf);await assert.rejects(C.checkPDF(new Blob(['<html>login</html>'])));await assert.rejects(C.checkPDF(new Blob([])));
});
test('Windows, Linux, UNC paths preserve special characters', () => {
  assert.equal(C.pathURL('C:\\Users\\User\\A #1.pdf'),'file:///C:/Users/User/A%20%231.pdf');
  assert.equal(C.pathURL('/home/test/Ü.pdf'),'file:///home/test/%C3%9C.pdf');
  assert.equal(C.pathURL('\\\\server\\share\\a.pdf'),'file://server/share/a.pdf');
});
async function harness(mode='success',extra={}) {
  const local={},session={},events=[],network=[],windows=[],badges=[],messages=[],menuListeners=[],downloadQueries=[],clipboard=[],paths=new Map([['/tmp/original.pdf',pdf]]);
  const storage = obj => ({get:async key=>({[key]:structuredClone(obj[key])}),set:async x=>Object.assign(obj,structuredClone(x)),remove:async key=>{delete obj[key];}});
  const cb={addListener(){}};
  let status=mode, activeTabs=[];
  const fetcher=async(url,init)=>{
    network.push({url,init});
    if(extra.fetch){const response=await extra.fetch(url,init);if(response!==undefined)return response;}
    if(/\/(custom_fields|correspondents|document_types|storage_paths)\//.test(url))return Response.json({results:url.includes('/custom_fields/')?extra.fields || []:[],next:null});
    if(url.includes('/tags/')) return Response.json({results:[],next:null});
    if(url.includes('checksum__iexact=')) {
      if(status==='check-error') return new Response('',{status:403});
      const sha=createHash('sha256').update(Buffer.from(await pdf.arrayBuffer())).digest('hex');
      return Response.json({results:['duplicate','duplicate-rejected'].includes(status)&&new URL(url).searchParams.get('checksum__iexact')===sha?[{id:42,title:'Vorhandene Rechnung'}]:[],next:null});
    }
    if(url.includes('/documents/42/metadata/')) return Response.json({original_checksum:createHash('sha256').update(Buffer.from(await pdf.arrayBuffer())).digest('hex')});
    if(url.includes('/post_document/')) {events.push('upload');return Response.json(task);}
    if(url.includes('/tasks/')) {
      events.push('task');
      if(status==='v10') return Response.json({results:[{task_id:task,status:'success',result_data:{document_id:12},related_document_ids:[12]}]});
      if(status==='duplicate-rejected') return Response.json([{task_id:task,status:'FAILURE',result:'It is a duplicate of document #42',related_document:'42'}]);
      if(status==='offline') throw new Error('offline');
      if(status==='http403') return new Response('',{status:403});
      return Response.json([{task_id:task,status:status==='failure'?'FAILURE':status==='pending'?'STARTED':'SUCCESS',related_document:status==='missing-doc'?null:'12'}]);
    }
    if(url.includes('/documents/12/')) {events.push('document');return Response.json({id:status==='wrong-doc'?99:12});}
    throw new Error('Unexpected URL '+url);
  };
  const ctx=context(fetcher);ctx.window=ctx;ctx.navigator={clipboard:{writeText:async text=>{if(extra.clipboardError)throw new Error('clipboard blocked');clipboard.push(text);}}};
  ctx.setTimeout=(fn,ms)=>setTimeout(fn,Math.min(ms,1));
  ctx.XMLHttpRequest=class {open(method,url){this.url=url;}send(){this.response=paths.get(decodeURIComponent(new URL(this.url).pathname));queueMicrotask(()=>this.response?this.onload():this.onerror());}};
  ctx.browser={storage:{local:storage(local),session:storage(session)},permissions:{contains:async()=>false},runtime:{getURL:x=>'moz-extension://test/'+x,onInstalled:cb},notifications:{create:async(...args)=>messages.push(args.at(-1)),onClicked:cb},tabs:{create:async()=>{},query:async()=>activeTabs},windows:{create:async x=>windows.push(x)},browserAction:{onClicked:cb,setBadgeText:async x=>badges.push(x.text),setBadgeBackgroundColor:async()=>{},setTitle:async()=>{}},contextMenus:{removeAll:async()=>{},create(){},onClicked:{addListener:fn=>menuListeners.push(fn)}},downloads:{search:async query=>{downloadQueries.push(query);return query?.startedAfter?(extra.newDownloads||[]):[{id:4,filename:'/tmp/original.pdf',exists:true,state:'complete'}];},removeFile:async()=>{events.push('delete');paths.delete('/tmp/original.pdf');},erase:async()=>events.push('erase')}};
  vm.runInContext(backgroundCode,ctx);
  const P=ctx.Paperless;await P.saveSettings({base:'https://archive.test/',eraseHistory:true});await P.unlock('session-secret');
  return {P,local,session,events,network,paths,windows,badges,messages,downloadQueries,clipboard,setTabs:tabs=>{activeTabs=tabs;},menuClick:async(info,tab)=>{menuListeners[0](info,tab);await new Promise(resolve=>setImmediate(resolve));},status:x=>{status=x;}};
}
async function settled(P,id) {
  for(let i=0;i<1000;i++){const j=P.jobs().find(j=>j.id===id);if(j&&!j.busy)return j;await new Promise(r=>setTimeout(r,2));}
  throw new Error('Job did not settle');
}
test('session token is never persisted, locking clears it and new server invalidates it', async()=>{
  const h=await harness();assert.equal(h.session.auth.token,'session-secret');assert.ok(!JSON.stringify(h.local).includes('session-secret'));assert.ok(!JSON.stringify(await h.P.state()).includes('session-secret'));
  await h.P.lock();assert.equal(h.session.auth,undefined);assert.equal((await h.P.state()).unlocked,false);
  await h.P.unlock('second-secret');await h.P.saveSettings({base:'https://second.test/'});assert.equal(h.session.auth,undefined);
});
test('download watcher only accepts a completed PDF started after activation',async()=>{
  const h=await harness('success',{newDownloads:[{id:8,filename:'/tmp/image.png',exists:true,state:'complete'},{id:9,filename:'/tmp/annotated.pdf',exists:true,state:'complete'}]});
  const since=Date.now(),item=await h.P.waitForPDFDownload(since),query=h.downloadQueries.at(-1);
  assert.equal(item.id,9);assert.equal(item.path,'/tmp/annotated.pdf');assert.equal(item.name,'annotated.pdf');
  assert.equal(Date.parse(query.startedAfter),since);assert.equal(query.state,'complete');assert.equal(query.exists,true);
});
test('download watcher rejects stale activation timestamps',async()=>{
  const h=await harness();await assert.rejects(h.P.waitForPDFDownload(Date.now()-20000),/sicher gestartet/);
});
test('download watcher selects only the newly downloaded PDF matching the active document',async()=>{
  const h=await harness('success',{newDownloads:[{id:10,filename:'/tmp/other.pdf',url:'https://mail.test/other.pdf',exists:true,state:'complete'},{id:11,filename:'/tmp/Rechnung (1).pdf',url:'blob:https://mail.test/id',exists:true,state:'complete'}]});
  const item=await h.P.waitForPDFDownload(Date.now(),'Rechnung.pdf');assert.equal(item.id,11);assert.equal(item.name,'Rechnung (1).pdf');
});
test('HTML or authorization responses from protected viewers are marked for download capture',async()=>{
  for(const response of [new Response('<html>login</html>',{headers:{'Content-Type':'text/html'}}),new Response('',{status:403})]) {
    const h=await harness('success',{fetch:async url=>url==='https://webmail.test/inbox'?response:undefined});
    await assert.rejects(h.P.sourceURL('https://webmail.test/inbox'),error=>error.code==='PDF_SOURCE_PROTECTED');
  }
});
test('confirmed Paperless link is copied once after the complete send batch is sealed',async()=>{
  const h=await harness(),batch=await h.P.beginBatch(),source=await h.P.chooseDownload(4);
  const id=await h.P.start(source.id,{},false,'https://archive.test/',batch);await settled(h.P,id);await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(h.clipboard,[],'an unsealed batch must not overwrite the clipboard');
  await h.P.sealBatch(batch);await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(h.clipboard,['https://archive.test/documents/12/details']);
  assert.equal(h.P.jobs().find(job=>job.id===id).linkCopied,true);
});
test('manual copy returns only the trusted confirmed Paperless document URL',async()=>{
  const h=await harness(),source=await h.P.chooseDownload(4),id=await h.P.start(source.id,{},false);await settled(h.P,id);await new Promise(resolve=>setImmediate(resolve));
  const url=await h.P.copyJobLink(id);
  assert.equal(url,'https://archive.test/documents/12/details');assert.equal(h.clipboard.at(-1),url);
});
test('clipboard failure leaves the archived job intact and exposes a manual fallback',async()=>{
  const h=await harness('success',{clipboardError:true}),source=await h.P.chooseDownload(4),id=await h.P.start(source.id,{},false);await settled(h.P,id);await new Promise(resolve=>setImmediate(resolve));
  const job=h.P.jobs().find(item=>item.id===id);assert.equal(job.state,'success');assert.match(job.linkCopyError,/Link kopieren/);
  await assert.rejects(h.P.copyJobLink(id),/clipboard blocked/);
});
test('original deleted only AFTER successful task AND document confirmation, history erased afterwards',async()=>{
  const h=await harness();const s=await h.P.chooseDownload(4);const id=await h.P.start(s.id,{tags:[2]},true);const j=await settled(h.P,id);
  assert.equal(j.state,'success');assert.deepEqual(h.events,['upload','task','document','delete','erase']);assert.equal(h.paths.size,0);
});
for(const mode of ['failure','pending','offline','http403','missing-doc','wrong-doc']) {
  test(`${mode}: original remains intact`,async()=>{
    const h=await harness(mode);const s=await h.P.chooseDownload(4);const id=await h.P.start(s.id,{},true);const j=await settled(h.P,id);
    assert.notEqual(j.state,'success');assert.ok(!h.events.includes('delete'));assert.equal(h.paths.size,1);
  });
}
test('changed local download preserved even after confirmed archive',async()=>{
  const h=await harness();const s=await h.P.chooseDownload(4);h.paths.set('/tmp/original.pdf',new Blob(['%PDF-1.4 changed']));
  const j=await settled(h.P,await h.P.start(s.id,{},true));assert.equal(j.state,'success');assert.equal(j.cleanupWarning,true);assert.ok(!h.events.includes('delete'));
});
test('manual status retry after a pending task does not upload a second copy',async()=>{
  const h=await harness('offline');const s=await h.P.chooseDownload(4),id=await h.P.start(s.id,{},true);await settled(h.P,id);h.status('success');await h.P.retryStatus(id);await settled(h.P,id);
  assert.equal(h.events.filter(e=>e==='upload').length,1);assert.equal(h.events.filter(e=>e==='delete').length,1);
});
test('generic picker cannot delete and concurrent duplicate send is rejected',async()=>{
  const h=await harness();const f=new Blob([await pdf.arrayBuffer()]);f.name='picked.pdf';const s=await h.P.chooseFile(f);
  await assert.rejects(h.P.start(s.id,{},true));const id=await h.P.start(s.id,{},false);await assert.rejects(h.P.start(s.id,{},false));await settled(h.P,id);
});
test('stale target address blocks upload before sending any document',async()=>{
  const h=await harness();const s=await h.P.chooseDownload(4);
  await assert.rejects(h.P.start(s.id,{},true,'https://old-server.test/'));
  assert.ok(!h.events.includes('upload'));
});
test('profiles store ID metadata without retaining document title or arbitrary secrets',async()=>{
  const h=await harness();await h.P.saveProfile('Rechnung',{tags:[1,2],title:'private title',token:'do-not-store',correspondent:3});
  const p=h.local.settings.profiles[0];assert.equal(p.title,undefined);assert.equal(p.token,undefined);assert.equal(p.correspondent,3);
});
test('browser-native fetch is invoked on the window/global receiver, not on the API instance',async()=>{
  const ctx=context();ctx.Response=Response;
  vm.runInContext(`globalThis.fetch = function(url, options) {
    if (this !== globalThis) throw new TypeError("'fetch' called on an object that does not implement interface Window.");
    return Promise.resolve(Response.json({results: [], next: null}));
  };`,ctx);
  const api=new ctx.Core.API('https://archive.test/',async()=>'test-key');
  assert.equal((await api.list('tags')).length,0);
});
test('login errors identify the request without claiming a document was uploaded or leaking a token',async()=>{
  const api=new C.API('https://archive.test/',async()=>'private-test-token',async()=>{throw new TypeError('invalid header private-test-token');});
  await assert.rejects(api.list('tags'),e=>{
    assert.match(e.message,/GET https:\/\/archive.test\/api\/tags\//);
    assert.doesNotMatch(e.message,/private-test-token|Upload-Ergebnis|gesendet/);
    return true;
  });
});
test('uncertain upload errors retain the original and distinguish upload from login',async()=>{
  const api=new C.API('https://archive.test/',async()=>'test',async()=>{throw new Error('network');});
  await assert.rejects(api.upload(pdf,'x.pdf',{}),/Upload-Ergebnis unklar/);
});
test('reverse-proxy pagination uses only the page number and keeps token on configured HTTPS host',async()=>{
  for (const next of ['http://paperless:8000/api/tags/?page=2', 'http://archive.test/api/tags/?page=2', 'https://other.test/internal/tags/?page=2&ordering=evil', '?page=2']) {
    const calls=[];
    const api=new C.API('https://archive.test/paperless/',async()=>'test-key',async(url,init)=>{
      calls.push(url);
      assert.equal(new URL(url).origin,'https://archive.test');
      assert.equal(new URL(url).pathname,'/paperless/api/tags/');
      assert.equal(new URL(url).searchParams.get('ordering'),'name');
      return Response.json(calls.length===1?{results:[{id:1}],next}:{results:[{id:2}],next:null});
    });
    assert.equal((await api.list('tags')).length,2);
    assert.equal(calls.length,2);
    assert.equal(new URL(calls[1]).searchParams.get('page'),'2');
  }
});
test('pagination loops and malformed page numbers stop safely',async()=>{
  for (const page of ['1','-2','NaN','2e0','2.5','99999999999999999999']) {
    let calls=0;
    const api=new C.API('https://archive.test/',async()=>'test',async()=>{calls++;return Response.json({results:[],next:'http://internal/api/tags/?page='+page});});
    await assert.rejects(api.list('tags'));assert.equal(calls,1);
  }
});

test('composer opens a compact extension window with no token in its URL',async()=>{
  const h=await harness();await h.P.openComposer();
  assert.equal(h.windows.length,1);assert.equal(h.windows[0].type,'popup');
  assert.match(h.windows[0].url,/app.html\?compact=1/);assert.ok(!JSON.stringify(h.windows).includes('session-secret'));
});
test('UI cleanup does not interrupt the job; unread success remains visible on the badge',async()=>{
  const h=await harness();const s=await h.P.chooseDownload(4);const id=await h.P.start(s.id,{},false);
  await h.P.removeSource(s.id);const j=await settled(h.P,id);
  assert.equal(j.state,'success');assert.ok(h.badges.includes('1'));assert.equal(h.badges.at(-1),'✓');
  assert.equal(h.paths.size,1);assert.equal(h.messages.length,1);
});
test('failed jobs show a warning badge and one notification; removing the job clears the badge',async()=>{
  const h=await harness('failure');const s=await h.P.chooseDownload(4);const id=await h.P.start(s.id,{},true);
  await settled(h.P,id);assert.equal(h.badges.at(-1),'!');assert.equal(h.messages.length,1);assert.equal(h.paths.size,1);
  await h.P.discardJob(id);assert.equal(h.badges.at(-1),'');
});

test('document datetime is sent as created with timezone conversion; blank date is omitted',async()=>{
  for (const [value,expected] of [['2026-09-08T15:30:00+02:00','2026-09-08T13:30:00.000Z'],['',null]]) {
    const api=new C.API('https://archive.test/',async()=>'test',async(url,init)=>{
      assert.equal(init.body.get('created'),expected);return Response.json(task);
    });
    await api.upload(pdf,'test.pdf',{created:value});
  }
  assert.throws(()=>C.metadata({created:'invalid'}));
  assert.throws(()=>C.metadata({created:'2026-09-08T15:30'}));
});
test('document date is not retained in reusable profiles',async()=>{
  const h=await harness();const p=await h.P.saveProfile('Datum',{created:'2026-09-08T13:30:00Z'});
  assert.equal(p.created,undefined);assert.ok(!JSON.stringify(h.local).includes('2026-09-08'));
});

test('toolbar composer passes the active mail PDF into its transfer ticket',async()=>{
  const h=await harness();const url='https://mail.test/SOGo/so/user/Mail/0/folderINBOX/2379/2/attachment.pdf';
  h.setTabs([{id:7,url,title:'Rechnung September.pdf — Mozilla Firefox'}]);await h.P.openComposer();
  const ticket=new URL(h.windows[0].url).searchParams.get('intent');
  assert.ok(ticket);const data=await h.P.intent(ticket);assert.equal(data.url,url);assert.equal(data.name,'Rechnung September.pdf');assert.equal(data.viewerSource,true);
  assert.ok(!JSON.stringify(h.windows).includes('session-secret'));
});
test('context menu keeps the clicked attachment link and selected profile',async()=>{
  const h=await harness();const url='https://mail.test/attachment?id=17';
  await h.menuClick({menuItemId:'profile:invoice',linkUrl:url,pageUrl:'https://mail.test/inbox'},{url:'https://mail.test/inbox'});
  const ticket=new URL(h.windows[0].url).searchParams.get('intent');const data=await h.P.intent(ticket);
  assert.equal(data.url,url);assert.equal(data.profileId,'invoice');assert.equal(data.viewerSource,false);
});
test('internal PDF viewer address falls back to original tab; embedded PDF keeps its frame URL',async()=>{
  const h=await harness();const url='https://mail.test/attachment.pdf';
  await h.menuClick({menuItemId:'send',pageUrl:'resource://pdf.js/web/viewer.html'},{url});
  await h.menuClick({menuItemId:'send',pageUrl:'https://mail.test/inbox',frameId:2,frameUrl:url},{url:'https://mail.test/inbox'});
  for(const window of h.windows){const data=await h.P.intent(new URL(window.url).searchParams.get('intent'));assert.equal(data.url,url);assert.equal(data.viewerSource,true);}
});
test('ordinary web pages do not become implicit PDF sources via toolbar',async()=>{
  const h=await harness();h.setTabs([{url:'https://mail.test/inbox',title:'Posteingang'}]);await h.P.openComposer();
  assert.equal(new URL(h.windows[0].url).searchParams.get('intent'),null);
});
test('invalid metadata does not consume the source before a corrected send',async()=>{
  const h=await harness();const source=await h.P.chooseDownload(4);
  await assert.rejects(h.P.start(source.id,{created:'invalid'},false));
  const id=await h.P.start(source.id,{created:'2026-09-08T13:30:00Z'},false);
  assert.equal((await settled(h.P,id)).state,'success');
});

test('MD5 compatibility hashes match native reference for padding edges and binary files',async()=>{
  for(const data of [Buffer.alloc(0),Buffer.from('abc'),Buffer.from('äöü'),...Array.from([55,56,63,64,65,4097],n=>Buffer.from(Array.from({length:n},(_,i)=>(i*17)%256)))]) {
    assert.equal(await C.md5(new Uint8Array(data)),createHash('md5').update(data).digest('hex'));
  }
});
test('API v10 success and duplicate failures are distinguished without treating a duplicate ID as imported',()=>{
  assert.equal(C.taskState({results:[{task_id:task,status:'success',result_data:{document_id:12}}]},task).documentId,12);
  assert.equal(C.taskState([{task_id:task,status:'success',related_document_ids:[12]}],task).documentId,12);
  assert.equal(C.taskState([{task_id:task,status:'failure',result_data:{duplicate_of:42},related_document_ids:[42]}],task).state,'duplicate_rejected');
  assert.equal(C.taskState([{task_id:task,status:'revoked'}],task).state,'cancelled');
  assert.equal(C.taskState([{task_id:task,status:'success',related_document_ids:[12,13]}],task).state,'pending');
});
test('duplicate No sends nothing, preserves original and cancels the background job',async()=>{
  const h=await harness('duplicate');const src=await h.P.chooseDownload(4);const id=await h.P.start(src.id,{},true);
  let j=await settled(h.P,id);assert.equal(j.state,'duplicate');assert.equal(j.duplicates[0].id,42);assert.ok(!h.events.includes('upload'));
  await h.P.decideDuplicate(id,false);j=h.P.jobs().find(j=>j.id===id);
  assert.equal(j.state,'cancelled');assert.ok(!h.events.includes('upload'));assert.equal(h.paths.size,1);
});
test('duplicate Yes uploads unchanged bytes only once and deletes only after confirmed import',async()=>{
  const h=await harness('duplicate');const src=await h.P.chooseDownload(4);const id=await h.P.start(src.id,{tags:[2],created:'2026-09-08T12:00:00Z'},true);
  await settled(h.P,id);
  const decisions=await Promise.allSettled([h.P.decideDuplicate(id,true),h.P.decideDuplicate(id,true)]);
  assert.equal(decisions.filter(r=>r.status==='fulfilled').length,1);
  assert.equal((await settled(h.P,id)).state,'success');
  assert.deepEqual(h.events,['upload','task','document','delete','erase']);
  const req=h.network.find(r=>r.url.includes('post_document'));
  assert.equal(await req.init.body.get('document').text(),await pdf.text());
  assert.equal(req.init.body.get('created'),'2026-09-08T12:00:00.000Z');
});
test('server duplicate rejection after Yes is reported as rejected, never as archived',async()=>{
  const h=await harness('duplicate-rejected');const src=await h.P.chooseDownload(4);const id=await h.P.start(src.id,{},true);
  await settled(h.P,id);await h.P.decideDuplicate(id,true);const j=await settled(h.P,id);
  assert.equal(j.state,'duplicate_rejected');assert.equal(j.documentURL,undefined);assert.equal(h.paths.size,1);assert.equal(h.badges.at(-1),'!');
});
test('identical files in one batch produce one upload and one background decision',async()=>{
  const h=await harness();const a=await h.P.chooseDownload(4),b=await h.P.chooseDownload(4);
  const ids=await Promise.all([h.P.start(a.id,{},false),h.P.start(b.id,{},false)]);
  const states=await Promise.all(ids.map(id=>settled(h.P,id)));
  assert.deepEqual(states.map(j=>j.state),['success','duplicate']);assert.equal(h.events.filter(x=>x==='upload').length,1);
});
test('a failed duplicate check never uploads automatically and can be retried',async()=>{
  const h=await harness('check-error');const src=await h.P.chooseDownload(4);const id=await h.P.start(src.id,{},true);
  assert.equal((await settled(h.P,id)).state,'check_failed');assert.equal(h.events.length,0);assert.equal(h.paths.size,1);
  h.status('success');await h.P.retryCheck(id);assert.equal((await settled(h.P,id)).state,'success');
});
test('v10 completion emits one final notification and a success badge until acknowledged',async()=>{
  const h=await harness('v10');const src=await h.P.chooseDownload(4);const id=await h.P.start(src.id,{},false);
  const j=await settled(h.P,id);assert.equal(j.state,'success');assert.equal(j.documentId,12);assert.equal(j.busy,false);
  assert.equal(h.messages.length,1);assert.equal(h.messages[0].title,'Archivierung abgeschlossen');assert.equal(h.badges.at(-1),'✓');
  await h.P.acknowledgeJob(id);assert.equal(h.badges.at(-1),'');
});
test('an unconfirmed checksum filter cannot falsely label all server documents as duplicates',async()=>{
  const hashes=await C.fingerprints(pdf);
  const api=new C.API('https://archive.test/',async()=>'test',async url=>Response.json(url.includes('/metadata/')?{original_checksum:'0'.repeat(64)}:{results:[{id:42,title:'Unrelated'}]}));
  await assert.rejects(api.duplicates(hashes),/Prüfsummenfilter/);
});

const fields=[{id:20,name:'Wiedervorlage',data_type:'date'},{id:21,name:'Erledigt',data_type:'boolean'},{id:22,name:'Anzahl',data_type:'integer'}];
async function deckHarness(mode='success',share=false) {
  const cloud={cards:[],posts:0,fault:'',reads:0};
  const h=await harness(mode,{fields,fetch:async(url,init)=>{
    if(share && url.includes('/share_links/'))return Response.json({slug:'deck-public'});
    if(!url.startsWith('https://cloud.test/'))return;
    const path=new URL(url).pathname;
    assert.equal(init.headers.Authorization,'Basic '+btoa('frank:app-secret'));
    assert.equal(init.headers['OCS-APIRequest'],'true');assert.equal(init.redirect,'error');assert.equal(init.credentials,'omit');
    if(path.endsWith('/boards'))return Response.json([{id:1,title:'Büro',permissions:{PERMISSION_EDIT:true},archived:false,deletedAt:0}]);
    if(path.endsWith('/stacks')){cloud.reads++;return Response.json([{id:2,title:'Eingang',cards:cloud.cards}]);}
    if(path.endsWith('/cards')&&init.method==='POST'){
      cloud.posts++;h.events.push('deck');
      if(cloud.fault==='403')return new Response('',{status:403});
      if(cloud.fault==='timeout-empty')throw new Error('timeout');
      const card={...JSON.parse(init.body),id:100+cloud.posts,stackId:2,deletedAt:0};cloud.cards.push(card);
      if(cloud.fault==='timeout-created')throw new Error('timeout');
      return Response.json(card);
    }
    throw new Error('Unexpected Deck URL '+url);
  }});
  const boards=await h.P.connectNextcloud({base:'https://cloud.test/nc/',username:'frank',password:'app-secret'});
  assert.equal(boards[0].name,'Büro');await h.P.saveNextcloud({base:'https://cloud.test/nc/',username:'frank',boardId:1,stackId:2});
  return {...h,cloud};
}
test('all custom values are typed and serialized as one JSON multipart map',async()=>{
  const F=context().CustomFields;
  const map=F.validate({'20':'2026-10-06','21':'false','22':'0'},fields);
  const api=new C.API('https://archive.test/',async()=>'key',async(url,init)=>{
    assert.deepEqual(JSON.parse(init.body.get('custom_fields')),{'20':'2026-10-06','21':false,'22':0});return Response.json(task);
  });
  await api.upload(pdf,'test.pdf',{custom_fields:map});
});
test('custom field values are validated before consuming the source and are excluded from profiles',async()=>{
  const h=await harness('success',{fields});const source=await h.P.chooseFile(Object.assign(pdf,{name:'Test.pdf'}));
  await assert.rejects(h.P.start(source.id,{custom_fields:{20:'2026-02-30'}},false),/Kalenderdatum/);
  await assert.rejects(h.P.start(source.id,{custom_fields:{99:'unknown'}},false),/nicht mehr verfügbar/);
  const profile=await h.P.saveProfile('Typ',{custom_fields:{20:'2026-10-06'},tags:[]});assert.equal(profile.custom_fields,undefined);
  const job=await settled(h.P,await h.P.start(source.id,{custom_fields:{20:'2026-10-06'}},false));assert.equal(job.state,'success');
});
test('Deck credentials stay in session and locks clear both secrets',async()=>{
  const h=await deckHarness();assert.equal((await h.P.state()).nextcloudUnlocked,true);
  assert.ok(!JSON.stringify(h.local).includes('app-secret'));assert.ok(!JSON.stringify(await h.P.state()).includes('app-secret'));
  await h.P.lock();assert.equal(h.session.nextcloudAuth,undefined);assert.equal(h.session.auth,undefined);
});
test('Deck card contains the confirmed Paperless link and date, before original deletion',async()=>{
  const h=await deckHarness(),s=await h.P.chooseDownload(4);
  const j=await settled(h.P,await h.P.start(s.id,{title:'Bescheid',custom_fields:{20:'2026-10-06',21:false,22:0},deck_fields:[20]},true));
  assert.equal(j.state,'success');assert.equal(j.deckWarning,false);assert.equal(j.deckLinks.length,1);
  assert.deepEqual(h.events,['upload','task','document','deck','delete','erase']);
  assert.equal(h.cloud.cards[0].title,'Wiedervorlage: Bescheid');
  assert.match(h.cloud.cards[0].description,/\[Dokument in Paperless öffnen\]\(https:\/\/archive.test\/documents\/12\/details\)/);
  assert.match(h.cloud.cards[0].duedate,/2026-10-06/);
  assert.equal(h.cloud.cards[0].type,'plain');
});
test('Deck is opt-in, and failed Paperless processing never creates a card',async()=>{
  for(const mode of ['success','failure']){
    const h=await deckHarness(mode),s=await h.P.chooseDownload(4);
    await settled(h.P,await h.P.start(s.id,{custom_fields:{20:'2026-10-06'},deck_fields:mode==='failure'?[20]:[]},false));
    assert.equal(h.cloud.posts,0);
  }
});
test('duplicate No creates no Deck card; Yes retains the selected custom date',async()=>{
  for(const accept of [false,true]){
    const h=await deckHarness('duplicate'),s=await h.P.chooseDownload(4),id=await h.P.start(s.id,{custom_fields:{20:'2026-10-06'},deck_fields:[20]},false);
    assert.equal((await settled(h.P,id)).state,'duplicate');await h.P.decideDuplicate(id,accept);await settled(h.P,id);
    assert.equal(h.cloud.posts,accept?1:0);
    if(accept)assert.match(h.cloud.cards[0].description,/2026-10-06/);
  }
});
test('Deck failure keeps original and retry creates card without repeating Paperless upload',async()=>{
  const h=await deckHarness();h.cloud.fault='403';const s=await h.P.chooseDownload(4),id=await h.P.start(s.id,{custom_fields:{20:'2026-10-06'},deck_fields:[20]},true);
  const pending=await settled(h.P,id);assert.equal(pending.state,'success');assert.equal(pending.deckWarning,true);assert.equal(h.paths.size,1);assert.equal(h.badges.at(-1),'!');assert.match(h.messages.at(-1).title,/Deck offen/);
  h.cloud.fault='';await h.P.retryDeck(id);const done=await settled(h.P,id);
  assert.equal(done.deckWarning,false);assert.equal(h.events.filter(e=>e==='upload').length,1);assert.equal(h.paths.size,0);
});
test('Deck timeout after creation is recovered by matching existing card, without duplicate POST',async()=>{
  const h=await deckHarness();h.cloud.fault='timeout-created';const s=await h.P.chooseDownload(4),id=await h.P.start(s.id,{custom_fields:{20:'2026-10-06'},deck_fields:[20]},true);
  assert.equal((await settled(h.P,id)).deckUncertain,true);h.cloud.fault='';await h.P.retryDeck(id);
  const done=await settled(h.P,id);assert.equal(done.deckWarning,false);assert.equal(h.cloud.posts,1);assert.equal(h.paths.size,0);
});
test('unconfirmed Deck POST cannot be blindly repeated without explicit approval',async()=>{
  const h=await deckHarness();h.cloud.fault='timeout-empty';const s=await h.P.chooseDownload(4),id=await h.P.start(s.id,{custom_fields:{20:'2026-10-06'},deck_fields:[20]},true);
  await settled(h.P,id);h.cloud.fault='';await h.P.retryDeck(id);assert.equal((await settled(h.P,id)).deckUncertain,true);
  assert.equal(h.cloud.posts,1);assert.equal(h.paths.size,1);
  await h.P.retryDeck(id,true);assert.equal((await settled(h.P,id)).deckWarning,false);assert.equal(h.cloud.posts,2);
});
test('Deck route rejects foreign hosts and traversal before reading the password or sending',async()=>{
  let calls=0;const N=context().Nextcloud,client=new N.Client('https://cloud.test/nc/','frank',async()=>{calls++;return 'secret';},async()=>{throw new Error('must not fetch');});
  for(const path of ['https://evil.test/boards','../boards','boards/1/../../evil','boards?url=https://evil.test'])await assert.rejects(client.request(path),/API-Pfad/);
  assert.equal(calls,0);
});
test('share link API sends chosen version and expiry and preserves a server subpath',async()=>{
  for(const days of [0,1,7,30])for(const archive of [false,true]){
    let payload,url;
    const client=new C.API('https://archive.test/paperless/',async()=>'token',async(u,init)=>{url=u;payload=JSON.parse(init.body);return Response.json({slug:'public_abc-123'});});
    const before=Date.now(),link=await client.createShareLink(12,{days,archive});
    assert.equal(url,'https://archive.test/paperless/api/share_links/');
    assert.equal(payload.document,12);assert.equal(payload.file_version,archive?'archive':'original');
    assert.equal(link.url,'https://archive.test/paperless/share/public_abc-123');
    if(days)assert.ok(Math.abs(Date.parse(payload.expiration)-before-days*86400000)<1000);else assert.equal(payload.expiration,null);
  }
});
test('public link is created once after archive confirmation and copied for the batch',async()=>{
  const h=await harness('success',{fetch:async(url,init)=>{
    if(url.includes('/share_links/')){h.events.push('share');assert.equal(JSON.parse(init.body).document,12);return Response.json({slug:'anonymous-link'});}
  }}),source=await h.P.chooseDownload(4),batch=await h.P.beginBatch();
  const id=await h.P.start(source.id,{share:{days:7,archive:false}},false,'https://archive.test/',batch);
  const job=await settled(h.P,id);await h.P.sealBatch(batch);
  assert.equal(job.state,'success');assert.equal(job.shareURL,'https://archive.test/share/anonymous-link');
  assert.deepEqual(h.events,['upload','task','document','share']);assert.deepEqual(h.clipboard,[job.shareURL]);
  await h.P.copyShareLink(id);assert.equal(h.clipboard.at(-1),job.shareURL);
});
test('failed or uncertain public sharing preserves the original and never copies an internal fallback',async()=>{
  for(const mode of ['403','timeout','invalid']){
    let posts=0;
    const h=await harness('success',{fetch:async(url)=>{if(url.includes('/share_links/')){posts++;if(mode==='timeout')throw new Error('timeout');return mode==='403'?new Response('',{status:403}):Response.json({slug:'../unsafe'});}}});
    const source=await h.P.chooseDownload(4),batch=await h.P.beginBatch(),id=await h.P.start(source.id,{share:{days:7,archive:false}},true,'https://archive.test/',batch);
    const job=await settled(h.P,id);await h.P.sealBatch(batch);
    assert.equal(job.state,'success');assert.ok(job.shareWarning);assert.equal(h.paths.size,1);assert.deepEqual(h.clipboard,[]);assert.equal(posts,1);
    await h.P.retryStatus(id);assert.equal(posts,1);assert.equal(h.events.filter(e=>e==='upload').length,1);
  }
});
test('approval Deck cards use the requested public share link',async()=>{
  const h=await deckHarness('success',true),s=await h.P.chooseDownload(4);
  const j=await settled(h.P,await h.P.start(s.id,{share:{days:7,archive:false},custom_fields:{20:'2026-10-06'},deck_fields:[20]},false));
  assert.equal(j.deckWarning,false);assert.equal(h.cloud.cards.length,1);
  assert.ok(JSON.stringify(h.cloud.cards[0]).includes('https://archive.test/share/deck-public'));
  assert.ok(!JSON.stringify(h.cloud.cards[0]).includes('/documents/12/details'));
});
test('completed tagging removes all inbox tags but preserves other tags after processing',async()=>{
  let tags=[1,2,3,4],patches=0;
  const h=await harness('success',{fetch:async(url,init)=>{
    if(url.includes('/tags/'))return Response.json({results:[{id:1,is_inbox_tag:true},{id:2,is_inbox_tag:false},{id:3,is_inbox_tag:true},{id:4,name:'Automatisch'}],next:null});
    if(url.endsWith('/documents/12/')){
      if(init.method==='PATCH'){patches++;tags=JSON.parse(init.body).tags;h.events.push('tags');}
      return Response.json({id:12,tags});
    }
  }}),s=await h.P.chooseDownload(4),j=await settled(h.P,await h.P.start(s.id,{complete_tagging:true},true));
  assert.equal(j.inboxDone,true);assert.equal(j.inboxWarning,undefined);assert.deepEqual(tags,[2,4]);assert.equal(patches,1);
  assert.ok(h.events.indexOf('tags')>h.events.indexOf('task'));assert.ok(h.events.indexOf('delete')>h.events.indexOf('tags'));
});
test('inbox option disabled never changes document tags',async()=>{
  let patches=0;const h=await harness('success',{fetch:async(url,init)=>{if(init.method==='PATCH')patches++;}}),s=await h.P.chooseDownload(4);
  const j=await settled(h.P,await h.P.start(s.id,{complete_tagging:false},false));assert.equal(j.inboxDone,undefined);assert.equal(patches,0);
});
test('failed inbox cleanup can be retried without another upload and retains original until confirmed',async()=>{
  let tags=[1,2],fail=true;
  const h=await harness('success',{fetch:async(url,init)=>{
    if(url.includes('/tags/'))return Response.json({results:[{id:1,is_inbox_tag:true},{id:2,is_inbox_tag:false}],next:null});
    if(url.endsWith('/documents/12/')){if(init.method==='PATCH'){if(fail)return new Response('',{status:403});tags=JSON.parse(init.body).tags;}return Response.json({id:12,tags});}
  }}),s=await h.P.chooseDownload(4),id=await h.P.start(s.id,{complete_tagging:true},true);
  const j=await settled(h.P,id);assert.equal(j.state,'success');assert.ok(j.inboxWarning);assert.equal(h.paths.size,1);
  fail=false;await h.P.retryInbox(id);const done=await settled(h.P,id);assert.equal(done.inboxDone,true);assert.equal(done.inboxWarning,undefined);assert.equal(h.paths.size,0);assert.equal(h.events.filter(e=>e==='upload').length,1);
});
test('inbox tags reapplied by a workflow are reported rather than marked complete',async()=>{
  const api=new C.API('https://archive.test/',async()=>'token',async url=>Response.json(url.includes('/tags/')?[{id:1,is_inbox_tag:true}]:{id:12,tags:[1,2]}));
  await assert.rejects(api.removeInboxTags(12),/Workflows prüfen/);
});
test('profiles persist optional sharing and inbox completion, but not document-specific values',async()=>{
  const h=await harness(),p=await h.P.saveProfile('Genehmigung',{tags:[2],share:{days:7,archive:true},complete_tagging:true,title:'Privater Titel',custom_fields:{20:'2026-10-06'}});
  assert.deepEqual(JSON.parse(JSON.stringify(p.share)),{days:7,archive:true});assert.equal(p.complete_tagging,true);assert.equal(p.title,undefined);assert.equal(p.custom_fields,undefined);
  assert.deepEqual(h.local.settings.profiles[0].share,JSON.parse(JSON.stringify(p.share)));
  const before=h.local.settings.profiles.length;await assert.rejects(h.P.saveProfile('Falsch',{share:{days:9,archive:true}}),/Freigabeoptionen/);assert.equal(h.local.settings.profiles.length,before);
});
test('title history is bounded, deduplicated, durable, and isolated per Paperless base',async()=>{
  const h=await harness();
  await Promise.all(Array.from({length:55},(_,i)=>h.P.rememberTitle('Titel '+i)));
  const titles=await h.P.titleHistory();assert.equal(titles.length,50);assert.equal(titles[0],'Titel 54');assert.equal(titles.at(-1),'Titel 5');
  await h.P.rememberTitle('  TITEL 50  ');assert.equal((await h.P.titleHistory())[0],'TITEL 50');assert.equal((await h.P.titleHistory()).length,50);
  assert.ok(h.local.titleHistory['https://archive.test/'].includes('TITEL 50'));
  h.local.titleHistory['https://other.test/']=['Anderer Server'];
  await assert.rejects(h.P.rememberTitle('Falsches Ziel','https://other.test/'),/Adresse/);
  await h.P.clearTitleHistory();assert.equal((await h.P.titleHistory()).length,0);assert.deepEqual(h.local.titleHistory['https://other.test/'],['Anderer Server']);
});
test('document dates accept compact German notation and reject invalid calendar dates',()=>{
  const F=context().CustomFields;
  for(const input of ['220826','22082026','22.08.26','22.08.2026','2026-08-22']){
    const d=F.documentDate(input);assert.equal(d.display,'22.08.2026');const local=new Date(d.iso);assert.equal(local.getFullYear(),2026);assert.equal(local.getMonth(),7);assert.equal(local.getDate(),22);
    assert.equal(F.documentDate(d.display).iso,d.iso);
  }
  assert.equal(F.documentDate('290228').display,'29.02.2028');
  assert.equal(F.documentDate('22.08.2026 14:30').display,'22.08.2026 14:30');
  assert.equal(F.documentDate('').iso,'');
  for(const bad of ['290226','310426','321326','22082','22.08.2026 25:00'])assert.throws(()=>F.documentDate(bad));
});
test('monetary fast entry treats digit-only input as cents and is idempotent',()=>{
  const F=context().CustomFields,field={data_type:'monetary'};
  for(const [input,expected] of [['1489','14.89'],['1','0.01'],['12','0.12'],['0','0.00'],['0001489','14.89'],['-1489','-14.89'],['EUR 1489','EUR14.89'],['14,89','14.89'],['14.89','14.89'],['1489.00','1489.00']]){
    assert.equal(F.normalize(field,input),expected);assert.equal(F.normalize(field,expected),expected);
  }
  assert.equal(F.normalize({data_type:'integer'},'1489'),1489);
  assert.equal(F.normalize({data_type:'float'},'1489'),1489);
  assert.throws(()=>F.normalize(field,'14.899'));
});
test('early duplicate check finds matches without uploading or consuming the PDF',async()=>{
  const h=await harness('duplicate'),s=await h.P.chooseDownload(4);
  const result=await h.P.precheckSource(s.id,'https://archive.test/');
  assert.equal(result.state,'duplicate');assert.equal(result.matches[0].id,42);assert.equal(h.P.jobs().length,0);assert.equal(h.paths.size,1);assert.equal(h.events.includes('upload'),false);
  const j=await settled(h.P,await h.P.start(s.id,{},false));assert.equal(j.state,'duplicate');
});
test('sending checks the server again after a clear early result',async()=>{
  const h=await harness(),s=await h.P.chooseDownload(4);
  assert.equal((await h.P.precheckSource(s.id)).state,'clear');h.status('duplicate');
  const j=await settled(h.P,await h.P.start(s.id,{},false));assert.equal(j.state,'duplicate');assert.equal(h.events.includes('upload'),false);
});
test('early check stays pending when locked and does not treat API failure as no duplicate',async()=>{
  const h=await harness('check-error'),s=await h.P.chooseDownload(4);
  await assert.rejects(h.P.precheckSource(s.id),/403/);assert.equal(h.P.jobs().length,0);
  await h.P.lock();const before=h.network.length;assert.equal((await h.P.precheckSource(s.id)).state,'locked');assert.equal(h.network.length,before);
});
test('early check discards an in-flight response after session locking',async()=>{
  let release,entered=false;const gate=new Promise(resolve=>{release=resolve;});
  const h=await harness('success',{fetch:async url=>{if(url.includes('checksum__iexact=')){entered=true;await gate;return Response.json({results:[],next:null});}}}),s=await h.P.chooseDownload(4);
  const pending=assert.rejects(h.P.precheckSource(s.id),/verworfen/);
  while(!entered)await new Promise(resolve=>setImmediate(resolve));
  await h.P.lock();release();await pending;assert.equal(h.events.includes('upload'),false);
});
test('shortcut settings validate conflicts and survive general settings saves',async()=>{
  const h=await harness(),keys={send:'Strg+Enter',profile:'Ctrl+Shift+S',tags:'Alt+T',calendar:'Alt+D',share:''};
  await h.P.saveKeyboard({shortcuts:keys,fastTabs:false});
  assert.equal(h.local.settings.shortcuts.send,'Ctrl+Enter');assert.equal(h.local.settings.shortcuts.share,'');assert.equal(h.local.settings.fastTabs,false);
  await h.P.saveSettings({base:'https://archive.test/',theme:'dark'});assert.equal((await h.P.state()).config.shortcuts.send,'Ctrl+Enter');assert.equal((await h.P.state()).config.fastTabs,false);
  await assert.rejects(h.P.saveKeyboard({shortcuts:{...keys,share:'Alt+T'}}),/doppelt/);
  assert.equal((await h.P.state()).config.shortcuts.share,'');
});
test('shortcut matching ignores ordinary typing, AltGr and reserved editing keys',()=>{
  const K=context().Shortcuts;
  assert.equal(K.eventKey({key:'s',ctrlKey:true}),'Ctrl+S');assert.equal(K.eventKey({key:'S',ctrlKey:true,shiftKey:true}),'Ctrl+Shift+S');
  for(const event of [{key:'s'},{key:'s',ctrlKey:true,isComposing:true},{key:'@',ctrlKey:true,altKey:true,getModifierState:()=>true},{key:'c',ctrlKey:true}])assert.equal(K.eventKey(event),'');
  assert.throws(()=>K.validate({send:'Ctrl+W'}));assert.throws(()=>K.validate({send:'Tab'}));
});
test('updating a profile preserves its ID without creating another profile',async()=>{
  const h=await harness(),p=await h.P.saveProfile('Original',{tags:[1]});
  const updated=await h.P.saveProfile('Aktualisiert',{tags:[2],share:{days:7,archive:false},complete_tagging:true},p.id);
  assert.equal(updated.id,p.id);assert.equal(h.local.settings.profiles.length,1);assert.equal(h.local.settings.profiles[0].name,'Aktualisiert');assert.deepEqual(h.local.settings.profiles[0].tags,[2]);
  await assert.rejects(h.P.saveProfile('Fehlt',{},'missing'),/existiert/);assert.equal(h.local.settings.profiles.length,1);
});
test('assignment history ranks repeated choices and records only confirmed document uploads',async()=>{
  const h=await harness(),source=await h.P.chooseDownload(4);
  await settled(h.P,await h.P.start(source.id,{correspondent:2,document_type:3,tags:[4]},false));
  let suggestions=await h.P.assignmentSuggestions(2);assert.equal(suggestions.length,1);assert.equal(suggestions[0].count,1);
  await h.P.rememberAssignment({correspondent:2,document_type:3,tags:[4]},'https://archive.test/');suggestions=await h.P.assignmentSuggestions(2);assert.equal(suggestions[0].count,2);
  await h.P.rememberAssignment({correspondent:2,document_type:8,tags:[]},'https://other.test/');assert.equal((await h.P.assignmentSuggestions(2))[0].document_type,3);
  await h.P.clearAssignmentHistory();assert.equal((await h.P.assignmentSuggestions(2)).length,0);
  const failed=await harness('failure'),f=await failed.P.chooseDownload(4);await settled(failed.P,await failed.P.start(f.id,{correspondent:2,tags:[4]},false));assert.equal((await failed.P.assignmentSuggestions(2)).length,0);
});
test('existing duplicate can be used and shared without upload or modifying original metadata',async()=>{
  let posts=0;const h=await harness('duplicate',{fetch:async(url,init)=>{if(url.includes('/share_links/')){posts++;assert.equal(JSON.parse(init.body).document,42);return Response.json({slug:'existing-public'});}}}),s=await h.P.chooseDownload(4);
  const internal=await h.P.useExistingDuplicate(s.id,42);assert.equal(internal.url,'https://archive.test/documents/42/details');
  const shared=await h.P.useExistingDuplicate(s.id,42,{days:7,archive:false});assert.equal(shared.url,'https://archive.test/share/existing-public');assert.equal(shared.copied,true);
  await h.P.useExistingDuplicate(s.id,42,{days:7,archive:false});assert.equal(posts,1);assert.equal(h.P.jobs().length,0);assert.equal(h.events.includes('upload'),false);assert.equal(h.paths.size,1);assert.equal(h.network.some(n=>n.init.method==='PATCH'),false);
  await assert.rejects(h.P.useExistingDuplicate(s.id,999),/nicht als identische/);
});
test('uncertain existing-document share is not blindly posted again',async()=>{
  let posts=0;const h=await harness('duplicate',{fetch:async url=>{if(url.includes('/share_links/')){posts++;throw new Error('timeout');}}}),s=await h.P.chooseDownload(4);
  for(let i=0;i<2;i++)await assert.rejects(h.P.useExistingDuplicate(s.id,42,{days:7,archive:false}),/Share Links/);
  assert.equal(posts,1);assert.equal(h.paths.size,1);
});
test('completed job can generate a public link later without another upload',async()=>{
  let posts=0;const h=await harness('success',{fetch:async(url,init)=>{if(url.includes('/share_links/')){posts++;assert.equal(JSON.parse(init.body).document,12);return Response.json({slug:'from-popup'});}}}),s=await h.P.chooseDownload(4),id=await h.P.start(s.id,{},false);
  await settled(h.P,id);const url=await h.P.createJobShare(id,{days:7,archive:false});assert.equal(url,'https://archive.test/share/from-popup');
  assert.equal(h.clipboard.at(-1),url);await h.P.createJobShare(id,{days:7,archive:false});assert.equal(posts,1);assert.equal(h.events.filter(x=>x==='upload').length,1);assert.equal(h.P.jobs()[0].shareURL,url);
});
test('failed manual job sharing keeps the archived result and blocks duplicate POST retries',async()=>{
  let posts=0;const h=await harness('success',{fetch:async url=>{if(url.includes('/share_links/')){posts++;throw new Error('timeout');}}}),s=await h.P.chooseDownload(4),id=await h.P.start(s.id,{},false);await settled(h.P,id);
  for(let i=0;i<2;i++)await assert.rejects(h.P.createJobShare(id,{days:7,archive:false}),/Share Links/);
  assert.equal(posts,1);assert.equal(h.P.jobs()[0].state,'success');assert.ok(h.P.jobs()[0].manualShareError);assert.equal(h.events.filter(x=>x==='upload').length,1);
});

test('thumbnail is authenticated and read-only; locked and stale sessions return no image',async()=>{
  let release,block=false,started=false;
  const h=await harness('success',{fetch:async(url,init)=>{
    if(!url.endsWith('/documents/12/thumb/'))return;
    assert.equal(init.method,'GET');assert.equal(init.headers.Authorization,'Token session-secret');assert.equal(init.redirect,'error');assert.equal(init.headers.Accept,'*/*');
    if(block){started=true;await new Promise(r=>release=r);}
    return new Response(new Uint8Array([1,2,3]),{headers:{'Content-Type':'image/webp'}});
  }}),s=await h.P.chooseDownload(4),id=await h.P.start(s.id,{},false);
  await settled(h.P,id);assert.equal((await h.P.jobThumbnail(id)).type,'image/webp');
  block=true;const pending=h.P.jobThumbnail(id);while(!started)await new Promise(r=>setImmediate(r));
  await h.P.lock();release();assert.equal(await pending,null);const count=h.network.length;
  assert.equal(await h.P.jobThumbnail(id),null);assert.equal(h.network.length,count);
  assert.equal(h.events.filter(x=>x==='upload').length,1);
});
test('thumbnail rejects login HTML and non-image payloads',async()=>{
  const C=context().Core;
  const client=new C.API('https://archive.test/',async()=>'test',async()=>new Response('<html>login</html>',{headers:{'Content-Type':'text/html'}}));
  await assert.rejects(client.request('documents/12/thumb/',{image:true}),/Vorschaubild/);
});

test('known duplicate consent is carried into the job; unseen matches still require a decision',async()=>{
  for(const approved of [[],['document:42'],['document:99']]){
    const h=await harness('duplicate'),s=await h.P.chooseDownload(4);
    const id=await h.P.start(s.id,{},false,'https://archive.test/','',approved);
    const job=await settled(h.P,id);
    if(approved.includes('document:42')){assert.equal(job.state,'success');assert.equal(h.events.filter(x=>x==='upload').length,1);}
    else {assert.equal(job.state,'duplicate');assert.equal(h.events.filter(x=>x==='upload').length,0);}
  }
});

test('thumbnail accepts API content negotiation before receiving the binary image',async()=>{
  const C=context().Core;
  const client=new C.API('https://archive.test/',async()=>'test',async(url,init)=>{
    if(init.headers.Accept!=='*/*')return new Response('',{status:406});
    return new Response(new Uint8Array([1,2,3]),{headers:{'Content-Type':'image/webp'}});
  });
  assert.equal((await client.request('documents/12/thumb/',{image:true})).type,'image/webp');
});

test('duplicate preview fetches the requested existing document without sending or sharing',async()=>{
  const ids=[];let release,block=false,entered=false;
  const h=await harness('success',{fetch:async(url,init)=>{
    if(!url.endsWith('/thumb/'))return;
    ids.push(Number(url.match(/documents\/(\d+)\//)[1]));assert.equal(init.method,'GET');assert.equal(init.headers.Authorization,'Token session-secret');
    if(block){entered=true;await new Promise(r=>release=r);}
    return new Response(new Uint8Array([1,2,3]),{headers:{'Content-Type':'image/webp'}});
  }});
  for(const id of [42,43])assert.equal((await h.P.documentThumbnail(id,'https://archive.test/')).type,'image/webp');
  assert.deepEqual(ids,[42,43]);assert.equal(h.events.includes('upload'),false);
  assert.equal(await h.P.documentThumbnail(42,'https://other.test/'),null);assert.deepEqual(ids,[42,43]);
  await assert.rejects(h.P.documentThumbnail('../12'),/Dokument-ID/);
  block=true;const pending=h.P.documentThumbnail(42);while(!entered)await new Promise(r=>setImmediate(r));
  await h.P.lock();release();assert.equal(await pending,null);assert.equal(await h.P.documentThumbnail(42),null);
});

test('duplicate assignment is read without modifying the document and rejected on wrong target',async()=>{
  const h=await harness('success',{fetch:async(url,init)=>{
    if(url.endsWith('/documents/42/')){assert.equal(init.method,'GET');return Response.json({id:42,tags:[1,2,2]});}
  }});
  assert.deepEqual(Array.from((await h.P.documentAssignment(42,'https://archive.test/')).tags),[1,2]);assert.equal(h.events.includes('upload'),false);
  await assert.rejects(h.P.documentAssignment(42,'https://other.test/'),/entsperren/);
  await h.P.lock();await assert.rejects(h.P.documentAssignment(42),/entsperren/);
});

test('multipage preview reads only the matching original PDF with authentication',async()=>{
  let release,blocked=false,entered=false;
  const h=await harness('success',{fetch:async(url,init)=>{
    if(!url.includes('/preview/'))return;
    assert.equal(url,'https://archive.test/api/documents/42/preview/?original=true');assert.equal(init.method,'GET');assert.equal(init.headers.Authorization,'Token session-secret');assert.equal(init.headers.Accept,'*/*');assert.equal(init.redirect,'error');
    if(blocked){entered=true;await new Promise(r=>release=r);}
    return new Response(pdf,{headers:{'Content-Type':'application/pdf'}});
  }});
  assert.equal(await (await h.P.documentPDF(42,'https://archive.test/')).text(),await pdf.text());
  const requests=h.network.length;assert.equal(await h.P.documentPDF(42,'https://elsewhere.test/'),null);assert.equal(h.network.length,requests);
  blocked=true;const pending=h.P.documentPDF(42);while(!entered)await new Promise(r=>setImmediate(r));await h.P.lock();release();assert.equal(await pending,null);
  assert.equal(h.events.includes('upload'),false);
});
test('multipage preview rejects non-PDF and oversized responses before rendering',async()=>{
  for(const response of [new Response('<html>login</html>'),new Response('%PDF-1.4',{headers:{'Content-Length':String(C.MAX_BYTES+1)}})]){
    const client=new C.API('https://archive.test/',async()=>'token',async()=>response);
    await assert.rejects(client.request('documents/42/preview/?original=true',{pdf:true}),/PDF/);
  }
});

test('native preview page count is read-only, validated and discarded on session changes', async () => {
  let count = 3, entered = false, blocked = false, release;
  const h = await harness('success', {fetch: async (url, init) => {
    if (!url.endsWith('/documents/42/')) return;
    assert.equal(init.method, 'GET');
    assert.equal(init.headers.Authorization, 'Token session-secret');
    if (blocked) { entered = true; await new Promise(resolve => release = resolve); }
    return Response.json({page_count: count});
  }});
  assert.equal(await h.P.documentPageCount(42, 'https://archive.test/'), 3);
  for (count of [null, '3', -1, 0, 1.5]) assert.equal(await h.P.documentPageCount(42), null);
  const requests = h.network.length;
  assert.equal(await h.P.documentPageCount(42, 'https://elsewhere.test/'), null);
  assert.equal(h.network.length, requests);
  await assert.rejects(h.P.documentPageCount('../42'), /Dokument-ID/);
  blocked = true;
  const pending = h.P.documentPageCount(42);
  while (!entered) await new Promise(resolve => setImmediate(resolve));
  await h.P.lock(); release();
  assert.equal(await pending, null);
  assert.equal(await h.P.documentPageCount(42), null);
  assert.equal(h.events.includes('upload'), false);
});

test('series stores only the latest accepted classification as an isolated in-memory snapshot',async()=>{
 const fields=[{id:10,name:'Aktenzeichen',data_type:'string'},{id:11,name:'Betrag',data_type:'monetary'},{id:12,name:'Erledigt',data_type:'boolean'},{id:13,name:'Anzahl',data_type:'integer'},{id:14,name:'Verweise',data_type:'documentlink'}];
 const h=await harness('success',{fields}),state=await h.P.state();await h.P.saveSeriesOptions({enabled:true,inherit:true},state.config.base,state.previewRevision);
 const source=await h.P.chooseDownload(4),raw={title:'Titel pro PDF',tags:[1,2],correspondent:3,document_type:4,storage_path:5,created:'2026-09-11T00:00:00Z',custom_fields:{10:'PRIVATE-CASE-99',11:'EUR10.00',12:false,13:0,14:[42,43]},complete_tagging:true,share:{days:7,archive:false}};
 const id=await h.P.start(source.id,raw,false);raw.tags.push(99);raw.custom_fields[14].push(99);
 const remembered=(await h.P.state()).series;assert.equal(remembered.enabled,true);assert.equal(remembered.assignment.title,undefined);assert.equal(remembered.assignment.share,undefined);assert.equal(remembered.assignment.deck_fields,undefined);assert.equal(remembered.assignment.deleteLocal,undefined);
 assert.deepEqual(remembered.assignment.tags,[1,2]);assert.deepEqual(remembered.assignment.custom_fields[14],[42,43]);assert.equal(remembered.assignment.custom_fields[12],false);assert.equal(remembered.assignment.custom_fields[13],0);assert.equal(remembered.assignment.custom_fields[11],'EUR10.00');
 remembered.assignment.custom_fields[10]='mutated';assert.equal((await h.P.state()).series.assignment.custom_fields[10],'PRIVATE-CASE-99');
 assert.ok(!JSON.stringify(h.local).includes('PRIVATE-CASE-99'));assert.ok(!JSON.stringify(h.session).includes('PRIVATE-CASE-99'));
 await assert.rejects(h.P.start('missing',{tags:[99]},false),/Datei nicht mehr/);assert.deepEqual((await h.P.state()).series.assignment.tags,[1,2]);
 await settled(h.P,id);
 const next=await h.P.chooseDownload(4),nextId=await h.P.start(next.id,{tags:[7],custom_fields:{10:'NEXT-CASE'}},false);assert.deepEqual((await h.P.state()).series.assignment.tags,[7]);assert.equal((await h.P.state()).series.assignment.custom_fields[10],'NEXT-CASE');assert.equal((await h.P.state()).series.assignment.correspondent,null);await settled(h.P,nextId);
});
test('lock, a new login and a new Paperless target discard the previous series assignment',async()=>{
 for(const action of ['lock','login','target']) {
  const h=await harness(),s=await h.P.state();await h.P.saveSeriesOptions({enabled:true,inherit:false},s.config.base,s.previewRevision);const source=await h.P.chooseDownload(4),id=await h.P.start(source.id,{tags:[7]},false);await settled(h.P,id);
  if(action==='lock')await h.P.lock();else if(action==='login')await h.P.unlock('new-token');else await h.P.saveSettings({base:'https://other.test/'});
  const current=(await h.P.state()).series;assert.equal(current.assignment,null);assert.equal(current.enabled,false);assert.equal(current.inherit,true);
  await assert.rejects(h.P.saveSeriesOptions({enabled:true},s.config.base,s.previewRevision),/Sitzung/);
 }
});
