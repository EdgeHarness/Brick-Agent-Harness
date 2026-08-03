/* Agent Lab — pick a model, run a task, watch the loop. */
'use strict';

const $ = (id) => document.getElementById(id);
const CAPABILITY = new URLSearchParams(location.hash.slice(1)).get('capability') || '';
const authHeaders = (headers = {}) => ({
  ...headers, Authorization: `Bearer ${CAPABILITY}`,
});
const api = async (path, opts) => {
  opts = { ...(opts || {}), headers: authHeaders((opts && opts.headers) || {}) };
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({ error: r.statusText }));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
};
const post = (path, body) =>
  api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(body || {}) });

async function stream(path, opts, onEvent) {
  opts = { ...(opts || {}), headers: authHeaders((opts && opts.headers) || {}) };
  const response = await fetch(path, opts);
  if (!response.ok) {
    const value = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(value.error || response.statusText);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  while (true) {
    const { value, done } = await reader.read();
    pending += decoder.decode(value || new Uint8Array(), { stream: !done });
    const blocks = pending.split(/\r?\n\r?\n/);
    pending = blocks.pop();
    for (const block of blocks) {
      const line = block.split(/\r?\n/).find((part) => part.startsWith('data: '));
      if (line) onEvent(JSON.parse(line.slice(6)));
    }
    if (done) break;
  }
}

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}
const bytes = (n) => n < 1024 ? `${n} B`
  : n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1048576).toFixed(1)} MB`;
const clip = (s, n) => (s = String(s ?? ''), s.length > n ? s.slice(0, n) + '…' : s);
const ago = (ts) => {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 90) return 'just now';
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  if (s < 172800) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
};

const TOOL_ICON = {
  list_emails: '📥', read_email: '✉️', send_email: '📤', list_events: '📅',
  add_event: '📅', send_message: '💬', set_reminder: '⏰',
  create_presentation: '📊', create_spreadsheet: '📈', read_spreadsheet: '📈',
  think: '💭', save_memory: '🧠', recall_memories: '🧠', done: '✅',
};

const S = {
  agents: [], domains: [], agent: null, domain: null, ws: null, run: null, stream: null,
  call: null, banner: null, t0: 0, timer: null, seen: {}, first: true,
  locked: false, runScope: null,
  open: new Set(['files', 'inbox', 'calendar']),
};

/* ------------------------------------------------------------- models --- */

async function loadAgents(keep) {
  const data = await api('/api/agents');
  S.agents = data.agents;
  S.domains = data.domains || [];
  renderDomains();
  $('meter-ollama').className = 'meter ' + (data.ollama ? 'up' : 'down');
  $('meter-ollama').querySelector('.label').textContent =
    data.ollama ? 'ollama running' : 'ollama not running';
  renderDomainPresets();
  renderAgents();
  if (!keep) {
    const pick = S.agents.find((a) => a.installed) || S.agents[0];
    if (pick) selectAgent(pick.id);
  }
}

function renderAgents() {
  const box = $('agents');
  box.textContent = '';
  for (const a of S.agents) {
    const card = el('button', 'agent' + (a.id === S.agent ? ' on' : ''));
    card.onclick = () => selectAgent(a.id);
    card.disabled = S.locked;

    const top = el('div', 'agent-top');
    top.append(el('span', 'agent-size', a.name.replace(/^Agent\s*/, '')),
               el('span', 'agent-speed', a.speed));
    card.append(top, el('div', 'agent-model', `${a.model} · ${a.domain}`));

    const stats = el('div', 'agent-stats');
    stats.append(el('span', null, `${a.runs} run${a.runs === 1 ? '' : 's'}`),
                 el('span', null, `${a.files} file${a.files === 1 ? '' : 's'}`),
                 el('span', null, `${a.memories} learned`));
    card.append(stats, el('div', 'agent-blurb', a.blurb));

    if (!a.installed) {
      const row = el('div', 'agent-missing');
      row.append(el('span', null, 'not downloaded'));
      const btn = el('button', 'ghost small', 'Get it');
      btn.style.padding = '2px 9px';
      btn.onclick = (e) => { e.stopPropagation(); pullModel(a, row); };
      row.append(btn);
      card.append(row);
    }
    box.append(card);
  }
}

async function pullModel(a, row) {
  row.textContent = `downloading ${a.model}…`;
  const bar = el('div', 'pull-bar');
  const fill = el('i');
  bar.append(fill);
  row.after(bar);
  try {
    await stream('/api/pull', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: a.model }),
    }, (m) => {
    if (m.t === 'pull') {
      const pct = m.total ? (m.completed / m.total) * 100 : 0;
      fill.style.width = `${pct}%`;
      row.textContent = `${m.status}${m.total ? ` — ${bytes(m.completed)} / ${bytes(m.total)}` : ''}`;
    } else if (m.t === 'error') {
      row.textContent = m.message;
    } else if (m.t === 'closed') {
      loadAgents(true);
    }
    });
  } catch (err) {
    row.textContent = err.message;
  }
}

async function selectAgent(id) {
  if (S.locked) return;
  S.agent = id;
  S.first = true;
  S.seen = {};
  renderAgents();
  const selected = S.agents.find((a) => a.id === id);
  S.domain = (selected && selected.domain) ||
    (S.domains[0] && S.domains[0].name) || null;
  renderDomains();
  renderDomainPresets();
  await loadWorkspace();
  $('run').disabled = !!S.run;
}

function renderDomains() {
  const select = $('opt-domain');
  const current = S.domain;
  select.textContent = '';
  for (const domain of S.domains) {
    const option = el('option', null, `${domain.name} @ ${domain.version}`);
    option.value = domain.name;
    option.selected = domain.name === current;
    select.append(option);
  }
  if (!S.domain && S.domains.length) S.domain = S.domains[0].name;
}

function renderDomainPresets() {
  const domain = S.domains.find((item) => item.name === S.domain);
  renderPresets((domain && domain.presets) || []);
}

function renderPresets(list) {
  const box = $('presets');
  box.textContent = '';
  for (const t of list) {
    const b = el('button', 'preset', clip(t, 58));
    b.title = t;
    b.onclick = () => { $('task').value = t; $('task').focus(); };
    box.append(b);
  }
}

/* ---------------------------------------------------------- the folder --- */

async function loadWorkspace() {
  if (!S.agent) return;
  S.ws = await api(`/api/workspace?agent=${encodeURIComponent(S.agent)}` +
    `&domain=${encodeURIComponent(S.domain || '')}`);
  $('folder-path').textContent = S.ws.folder;
  renderTree(S.ws);
}

function section(key, icon, name, items, render, emptyText) {
  const d = el('details', 'node');
  d.open = S.open.has(key);
  d.ontoggle = () => d.open ? S.open.add(key) : S.open.delete(key);

  const sum = el('summary');
  const count = el('span', 'count', String(items.length));
  sum.append(el('span', 'caret', '▶'), el('span', 'ico', icon),
             el('span', 'nm', name), count);
  d.append(sum);

  const list = el('div', 'items');
  if (!items.length) {
    list.append(el('div', 'empty-note', emptyText));
  } else {
    const prev = S.seen[key] || null;
    const keys = [];
    items.forEach((item, i) => {
      const node = render(item, i);
      const k = JSON.stringify(item);
      keys.push(k);
      if (prev && !prev.has(k)) {
        node.classList.add('fresh');
        count.classList.add('bump');
        d.open = true;
        S.open.add(key);
      }
      list.append(node);
    });
    if (!S.first || !prev) S.seen[key] = new Set(keys);
  }
  d.append(list);
  return d;
}

function itemNode(line1, line2, onclick) {
  const n = el('button', 'item');
  const t1 = el('div', 't1');
  t1.innerHTML = line1;
  n.append(t1);
  if (line2) n.append(el('div', 't2', line2));
  if (onclick) n.onclick = onclick; else n.style.cursor = 'default';
  return n;
}

const esc = (s) => String(s ?? '').replace(/[&<>]/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

function renderTree(ws) {
  const tree = $('tree');
  tree.textContent = '';

  tree.append(section('files', '📁', 'files', ws.files || [], (f) =>
    itemNode(`<b>${esc(f.name)}</b>`, `${bytes(f.size)} · ${ago(f.mtime)}`,
             () => openFile(f.name)),
    'nothing created yet'));

  for (const domainSection of (ws.sections || [])) {
    tree.append(section(
      domainSection.id,
      domainSection.icon || '▣',
      domainSection.label,
      domainSection.items || [],
      (item) => {
        const object = item && typeof item === 'object' ? item : { value: item };
        const primary = object.subject ?? object.title ?? object.text ??
          object.name ?? object.value ?? JSON.stringify(object);
        const detail = Object.entries(object)
          .filter(([key]) => !['subject', 'title', 'text', 'name', 'value', 'body'].includes(key))
          .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`)
          .join(' · ');
        return itemNode(`<b>${esc(primary)}</b>`, clip(detail || object.body || '', 180),
          () => openViewer(domainSection.label, jsonBody(object)));
      },
      `no ${domainSection.label}`,
    ));
  }

  tree.append(section('memory', '🧠', 'memory', ws.memory || [], (f) =>
    itemNode(esc(f), null), 'nothing learned yet'));

  if (ws.tree) {
    tree.append(section('real', '💽', 'working folder', ws.tree, (f) =>
      itemNode((f.dir ? '📂 ' : '') + esc(f.name), f.dir ? null : bytes(f.size || 0)),
      'empty'));
  }

  tree.append(section('runs', '📜', 'past runs', ws.logs || [], (l) =>
    itemNode(esc(l.name.replace('.json', '')), ago(l.mtime), () => openLog(l.name)),
    'no runs yet'));

  S.first = false;
}

