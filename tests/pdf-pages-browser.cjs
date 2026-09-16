// Real Firefox built-in PDF viewer under the extension CSP; no bundled renderer.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const dep=name=>require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES?path.join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES,name):name);
const {firefox}=dep('playwright'),{PDFDocument,StandardFonts,rgb,degrees}=dep('pdf-lib');
(async()=>{
 const root=path.resolve(__dirname,'../extension'),manifest=JSON.parse(fs.readFileSync(path.join(root,'manifest.json')));
 async function fixture(count){const doc=await PDFDocument.create(),font=await doc.embedFont(StandardFonts.Helvetica),scan=await doc.embedPng(fs.readFileSync(path.join(root,'icons/paperless-send-96.png')));for(let n=1;n<=count;n++){const page=doc.addPage(n===3?[595,420]:[420,595]);page.drawRectangle({x:0,y:0,width:600,height:600,color:rgb(n===1?.9:.6,n===2?.9:.6,n===3?.9:.6)});if(n===2)page.drawImage(scan,{x:70,y:70,width:150,height:150});page.drawText('PAGE '+n+' OF '+count,{x:40,y:300,size:32,font});}return Buffer.from(await doc.save()).toString('base64');}
 const fixture3=await fixture(3),fixture2=await fixture(2),png=fs.readFileSync(path.join(root,'icons/paperless-send-96.png')).toString('base64');
 const server=http.createServer((req,res)=>{const target=path.resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));if(!target.startsWith(root+path.sep)){res.writeHead(404).end();return;}try{const data=fs.readFileSync(target),types={'.html':'text/html','.mjs':'text/javascript','.js':'text/javascript','.css':'text/css','.wasm':'application/wasm','.png':'image/png'};res.writeHead(200,{'Content-Type':types[path.extname(target)]||'application/octet-stream','Content-Security-Policy':manifest.content_security_policy});res.end(data);}catch(_){res.writeHead(404).end();}});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin='http://127.0.0.1:'+server.address().port;
 const browser=await firefox.launch({headless:true,timeout:20000,firefoxUserPrefs:{'pdfjs.disabled':false,...(process.env.PAPERLESS_TEST_DISABLE_BROWSER_SANDBOX==='1'?{'security.sandbox.content.level':0}:{})}});
 try{
  for(const mode of ['popup','app']){
   const page=await browser.newPage({viewport:mode==='popup'?{width:410,height:590}:{width:680,height:850}});page.setDefaultTimeout(20000);
   const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')console.log('BROWSER',m.text());});
   await page.addInitScript(({png,fixture3,fixture2,version,mode})=>{
    const blob=(data,type)=>new Blob([Uint8Array.from(atob(data),c=>c.charCodeAt(0))],{type}),base='https://archive.test/';
    window.pdfReads=[];window.connected=true;window.revision=0;
    const P={state:async()=>({config:{base,theme:'light',profiles:[],nextcloud:null},unlocked:window.connected,previewRevision:window.revision,helperAllowed:false}),
     jobs:()=>mode==='popup'?[{id:'j',base,name:'Drei Seiten.pdf',state:'success',documentId:12,documentURL:base+'documents/12/details'}]:[],
     jobThumbnail:async()=>blob(png,'image/png'),documentThumbnail:async()=>blob(png,'image/png'),
     documentPageCount:async id=>id===12?3:2,
     documentPDF:async(id,expectedBase)=>{if(expectedBase!==base||!window.connected)throw new Error('Wrong session');window.pdfReads.push(id);return blob(id===12?fixture3:fixture2,'application/pdf');},
     lock:async()=>{window.connected=false;window.revision++;},titleHistory:async()=>[],assignmentSuggestions:async()=>[],
     metadata:async()=>({tags:[],correspondents:[],document_types:[],storage_paths:[],custom_fields:[],warnings:[]}),intent:async()=>({url:base+'new.pdf'}),sourceURL:async()=>({id:'s',name:'Quelle.pdf',kind:'picker',size:1200,canDelete:false}),removeSource:async()=>{},
     precheckSource:async()=>({state:'duplicate',matches:[12,13].map(id=>({id,title:'Doublette '+id,url:base+'documents/'+id+'/details'}))})};
    window.browser={runtime:{getBackgroundPage:async()=>({Paperless:P}),getManifest:()=>({version}),getURL:p=>location.origin+'/'+p},storage:{session:{get:async()=>({}),set:async()=>{}}}};
   },{png,fixture3,fixture2,version:manifest.version,mode});
   await page.goto(origin+'/'+(mode==='popup'?'popup.html':'app.html?compact=1&intent=test'));
   const trigger=page.locator(mode==='popup'?'.job-thumbnail':'#files .duplicate-preview-trigger').first(),box=trigger.locator('.pdf-pager');
   await trigger.waitFor({state:'visible'});assert.deepEqual(await page.evaluate(()=>window.pdfReads),[]);
   await trigger.hover();await box.locator('.pdf-page-frame').waitFor({state:'visible'});
   const viewer=await (await box.locator('iframe').elementHandle()).contentFrame();
   const rendered=async(frame,number)=>frame.waitForFunction(n=>window.PDFViewerApplication?.page===n&&window.PDFViewerApplication.pdfViewer.getPageView(n-1)?.renderingState===3,number);
   const pixels=async(frame,number)=>frame.evaluate(n=>window.PDFViewerApplication.pdfViewer.getPageView(n-1).canvas.toDataURL(),number);
   await rendered(viewer,1);assert.equal(await viewer.evaluate(()=>window.PDFViewerApplication.pagesCount),3);
   assert.equal(await box.locator('iframe').evaluate(f=>f.contentDocument),null,'Add-on cannot access the native viewer DOM');
   assert.equal(await box.getAttribute('data-pages'),'3');assert.equal(await box.getAttribute('data-page'),'1');
   const firstPixels=await pixels(viewer,1);
   const scroll=await page.evaluate(()=>window.scrollY);await page.mouse.wheel(0,120);
   await page.waitForFunction(()=>document.querySelector('.pdf-pager[data-page="2"]'));
   assert.equal(await page.evaluate(()=>window.scrollY),scroll);await rendered(viewer,2);assert.notEqual(await pixels(viewer,2),firstPixels);
   await page.keyboard.press('ArrowRight');await page.waitForFunction(()=>document.querySelector('.pdf-pager[data-page="3"]'));
   await rendered(viewer,3);await page.keyboard.press('ArrowRight');assert.equal(await box.getAttribute('data-page'),'3');
   await page.keyboard.press('ArrowLeft');await page.waitForFunction(()=>document.querySelector('.pdf-pager[data-page="2"]'));
   const previousNavigation=await box.locator('iframe').getAttribute('src');
   await page.keyboard.press('Escape');await box.waitFor({state:'hidden'});await page.mouse.move(405,5);await trigger.hover();await box.waitFor({state:'visible'});
   await page.waitForFunction(previous=>document.querySelector('.pdf-page-frame')?.src!==previous,previousNavigation);await rendered(viewer,2);
   await viewer.waitForFunction(()=>{const page=window.PDFViewerApplication.pdfViewer.getPageView(1).div.getBoundingClientRect(),container=document.getElementById('viewerContainer').getBoundingClientRect();return page.top>=container.top-12&&page.bottom<=container.bottom+12;});
   assert.deepEqual(await page.evaluate(()=>window.pdfReads),[12]);
   if(mode==='app'){
    const second=page.locator('#files .duplicate-preview-trigger').nth(1);await second.hover();await second.locator('iframe').waitFor({state:'visible'});const secondViewer=await (await second.locator('iframe').elementHandle()).contentFrame();await rendered(secondViewer,1);assert.equal(await second.locator('.pdf-pager').getAttribute('data-pages'),'2');
    await page.keyboard.press('ArrowRight');await page.waitForFunction(()=>document.querySelectorAll('.pdf-pager')[1].dataset.page==='2');await rendered(secondViewer,2);assert.deepEqual(await page.evaluate(()=>window.pdfReads),[12,13]);
   }
   const bounds=await (mode==='app'?page.locator('#files .duplicate-preview-trigger').nth(1):trigger).locator('.pdf-pager').boundingBox();assert.ok(bounds.x>=0&&bounds.y>=0);
   if(process.env.PAPERLESS_TEST_SCREENSHOT)await page.screenshot({path:process.env.PAPERLESS_TEST_SCREENSHOT+'-'+mode+'.png'});
   await page.locator(mode==='popup'?'#lock-session':'#lock').click();await page.waitForFunction(()=>document.querySelectorAll('.pdf-page-frame').length===0);
   assert.deepEqual(errors,[]);console.log('Firefox PDF PASS:',mode,'3 native rendered pages, wheel, arrows, bounds, Escape, cache, frame isolation, locking');await page.close();
  }
 }finally{await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
