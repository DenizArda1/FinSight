// Run the actual history handlers with isolated browser state and mocked HTTP.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

module.exports = async function testHistoryDeletion() {
  const nodes = new Map(), storage = new Map(), alerts = [], calls = [];
  const node = selector => {
    if (!nodes.has(selector)) nodes.set(selector, {
      value: '', innerHTML: '', textContent: '', disabled: false, hidden: false,
      classList: {toggle() {}, add() {}, remove() {}},
      addEventListener() {}, focus() {},
    });
    return nodes.get(selector);
  };
  const context = vm.createContext({
    Map, Set, Date, Intl, String, Number, JSON, encodeURIComponent,
    localStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value)},
    document: {querySelector: node, addEventListener() {}, documentElement: {scrollHeight: 0}},
    window: {innerHeight: 800, scrollY: 0, scrollTo() {}, confirm: () => false, alert: text => alerts.push(text)},
    fetch: async (url, options) => { calls.push([url, options]); return {ok: true, json: async () => []}; },
    requestAnimationFrame: callback => callback(), setInterval() {}, setTimeout() {},
  });
  const run = code => vm.runInContext(code, context);
  run(fs.readFileSync(path.join(__dirname, '../src/static/research.js'), 'utf8'));
  await new Promise(resolve => setImmediate(resolve));
  const seed = () => run(`jobs = [
    {id:'message-a', conversation_id:'a', question:'First', status:'completed', created_at:'2026-01-01'},
    {id:'message-b', conversation_id:'b', question:'Other', status:'completed', created_at:'2026-01-02'}
  ]; conversationId = 'a'; sourceJobId = 'message-a';`);
  seed();
  await run("deleteConversation('a')");
  assert.equal(run('jobs.length'), 2, 'Cancelling must preserve history');
  assert.equal(calls.filter(([, options]) => options?.method === 'DELETE').length, 0);

  context.window.confirm = () => true;
  let finishPoll;
  context.fetch = (url, options) => {
    calls.push([url, options]);
    if (options?.method === 'DELETE') return Promise.resolve({ok: true, json: async () => ({deleted:true})});
    return new Promise(resolve => { finishPoll = resolve; });
  };
  const polling = run('refresh()');
  await run("deleteConversation('a')");
  assert.equal(run('jobs.length'), 1);
  assert.equal(run('conversationId'), null);
  assert.equal(run('sourceJobId'), null);
  assert.equal(storage.get('finsight-conversation'), '');
  assert.equal(run("drafts.has('a')"), false);
  finishPoll({ok:true, json:async () => [{id:'message-a', conversation_id:'a'}]});
  await polling;
  assert.equal(run('jobs[0].id'), 'message-b', 'A stale poll must not resurrect deleted messages');

  seed();
  context.fetch = async () => ({ok:false, json:async () => ({error:'Delete failed'})});
  await run("deleteConversation('a')");
  assert.equal(run('jobs.length'), 2, 'Server failure must preserve visible history');
  assert.equal(alerts.at(-1), 'Delete failed');
  assert.equal(run('deleting'), false);
};

if (require.main === module) {
  module.exports().then(() => console.log('Chat history deletion passed.')).catch(error => {
    console.error(error);
    process.exitCode = 1;
  });
}
