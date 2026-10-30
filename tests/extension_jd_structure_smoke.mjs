import assert from 'node:assert/strict';
import fs from 'node:fs';
import { chromium } from 'playwright';

function functionSource(source, name) {
  const start = source.indexOf(`  function ${name}(`);
  assert.ok(start >= 0, `Missing ${name}`);
  const end = source.indexOf('\n  function ', start + 1);
  return source.slice(start, end);
}
const browser = await chromium.launch({headless:true});
try {
  const page = await browser.newPage();
  const markup = '<h2>Required Qualifications</h2><ul><li>Experience with Java</li><li>Experience with SQL</li></ul><h2>Preferred Qualifications</h2><ul><li>Experience with Kubernetes</li></ul>';
  for (const filename of ['content-script.js','ats-content-script.js','dice-content-script.js']) {
    const source=fs.readFileSync(`extension/public/${filename}`,'utf8');
    await page.setContent(`<div id="job-details">${markup}</div><h1>Software<br>Engineer</h1>`);
    const code=['cleanText','stripHtml'].map(n=>functionSource(source,n)).join('\n');
    const stripped=await page.evaluate(({code,markup})=>eval(`${code}; stripHtml(${JSON.stringify(markup)})`),{code,markup});
    assert.match(stripped,/Required Qualifications\n/);
    assert.match(stripped,/Experience with Java\nExperience with SQL/);
    assert.match(stripped,/Preferred Qualifications\n/);
    if (filename==='content-script.js') {
      const reader=code+'\n'+['isVisible','textCandidate'].map(n=>functionSource(source,n)).join('\n');
      const result=await page.evaluate(code=>eval(`${code}; ({description:textCandidate(['#job-details'],1,true).value, title:textCandidate(['h1']).value})`),reader);
      assert.match(result.description,/Experience with Java\nExperience with SQL/);
      assert.equal(result.title,'Software Engineer');
    }
  }
  console.log('Extension JD structure smoke passed.');
} finally {await browser.close();}
