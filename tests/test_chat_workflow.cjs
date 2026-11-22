// Real UI handlers, isolated DOM state and controlled HTTP responses; no model calls.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

module.exports = async function testChatWorkflow() {
  const nodes = new Map(), handlers = {};
  const node = selector => {
    if (!nodes.has(selector)) nodes.set(selector, {
      value: '', innerHTML: '', textContent: '', disabled: false, hidden: false,
      listeners: {}, classList: {toggle() {}, add() {}, remove() {}},
      addEventListener(name, fn) { this.listeners[name] = fn; }, focus() {},
    });
    return nodes.get(selector);
  };
  const context = vm.createContext({
    Map, Set, Date, Intl, String, Number, JSON, encodeURIComponent,
    localStorage: {getItem() { return null; }, setItem() {}},
    document: {querySelector: node, addEventListener(name, fn) { handlers[name] = fn; }, documentElement: {scrollHeight: 0}},
    window: {innerHeight: 800, scrollY: 0, scrollTo() {}},
    fetch: async () => ({ok: true, json: async () => []}),
    requestAnimationFrame: fn => fn(), setInterval() {}, setTimeout() {},
  });
  const run = code => vm.runInContext(code, context);
  run(fs.readFileSync(path.join(__dirname, '../src/static/research.js'), 'utf8'));
  await new Promise(resolve => setImmediate(resolve));
  const input = node('#question-input');
  const submit = () => node('#new-form').listeners.submit({preventDefault() {}});

  input.value = 'New conversation draft';
  run("selectConversation('a')");
  input.value = 'Conversation A draft';
  run('selectConversation(null)');
  assert.equal(input.value, 'New conversation draft');
  run("selectConversation('a')");
  assert.equal(input.value, 'Conversation A draft');

  context.fetch = async () => { throw new TypeError('Failed to fetch'); };
  await submit();
  assert.equal(input.value, 'Conversation A draft');
  assert.equal(run('jobs.length'), 0);
  assert.equal(run('submitting'), false);
  assert.match(node('#form-error').textContent, /Sunucuya ulaşılamıyor/);
  assert.doesNotMatch(node('#form-error').textContent, /TypeError|Failed to fetch/);
  await run('refresh()');
  assert.equal(node('#connection-status').textContent, 'Sunucuya ulaşılamıyor');

  context.fetch = async () => ({ok: false, json: async () => { throw new SyntaxError('Unexpected token <'); }});
  await submit();
  assert.equal(input.value, 'Conversation A draft');
  assert.match(node('#form-error').textContent, /geçerli bir yanıt/);

  context.fetch = async () => ({ok: false, json: async () => ({error: 'Bir araştırma zaten sürüyor.'})});
  await submit();
  assert.equal(node('#form-error').textContent, 'Bir araştırma zaten sürüyor.');

  // A delayed successful send must not hijack a newly opened conversation.
  let finish;
  context.fetch = () => new Promise(resolve => { finish = resolve; });
  const sending = submit();
  run('selectConversation(null)');
  input.value = 'Another draft';
  finish({ok: true, json: async () => ({id:'message-a', conversation_id:'a', question:'Conversation A draft', status:'running', created_at:'2026-01-01'})});
  await sending;
  assert.equal(run('conversationId'), null);
  assert.equal(input.value, 'Another draft');
  assert.equal(run('jobs.length'), 1);

  run("jobs[0].status = 'failed'; jobs[0].error = 'Model unavailable'; selectConversation('a');");
  const retryButton = {dataset: {retry:'message-a'}, hasAttribute() { return false; }};
  handlers.click({target: {closest() { return retryButton; }}});
  assert.equal(input.value, 'Conversation A draft');
  assert.equal(run('jobs.length'), 1, 'Retry prepares the composer; it must not send automatically');
  const rendered = run("messageHTML({...jobs[0], status:'completed', elapsed_seconds:69.9, result:{supported:true, prose:'Answer', rows:[], sources:[], usage:{estimated_cost_usd:0.002444}}})");
  assert.doesNotMatch(rendered, /69\.9|0\.002444|\bundefined\b/);
  context.fetch = async () => ({ok:true, json:async () => []});
  await run('refresh()');
  assert.equal(node('#connection-status').textContent, 'Yerel çalışma alanı');
};
if (require.main === module) module.exports().then(() => console.log('Chat workflow passed.')).catch(error => {
  console.error(error); process.exitCode = 1;
});
