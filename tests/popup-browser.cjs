// Optional real Firefox regression. Requires Playwright and its Firefox browser.
// Run: node tests/popup-browser.cjs [extension-directory]
// API responses are local fixtures; no Paperless server or credentials required.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {firefox}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES?path.join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES,'playwright'):'playwright');
(async()=>{
  const root=path.resolve(process.argv[2]||path.join(__dirname,'../extension'));
  const browser=await firefox.launch({headless:true,timeout:20000,...(process.env.PAPERLESS_TEST_DISABLE_BROWSER_SANDBOX==='1'?{firefoxUserPrefs:{'security.sandbox.content.level':0}}:{})});
  try{
    const page=await browser.newPage({viewport:{width:410,height:590}});page.setDefaultTimeout(10000);
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.addInitScript(({png})=>{
      const blob=new Blob([Uint8Array.from(atob(png),c=>c.charCodeAt(0))],{type:'image/png'});
      window.thumbnailReads=0;
      window.testJobs=[{id:'j',name:'20260829-MEM4AZ7L-daily-payout-report-1.pdf',state:'success',documentId:12,documentURL:'https://archive.test/documents/12/details',message:'In Paperless archiviert.'}];
      window.browser={runtime:{getBackgroundPage:async()=>({Paperless:{state:async()=>({config:{base:'https://archive.test/',theme:'light'},unlocked:true}),jobs:()=>window.testJobs,jobThumbnail:async()=>{window.thumbnailReads++;return blob;}}})}};
    },{png:fs.readFileSync(path.join(root,'icons/paperless-send-96.png')).toString('base64')});
    await page.goto(pathToFileURL(path.join(root,'popup.html')).href);
    const tile=page.locator('.job-thumbnail'),zoom=page.locator('.thumbnail-zoom');
    await tile.waitFor({state:'visible'});await tile.hover();await zoom.waitFor({state:'visible'});
    const bounds=await zoom.locator('img').boundingBox();assert.ok(bounds.width>300&&bounds.height>400,'The actual image must be enlarged.');
    // Firefox toolbar popups can resize after an asynchronous image is displayed.
    await page.setViewportSize({width:410,height:580});await page.waitForTimeout(100);
    assert.equal(await zoom.isVisible(),true,'Resize must not immediately cancel hover.');
    await page.evaluate(()=>{window.testJobs[0].message='Updated job';});
    await page.getByText('Updated job',{exact:true}).waitFor();
    await zoom.waitFor({state:'visible'});
    await page.keyboard.press('Escape');await zoom.waitFor({state:'hidden'});
    await page.mouse.move(405,5);await tile.hover();await zoom.waitFor({state:'visible'});
    const position=await tile.boundingBox();await page.mouse.move(position.x+10,position.y+10);assert.equal(await zoom.isVisible(),true);
    await page.mouse.move(405,5);await zoom.waitFor({state:'hidden'});
    await tile.focus();await zoom.waitFor({state:'visible'});await page.keyboard.press('Tab');await zoom.waitFor({state:'hidden'});
    // Reopen at a scrolled position; fixed preview remains fully in the viewport.
    await page.evaluate(()=>window.scrollTo(0,60));await tile.hover();await zoom.waitFor({state:'visible'});
    const clipped=await zoom.locator('img').boundingBox();assert.ok(clipped.x>=0&&clipped.y>=0&&clipped.x+clipped.width<=410&&clipped.y+clipped.height<=580);
    assert.equal(await page.evaluate(()=>window.thumbnailReads),1);assert.deepEqual(errors,[]);
    if(process.env.PAPERLESS_TEST_SCREENSHOT)await page.screenshot({path:process.env.PAPERLESS_TEST_SCREENSHOT});
    console.log('Firefox PASS: hover, size, resize, refresh under pointer, Escape, leave/reentry, focus, scrolling, cache.');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
