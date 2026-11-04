import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source = fs.readFileSync('extension/src/panel-main.jsx', 'utf8');
const start = source.indexOf('    const listener = (message) => {');
assert.ok(start >= 0);
const end = source.indexOf('    const storageListener =', start);
const changes=[];
const sandbox=vm.createContext({
  chrome:{tabs:{query:async()=>[{id:1}]}},viewingCurrentRef:{current:true},currentContextRef:{current:null},
  resolveContext:context=>changes.push(context), setAutofillStatus:()=>{},
});
const listener=vm.runInContext(source.slice(start,end)+'\nlistener',sandbox);
// An async onMessage listener implicitly returns a Promise even for messages it
// does not handle. Chrome may use that response instead of the worker's API reply.
for (const type of ['API_REQUEST','GET_SERVER_URL','GET_ACTIVE_CONTEXT']) {
  assert.equal(listener({type}),undefined,`${type} must be left for the background worker to answer`);
}
assert.equal(listener({type:'JOB_CONTEXT_CHANGED',tabId:2,context:{role_title:'Wrong tab'}}),undefined);
await new Promise(resolve=>setTimeout(resolve,0));
assert.equal(changes.length,0);
assert.equal(listener({type:'JOB_CONTEXT_CHANGED',tabId:1,context:{role_title:'Engineer'}}),undefined);
await new Promise(resolve=>setTimeout(resolve,0));
assert.equal(changes[0].role_title,'Engineer');
console.log('Panel message routing passed: API replies remain owned by the background worker; job updates are scoped to the active tab.');
