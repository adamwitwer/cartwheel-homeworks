/* Cartwheel review app (HW4). Plain JS, no build step, no dependencies.
   Views: Review (one conversation at a time), Taxonomy, Labels, Progress.
   The server owns every write; the page posts one change at a time. */

const S = {
  convs: [], ctx: {}, status: {},
  ann: { annotations: [], reviewed: {} },
  sugg: { suggestions: [] },
  patterns: { modes: [] },
  samples: { batches: [] },
  labels: {},
  view: 'review', scope: 'sample', search: '', cur: null,
  drawer: null, revealed: {}, focusPolicy: null,
  pending: null, editing: null, labFilter: 'sample',
};
const IDX = { bySid: new Map(), byTrace: new Map(), sample: new Map(), hay: new Map() };

/* ------------------------------------------------------------ utilities */
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function clip(s, n) { s = String(s ?? ''); return s.length > n ? s.slice(0, n) + '…' : s; }
function toast(msg, bad = false) {
  const t = document.createElement('div');
  t.className = 'toast' + (bad ? ' bad' : '');
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), bad ? 6000 : 2200);
}
async function get(path) {
  const r = await fetch(path, { cache: 'no-store' });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}
async function post(path, body) {
  const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) { toast(data.error || `${path} failed (${r.status})`, true); throw new Error(data.error || r.status); }
  return data;
}
function fmtTime(ts) { return ts ? String(ts).replace('T', ' ').slice(0, 19) : ''; }
function store(key, val) { try { if (val === undefined) return localStorage.getItem(key); localStorage.setItem(key, val); } catch (e) { return null; } }