function jsonBody(value) {
  const pre = el('pre', 'raw');
  pre.textContent = JSON.stringify(value, null, 2);
  return pre;
}

/* -------------------------------------------------------------- viewer --- */

function openViewer(title, node, dl) {
  $('viewer-title').textContent = title;
  const body = $('viewer-body');
  body.textContent = '';
  body.append(node);
  const a = $('viewer-dl');
  if (dl) {
    a.href = '#';
    a.onclick = (event) => { event.preventDefault(); dl(); };
    a.classList.remove('hidden');
  } else {
    a.onclick = null;
    a.classList.add('hidden');
  }
  $('viewer').classList.remove('hidden');
}
const closeViewer = () => $('viewer').classList.add('hidden');

function mailBody(e) {
  const box = el('div');
  box.append(el('div', 'mail-meta',
    `${e.from ? 'from ' + e.from : ''}${e.to ? 'to ' + e.to : ''}${e.date ? ' · ' + e.date : ''}`));
  box.append(el('div', 'mail-body', e.body || ''));
  return box;
}
const openEmail = (e) => openViewer(e.subject, mailBody(e));

async function openFile(name) {
  const domain = encodeURIComponent(S.domain || '');
  const url = `/api/download?agent=${encodeURIComponent(S.agent)}` +
    `&domain=${domain}&name=${encodeURIComponent(name)}`;
  let p;
  try {
    p = await api(`/api/preview?agent=${encodeURIComponent(S.agent)}` +
      `&domain=${domain}&name=${encodeURIComponent(name)}`);
  } catch (err) {
    return openViewer(name, el('div', 'plain', String(err.message)));
  }
  const box = el('div');
  if (p.kind === 'pptx') {
    p.slides.forEach((s, i) => {
      const card = el('div', 'slide');
      card.append(el('div', 'n', `slide ${i + 1}`), el('h4', null, s.title || '(no title)'));
      if (s.bullets.length) {
        const ul = el('ul');
        s.bullets.forEach((b) => ul.append(el('li', null, b)));
        card.append(ul);
      }
      box.append(card);
    });
  } else if (p.kind === 'xlsx') {
    p.sheets.forEach((sh) => {
      box.append(el('div', 'n', sh.sheet));
      const t = el('table', 'sheet');
      sh.rows.forEach((row) => {
        const tr = el('tr');
        row.forEach((c) => tr.append(el('td', null, String(c))));
        t.append(tr);
      });
      box.append(t);
    });
  } else if (p.kind === 'text') {
    box.append(el('div', 'plain', p.text));
  } else {
    box.append(el('div', 'plain', `binary file, ${bytes(p.size)} — download to open it`));
  }
  openViewer(name, box, async () => {
    const response = await fetch(url, { headers: authHeaders() });
    if (!response.ok) throw new Error('download failed');
    const objectUrl = URL.createObjectURL(await response.blob());
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = name;
    anchor.click();
    URL.revokeObjectURL(objectUrl);
  });
}

