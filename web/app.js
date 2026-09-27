'use strict';
const $ = (id) => document.getElementById(id);
let cases = {}, selected = '';
const messages = {
  'Price and offer changes': 'Current price, not cached copy.',
  'Service issue before a discount': 'Address a real operational signal.',
  'Consent-aware customer reminder': 'Permission before persuasion.'
};
function current() { return JSON.parse($('context').value); }
function write(data) { $('context').value = JSON.stringify(data, null, 2); }
function error(message = '') { $('error').textContent = message; }
function headers() {
  const token = $('token').value.trim();
  if (!token) throw new Error('Enter the admin token configured on this server. It is not stored by this page.');
  return {'Content-Type': 'application/json', 'Authorization': `Bearer ${token}`};
}
async function request(path, options = {}) {
  const response = await fetch(path, {...options, headers: headers(), credentials: 'omit'});
  const data = await response.json();
  if (!response.ok) throw new Error(`${response.status}: ${data.reason || 'request failed'}`);
  return data;
}
function pick(name) {
  selected = name; write(cases[name]); $('case-title').textContent = name;
  for (const button of $('scenarios').querySelectorAll('button')) button.classList.toggle('selected', button.dataset.name === name);
  error(); $('revoke').disabled = !cases[name].customer;
}
function render(data) {
  const sent = data.decision === 'send';
  $('decision-title').textContent = sent ? 'Useful next action' : 'Restraint is the action';
  $('badge').textContent = sent ? 'SEND CANDIDATE' : 'SKIP'; $('badge').className = `badge ${sent ? 'send' : 'skip'}`;
  $('message').textContent = data.body || 'No message should be sent for this supplied context.';
  $('reason').textContent = data.reason;
  $('pending').textContent = data.pending_action ? JSON.stringify(data.pending_action) : 'No action promised.';
  const facts = data.trace?.evidence?.facts || [];
  $('evidence-count').textContent = `${facts.length} supplied facts`;
  $('facts').replaceChildren();
  for (const fact of facts) {
    const row = document.createElement('div'); row.className = 'fact';
    const path = document.createElement('span'); path.className = 'path'; path.textContent = `${fact.scope}.${fact.path}`;
    const value = document.createElement('span'); value.className = 'value'; value.textContent = typeof fact.value === 'string' ? fact.value : JSON.stringify(fact.value);
    row.append(path, value); $('facts').append(row);
  }
}
async function preview() {
  error(); $('preview').disabled = true;
  try { render(await request('/debug/preview', {method: 'POST', body: JSON.stringify(current())})); }
  catch (e) { error(e.message); }
  finally { $('preview').disabled = false; }
}
async function traces() {
  error();
  try {
    const data = await request('/debug/traces?limit=12');
    $('connection-status').textContent = 'Connected · token kept in this tab only';
    $('traces').replaceChildren();
    if (!data.traces.length) $('traces').textContent = 'No stored decisions. Preview is intentionally stateless; run the API demo to populate actual records.';
    for (const trace of data.traces.slice().reverse()) {
      const row = document.createElement('div'); row.className = 'trace-row';
      const type = document.createElement('strong'); type.textContent = trace.type;
      const body = document.createElement('span'); body.textContent = trace.action?.body || trace.response?.body || trace.response?.rationale || trace.reason || JSON.stringify(trace.decisions || trace.intent || '');
      row.append(type, body); $('traces').append(row);
    }
  } catch (e) { error(e.message); $('connection-status').textContent = 'Connection not established'; }
}
function mutate(kind) {
  try {
    const c = current();
    if (kind === 'price') {
      if (!c.merchant.offers?.length) throw new Error('This case has no merchant offer to change.');
      c.merchant.offers[0].title = 'Hair Spa @ ₹599'; c.merchant.offers[0].status = 'active';
    }
    if (kind === 'withdraw') for (const offer of c.merchant.offers || []) offer.status = 'paused';
    if (kind === 'revoke') {
      if (!c.customer) throw new Error('Choose the customer reminder case first.');
      c.customer.consent.revoked_at = c.now;
    }
    write(c); error();
  } catch (e) { error(e.message); }
}
$('preview').addEventListener('click', preview);
$('connect').addEventListener('click', traces); $('refresh').addEventListener('click', traces);
$('reset').addEventListener('click', () => pick(selected));
$('change-price').addEventListener('click', () => mutate('price')); $('withdraw').addEventListener('click', () => mutate('withdraw')); $('revoke').addEventListener('click', () => mutate('revoke'));
fetch('/assets/examples.json', {credentials: 'omit'}).then(r => { if (!r.ok) throw new Error('Example cases unavailable'); return r.json(); }).then(data => {
  cases = data;
  for (const [i, name] of Object.keys(cases).entries()) {
    const button = document.createElement('button'); button.className = 'scenario'; button.dataset.name = name;
    button.textContent = `${String(i + 1).padStart(2, '0')}  ${name}`;
    const sub = document.createElement('span'); sub.textContent = messages[name] || 'Synthetic case'; button.append(sub);
    button.addEventListener('click', () => pick(name)); $('scenarios').append(button);
  }
  pick(Object.keys(cases)[0]);
}).catch(e => error(e.message));
