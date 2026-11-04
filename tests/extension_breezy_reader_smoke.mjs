import assert from 'node:assert/strict';
import fs from 'node:fs';
import { chromium } from 'playwright';
const browser=await chromium.launch({headless:true});
try {
  const page=await browser.newPage();
  const sample='<div class="position"><h2 class="company-name">Magellan AI</h2><div class="position-header"><h1>Full Stack Developer</h1><div class="type"><i class="fa-map-marker"></i><span>New York, NY</span></div></div><div class="description"><h2>Responsibilities</h2><p>Develop Ruby on Rails applications, build reliable APIs and improve PostgreSQL performance. Collaborate with engineering teams on automated testing, deployment, architecture, documentation and production support.</p><h2>Qualifications</h2><p>Three years of development experience.</p><h2>Benefits</h2><p>Health insurance and paid time off.</p></div><form>APPLICATION FORM MUST NOT BE CAPTURED</form></div>';
  const html=process.env.BREEZY_JOB_HTML ? fs.readFileSync(process.env.BREEZY_JOB_HTML,'utf8') : sample;
  await page.route('**/*',route=>route.fulfill({contentType:'text/html',body:html}));
  await page.goto('https://magellan-ai.breezy.hr/p/0bf338142798-full-stack-developer');
  await page.evaluate(()=>{
    window.messages=[];
    window.chrome={runtime:{id:'test',getManifest:()=>({version:'1.7.1'}),sendMessage:async m=>window.messages.push(m),onMessage:{addListener:()=>{},removeListener:()=>{}}}};
  });
  for(const file of ['job-site-config.js','job-board-content-script.js'])await page.addScriptTag({content:fs.readFileSync(`extension/public/${file}`,'utf8')});
  await page.waitForFunction(()=>window.messages.some(m=>m.type==='JOB_CONTEXT'));
  const context=await page.evaluate(()=>window.messages.filter(m=>m.type==='JOB_CONTEXT').at(-1).context);
  assert.equal(context.source,'breezy'); assert.equal(context.role_title,'Full Stack Developer'); assert.equal(context.company_name,'Magellan AI'); assert.equal(context.location,'New York, NY');
  assert.match(context.job_description,/Qualifications/); assert.match(context.job_description,/benefits/i);
  assert.doesNotMatch(context.job_description,/APPLICATION FORM MUST NOT/);
  assert.equal(context.source_metadata.posted_at,''); assert.equal(context.source_metadata.updated_at,'');
  assert.equal(context.source_metadata.extraction_method,'platform_dom');
  if(process.env.BREEZY_JOB_HTML){assert.ok(context.job_description.length>5000); assert.match(context.job_description,/Ruby on Rails/);}
  console.log(`Breezy capture passed: ${context.company_name}, ${context.role_title}, ${context.job_description.length} JD characters; no invented posting/update dates.`);
}finally{await browser.close();}