async function openLog(name) {
  const log = await api(`/api/log?agent=${encodeURIComponent(S.agent)}` +
    `&domain=${encodeURIComponent(S.domain || '')}&name=${encodeURIComponent(name)}`);
  const box = el('div');
  box.append(el('div', 'mail-meta',
    `${log.model || ''} · ${log.finished ? 'finished' : 'ran out of budget'}${log.summary ? ' · ' + log.summary : ''}`));
  box.append(el('div', 'mail-body', log.task));
  const pre = el('pre', 'raw');
  pre.textContent = (log.transcript || [])
    .filter((t) => t.kind !== 'system')
    .map((t) => `[${t.kind}] ${t.content}`).join('\n\n');
  box.append(pre);
  openViewer(name, box);
}

/* ----------------------------------------------------------- the stage --- */

function addCard(cls) {
  const c = el('div', 'card ' + (cls || ''));
  $('timeline').append(c);
  autoscroll();
  return c;
}
function head(card, who, chips, meta) {
  const h = el('div', 'card-head');
  h.append(el('span', 'who', who));
  (chips || []).forEach((c) => h.append(el('span', 'chip ' + (c.cls || ''), c.text)));
  h.append(el('span', 'spacer'));
  const m = el('span', 'meta', meta || '');
  h.append(m);
  card.append(h);
  return m;
}
function autoscroll() {
  const t = $('timeline');
  if (t.scrollHeight - t.scrollTop - t.clientHeight < 220) t.scrollTop = t.scrollHeight;
}

