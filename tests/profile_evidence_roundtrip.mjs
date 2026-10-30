import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source = fs.readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8');
const functions = source.slice(source.indexOf('function preserveRoleEvidence('), source.indexOf('function isExperienceHistoryComplete('));
const scope = { structuredClone, experienceKeys: ['mckinsey'] };
vm.createContext(scope);
vm.runInContext(functions, scope);
const evidence = {key:'mckinsey', company:'Example', title:'Engineer', dates:'2022 - Present', location:'US', source_bullets:['Built APIs; reduced latency by 25%.'], metric_evidence:{measure:'latency', result:'25%'}};
for (const normalize of [scope.normalizeExperienceHistory, scope.normalizeInlineExperienceHistory]) {
  const saved = normalize([evidence]);
  assert.equal(JSON.stringify(saved[0].source_bullets), JSON.stringify(evidence.source_bullets));
  assert.equal(JSON.stringify(saved[0].metric_evidence), JSON.stringify(evidence.metric_evidence));
  saved[0].source_bullets.push('Changed editor value');
  assert.equal(evidence.source_bullets.length, 1);
}
console.log('Profile and inline editor evidence round trips passed.');
