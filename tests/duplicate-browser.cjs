// Real Firefox test of duplicate-name previews in the actual composer.
const assert=require('node:assert/strict'),path=require('node:path');
const {pathToFileURL}=require('node:url');
const {firefox}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES?path.join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES,'playwright'):'playwright');
(async()=>{
 const browser=await firefox.launch({headless:true,timeout:20000,...(process.env.PAPERLESS_TEST_DISABLE_BROWSER_SANDBOX==='1'?{firefoxUserPrefs:{'security.sandbox.content.level':0}}:{})});
 try{
  const page=await browser.newPage({viewport:{width:680,height:850}});page.setDefaultTimeout(10000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(({version})=>{
   window.previewReads=[];window.assignmentReads=[];window.unlocked=true;window.revision=0;window.delay42=false;
   const base='https://archive.test/';
   const matches=[42,43].map(id=>({id,title:'Rechnung '+id,url:base+'documents/'+id+'/details'}));
   const P={state:async()=>({config:{base,profiles:[],theme:'light',nextcloud:null},unlocked:window.unlocked,previewRevision:window.revision,helperAllowed:false}),
    jobs:()=>[],titleHistory:async()=>[],assignmentSuggestions:async()=>[],metadata:async()=>({tags:[{id:1,name:'Manuell'},{id:2,name:'Rechnung'},{id:3,name:'Zusatzkontext'}],correspondents:[{id:5,name:'Firma'}],document_types:[{id:6,name:'Rechnung'},{id:8,name:'Bescheid'}],storage_paths:[{id:7,name:'Belege'}],custom_fields:[{id:10,name:'Betrag',data_type:'monetary'},{id:11,name:'Bezahlt',data_type:'boolean'}],warnings:[]}),
    intent:async()=>({url:base+'test.pdf'}),sourceURL:async()=>({id:'file-1',name:'Rechnung.pdf',size:1234,kind:'picker',canDelete:false}),
    precheckSource:async()=>({state:'duplicate',matches}),removeSource:async()=>{},
    documentAssignment:async(id)=>{window.assignmentReads.push(id);return {tags:[2],correspondent:5,document_type:6,storage_path:7,custom_fields:{10:'EUR10',11:false}};},
    lock:async()=>{window.unlocked=false;window.revision++;},
    documentThumbnail:async(id,expectedBase)=>{
      if(expectedBase!==base)throw new Error('Wrong base');window.previewReads.push(id);
      if(window.delay42&&id===42)await new Promise(r=>{window.release42=r;});
      const canvas=document.createElement('canvas');canvas.width=300;canvas.height=420;
      const c=canvas.getContext('2d');c.fillStyle=id===42?'#e6f0ff':'#fff1dc';c.fillRect(0,0,300,420);c.fillStyle='#223344';c.font='26px sans-serif';c.fillText('Rechnung '+id,24,54);c.font='14px sans-serif';c.fillText('Testdokument',24,88);
      return new Promise(r=>canvas.toBlob(r,'image/png'));
    }
   };
   window.browser={runtime:{getManifest:()=>({version}),getBackgroundPage:async()=>({Paperless:P})},storage:{session:{get:async()=>({}),set:async()=>{}}}};
  },{version:require('../extension/manifest.json').version});
  await page.goto(pathToFileURL(path.resolve(__dirname,'../extension/app.html')).href+'?compact=1&intent=test');
  const links=page.locator('#files .duplicate-preview-trigger');await links.nth(1).waitFor({state:'visible'});
  assert.deepEqual(await page.evaluate(()=>window.previewReads),[],'No thumbnail request until hover');
  await links.nth(0).hover();const first=links.nth(0).locator('.duplicate-thumb-image');await first.waitFor({state:'visible'});const firstURL=await first.getAttribute('src');
  assert.equal(await links.nth(0).getAttribute('href'),'https://archive.test/documents/42/details');
  await links.nth(1).hover();const second=links.nth(1).locator('.duplicate-thumb-image');await second.waitFor({state:'visible'});assert.notEqual(await second.getAttribute('src'),firstURL);
  assert.equal(await links.nth(0).locator('.duplicate-thumb').isVisible(),false);assert.deepEqual(await page.evaluate(()=>window.previewReads),[42,43]);
  await links.nth(0).hover();await first.waitFor({state:'visible'});assert.deepEqual(await page.evaluate(()=>window.previewReads),[42,43]);
  await page.setViewportSize({width:600,height:750});await first.waitFor({state:'visible'});
  const box=await links.nth(0).locator('.duplicate-thumb').boundingBox();assert.ok(box.width>=250&&box.x>=0&&box.x+box.width<=600&&box.y>=0&&box.y+box.height<=750);
  await page.keyboard.press('Escape');await links.nth(0).locator('.duplicate-thumb').waitFor({state:'hidden'});
  await page.mouse.move(590,5);await links.nth(1).hover();await second.waitFor({state:'visible'});
  if(process.env.PAPERLESS_TEST_SCREENSHOT)await page.screenshot({path:process.env.PAPERLESS_TEST_SCREENSHOT});
  await page.mouse.move(590,5);
  await page.locator('#tag-list .tag-option').filter({hasText:'Manuell'}).locator('input').click();
  await page.getByRole('button',{name:'Zuordnung übernehmen',exact:true}).first().click();
  await page.locator('#notice').filter({hasText:'Zuordnung aus'}).waitFor();
  assert.equal(await page.locator('#correspondent').inputValue(),'5');assert.equal(await page.locator('#document_type').inputValue(),'6');assert.equal(await page.locator('#storage_path').inputValue(),'7');
  assert.equal(await page.locator('#custom-field-10').inputValue(),'EUR10.00');assert.equal(await page.locator('#custom-field-11').inputValue(),'false');
  await page.locator('#tag-list .tag-option').filter({hasText:'Zusatzkontext'}).locator('input').click();
  const selected=await page.locator('#selected-tags').innerText();for(const name of ['Manuell','Rechnung','Zusatzkontext'])assert.ok(selected.includes(name));
  await page.locator('#document_type-search').fill('Bescheid');await page.locator('#document_type-search').press('Enter');assert.equal(await page.locator('#document_type').inputValue(),'8');
  await page.locator('#custom-field-10').fill('EUR1234');await page.locator('#custom-field-10').press('Tab');assert.equal(await page.locator('#custom-field-10').inputValue(),'EUR12.34');
  assert.deepEqual(await page.evaluate(()=>window.assignmentReads),[42]);
  await links.nth(1).hover();await links.nth(1).locator('.duplicate-thumb-image').waitFor({state:'visible'});
  await page.locator('#lock').click();await links.nth(1).locator('.duplicate-thumb').waitFor({state:'hidden'});
  assert.deepEqual(errors,[]);console.log('Firefox PASS: composer duplicate hover, distinct images, cache, resize, Escape, unchanged links, editable assignment import and locking.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