/* tiny markdown renderer for SPEC.md and the policy corpus */
function inline(s) {
  return esc(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
}
function md(src) {
  const lines = String(src || '').split('\n');
  const out = []; let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (/^\s*$/.test(l)) { i++; continue; }
    const h = l.match(/^(#{1,4})\s+(.*)/);
    if (h) { const n = Math.min(h[1].length + 1, 4); out.push(`<h${n}>${inline(h[2])}</h${n}>`); i++; continue; }
    if (l.trim().startsWith('|')) {
      const rows = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) { rows.push(lines[i]); i++; }
      const cells = r => r.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
      const body = rows.filter(r => !/^\s*\|[\s:|-]+\|\s*$/.test(r));
      out.push('<table>' + body.map((r, k) => '<tr>' + cells(r).map(c => k === 0 ? `<th>${inline(c)}</th>` : `<td>${inline(c)}</td>`).join('') + '</tr>').join('') + '</table>');
      continue;
    }
    if (/^\s*([-*]|\d+\.)\s+/.test(l)) {
      const items = [];
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
        let item = lines[i].replace(/^\s*([-*]|\d+\.)\s+/, ''); i++;
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !/^\s*([-*]|\d+\.)\s+/.test(lines[i])) { item += ' ' + lines[i].trim(); i++; }
        items.push(`<li>${inline(item)}</li>`);
      }
      out.push(`<ul>${items.join('')}</ul>`); continue;
    }
    if (l.startsWith('>')) {
      const q = []; while (i < lines.length && lines[i].startsWith('>')) { q.push(lines[i].replace(/^>\s?/, '')); i++; }
      out.push(`<blockquote>${inline(q.join(' '))}</blockquote>`); continue;
    }
    const para = [];
    while (i < lines.length && !/^\s*$/.test(lines[i]) && !/^(#{1,4}\s|\s*\||\s*([-*]|\d+\.)\s+|>)/.test(lines[i])) { para.push(lines[i]); i++; }
    out.push(`<p>${inline(para.join(' '))}</p>`);
  }
  return out.join('\n');
}

/* ------------------------------------------------------------ indexes */
function buildIndexes() {
  IDX.bySid.clear(); IDX.byTrace.clear(); IDX.hay.clear();
  for (const c of S.convs) {
    IDX.bySid.set(c.scenario_id, c);
    const hay = [c.scenario_id, c.role, c.summary.tools.join(' '), c.scenario.data_quality_case_id || ''];
    for (const t of c.turns) {
      IDX.byTrace.set(t.trace_id, { conv: c, turn: t });
      hay.push(t.trace_id);
      for (const b of t.blocks) hay.push(b.text || b.name || '');
    }
    IDX.hay.set(c.scenario_id, hay.join(' ').toLowerCase());
  }
  buildSampleIndex();
}
function buildSampleIndex() {
  IDX.sample.clear();
  (S.samples.batches || []).forEach((b, bi) => {
    for (const item of b.traces || []) {
      const tid = typeof item === 'string' ? item : item.trace_id;
      if (!IDX.sample.has(tid)) IDX.sample.set(tid, { batch: b.id || b.name || `batch ${bi + 1}`, order: bi, reason: item.reason });
    }
  });
}
const modes = () => (S.patterns.modes || []).filter(m => m.name);
// The course report treats 'confirmed' and 'frozen' as final; 'final' is accepted too.
const isFinal = m => ['final', 'confirmed', 'frozen'].includes(m.status);
const finalModes = () => { const f = modes().filter(isFinal); return f.length ? f : modes(); };
function annsFor(tid) { return S.ann.annotations.filter(a => a.trace_id === tid); }
function turnStatus(tid) {
  if (annsFor(tid).length) return 'annotated';
  return (S.ann.reviewed[tid] || {}).status || 'unreviewed';
}
const isReviewed = tid => ['annotated', 'no_failure'].includes(turnStatus(tid));
function labelOf(mode, tid) { return ((S.labels[mode] || {})[tid] || null); }
function pendingSugg() { return (S.sugg.suggestions || []).filter(s => (s.status || 'pending') === 'pending'); }
function convInSample(c) { return c.turns.some(t => IDX.sample.has(t.trace_id)); }
function convBatchOrder(c) { return Math.min(...c.turns.map(t => (IDX.sample.get(t.trace_id) || { order: 1e9 }).order)); }

/* ------------------------------------------------------------ loading */
async function loadAll() {
  const [convs, ctx, status, ann, sugg, patterns, samples, labels] = await Promise.all([
    get('/api/conversations'), get('/api/context'), get('/api/status'), get('/api/annotations'),
    get('/api/suggestions'), get('/api/patterns'), get('/api/samples'), get('/api/labels'),
  ]);
  Object.assign(S, { convs, ctx, status, ann, sugg, patterns, samples, labels });
  buildIndexes();
}
async function refresh(...names) {
  const map = { ann: '/api/annotations', sugg: '/api/suggestions', patterns: '/api/patterns', samples: '/api/samples', labels: '/api/labels' };
  const vals = await Promise.all(names.map(n => get(map[n])));
  names.forEach((n, i) => { S[n] = vals[i]; });
  if (names.includes('samples')) buildSampleIndex();
}

/* ------------------------------------------------------------ frame */
function renderFrame() {
  const st = S.status;
  const src = { 'langfuse': 'Langfuse · live', 'langfuse-cache': 'Langfuse · cached', 'offline-export': 'Offline export' }[st.source] || st.source;
  $('#source-pill').textContent = `${src} · ${st.traces} traces · ${st.conversations} conversations`;
  $('#source-pill').title = st.note || '';
  const wp = $('#write-pill');
  wp.textContent = 'scores → Langfuse: ' + st.langfuse_writes;
  wp.className = 'pill' + (st.langfuse_writes === 'on' ? '' : ' warn');
  const banner = $('#banner');
  if (st.source === 'offline-export') { banner.hidden = false; banner.textContent = st.note; } else banner.hidden = true;
  const n = pendingSugg().length;
  const badge = $('#sugg-count'); badge.hidden = !n; badge.textContent = n;
}
function switchView(v) {
  S.view = v;
  $$('#tabs button').forEach(b => b.classList.toggle('active', b.dataset.view === v));
  $$('.view').forEach(el => el.classList.toggle('active', el.id === 'view-' + v));
  if (v !== 'review') closeDrawer();
  render();
}
function render() {
  renderFrame();
  if (S.view === 'review') { renderRail(); renderConversation(); }
  else if (S.view === 'taxonomy') renderTaxonomy();
  else if (S.view === 'labels') renderLabels();
  else if (S.view === 'progress') renderProgress();
}

/* ------------------------------------------------------------ rail */
function railConvs() {
  let list = S.scope === 'sample' ? S.convs.filter(convInSample) : S.convs.slice();
  const q = S.search.trim().toLowerCase();
  if (q) list = list.filter(c => q.split(/\s+/).every(w => IDX.hay.get(c.scenario_id).includes(w)));
  if (S.scope === 'sample') list.sort((a, b) => convBatchOrder(a) - convBatchOrder(b) || a.scenario_id.localeCompare(b.scenario_id));
  return list;
}
function renderRail() {
  $$('#rail-seg button').forEach(b => b.classList.toggle('active', b.dataset.scope === S.scope));
  const list = railConvs();
  const el = $('#rail-list');
  if (!list.length) {
    el.innerHTML = `<div class="empty">${S.scope === 'sample'
      ? 'No sample yet. The coding agent adds batches to <span class="mono">sample_manifest.json</span>; meanwhile browse <b>All 250</b>.'
      : 'No conversations match.'}</div>`;
    return;
  }
  const html = []; let group = null;
  for (const c of list) {
    const g = S.scope === 'sample'
      ? (IDX.sample.get(c.turns.find(t => IDX.sample.has(t.trace_id)).trace_id).batch)
      : (c.scenario.group || 'scenarios');
    if (g !== group) { html.push(`<div class="rail-group">${esc(g)}</div>`); group = g; }
    const dots = c.turns.map(t => {
      const out = S.scope === 'sample' && !IDX.sample.has(t.trace_id) ? ' out' : '';
      return `<span class="dot ${turnStatus(t.trace_id)}${out}" title="turn ${t.number}: ${turnStatus(t.trace_id)}"></span>`;
    }).join('');
    html.push(`<button class="conv-item${c.scenario_id === S.cur ? ' active' : ''}" data-sid="${esc(c.scenario_id)}">
      <div class="sid">${esc(c.scenario_id)}</div>
      <div class="sub"><span class="chip role-${esc(c.role)}" style="padding:0 6px">${esc(c.role)}</span>
      ${c.summary.turn_count} turn${c.summary.turn_count > 1 ? 's' : ''} · ${c.summary.tool_call_count} tool${c.summary.tool_call_count === 1 ? '' : 's'}
      <span class="dots">${dots}</span></div></button>`);
  }
  el.innerHTML = html.join('');
  const act = $('.conv-item.active', el);
  if (act && !isVisibleIn(act, $('.rail'))) act.scrollIntoView({ block: 'center' });
}
function isVisibleIn(el, box) { const a = el.getBoundingClientRect(), b = box.getBoundingClientRect(); return a.top >= b.top + 80 && a.bottom <= b.bottom; }

/* ------------------------------------------------------------ conversation */
function curConv() { return IDX.bySid.get(S.cur); }
function go(sid, opts = {}) {
  if (!IDX.bySid.has(sid)) return;
  const changed = S.cur !== sid;
  S.cur = sid;
  if (location.hash !== '#' + sid) history.replaceState(null, '', '#' + sid);
  if (S.view !== 'review') switchView('review'); else render();
  if (changed && !opts.trace && !opts.item) window.scrollTo(0, 0);
  if (S.drawer) renderDrawer();
  requestAnimationFrame(() => {
    let target = null;
    if (opts.item) target = $(`.hl[data-item="${opts.item}"]`) || $(`.mnote[data-item="${opts.item}"]`);
    if (!target && opts.trace) target = $(`.turn[data-trace="${opts.trace}"]`);
    if (target) {
      target.scrollIntoView({ block: 'center' });
      const note = opts.item && $(`.mnote[data-item="${opts.item}"]`);
      if (note) { note.classList.add('outline'); setTimeout(() => note.classList.remove('outline'), 1800); }
    }
  });
}

function renderConversation() {
  const main = $('#main');
  const c = curConv();
  if (!c) { main.innerHTML = '<div class="empty">Pick a conversation on the left.</div>'; return; }
  const sm = c.summary, sc = c.scenario;
  const flags = [];
  if (sm.no_tools) flags.push('<span class="chip flag">no tools called</span>');
  if (sm.no_policy_retrieved) flags.push('<span class="chip flag">no policy text retrieved</span>');
  if (sm.unretrieved_citations.length) flags.push(`<span class="chip flag">cites never-retrieved: ${esc(sm.unretrieved_citations.join(', '))}</span>`);
  if (sc.data_quality_case_id) flags.push(`<span class="chip dq" title="data-quality challenge case">⚠ ${esc(sc.data_quality_case_id)}</span>`);
  const tools = sm.tools.map(t => `<span class="chip tool">${esc(t)}</span>`).join('');
  const lf = c.turns.map(t => t.langfuse_url ? `<a class="ctxbtn" href="${esc(t.langfuse_url)}" target="_blank" rel="noopener">T${t.number} ↗</a>` : '').join('');
  const head = `<div class="convhead">
    <div class="row"><h1>${esc(c.scenario_id)}</h1>
      <span class="chip role-${esc(c.role)}">${esc(c.role)}</span>
      <span class="chip meta">user ${esc(c.user_id ?? '—')}</span>
      <span class="chip meta">store ${esc(c.store_id ?? 'none')}</span>
      <span class="chip meta">${esc(sc.group || '')}</span>
      <span class="chip meta">${sm.turn_count} turn${sm.turn_count > 1 ? 's' : ''}</span>
      <span class="chip meta" title="the seeded world's today (tool results carry it as as_of)">world date ${esc(S.ctx.world_asof)}</span>
      ${flags.join('')}</div>
    <div class="row">${tools || ''}
      <span class="spacer"></span>
      <button class="ctxbtn key" data-open="key">${S.revealed[c.session_id] ? 'Answer key' : 'Answer key (hidden)'}</button>
      <button class="ctxbtn" data-open="policies">Policies</button>
      <button class="ctxbtn" data-open="prompt">Prompt</button>
      <button class="ctxbtn" data-open="tools">Tools</button>
      <button class="ctxbtn" data-open="spec">SPEC</button>
      <span class="small">Langfuse</span>${lf}</div>
  </div>`;
  const turns = c.turns.map(t => renderTurn(c, t)).join('');
  main.innerHTML = head + `<div class="conv-body"><div class="thread" id="thread">${turns}</div><div class="margin" id="margin"></div></div>`;
  applyHighlights();
  layoutMargin();
}

function renderTurn(c, t) {
  const st = turnStatus(t.trace_id);
  const samp = IDX.sample.get(t.trace_id);
  const sampChip = samp ? `<span class="chip batch" title="${esc(samp.reason || '')}">${esc(samp.batch)}</span>`
    : (S.samples.batches.length ? '<span class="chip meta">not in sample</span>' : '');
  const noTools = t.tool_names.length ? '' : '<span class="chip flag">no tools this turn</span>';
  const nf = st === 'no_failure';
  const right = (nf ? '' : `<span class="status ${st}">${{ unreviewed: 'unreviewed', annotated: 'annotated', read: 'read' }[st]}</span>`) +
    (st === 'annotated' ? '' : `<button class="rbtn${nf ? ' on' : ''}" data-nofail="${t.trace_id}" title="${nf ? 'Click to undo' : 'Record that you read this trace and saw no failure'}">✓ no failure observed</button>`);
  const blocks = t.blocks.map(b => renderBlock(c, b)).join('');
  return `<section class="turn${samp || !S.samples.batches.length ? '' : ' notsampled'}" data-trace="${t.trace_id}">
    <div class="turnbar"><span class="tn">Turn ${t.number} of ${c.turns.length}</span>
      <span class="tmeta">${esc(fmtTime(t.timestamp))} · ${t.latency != null ? t.latency.toFixed(1) + ' s' : ''}</span>
      ${sampChip}${noTools}<span class="right">${right}</span></div>
    ${blocks}${renderLabelStrip(t)}</section>`;
}

function renderBlock(c, b) {
  const who = { user: `Customer · ${c.role}`, note: 'Agent · note before tool call', reply: 'Agent · reply sent to customer' }[b.kind];
  if (b.kind === 'tool') return renderTool(b);
  const cites = (b.citations || []).map(x => {
    const cls = x.retrieved ? 'retrieved' : 'unretrieved';
    const title = x.retrieved ? 'retrieved by a tool earlier in this conversation' : 'never retrieved in this conversation';
    return `<button class="cite ${cls}${x.known ? '' : ' unknown'}" data-policy="${esc(x.policy_id)}" title="${title}${x.known ? '' : ' · not a policy in the corpus'}">${esc(x.policy_id)} ${x.retrieved ? '✓' : '✗'}${x.known ? '' : ' ?'}</button>`;
  }).join('');
  return `<div class="blk ${b.kind}" data-key="${b.key}"><div class="who">${who}</div>
    <div class="txt ann-target" data-key="${b.key}" data-trace="${b.trace_id}">${esc(b.text)}</div>
    ${cites ? `<div class="cites">${cites}</div>` : ''}</div>`;
}

const DEC = () => new Set(S.ctx.decision_keys || []);
// Reviewer lookups: names for store_id / product_id from data/cartwheel.db.
// Drawn by CSS (::after), so they are not text in the trace: they cannot shift
// annotation offsets or end up in a quoted selection.
const LOOKUP_TIP = 'Reviewer lookup from data/cartwheel.db. Not part of the tool result the agent saw.';
function lookupName(k, v) {
  const N = S.ctx.names || {};
  if (v === null || v === undefined) return '';
  if (k === 'store_id') return (N.stores || {})[String(v)] || '';
  if (k === 'product_id') {
    const p = (N.products || {})[String(v)];
    if (!p) return '';
    const st = (N.stores || {})[String(p.store_id)];
    return `${p.title}${st ? ` · ${st} (store ${p.store_id})` : ''}`;
  }
  return '';
}
function valHtml(v, k) {
  const nm = k ? lookupName(k, v) : '';
  if (nm) return `<span class="lk" data-lk="${esc(nm)}" title="${esc(LOOKUP_TIP)}">${esc(v)}</span>`;
  if (v === null || v === undefined) return '<span class="val-null">null</span>';
  if (v === true) return '<span class="val-true">true</span>';
  if (v === false) return '<span class="val-false">false</span>';
  if (typeof v === 'object') return `<span class="mono">${esc(JSON.stringify(v))}</span>`;
  return esc(v);
}
function kvTable(obj, dec) {
  const rows = [];
  for (const [k, v] of Object.entries(obj)) {
    const d = dec.has(k) ? ' dec' : '';
    if (Array.isArray(v) && v.length && v.every(x => x && typeof x === 'object' && !Array.isArray(x))) {
      const cols = [...new Set(v.flatMap(x => Object.keys(x)))];
      // Wide records (orders) read better as one field/value list per item, so
      // no column, such as refund_eligible, is pushed off screen. Narrow
      // records (product lists) stay a compact row table.
      const sub = cols.length > 5
        ? v.map((x, n) => `${v.length > 1 ? `<div class="small" style="margin-top:6px">#${n + 1}</div>` : ''}${kvTable(x, dec)}`).join('')
        : `<div class="scrollx"><table class="kv"><tr>${cols.map(col => `<th class="${dec.has(col) ? 'dec' : ''}">${esc(col)}</th>`).join('')}</tr>` +
          v.map(x => `<tr>${cols.map(col => `<td class="${dec.has(col) ? 'dec' : ''}">${valHtml(x[col], col)}</td>`).join('')}</tr>`).join('') + '</table></div>';
      rows.push(`<tr><td class="k${d}">${esc(k)} (${v.length})</td><td>${sub}</td></tr>`);
    } else if (v && typeof v === 'object' && !Array.isArray(v)) {
      rows.push(`<tr><td class="k${d}">${esc(k)}</td><td>${kvTable(v, dec)}</td></tr>`);
    } else {
      rows.push(`<tr><td class="k${d}">${esc(k)}</td><td class="${d.trim()}">${valHtml(v, k)}</td></tr>`);
    }
  }
  return `<table class="kv">${rows.join('')}</table>`;
}
function renderTool(b) {
  const args = b.arguments && typeof b.arguments === 'object'
    ? Object.entries(b.arguments).map(([k, v]) => `${esc(k)}: ${esc(JSON.stringify(v))}`).join(', ')
    : esc(JSON.stringify(b.arguments ?? ''));
  let badge = '';
  if (b.permission_denied) badge = '<span class="chip err">permission denied</span>';
  else if (b.ok === true) badge = '<span class="chip ok">ok</span>';
  else if (b.ok === false) badge = `<span class="chip err">error: ${esc(b.error || 'failed')}</span>`;
  const res = b.result && typeof b.result === 'object' ? kvTable(b.result, DEC()) : `<pre>${esc(b.result)}</pre>`;
  return `<div class="blk tool" data-key="${b.key}"><div class="who">Tool call ${badge}</div>
    <div class="ann-target" data-key="${b.key}" data-trace="${b.trace_id}">
      <div class="fn">${esc(b.name)}(<span class="args">${args}</span>)</div>${res}</div>
    <details class="raw"><summary>raw JSON</summary><pre>${esc(JSON.stringify({ arguments: b.arguments, result: b.result }, null, 2))}</pre></details></div>`;
}

function renderLabelStrip(t) {
  const ms = modes();
  if (!ms.length) return '';
  const sugg = pendingSugg().filter(s => s.kind === 'label' && s.trace_id === t.trace_id);
  return `<div class="lstrip"><span class="small" style="align-self:center">Judgments:</span>${ms.map(m => {
    const cur = labelOf(m.name, t.trace_id);
    const sg = sugg.find(s => s.mode === m.name);
    const on = v => cur && cur.label === v ? ' on' : '';
    const ghost = v => sg && Number(sg.label) === v ? ' ghost' : '';
    return `<span class="lmode"><span class="mn">${esc(m.name)}</span>
      <button class="sbtn present${on(1)}${ghost(1)}" data-label="${t.trace_id}|${esc(m.name)}|1" title="failure present">present</button>
      <button class="sbtn absent${on(0)}${ghost(0)}" data-label="${t.trace_id}|${esc(m.name)}|0" title="failure absent">absent</button></span>`;
  }).join('')}</div>`;
}

/* ------------------------------------------------------------ highlights + margin */
function itemsForConv(c) {
  const ids = new Set(c.turns.map(t => t.trace_id));
  const anns = S.ann.annotations.filter(a => ids.has(a.trace_id)).map(a => ({ ...a, kind: 'human' }));
  const sg = pendingSugg().filter(s => ids.has(s.trace_id) && (s.kind || 'span') === 'span').map(s => ({ ...s, kind: 'sugg' }));
  return [...anns, ...sg];
}
function textNodes(el) {
  const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); const out = []; let n;
  while ((n = w.nextNode())) out.push(n);
  return out;
}
function wrapRange(el, start, end, cls, id) {
  let pos = 0; const spans = [];
  for (const node of textNodes(el)) {
    const len = node.nodeValue.length;
    const s = Math.max(start, pos), e = Math.min(end, pos + len);
    if (s < e) {
      let target = node;
      if (s > pos) target = target.splitText(s - pos);
      if (e < pos + len) target.splitText(e - s);
      const span = document.createElement('span');
      span.className = cls; span.dataset.item = id;
      target.parentNode.insertBefore(span, target); span.appendChild(target);
      spans.push(span);
    }
    pos += len;
    if (pos >= end) break;
  }
  return spans;
}
function locate(el, it) {
  const text = el.textContent;
  if (Number.isInteger(it.start) && text.slice(it.start, it.end) === it.quote) return [it.start, it.end];
  if (it.quote) { const p = text.indexOf(it.quote); if (p >= 0) return [p, p + it.quote.length]; }
  return null;
}
function applyHighlights() {
  const c = curConv(); if (!c) return;
  for (const it of itemsForConv(c)) {
    const el = it.block_key && $(`.ann-target[data-key="${CSS.escape(it.block_key)}"]`);
    if (!el) continue;
    const r = locate(el, it);
    if (r) wrapRange(el, r[0], r[1], it.kind === 'sugg' ? 'hl sugg' : 'hl', it.id);
  }
}
function layoutMargin() {
  const col = $('#margin'); const c = curConv();
  if (!col || !c) return;
  col.innerHTML = '';
  const colTop = col.getBoundingClientRect().top;
  const items = itemsForConv(c).map(it => {
    const hl = $(`.hl[data-item="${it.id}"]`);
    const anchor = hl || $(`.turn[data-trace="${it.trace_id}"]`);
    return { it, hl, top: anchor ? anchor.getBoundingClientRect().top - colTop : 0 };
  }).sort((a, b) => a.top - b.top);
  let last = 0;
  for (const { it, hl, top } of items) {
    const n = document.createElement('div');
    n.className = 'mnote ' + (it.kind === 'sugg' ? 'sugg' : 'human');
    n.dataset.item = it.id;
    let h = '';
    if (it.kind === 'sugg') h += `<div class="tag">AI suggestion${it.mode ? ' · ' + esc(it.mode) : ''}</div>`;
    else if (it.source === 'accepted_suggestion') h += '<div class="tag" style="color:var(--palm)">accepted suggestion</div>';
    if (it.quote) h += `<div class="quote">“${esc(clip(it.quote, 90))}”</div>`;
    if (S.editing === it.id) {
      h += `<textarea data-edit-input="${it.id}">${esc(it.note)}</textarea><div class="acts" style="visibility:visible"><button class="sbtn accept" data-edit-save="${it.id}">save</button><button class="sbtn" data-edit-cancel="1">cancel</button></div>`;
    } else {
      h += `<div class="body">${esc(it.note || '')}</div>`;
      h += it.kind === 'sugg'
        ? `<div class="acts"><button class="sbtn accept" data-decide="${it.id}|accepted">accept</button><button class="sbtn reject" data-decide="${it.id}|rejected">reject</button></div>`
        : `<div class="acts"><button class="sbtn" data-edit="${it.id}">edit</button><button class="sbtn reject" data-del="${it.id}|${it.trace_id}">delete</button></div>`;
    }
    n.innerHTML = h;
    const y = Math.max(top, last);
    n.style.top = y + 'px';
    col.appendChild(n);
    last = y + n.offsetHeight + 8;
    if (hl) {
      const all = $$(`.hl[data-item="${it.id}"]`);
      n.addEventListener('mouseenter', () => all.forEach(x => x.classList.add('outline')));
      n.addEventListener('mouseleave', () => all.forEach(x => x.classList.remove('outline')));
      all.forEach(x => {
        x.addEventListener('mouseenter', () => n.classList.add('outline'));
        x.addEventListener('mouseleave', () => n.classList.remove('outline'));
      });
    }
  }
  col.style.minHeight = last + 'px';
}

/* ------------------------------------------------------------ annotating */
function offsetIn(el, node, offset) {
  const r = document.createRange(); r.selectNodeContents(el); r.setEnd(node, offset);
  return r.toString().length;
}
function onSelect() {
  if (S.pending) return;
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || !sel.rangeCount) return;
  const range = sel.getRangeAt(0);
  const startEl = (range.startContainer.nodeType === 1 ? range.startContainer : range.startContainer.parentElement).closest('.ann-target');
  const endEl = (range.endContainer.nodeType === 1 ? range.endContainer : range.endContainer.parentElement).closest('.ann-target');
  if (!startEl) return;
  if (startEl !== endEl) { toast('Select text inside one message or tool result.'); return; }
  let start = offsetIn(startEl, range.startContainer, range.startOffset);
  let end = offsetIn(startEl, range.endContainer, range.endOffset);
  const text = startEl.textContent;
  while (start < end && /\s/.test(text[start])) start++;
  while (end > start && /\s/.test(text[end - 1])) end--;
  if (end <= start) return;
  sel.removeAllRanges();
  const spans = wrapRange(startEl, start, end, 'hl pending', 'pending');
  const ref = IDX.byTrace.get(startEl.dataset.trace);
  S.pending = {
    trace_id: startEl.dataset.trace, session_id: ref.conv.session_id, scenario_id: ref.conv.scenario_id,
    block_key: startEl.dataset.key, quote: text.slice(start, end), start, end,
  };
  const rect = spans[spans.length - 1].getBoundingClientRect();
  const pop = $('#popover');
  pop.style.display = 'block';
  pop.style.left = Math.min(window.scrollX + rect.left, window.scrollX + window.innerWidth - 380) + 'px';
  pop.style.top = (window.scrollY + rect.bottom + 8) + 'px';
  const input = $('#note-input'); input.value = ''; input.focus();
}
function cancelPending() {
  if (!S.pending) return;
  S.pending = null; $('#popover').style.display = 'none';
  renderConversation();
}
async function commitPending() {
  const note = $('#note-input').value.trim();
  if (!note) { cancelPending(); return; }
  const p = S.pending; S.pending = null; $('#popover').style.display = 'none';
  const y = window.scrollY;
  S.ann = await post('/api/annotations', { op: 'add', ...p, note });
  render(); window.scrollTo(0, y);
  toast('Saved. The coding agent will group your notes.');
}