function clearStage() {
  $('timeline').textContent = '';
  $('empty').classList.add('hidden');
  S.call = null;
}

function onBanner(e) {
  const card = addCard('banner');
  head(card, e.name, [{ text: e.model, cls: 'role-driver' },
                      { text: `${e.domain}@${e.domain_version}` },
                      { text: `${e.budget} call budget` },
                      { text: e.toolset }]);
  card.append(el('div', 'banner-title', e.task));
  const grid = el('div', 'banner-grid');
  grid.append(el('span', 'chip', `today: ${e.today}`),
              el('span', 'chip', e.endpoint));
  if (e.tiers) grid.append(el('span', 'chip', `tiers: ${Object.values(e.tiers.roles).join(', ')}`));
  card.append(grid);
  S.banner = card;
  $('calls-val').textContent = `0/${e.budget}`;
}

function onCallStart(e) {
  const card = addCard('call streaming');
  const meta = head(card, 'model', [
    { text: e.role, cls: 'role-' + e.role },
    { text: e.model },
  ], `call ${e.call}/${e.budget}`);
  const dots = el('div', 'dots');
  dots.append(el('i'), el('i'), el('i'));
  const stream = el('pre', 'stream');
  card.append(dots, stream);
  S.call = { card, stream, meta, dots, role: e.role, text: '' };
  $('calls-val').textContent = `${e.call}/${e.budget}`;
  $('calls-bar').style.width = `${(e.call / e.budget) * 100}%`;
}

