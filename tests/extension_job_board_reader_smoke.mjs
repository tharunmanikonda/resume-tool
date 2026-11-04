import assert from 'node:assert/strict';
import fs from 'node:fs';
import { chromium } from 'playwright';
const config = fs.readFileSync('extension/public/job-site-config.js', 'utf8');
const reader = fs.readFileSync('extension/public/job-board-content-script.js', 'utf8');
const browser = await chromium.launch({ headless: true });
const description = '<h2>Responsibilities</h2><p>Build reliable APIs and distributed services with Python and SQL. Maintain automated tests and monitor production systems.</p><h2>Qualifications</h2><ul><li>Experience designing secure backend applications.</li><li>Collaborate with engineering and product teams.</li></ul>';
const urls = {
  workday:'https://acme.wd1.myworkdayjobs.com/en-US/Careers/job/Austin/Engineer_R123',
  icims:'https://careers-acme.icims.com/jobs/123/engineer/job',
  smartrecruiters:'https://jobs.smartrecruiters.com/Acme/123456-engineer',
  workable:'https://apply.workable.com/acme/j/ABC123/',
  oracle:'https://acme.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX/job/123',
  taleo:'https://acme.taleo.net/careersection/2/jobdetail.ftl?job=123',
  successfactors:'https://career5.successfactors.eu/career?career_job_req_id=123',
  jobvite:'https://jobs.jobvite.com/acme/job/abc123',
  bamboohr:'https://acme.bamboohr.com/careers/123',
  personio:'https://acme.jobs.personio.de/job/123',
  indeed:'https://www.indeed.com/viewjob?jk=abc123',
  glassdoor:'https://www.glassdoor.com/job-listing/engineer-acme-JV.htm?jl=123',
  ziprecruiter:'https://www.ziprecruiter.com/c/Acme/Job/Engineer/-in-Austin,TX?jid=123',
  monster:'https://www.monster.com/job-openings/engineer-austin-tx--123',
  usajobs:'https://www.usajobs.gov/job/123456',
  avature:'https://acme.avature.net/careers/JobDetail/Engineer/123',
  phenom:'https://acme.phenompeople.com/us/en/job/123/Engineer',
};
async function setup(url, markup) {
  const page = await browser.newPage();
  await page.route('**/*', route => route.fulfill({ contentType:'text/html', body:`<html><body>${markup}</body></html>` }));
  await page.goto(url);
  await page.evaluate(() => {
    window.messages=[];
    window.chrome={runtime:{id:'test',getManifest:()=>({version:'1.7.0'}),sendMessage:async m=>window.messages.push(m),onMessage:{addListener:()=>{},removeListener:()=>{}}}};
  });
  await page.addScriptTag({content:config}); await page.addScriptTag({content:reader});
  return page;
}
async function captured(page) {
  await page.waitForFunction(()=>window.messages.some(m=>m.type==='JOB_CONTEXT'));
  return page.evaluate(()=>window.messages.filter(m=>m.type==='JOB_CONTEXT').at(-1).context);
}
try {
  for (const [source,url] of Object.entries(urls)) {
    const id = source==='indeed' ? 'abc123' : source==='glassdoor' ? '123' : 'job123';
    const job={ '@type':['Thing','JobPosting'],url,title:'Software Engineer',hiringOrganization:{name:'Acme'},identifier:{value:id},description,datePosted:'2026-11-03',dateModified:'2026-11-04T01:00:00Z',validThrough:'2026-12-03' };
    const page=await setup(url,`<h1>Software Engineer</h1><script type="application/ld+json">${JSON.stringify({'@graph':[{'@type':'BreadcrumbList'},job]})}</script>`);
    const context=await captured(page);
    assert.equal(context.source,source); assert.equal(context.company_name,'Acme');
    assert.match(context.job_description,/Qualifications\nExperience/);
    assert.equal(context.source_metadata.posted_at,'2026-11-03'); assert.equal(context.source_metadata.updated_at,'2026-11-04T01:00:00Z');
    assert.doesNotMatch(context.job_description,/2026-12-03/);
    assert.equal(context.url,url);
    assert.equal(context.external_job_id,url, "Job identity must stay scoped to its employer and URL");
    await page.close();
  }
  // DOM adapters collect the complete job region, never the surrounding form.
  const dom=await setup(urls.workday,`<h2 data-automation-id="jobPostingHeader">Platform Engineer</h2><div data-testid="company-name">Acme</div><div data-automation-id="jobPostingDescription">${description}</div><span data-automation-id="postedOn">Posted 2 Days Ago</span><form>PRIVATE APPLICATION FORM SHOULD NOT APPEAR</form>`);
  const domContext=await captured(dom); assert.equal(domContext.role_title,'Platform Engineer');
  assert.doesNotMatch(domContext.job_description,/PRIVATE APPLICATION/); assert.equal(domContext.source_metadata.posted_text,'Posted 2 Days Ago');
  assert.equal(domContext.source_metadata.posted_at,'');
  // A URL-only SPA switch clears the previous job before new description data arrives.
  await dom.evaluate(()=>history.pushState({},'', '/en-US/Careers/job/Austin/Engineer_R456'));
  await dom.waitForFunction(()=>window.messages.at(-1)?.type==='JOB_CONTEXT_CLEARED');
  await dom.waitForTimeout(900);
  assert.equal(await dom.evaluate(()=>window.messages.at(-1).type),'JOB_CONTEXT_CLEARED');
  await dom.evaluate(()=>document.querySelector('[data-automation-id="jobPostingDescription"]').innerHTML='<h2>New requirements</h2><p>Build Kubernetes infrastructure and internal developer tooling. Support incident response, improve database performance and deploy secure production workloads across distributed cloud platforms.</p>');
  await dom.waitForFunction(()=>window.messages.at(-1)?.context?.job_description.includes('Kubernetes'));
  await dom.close();
  const customJob={'@type':'JobPosting',title:'Custom Engineer',hiringOrganization:{name:'Custom Co'},description,datePosted:'2026-11-03'};
  const custom=await setup('https://careers.custom.test/roles/123',`<script type="application/ld+json">${JSON.stringify(customJob)}</script>`);
  assert.equal((await captured(custom)).source,'career_page');
  await custom.evaluate(()=>{document.querySelector('script[type="application/ld+json"]').remove(); history.pushState({},'', '/about');});
  await custom.waitForFunction(()=>window.messages.at(-1)?.type==='JOB_CONTEXT_CLEARED'); await custom.close();
  const workable=await setup(urls.workable,`<h1>Engineer</h1><div data-testid="company-name">Acme</div><div data-ui="job-description">${description}</div><div data-ui="job-requirements">REQUIREMENTS SECTION</div><div data-ui="job-benefits">BENEFITS SECTION</div>`);
  const full=(await captured(workable)).job_description; assert.match(full,/REQUIREMENTS SECTION/); assert.match(full,/BENEFITS SECTION/); await workable.close();
  // A search results page must not capture the first card's schema or the whole body.
  for (const [url,markup] of [
    ['https://www.indeed.com/jobs?q=engineer',`<script type="application/ld+json">${JSON.stringify(customJob)}</script><h1>Search results</h1>`],
    ['https://example.test/about','<h1>About our company</h1>'+description],
    ['https://www.indeed.com/viewjob?jk=blocked','<h1>Verify you are human</h1><p>Sign in to continue</p>'],
  ]) {
    const page=await setup(url,markup); await page.waitForTimeout(900);
    assert.equal(await page.evaluate(()=>window.messages.some(m=>m.type==='JOB_CONTEXT')),false); await page.close();
  }
  if (process.env.JOB_READER_FIXTURE_DIR) {
    for (const [name,url] of [
      ['workday','https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/Senior-Systems-Software-Engineer--Workload-Systems-Engineering_JR2028215'],
      ['icims','https://careers-i3-corps.icims.com/jobs/5272/software-engineer/job'],
    ]) {
      const page=await setup(url,fs.readFileSync(`${process.env.JOB_READER_FIXTURE_DIR}/${name}-reader-example.html`,'utf8'));
      const context=await captured(page);
      assert.equal(context.source,name); assert.ok(context.job_description.length>1000); assert.ok(context.source_metadata.posted_at);
      console.log(`Real ${name} markup: ${context.role_title}, ${context.job_description.length} description characters, posted ${context.source_metadata.posted_at}`);
      await page.close();
    }
  }
  console.log('Job board reader smoke passed: 17 platforms, custom career pages, DOM regions, dates, SPA clearing, and no search/login capture.');
} finally { await browser.close(); }
