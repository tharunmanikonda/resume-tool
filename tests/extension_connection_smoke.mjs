import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { chromium } from 'playwright';
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'resume-connection-test-'));
const server=http.createServer((req,res)=>{
  res.writeHead(200,{'Content-Type':'application/json'});
  const status={success:true,server_ready:true,ai_ready:true,onboarding_required:false,experience_history:[],identities:[],pdf_ready:true};
  res.end(JSON.stringify(req.url==='/api/extension/status'?status:{success:true,drafts:[],profile:{},application:{}}));
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const extension=path.resolve('extension/dist');
let context;
try {
  context=await chromium.launchPersistentContext(profile,{channel:'chromium',headless:true,args:[`--disable-extensions-except=${extension}`,`--load-extension=${extension}`]});
  let worker=context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
  const id=new URL(worker.url()).host;
  const page=await context.newPage();
  const urls=[`http://127.0.0.1:${server.address().port}`];
  if(process.env.RESUME_SERVER_URL)urls.push(process.env.RESUME_SERVER_URL);
  for(const url of urls){
    await worker.evaluate(url=>chrome.storage.local.set({resumeServerUrl:url}),url);
    await page.goto(`chrome-extension://${id}/sidepanel.html`);
    await page.getByRole('heading',{name:'No supported job selected',exact:true}).waitFor();
    const result=await page.evaluate(()=>chrome.runtime.sendMessage({type:'API_REQUEST',path:'/api/extension/status',method:'GET'}));
    assert.equal(result?.success,true,'An open panel must not intercept the background API response');
    assert.equal(result.server_ready,true);
    assert.equal(await page.getByRole('heading',{name:'Start the local resume app',exact:true}).count(),0);
    console.log(`Extension connection passed: ${url}`);
  }
} finally {
  await context?.close(); await new Promise(resolve=>server.close(resolve)); fs.rmSync(profile,{recursive:true,force:true});
}
