// Exercise the real input listeners without browser dependencies or network requests.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const nodes = new Map();
function node(selector) {
  if (!nodes.has(selector)) nodes.set(selector, {
    value: '', innerHTML: '', textContent: '', disabled: false, hidden: false,
    listeners: {}, classList: {toggle() {}, add() {}, remove() {}},
    addEventListener(name, callback) { this.listeners[name] = callback; },
    querySelector(child) { return node(`${selector} ${child}`); },
    focus() {},
    requestSubmit() { this.submissions = (this.submissions || 0) + 1; },
  });
  return nodes.get(selector);
}
const context = vm.createContext({
  console, Map, Set, Date, Intl, String, Number, JSON,
  localStorage: {getItem() { return null; }, setItem() {}},
  document: {querySelector: node, addEventListener() {}, documentElement: {scrollHeight: 0}},
  window: {innerHeight: 800, scrollY: 0, scrollTo() {}},
  fetch: async () => ({ok: true, json: async () => []}),
  requestAnimationFrame(callback) { callback(); }, setInterval() {}, setTimeout() {},
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../src/static/research.js'), 'utf8'), context);
const input = node('#question-input');
const form = node('#new-form');
input.value = 'Microsoft revenue?';
input.listeners.input();
let prevented = 0;
input.listeners.keydown({key:'Enter', shiftKey:false, isComposing:false, preventDefault(){prevented++;}});
assert.equal(form.submissions, 1);
assert.equal(prevented, 1);
input.listeners.keydown({key:'Enter', shiftKey:true, isComposing:false, preventDefault(){prevented++;}});
input.listeners.keydown({key:'Enter', shiftKey:false, isComposing:true, preventDefault(){prevented++;}});
assert.equal(form.submissions, 1, 'Shift+Enter and IME composition must not send');
assert.equal(prevented, 1, 'Shift+Enter must retain native newline behavior');
input.value = '  ';
input.listeners.input();
input.listeners.keydown({key:'Enter', shiftKey:false, isComposing:false, preventDefault(){}});
assert.equal(form.submissions, 1, 'Blank input must not send');
console.log('Chat keyboard: Enter, Shift+Enter, IME and blank input passed.');