/* ------------------------------------------------------------ actions */
async function setReviewed(tid, status) {
  const y = window.scrollY;
  S.ann = await post('/api/annotations', { op: 'reviewed', trace_id: tid, status });
  render(); window.scrollTo(0, y);
}
async function saveLabel(tid, mode, label) {
  const cur = labelOf(mode, tid);
  const value = cur && cur.label === label ? null : label;  // clicking the active choice clears it
  const y = window.scrollY;
  try {
    await post('/api/labels', { trace_id: tid, mode, label: value });
    await refresh('labels');
    toast(value === null ? `Cleared ${mode}` : `${mode}: ${value ? 'present' : 'absent'} · saved`);
  } catch (e) { /* toast already shown; nothing saved */ }
  render(); window.scrollTo(0, y);
}
async function decide(id, decision, note) {
  const y = window.scrollY;
  try {
    S.sugg = await post('/api/suggestions/decide', { id, decision, note });
    await refresh('ann', 'labels');
  } catch (e) { return; }
  render(); window.scrollTo(0, y);
}

/* ------------------------------------------------------------ drawer */
function openDrawer(tab, opts = {}) {
  S.drawer = tab; if (opts.policy) S.focusPolicy = opts.policy;
  $('#drawer').classList.add('open');
  renderDrawer();
}
function closeDrawer() { S.drawer = null; $('#drawer').classList.remove('open'); }
function renderDrawer() {
  if (!S.drawer) return;
  $$('#drawer-tabs button[data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === S.drawer));
  const c = curConv(); const body = $('#drawer-body');
  if (!c) { body.innerHTML = ''; return; }
  const f = { key: drawerKey, policies: drawerPolicies, prompt: drawerPrompt, tools: drawerTools, spec: drawerSpec }[S.drawer];
  body.innerHTML = f(c);
  const foc = $('.card.focus', body);
  if (foc) foc.scrollIntoView({ block: 'start' }); else body.scrollTop = 0;
}
function drawerKey(c) {
  if (!S.revealed[c.session_id]) {
    return `<p class="small">The answer key is hidden so you read the trace and form your own view first.</p>
      <button class="reveal" data-reveal="1">Reveal the answer key for ${esc(c.scenario_id)}</button>`;
  }
  const e = c.scenario.expected || {}; const tup = c.scenario.tuple || {};
  return `<h2>${esc(c.scenario_id)} · expected</h2>
    <div class="kvlist"><span class="k">outcome</span><span><b>${esc(e.outcome)}</b></span>
    <span class="k">reason</span><span>${esc(e.reason)}</span>
    <span class="k">source</span><span>${esc((e.source || {}).type)} · <span class="mono">${esc((e.source || {}).reference)}</span></span>
    <span class="k">evaluation</span><span>${esc(e.evaluation)}</span>
    ${c.scenario.data_quality_case_id ? `<span class="k">data quality</span><span>${esc(c.scenario.data_quality_case_id)}</span>` : ''}</div>
    <h3>Scenario tuple</h3><div class="kvlist">${Object.entries(tup).map(([k, v]) => `<span class="k">${esc(k)}</span><span>${esc(v)}</span>`).join('')}</div>
    <h3>Scripted messages</h3><ol><li>${esc(c.scenario.opening_message)}</li>${(c.scenario.followups || []).map(m => `<li>${esc(m)}</li>`).join('')}</ol>
    <button class="ctxbtn" data-reveal="0">Hide again</button>`;
}
function drawerPolicies(c) {
  const P = S.ctx.policies || {};
  const turnOf = {};
  c.turns.forEach(t => t.blocks.forEach(b => {
    if (b.kind === 'tool') for (const id of Object.keys(P)) if (JSON.stringify(b.result || '').includes(`"${id}"`)) (turnOf[id] ||= new Set()).add(t.number);
  }));
  const cited = new Set(c.summary.cited_policies);
  const ids = [...new Set([...c.summary.cited_policies, ...c.summary.retrieved_policies])];
  const card = id => {
    const p = P[id]; const chips = [];
    if (cited.has(id)) chips.push('<span class="chip meta">cited</span>');
    chips.push(turnOf[id] ? `<span class="chip ok">retrieved in turn ${[...turnOf[id]].join(', ')}</span>` : '<span class="chip flag">never retrieved</span>');
    if (!p) return `<div class="card${S.focusPolicy === id ? ' focus' : ''}"><div class="t mono">${esc(id)}</div>${chips.join(' ')}<p class="small">Not a policy in the corpus (data/policies).</p></div>`;
    return `<div class="card${S.focusPolicy === id ? ' focus' : ''}"><div class="t">${esc(p.title)} <span class="mono small">${esc(id)}</span></div>${chips.join(' ')} <span class="chip meta">audience ${esc(p.audience)}</span>${md(p.body)}</div>`;
  };
  const others = Object.keys(P).filter(id => !ids.includes(id));
  return `<h2>In this conversation</h2>${ids.length ? ids.map(card).join('') : '<p class="small">No policy was cited or retrieved in this conversation.</p>'}
    <h2>All other policies</h2>${others.map(id => `<details class="card"><summary><b>${esc(P[id].title)}</b> <span class="mono small">${esc(id)}</span></summary>${md(P[id].body)}</details>`).join('')}`;
}
function drawerPrompt(c) {
  const lines = esc(c.system_prompt || '(no system prompt captured)').split('\n')
    .map(l => /^- (User role|User id|Store id):/.test(l) ? `<mark>${l}</mark>` : l).join('\n');
  return `<h2>System prompt</h2><p class="small">Version <span class="mono">${esc(c.prompt_version)}</span> (all conversations: ${esc((S.ctx.prompt_versions || []).join(', '))}). Only the highlighted session fields differ between conversations. Model: ${esc(c.models.join(', '))}.</p><pre>${lines}</pre>`;
}
function drawerTools(c) {
  const used = {}; c.turns.forEach(t => t.tool_names.forEach(n => used[n] = (used[n] || 0) + 1));
  const avail = new Set(c.available_tools);
  const tools = (S.ctx.tools || []).filter(t => avail.has(t.name)).sort((a, b) => (used[b.name] || 0) - (used[a.name] || 0));
  return `<h2>Tools available to this ${esc(c.role)}</h2>` + tools.map(t => {
    const k = t.contract || {};
    const params = Object.entries((t.parameters || {}).properties || {}).map(([n, p]) => `<span class="k">${esc(n)}</span><span>${esc(p.type || (p.anyOf || []).map(x => x.type).join(' | '))}${p.description ? ' · ' + esc(p.description) : ''}</span>`).join('');
    return `<div class="card"><div class="t mono">${esc(t.name)} ${used[t.name] ? `<span class="chip tool">used ×${used[t.name]}</span>` : ''}</div>
      <p class="small">${esc(t.description || '')}</p>
      ${params ? `<div class="kvlist">${params}</div>` : ''}
      ${k.id ? `<h3>SPEC ${esc(k.id)} · risk ${esc(k.risk)}</h3><div class="kvlist"><span class="k">side effects</span><span>${inline(k.effects || '')}</span><span class="k">on success</span><span>${inline(k.success || '')}</span><span class="k">on failure</span><span>${inline(k.failure || '')}</span></div>`
        : '<p><span class="chip flag">no SPEC.md contract for this tool</span></p>'}</div>`;
  }).join('');
}
function drawerSpec() {
  return `<input type="search" id="spec-q" placeholder="Filter, e.g. RESP-2 or refund" style="width:100%;padding:7px 10px;border-radius:8px;border:1px solid var(--line)"><div id="spec-body">${md(S.ctx.spec)}</div>`;
}
function filterSpec(q) {
  const body = $('#spec-body'); if (!body) return;
  q = q.trim().toLowerCase();
  $$('#spec-body > *').forEach(el => { el.style.display = !q || el.textContent.toLowerCase().includes(q) || /^H\d$/.test(el.tagName) ? '' : 'none'; });
}

/* ------------------------------------------------------------ taxonomy */
function renderTaxonomy() {
  const el = $('#taxonomy'); const ms = modes();
  const byId = new Map(S.ann.annotations.map(a => [a.id, a]));
  const used = new Set(ms.flatMap(m => m.annotation_ids || []));
  const annLi = a => {
    const ref = IDX.byTrace.get(a.trace_id); const sid = ref ? ref.conv.scenario_id : a.scenario_id;
    return `<li><a data-goto="${esc(sid)}|${a.trace_id}|${a.id}"><span class="mono small">${esc(sid)} T${ref ? ref.turn.number : '?'}</span> ${esc(clip(a.note, 160))}</a></li>`;
  };
  const goto = tid => { const ref = IDX.byTrace.get(tid); return ref ? `<a data-goto="${esc(ref.conv.scenario_id)}|${tid}|"><span class="mono small">${esc(ref.conv.scenario_id)} T${ref.turn.number}</span></a>` : esc(tid); };
  const cards = ms.map(m => {
    const lab = Object.values(S.labels[m.name] || {});
    const pos = lab.filter(r => r.label === 1).length, neg = lab.filter(r => r.label === 0).length;
    const anns = (m.annotation_ids || []).map(id => byId.get(id)).filter(Boolean);
    const sg = pendingSugg().filter(s => s.mode === m.name).length;
    return `<div class="mode"><div class="name">${esc(m.name)} <span class="chip ${isFinal(m) ? 'ok' : 'meta'}">${esc(m.status || 'candidate')}</span></div>
      <div class="def">${esc(m.definition || '')}</div>
      <div class="facts">${m.requirement_source ? `requirement: <b>${esc(m.requirement_source)}</b> · ` : ''}${(m.evaluator_type || m.evaluator) ? `evaluator: ${esc(m.evaluator_type || m.evaluator)} · ` : ''}${anns.length} supporting note${anns.length === 1 ? '' : 's'} · labels ${pos} present / ${neg} absent${sg ? ` · ${sg} AI suggestion${sg > 1 ? 's' : ''} pending` : ''}</div>
      ${m.boundary ? `<div class="facts" style="margin-top:4px">boundary: ${esc(m.boundary)}</div>` : ''}
      ${(m.close_negative_trace_ids || []).length ? `<div class="facts" style="margin-top:4px">close negatives: ${m.close_negative_trace_ids.map(goto).join(', ')}</div>` : ''}
      ${(m.open_questions || []).length ? `<div class="facts" style="margin-top:4px">open: ${m.open_questions.map(esc).join(' · ')}</div>` : ''}
      <div class="bar" style="margin:8px 0"><span style="width:${(pos / Math.max(1, pos + neg)) * 100}%;background:var(--flamingo)"></span><span style="width:${(neg / Math.max(1, pos + neg)) * 100}%;background:var(--palm)"></span></div>
      <ul>${anns.map(annLi).join('') || '<li class="small">No supporting annotations linked yet.</li>'}</ul></div>`;
  }).join('');
  const loose = S.ann.annotations.filter(a => !used.has(a.id));
  el.innerHTML = `<h1>Taxonomy</h1><p class="lede">Failure modes the coding agent groups from your open codes (axial coding). Click a note to jump to it.</p>
    ${ms.length ? `<div class="grid-cards">${cards}</div>` : '<div class="card">No modes yet. Write open codes in the Review view; after about five annotated traces the coding agent proposes groupings here for you to accept or revise.</div>'}
    <h2 style="font-family:var(--display);margin-top:26px">Not yet in a mode (${loose.length})</h2>
    <div class="mode" style="border-image:none;border-top-color:var(--anno)"><ul>${loose.map(annLi).join('') || '<li class="small">Every note belongs to a mode.</li>'}</ul></div>`;
}

/* ------------------------------------------------------------ labels */
function labelRows() {
  const sampled = S.convs.flatMap(c => c.turns.filter(t => IDX.sample.has(t.trace_id)).map(t => ({ c, t })));
  let rows = S.labFilter === 'all' ? S.convs.flatMap(c => c.turns.map(t => ({ c, t }))) : sampled;
  if (S.labFilter === 'reviewed') rows = sampled.filter(r => isReviewed(r.t.trace_id));
  if (S.labFilter === 'incomplete') rows = sampled.filter(r => isReviewed(r.t.trace_id) && finalModes().some(m => !labelOf(m.name, r.t.trace_id)));
  return rows;
}
function renderLabels() {
  const el = $('#labels'); const ms = modes();
  if (!ms.length) { el.innerHTML = '<h1>Labels</h1><div class="card">No failure modes yet. Once the taxonomy has modes, this grid holds one present / absent judgment per trace and mode.</div>'; return; }
  const counts = ms.map(m => {
    const lab = Object.values(S.labels[m.name] || {});
    const p = lab.filter(r => r.label === 1).length, a = lab.filter(r => r.label === 0).length;
    return `<div class="stat"><div class="mono" style="font-weight:700">${esc(m.name)}</div><div class="l">${p} present · ${a} absent ${p >= 30 && a >= 30 ? '<span class="chip ok">HW5 ready</span>' : `<span class="chip meta" title="HW5 needs 30 of each">HW5: ${Math.max(0, 30 - p)} / ${Math.max(0, 30 - a)} to go</span>`}</div></div>`;
  }).join('');
  const rows = labelRows(); const html = []; let last = null;
  const sug = pendingSugg().filter(s => s.kind === 'label');
  for (const { c, t } of rows) {
    if (c !== last) { html.push(`<tr class="convrow"><td colspan="${ms.length + 2}"><span class="link" data-goto="${esc(c.scenario_id)}|${t.trace_id}|">${esc(c.scenario_id)}</span> <span class="chip role-${esc(c.role)}">${esc(c.role)}</span></td></tr>`); last = c; }
    const cells = ms.map(m => {
      const cur = labelOf(m.name, t.trace_id); const sg = sug.find(s => s.trace_id === t.trace_id && s.mode === m.name);
      const on = v => cur && cur.label === v ? ' on' : ''; const gh = v => sg && Number(sg.label) === v ? ' ghost' : '';
      const sgc = sg ? ` <button class="sbtn accept" data-decide="${sg.id}|accepted" title="${esc(sg.note || '')}">AI ✓</button><button class="sbtn reject" data-decide="${sg.id}|rejected">✗</button>` : '';
      return `<td class="cell"><button class="sbtn present${on(1)}${gh(1)}" data-label="${t.trace_id}|${esc(m.name)}|1">P</button> <button class="sbtn absent${on(0)}${gh(0)}" data-label="${t.trace_id}|${esc(m.name)}|0">A</button>${sgc}</td>`;
    }).join('');
    html.push(`<tr><td><span class="link" data-goto="${esc(c.scenario_id)}|${t.trace_id}|">turn ${t.number}</span> <span class="small mono">${t.trace_id.slice(0, 8)}</span></td><td><span class="status ${turnStatus(t.trace_id)}">${turnStatus(t.trace_id).replace('_', ' ')}</span></td>${cells}</tr>`);
  }
  const f = k => `<button class="ctxbtn${S.labFilter === k ? ' key' : ''}" data-labfilter="${k}">${{ sample: 'Sampled traces', reviewed: 'Reviewed only', incomplete: 'Incomplete only', all: 'All 356' }[k]}</button>`;
  el.innerHTML = `<h1>Labels</h1><p class="lede">One decision per trace and mode: <b>P</b> = failure present, <b>A</b> = absent. Click an active choice again to clear it. Each change is written to Langfuse as a score, then to <span class="mono">analysis/state/labels/&lt;mode&gt;.jsonl</span>. Dashed outline = AI suggestion awaiting your decision.</p>
    <div class="stats">${counts}</div><div class="toolbar">${['sample', 'reviewed', 'incomplete', 'all'].map(f).join('')}<span class="small">${rows.length} traces</span></div>
    <table class="lab"><tr><th>trace</th><th>review</th>${ms.map(m => `<th>${esc(m.name)}${isFinal(m) ? ' ★' : ''}</th>`).join('')}</tr>${html.join('') || `<tr><td colspan="${ms.length + 2}" class="small">No traces in this filter.</td></tr>`}</table>`;
}

/* ------------------------------------------------------------ progress */
function renderProgress() {
  const el = $('#progress');
  const sampled = [...IDX.sample.keys()].filter(tid => IDX.byTrace.has(tid));
  const rev = sampled.filter(isReviewed);
  const nf = sampled.filter(t => turnStatus(t) === 'no_failure').length;
  const pend = pendingSugg();
  const fm = finalModes();
  const incomplete = rev.filter(t => fm.some(m => !labelOf(m.name, t)));
  const batches = (S.samples.batches || []).map(b => {
    const ids = (b.traces || []).map(x => typeof x === 'string' ? x : x.trace_id);
    const r = ids.filter(isReviewed).length;
    return `<tr><td><b>${esc(b.id || b.name)}</b></td><td>${esc(b.method || '')}</td><td>${ids.length}</td><td>${r}</td><td style="width:30%"><div class="bar"><span style="width:${ids.length ? r / ids.length * 100 : 0}%;background:var(--sunset)"></span></div></td></tr>`;
  }).join('');
  const goto = tid => { const ref = IDX.byTrace.get(tid); return ref ? `<span class="link" data-goto="${esc(ref.conv.scenario_id)}|${tid}|">${esc(ref.conv.scenario_id)} T${ref.turn.number}</span>` : esc(tid); };
  const unrev = sampled.filter(t => !isReviewed(t));
  const queue = pend.map(s => `<tr><td><input type="checkbox" class="qsel" value="${s.id}"></td><td class="mono">${esc(s.mode || '')}</td><td>${s.kind === 'label' ? `label: <b>${Number(s.label) ? 'present' : 'absent'}</b>` : 'span'}</td>
    <td>${s.quote ? `“${esc(clip(s.quote, 90))}”<br>` : ''}<span class="small">${esc(clip(s.note || '', 160))}</span></td><td>${goto(s.trace_id)}</td>
    <td style="white-space:nowrap"><button class="sbtn accept" data-decide="${s.id}|accepted">accept</button> <button class="sbtn reject" data-decide="${s.id}|rejected">reject</button></td></tr>`).join('');
  const decided = (S.sugg.suggestions || []).filter(s => s.status && s.status !== 'pending');
  el.innerHTML = `<h1>Progress</h1><p class="lede">Reviewed = annotated or marked “no failure observed”.</p>
    <div class="stats">
      <div class="stat"><div class="n">${sampled.length}</div><div class="l">traces in the sample</div></div>
      <div class="stat"><div class="n">${rev.length}</div><div class="l">reviewed (${rev.length - nf} annotated, ${nf} no failure)</div></div>
      <div class="stat"><div class="n">${unrev.length}</div><div class="l">not yet reviewed</div></div>
      <div class="stat"><div class="n">${S.ann.annotations.length}</div><div class="l">annotations</div></div>
      <div class="stat"><div class="n">${incomplete.length}</div><div class="l">reviewed traces with incomplete judgments${fm.length ? '' : ' (no modes yet)'}</div></div>
      <div class="stat"><div class="n">${pend.length}</div><div class="l">AI suggestions to decide</div></div></div>
    <h2 style="font-family:var(--display)">Batches</h2>
    ${batches ? `<table class="tbl"><tr><th>batch</th><th>method</th><th>traces</th><th>reviewed</th><th></th></tr>${batches}</table>` : '<div class="card">No batches yet.</div>'}
    <h2 style="font-family:var(--display);margin-top:24px">AI suggestions to review</h2>
    ${pend.length ? `<div class="toolbar"><label><input type="checkbox" id="qall"> select all</label><button class="sbtn accept" id="qaccept">Accept selected</button><button class="sbtn reject" id="qreject">Reject selected</button></div>
      <table class="tbl"><tr><th></th><th>mode</th><th>kind</th><th>suggestion</th><th>trace</th><th></th></tr>${queue}</table>` : '<div class="card">Nothing pending.</div>'}
    <p class="small">${decided.filter(s => s.status === 'accepted').length} accepted · ${decided.filter(s => s.status === 'rejected').length} rejected (rejected suggestions stay on file).</p>
    <h2 style="font-family:var(--display);margin-top:24px">Incomplete judgments</h2>
    ${incomplete.length ? `<table class="tbl"><tr><th>trace</th><th>missing modes</th></tr>${incomplete.map(t => `<tr><td>${goto(t)}</td><td class="mono">${fm.filter(m => !labelOf(m.name, t)).map(m => esc(m.name)).join(', ')}</td></tr>`).join('')}</table>` : '<div class="card">None.</div>'}
    <h2 style="font-family:var(--display);margin-top:24px">Not yet reviewed (${unrev.length})</h2>
    <div class="card">${unrev.map(goto).join(' · ') || 'All sampled traces are reviewed.'}</div>`;
}

/* ------------------------------------------------------------ events */
document.addEventListener('click', async (e) => {
  const t = e.target.closest('button, a, span.link, input'); if (!t) return;
  const d = t.dataset;
  if (d.view) return switchView(d.view);
  if (d.scope) { S.scope = d.scope; store('scope', d.scope); return renderRail(); }
  if (d.sid) return go(d.sid);
  if (d.goto) { const [sid, tr, item] = d.goto.split('|'); return go(sid, { trace: tr, item: item || null }); }
  if (d.open) return openDrawer(d.open);
  if (d.tab) return openDrawer(d.tab);
  if (t.id === 'drawer-close') return closeDrawer();
  if (d.policy) return openDrawer('policies', { policy: d.policy });
  if (d.reveal) { const c = curConv(); S.revealed[c.session_id] = d.reveal === '1'; renderDrawer(); return renderConversation(); }
  if (d.nofail) return setReviewed(d.nofail, turnStatus(d.nofail) === 'no_failure' ? null : 'no_failure');
  if (d.label) { const [tid, mode, v] = d.label.split('|'); return saveLabel(tid, mode, Number(v)); }
  if (d.decide) { const [id, dec] = d.decide.split('|'); return decide(id, dec); }
  if (d.del) {
    const [id, tid] = d.del.split('|');
    S.ann = await post('/api/annotations', { op: 'delete', id, trace_id: tid });
    return render();
  }
  if (d.edit) { S.editing = d.edit; return layoutMargin(); }
  if (d.editCancel) { S.editing = null; return layoutMargin(); }
  if (d.editSave) {
    const v = $(`[data-edit-input="${d.editSave}"]`).value.trim();
    S.editing = null;
    if (v) S.ann = await post('/api/annotations', { op: 'update', id: d.editSave, note: v });
    return render();
  }
  if (d.labfilter) { S.labFilter = d.labfilter; return renderLabels(); }
  if (t.id === 'qall') { $$('.qsel').forEach(x => x.checked = t.checked); return; }
  if (t.id === 'qaccept' || t.id === 'qreject') {
    const ids = $$('.qsel').filter(x => x.checked).map(x => x.value);
    if (!ids.length) return toast('Select at least one suggestion.');
    for (const id of ids) { try { S.sugg = await post('/api/suggestions/decide', { id, decision: t.id === 'qaccept' ? 'accepted' : 'rejected' }); } catch (err) { break; } }
    await refresh('ann', 'labels'); return render();
  }
  if (t.id === 'theme-btn') {
    const night = document.documentElement.dataset.theme !== 'night';
    document.documentElement.dataset.theme = night ? 'night' : 'day'; store('theme', night ? 'night' : 'day');
  }
});
document.addEventListener('mouseup', (e) => { if (e.target.closest('#thread') && !e.target.closest('button')) setTimeout(onSelect, 0); });
document.addEventListener('mousedown', (e) => { if (S.pending && !e.target.closest('#popover')) cancelPending(); });
$('#note-input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); commitPending(); }
  else if (e.key === 'Escape') cancelPending();
});
$('#rail-search').addEventListener('input', (e) => { S.search = e.target.value; renderRail(); });
document.addEventListener('input', (e) => { if (e.target.id === 'spec-q') filterSpec(e.target.value); });
document.addEventListener('toggle', () => layoutMargin(), true);
window.addEventListener('resize', () => layoutMargin());
window.addEventListener('hashchange', () => { const sid = decodeURIComponent(location.hash.slice(1)); if (sid && sid !== S.cur) go(sid); });
document.addEventListener('keydown', (e) => {
  if (e.target.closest('input, textarea')) return;
  if (e.key === 'Escape') { if (S.drawer) closeDrawer(); return; }
  if (S.view !== 'review') return;
  if (e.key === ']' || e.key === '[') {
    const list = railConvs(); const i = list.findIndex(c => c.scenario_id === S.cur);
    const next = list[Math.min(list.length - 1, Math.max(0, i + (e.key === ']' ? 1 : -1)))];
    if (next) go(next.scenario_id);
  }
});