function onToken(e) {
  if (!S.call) return;
  S.call.text += e.text;
  S.call.stream.textContent = S.call.text;
  S.call.stream.scrollTop = S.call.stream.scrollHeight;
  autoscroll();
}

function onCallEnd(e) {
  if (!S.call) return;
  S.call.card.classList.remove('streaming');
  S.call.dots.remove();
  S.call.meta.textContent = `${(e.ms / 1000).toFixed(1)}s · ${e.output_tokens} tokens`;
  $('tok-val').textContent = (+$('tok-val').textContent + e.output_tokens);
}

function onPlan(content) {
  const card = S.call ? S.call.card : addCard('call');
  if (S.call) S.call.stream.remove();
  const list = el('ul', 'plan');
  const steps = String(content).split('\n').filter(Boolean);
  if (!steps.length) {
    card.append(el('div', 'thought quiet', 'no usable plan — going straight to the first call'));
  } else {
    steps.forEach((s) => {
      const li = el('li');
      const m = s.match(/^\d+\.\s*(\S+)\s*-\s*(.*)$/);
      li.append(el('code', null, m ? m[1] : s));
      if (m && m[2]) li.append(el('span', null, m[2]));
      list.append(li);
    });
    card.append(el('div', 'thought quiet', 'planned tool sequence'), list);
  }
  S.call = null;
}

function onModelReply(content) {
  const card = S.call ? S.call.card : addCard('call');
  let obj = null;
  try { obj = JSON.parse(content); } catch (_) { /* the harness will repair it */ }
  if (S.call) {
    S.call.stream.remove();
    const thought = obj && (obj.thought || obj.reasoning);
    if (thought) card.append(el('div', 'thought', String(thought)));
    else if (!obj) card.append(el('div', 'thought quiet', 'reply was not valid JSON'));
    const det = el('details');
    det.append(el('summary', null, 'raw reply'));
    const pre = el('pre', 'raw');
    pre.textContent = content;
    det.append(pre);
    det.querySelector('summary').style.cssText = 'cursor:pointer;font-size:10.5px;color:var(--ink-faint);margin-top:8px';
    card.append(det);
  }
  S.call = null;
}

function onTool(e) {
  const err = !e.ok;
  const card = addCard('tool' + (err ? ' err' : '') + (e.name === 'think' ? ' think' : ''));
  const h = el('div', 'card-head');
  h.append(el('span', 'ico', TOOL_ICON[e.name] || '🔧'),
           el('span', 'tool-name', e.name));
  h.append(el('span', 'spacer'), el('span', 'meta', err ? 'error' : 'ok'));
  h.querySelector('.ico').style.marginRight = '2px';
  card.append(h);

  const args = el('div', 'args');
  for (const [k, v] of Object.entries(e.args || {})) {
    const row = el('div', 'arg');
    const val = typeof v === 'string' ? v : JSON.stringify(v);
    row.append(el('span', 'k', k + ':'), el('span', 'v', clip(val, 400)));
    args.append(row);
  }
  if (args.children.length) card.append(args);
  if (e.name !== 'think') {
    card.append(el('div', 'result ' + (err ? 'err' : 'ok'), clip(e.result, 1200)));
  }
}