/* poll for what the coding agent pushes: suggestions, taxonomy, samples, labels */
let lastSig = '';
async function poll() {
  try {
    const before = pendingSugg().length;
    await refresh('sugg', 'patterns', 'samples', 'labels');
    const sig = JSON.stringify([S.sugg, S.patterns, S.samples, S.labels]);
    if (sig !== lastSig) {
      const first = !lastSig; lastSig = sig;
      if (!first && !S.pending && !S.editing) {
        const y = window.scrollY; render(); window.scrollTo(0, y);
        const after = pendingSugg().length;
        if (after > before) toast(`${after - before} new AI suggestion${after - before > 1 ? 's' : ''}`);
      }
    }
  } catch (e) { /* server restarting; try again */ }
  setTimeout(poll, 4000);
}

(async function boot() {
  const theme = store('theme'); if (theme) document.documentElement.dataset.theme = theme;
  try { await loadAll(); } catch (e) { $('#main').innerHTML = `<div class="empty">Could not load data: ${esc(e.message)}</div>`; return; }
  S.scope = store('scope') || 'sample';
  if (!S.samples.batches.length) S.scope = 'all';
  const fromHash = decodeURIComponent(location.hash.slice(1));
  S.cur = IDX.bySid.has(fromHash) ? fromHash : (railConvs()[0] || S.convs[0]).scenario_id;
  render();
  lastSig = JSON.stringify([S.sugg, S.patterns, S.samples, S.labels]);
  setTimeout(poll, 4000);
})();