function onNote(e) {
  const k = e.kind;
  if (k === 'system') {
    if (!S.banner) return;
    const det = el('details');
    det.append(el('summary', null, 'the prompt the harness built'));
    const pre = el('pre', 'raw');
    pre.textContent = e.content;
    det.append(pre);
    S.banner.append(det);
    return;
  }
  if (k === 'task' || k === 'observation') return;   // shown by the banner / tool card
  if (k === 'plan') return onPlan(e.content);
  if (k === 'model') return onModelReply(e.content);

  if (k === 'repair') {
    const c = addCard('note repair');
    c.append(el('div', 'tag', 'harness repaired the call'), el('div', 'note-text', e.content));
    return;
  }
  if (k === 'feedback') {
    const c = addCard('note feedback');
    c.append(el('div', 'tag', 'harness → model'), el('div', 'note-text', e.content));
    return;
  }
  if (k === 'verify') {
    let v = {};
    try { v = JSON.parse(e.content); } catch (_) { /* keep the raw text */ }
    const ok = v.complete !== false;
    const c = addCard('note ' + (ok ? 'verify' : 'feedback'));
    c.append(el('div', 'tag', ok ? 'verifier: complete' : 'verifier: not done'),
             el('div', 'note-text', ok ? 'every requirement checks out against the action log'
                                       : `missing: ${v.missing || e.content}`));
    return;
  }
  if (k === 'done') {
    const c = addCard('done');
    c.append(el('div', 'tag', 'done'), el('div', 'note-text', e.content || '(no summary)'));
    c.querySelector('.tag').style.color = 'var(--good)';
  }
}

function onEnd(e) {
  const card = addCard(e.finished ? 'done' : 'note');
  head(card, e.finished ? 'run complete' : 'run stopped at the budget', []);
  if (e.summary) card.append(el('div', 'note-text', e.summary));
  const grid = el('div', 'summary-grid');
  const stat = (v, l) => {
    const s = el('div', 'stat');
    s.append(el('b', null, String(v)), el('span', null, l));
    return s;
  };
  grid.append(stat(`${e.calls}/${e.budget}`, 'llm calls'),
              stat(`${e.wall}s`, 'model time'),
              stat(e.output_tokens, 'tokens out'),
              stat(e.actions.length, 'actions'),
              stat(e.tool_errors, 'tool errors'),
              stat(e.parse_failures + e.invalid_calls, 'bad replies'));
  card.append(grid);
  if (e.log) card.append(el('div', 'note-text', `transcript saved to ${e.log}`));
}

function onError(e) {
  const card = addCard('note bad');
  card.append(el('div', 'tag', 'error'), el('div', 'note-text', e.message));
}

function onConfirmation(e) {
  const card = addCard('note feedback');
  card.append(el('div', 'tag', 'operator confirmation required'),
              el('div', 'note-text', `${e.action}: ${e.detail}`));
  const controls = el('div', 'confirm-controls');
  const decide = async (decision) => {
    for (const button of controls.querySelectorAll('button')) button.disabled = true;
    try {
      await post('/api/confirm', {
        run_id: S.run, confirmation_id: e.confirmation_id,
        nonce: e.nonce, decision,
      });
      controls.append(el('span', 'note-text', decision ? 'approved' : 'denied'));
    } catch (err) {
      controls.append(el('span', 'note-text', err.message));
    }
  };
  const deny = el('button', 'ghost small', 'Deny');
  const approve = el('button', 'ghost small', 'Approve once');
  deny.onclick = () => decide(false);
  approve.onclick = () => decide(true);
  controls.append(deny, approve);
  card.append(controls);
}

/* ---------------------------------------------------------------- run --- */

function handle(e) {
  switch (e.t) {
    case 'banner': return onBanner(e);
    case 'llm_start': return onCallStart(e);
    case 'token': return onToken(e);
    case 'llm_end': return onCallEnd(e);
    case 'note': return onNote(e);
    case 'tool': return onTool(e);
    case 'world': return renderTree({ ...S.ws, ...e, logs: (S.ws || {}).logs || [] });
    case 'end': return onEnd(e);
    case 'error': return onError(e);
    case 'confirmation': return onConfirmation(e);
    case 'stdout': return void console.log('[runner]', e.text);
    case 'closed': return finishRun();
  }
}

async function startRun() {
  if (!S.agent || S.locked) return;
  const task = $('task').value.trim();
  if (!task) { $('task').focus(); return; }
  const body = {
    agent: S.agent, domain: S.domain, task,
    tiers: $('opt-tiers').checked,
    max_calls: Number.isNaN(parseInt($('opt-calls').value, 10))
      ? null : parseInt($('opt-calls').value, 10),
  };
  clearStage();
  S.locked = true;
  S.runScope = { agent: S.agent, domain: S.domain };
  $('opt-domain').disabled = true;
  $('run').disabled = true;
  renderAgents();
  let res;
  try {
    res = await post('/api/run', body);
  } catch (err) {
    S.locked = false;
    S.runScope = null;
    $('opt-domain').disabled = false;
    $('run').disabled = false;
    renderAgents();
    $('empty').classList.add('hidden');
    return onError({ message: err.message });
  }
  S.run = res.run;
  S.seen = {};
  S.first = false;
  $('run').disabled = true;
  $('stop').classList.remove('hidden');
  $('tok-val').textContent = '0';
  ['meter-calls', 'meter-time', 'meter-tok'].forEach((id) => $(id).classList.remove('hidden'));
  S.t0 = Date.now();
  S.timer = setInterval(() => {
    $('time-val').textContent = `${Math.round((Date.now() - S.t0) / 1000)}s`;
  }, 500);

  const controller = new AbortController();
  S.stream = controller;
  stream(`/api/events?run=${encodeURIComponent(S.run)}`, {
    signal: controller.signal,
  }, handle).catch((err) => {
    if (S.run && err.name !== 'AbortError') onError({ message: err.message });
    if (S.run) finishRun();
  });
}

function finishRun() {
  if (S.stream) { S.stream.abort(); S.stream = null; }
  if (S.timer) { clearInterval(S.timer); S.timer = null; }
  S.run = null;
  S.locked = false;
  S.runScope = null;
  S.call = null;
  $('run').disabled = false;
  $('opt-domain').disabled = false;
  renderAgents();
  $('stop').classList.add('hidden');
  loadAgents(true);
  loadWorkspace();
}

/* --------------------------------------------------------------- boot --- */

$('run').onclick = startRun;
$('stop').onclick = () => {
  if (S.run) post('/api/stop', { run_id: S.run }).catch(() => {});
};
$('viewer-close').onclick = closeViewer;
$('viewer').onclick = (e) => { if (e.target === $('viewer')) closeViewer(); };
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeViewer();
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) startRun();
});

$('opt-domain').onchange = async () => {
  if (S.locked) {
    $('opt-domain').value = S.domain || '';
    return;
  }
  S.domain = $('opt-domain').value;
  S.seen = {};
  S.first = true;
  renderDomainPresets();
  await loadWorkspace();
};
$('reveal').onclick = () => post('/api/reveal', {
  agent: S.agent, domain: S.domain,
}).catch((e) => alert(e.message));
$('reset').onclick = async () => {
  if (!S.agent || S.locked) return;
  const a = S.agents.find((x) => x.id === S.agent);
  if (!confirm(`Factory-reset ${a.name}'s ${S.domain} state?\n\nThis clears the selected ` +
               `domain state, deletes the files it created, and erases everything ` +
               `it has learned. Past run transcripts are kept.`)) return;
  await post('/api/reset', {
    agent: S.agent, domain: S.domain, what: ['world', 'memory', 'files'],
  });
  S.seen = {};
  S.first = true;
  await loadWorkspace();
  await loadAgents(true);
};

if (!CAPABILITY) {
  document.body.textContent = 'Agent Lab capability missing. Launch Agent Lab again.';
} else {
  loadAgents();
}
setInterval(() => { if (!S.run) loadAgents(true); }, 20000);
