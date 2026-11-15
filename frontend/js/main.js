import {$, $$, esc, S, A, ACT, api, setCase, refresh, onChange, toast, sfx, iris, REDUCED, stamp, pill, meter, col, fmtDate, sleep, countUp} from './core.js';
import {scene, init as initScene} from './scene.js';
import * as landing from './views/landing.js';
import * as connect from './views/connect.js';
import * as reconstruct from './views/reconstruct.js';
import * as verify from './views/verify.js';
import * as review from './views/review.js';
import * as handover from './views/handover.js';
import * as map from './views/map.js';
import * as audit from './views/audit.js';
import {startTour} from './tour.js';

const VIEWS = {landing, connect, reconstruct, verify, review, handover, map, audit};
const RAIL = [['connect', '1', 'Connect'], ['reconstruct', '2', 'Rebuild'], ['verify', '3', 'Verify'], ['review', '4', 'Review'], ['handover', '5', 'Handover'], ['map', '◉', 'Map'], ['audit', '⛓', 'Audit']];
const NEEDS_CLAIMS = new Set(['verify', 'review', 'handover', 'map', 'audit']);
let cur = null;

/* ---------- routing ---------- */
export function go(route, opts = {}) {
  if (!VIEWS[route]) route = 'landing';
  if (route !== 'landing' && !S.cid) route = 'landing';
  if (NEEDS_CLAIMS.has(route) && !(S.case && S.case.reconstructed)) { toast('Reconstruct the case first'); route = S.cid ? 'connect' : 'landing'; }
  const run = () => {
    if (cur && VIEWS[cur].leave) VIEWS[cur].leave();
    scene.undock(); cur = route; S.route = route; history.replaceState(null, '', '#/' + route);
    const st = $('#stage'); st.innerHTML = '<section></section>'; st.scrollTop = 0; VIEWS[route].enter(st.firstChild, opts);
    chrome(); syncScene();
  };
  if (document.startViewTransition && !REDUCED && !opts.instant) document.startViewTransition(run); else run();
}
ACT.go = t => go(t.dataset.r);
window.addEventListener('hashchange', () => { const r = location.hash.replace('#/', ''); if (r && r !== cur) go(r); });

/* ---------- scene sync (backend is the source of truth) ---------- */
let syncing = 0;
export async function syncScene() {
  if (!scene.ready) return; const my = ++syncing, r = S.route;
  const mode = {landing: 'landing', connect: 'connect', reconstruct: 'reconstruct', map: 'map'}[r] || 'work'; scene.setMode(mode);
  try {
    let g;
    if (!S.cid || r === 'landing' || !(S.case && S.case.reconstructed)) {
      const src = S.sources.filter(s => !s.restricted);
      g = {nodes: src.length ? src.map(s => ({id: s.id, kind: 'src', name: s.name, acl: s.acl})) : DEMO_RING, edges: [], dates: []};
    } else g = await A.graph(r === 'map' ? S.role : r === 'handover' ? S.role : 'manager', r === 'handover');
    if (my !== syncing) return; scene.setGraph(g);
    if (r === 'map') map.onGraph && map.onGraph(g);
  } catch (e) { /* the backdrop is decorative; never block the UI on it */ }
}
const DEMO_RING = ['repo', 'notes', 'tasks', 'chat', 'docs'].map((n, i) => ({id: 'S' + (i + 1), kind: 'src', name: n, acl: ['team', 'team', 'team', 'confidential', 'public'][i]}));
export const resync = syncScene;

/* ---------- chrome: top bar, rail, ring, next best action ---------- */
export function chrome() {
  const c = S.case; $('#casechip').innerHTML = c ? `<b>${esc(c.id)}</b> ${esc(c.name)} · leaver <b>${esc(c.leaver || 'n/a')}</b> · last day <b>${esc(c.last_day || 'n/a')}</b>` : '';
  const roles = ['guest', 'developer', 'manager'], d = $('#dial'), i = roles.indexOf(S.role), b = $$('button', d)[i];
  $$('button', d).forEach((x, k) => x.classList.toggle('on', k === i)); const bg = $('.pill-bg', d); if (b) { bg.style.left = b.offsetLeft + 'px'; bg.style.width = b.offsetWidth + 'px'; bg.style.background = ['var(--grn)', 'var(--amb)', 'var(--red)'][i]; }
  const p = S.readiness.percent, ring = $('#ring'); ring.style.setProperty('--p', p); ring.style.setProperty('--c', p >= 80 ? 'var(--grn)' : p >= 40 ? 'var(--amb)' : 'var(--red)'); $('span', ring).textContent = p + '%'; ring.title = 'Handover readiness: ' + S.readiness.parts?.map(x => `${x.label} ${Math.round(x.value * 100)}%`).join(', ');
  const rl = $('#rail'), has = !!(S.case && S.case.reconstructed), done = {connect: S.sources.length > 0 && has, reconstruct: has, verify: has && S.claims.length && !S.claims.some(c => c.state === 'CONFLICT'), review: has && S.claims.length && S.claims.every(c => c.status !== 'pending' && c.status !== 'drifted'), handover: !!S.readiness.parts?.[3]?.value};
  rl.innerHTML = '<i id="baton"></i>' + RAIL.map(([r, ic, l]) => `<button data-act="go" data-r="${r}" class="${S.route === r ? 'on' : done[r] ? 'done' : ''} ${NEEDS_CLAIMS.has(r) && !has || (!S.cid) ? 'lock' : ''}" aria-label="${l}" ${S.route === r ? 'aria-current="step"' : ''}><i>${done[r] && S.route !== r ? '✓' : ic}</i>${l}</button>`).join('');
  const on = $('button.on', rl), bt = $('#baton'); if (on && bt && innerWidth > 820) bt.style.top = on.offsetTop + 7 + 'px'; else if (bt) bt.style.display = 'none';
  $('#sndbtn').textContent = 'SND ' + (S.sound ? 'on' : 'off'); $('#sndbtn').setAttribute('aria-pressed', S.sound);
  const n = nba(); $('#nba').innerHTML = `<span class="sp"><b>NEXT</b> ${esc(n.t)}</span>${n.b ? `<button class="btn sm" data-act="${n.act}" ${n.arg ? `data-arg="${esc(n.arg)}"` : ''}>${n.b}</button>` : ''}`;
}
function nba() {
  if (!S.cid) return {t: 'Start with the demo case or an empty one.'};
  if (!S.case.reconstructed) return {t: S.sources.length ? `${S.sources.filter(s => s.included).length} sources ready. Reconstruct the case.` : 'Add evidence sources.', b: 'Reconstruct', act: 'rebuild'};
  const cf = S.claims.find(c => c.state === 'CONFLICT'), ms = S.claims.find(c => c.state === 'MISSING' && c.status !== 'rejected'), pd = S.claims.filter(c => c.status === 'pending' || c.status === 'drifted'), dr = S.claims.find(c => c.status === 'drifted');
  if (dr) return {t: `Drift alert: ${dr.ref} changed after approval.`, b: 'Re-review', act: 'focus', arg: dr.id};
  if (cf) return {t: `Conflict to resolve: ${cf.text}`, b: 'Resolve', act: 'focus', arg: cf.id};
  if (ms) return {t: `Ask the leaver: ${ms.text.slice(0, 70)}`, b: 'Interview', act: 'interview'};
  if (pd.length) return {t: `${pd.length} claims still need your decision.`, b: 'Review deck', act: 'go-review'};
  if (!S.readiness.parts?.[3]?.value) return {t: 'Review complete. Hand over and collect a receipt.', b: 'Handover', act: 'go-handover'};
  return {t: 'Receipt on file. Export the evidence bundle.', b: 'Export', act: 'go-handover'};
}
ACT['go-review'] = () => go('review'); ACT['go-handover'] = () => go('handover'); ACT.rebuild = () => { go('reconstruct', {run: true}); };
ACT.focus = t => { go('verify', {focus: +t.dataset.arg}); }; ACT.interview = () => { go('verify', {interview: true}); };
onChange(() => { chrome(); });

/* ---------- clearance dial ---------- */
ACT.role = (t, e) => { setRole(t.dataset.role, e); };
export function setRole(r, e) {
  if (r === S.role) return; const b = e && e.target ? e.target.getBoundingClientRect() : {left: innerWidth - 120, top: 30, width: 0}; iris(b.left + b.width / 2, b.top + 20); sfx('tick');
  setTimeout(() => { S.role = r; chrome(); if (['handover', 'map'].includes(S.route)) { VIEWS[S.route].onRole ? VIEWS[S.route].onRole() : go(S.route, {instant: true}); } syncScene(); if ($('#insp').classList.contains('open') && S.insp) S.insp(); }, REDUCED ? 0 : 280);
}
ACT.sound = () => { S.sound = !S.sound; chrome(); };

/* ---------- inspector: the evidence, on paper, under a lamp ---------- */
export function closeInspector() { $('#insp').classList.remove('open'); S.insp = null; scene.focus && 0; }
ACT['insp-close'] = closeInspector;
document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeInspector(); const d = $('#dlg'); d.open && d.close(); } });
function paper(lines, hit, restricted) {
  return `<div class="paper">${lines.map((l, i) => `<div class="ln ${i === hit ? 'hit' : ''}"><em>${i + 1}</em><span>${esc(l)}</span></div>`).join('')}</div>`;
}
export async function inspectSource(sid, line = -1) {
  const el = $('#insp'); S.insp = () => inspectSource(sid, line); el.classList.add('open');
  el.innerHTML = '<header><b>Source</b><span class="sp"></span><button class="btn sm ghost" data-act="insp-close">Close</button></header><div class="body"><p class="mut mono">loading…</p></div>';
  try {
    const s = await A.source(sid, S.role);
    el.innerHTML = `<header><div><div class="mono sm mut">${esc(s.id)} · ${esc(s.kind)} · ${esc(s.origin)}</div><b>${esc(s.name)}</b></div><span class="sp"></span>${pill(s.acl)}<button class="btn sm ghost" data-act="insp-close">Close</button></header><div class="body">${s.redactions ? `<p class="mono sm" style="color:var(--amb)">⚠ ${s.redactions} secret(s) masked at ingest. The original value was never stored.</p>` : ''}${paper(s.content, line)}</div>`;
    const h = $('.hit', el); h && h.scrollIntoView({block: 'center'});
  } catch (e) {
    el.innerHTML = `<header><b>Restricted</b><span class="sp"></span><button class="btn sm ghost" data-act="insp-close">Close</button></header><div class="body"><div class="redact" style="min-height:140px"><span>██████████ This source needs higher clearance than <b>${S.role}</b>.</span></div><p class="mut sm">The server refused to send it. Switch the dial to a higher clearance to preview as a manager.</p></div>`;
  }
}
export async function inspectClaim(num, role) {
  const el = $('#insp'), rl = role || S.role; S.insp = () => inspectClaim(num, role); el.classList.add('open');
  el.innerHTML = '<header><b>Claim</b><span class="sp"></span><button class="btn sm ghost" data-act="insp-close">Close</button></header><div class="body"><p class="mut mono">loading…</p></div>';
  try {
    const c = await A.claim(num, rl); let hist = []; if (rl === 'manager') hist = await A.history(num).catch(() => []);
    scene.focus(c.ref);
    el.innerHTML = `<header><div><div class="mono sm mut">${c.ref} · ${c.type} · v${c.version}</div></div><span class="sp"></span>${stamp(c.state)}<button class="btn sm ghost" data-act="insp-close">Close</button></header><div class="body">
      <p style="font:600 19px/1.35 var(--ui);margin:0 0 12px">${esc(c.text)}</p>
      <div class="row" style="margin-bottom:10px"><span class="badge ${c.status}">${c.status}</span>${pill(c.access)}${c.date ? `<span class="mono sm mut">${fmtDate(c.date)}</span>` : ''}</div>
      <div class="conf"><div>${meter(c.confidence, col(c.state))}</div><b style="color:var(--txt)">${Math.round(c.confidence * 100)}%</b></div>
      <div class="why" style="margin:8px 0 14px">${c.factors.map(f => `<div><span class="${f.delta >= 0 ? 'p' : 'n'}">${f.delta >= 0 ? '+' : ''}${Math.round(f.delta * 100)}</span> ${esc(f.label)}</div>`).join('')}</div>
      ${c.note ? `<p class="mono sm" style="color:var(--amb)">${esc(c.note)}</p>` : ''}
      ${c.hint && c.hint.newest ? `<p class="mono sm mut">Recency hint: newest dated evidence says <b style="color:var(--txt)">${esc(c.hint.newest)}</b>. A hint, not a verdict.</p>` : ''}
      <h3 style="margin-top:18px">Evidence (${c.evidence.length})</h3>
      ${c.evidence.map(e => `<div style="margin-bottom:14px"><div class="row mono sm mut" style="margin-bottom:5px"><b style="color:var(--txt)">${esc(e.source)}</b> line ${e.line + 1} ${e.date ? '· ' + e.date : ''} ${e.variant ? `<span class="chip">${esc(e.variant)}</span>` : ''}<span class="sp"></span><button class="chip" data-act="open-src" data-sid="${e.sid}" data-line="${e.line}">open source</button></div><div class="paper"><div class="ln hit"><em>${e.line + 1}</em><span>${esc(e.quote)}</span></div></div></div>`).join('')}
      ${c.deadlines.length ? `<h3>Dates in this claim</h3>${c.deadlines.map(d => `<div class="mono sm">${fmtDate(d.iso)}</div>`).join('')}` : ''}
      ${hist.length ? `<h3>Version history</h3>${hist.map(h => `<div class="mono sm mut" style="padding:4px 0;border-bottom:1px dashed #ffffff14">v${h.version} · <b style="color:var(--txt)">${esc(h.action)}</b> · ${esc(h.actor)} · ${new Date(h.at * 1000).toLocaleTimeString()}</div>`).join('')}` : ''}</div>`;
  } catch (e) {
    el.innerHTML = `<header><b>Restricted</b><span class="sp"></span><button class="btn sm ghost" data-act="insp-close">Close</button></header><div class="body"><div class="redact" style="min-height:120px"><span>██████████ ${esc(e.message)}</span></div></div>`;
  }
}
ACT['open-src'] = t => inspectSource(t.dataset.sid, +t.dataset.line);
ACT.cite = t => inspectClaim(+t.dataset.n, t.dataset.role);
window.inspectClaim = inspectClaim; window.inspectSource = inspectSource;

/* ---------- command palette ---------- */
ACT.palette = openPalette; document.addEventListener('keydown', e => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openPalette(); } });
function commands() {
  const out = [...RAIL.map(([r, , l]) => ({t: 'Go to ' + l, k: 'nav', f: () => go(r)})), {t: 'Home', k: 'nav', f: () => go('landing')},
    ...['guest', 'developer', 'manager'].map(r => ({t: 'Preview as ' + r, k: 'role', f: () => setRole(r)})),
    {t: 'Run the guided tour', k: 'tour', f: () => startTour()}, {t: 'Toggle sound', k: 'ui', f: () => ACT.sound()}];
  if (S.case && S.case.reconstructed) {
    out.push({t: 'Download handover (Markdown)', k: 'export', f: () => location.href = A.exportUrl(S.role, 'md')}, {t: 'Download evidence bundle (JSON)', k: 'export', f: () => location.href = A.exportUrl(S.role, 'json')},
      {t: 'Verify audit chain', k: 'audit', f: () => go('audit')}, {t: 'Interview the leaver', k: 'review', f: () => go('verify', {interview: true})});
    const clr = {guest: 0, developer: 1, manager: 2}[S.role];
    S.claims.filter(c => c.level <= clr).forEach(c => out.push({t: `${c.ref} ${c.text.split('  >>')[0].slice(0, 80)}`, k: c.state, f: () => inspectClaim(c.id, S.role)}));
  }
  return out;
}
function openPalette() {
  const d = $('#dlg'); const all = commands();
  d.innerHTML = `<div style="padding:14px 16px;border-bottom:1px solid var(--line)"><input id="pq" placeholder="Type a command or search a claim…" autocomplete="off" aria-label="Command"></div><div id="pl" style="max-height:52vh;overflow:auto;padding:6px"></div>`;
  d.showModal(); const q = $('#pq', d), pl = $('#pl', d); let idx = 0, list = [];
  const draw = () => { const s = q.value.toLowerCase(); list = all.filter(c => c.t.toLowerCase().includes(s)).slice(0, 40); idx = Math.min(idx, Math.max(0, list.length - 1));
    pl.innerHTML = list.map((c, i) => `<div class="mono" data-i="${i}" style="padding:9px 12px;border-radius:8px;cursor:pointer;display:flex;gap:10px;${i === idx ? 'background:#5eead41a' : ''}"><span class="mut" style="width:70px;font-size:10px;text-transform:uppercase">${esc(c.k)}</span>${esc(c.t)}</div>`).join('') || '<p class="mut mono" style="padding:12px">No match</p>'; };
  q.oninput = () => { idx = 0; draw(); }; q.focus(); draw();
  q.onkeydown = e => { if (e.key === 'ArrowDown') { idx = Math.min(list.length - 1, idx + 1); draw(); e.preventDefault(); } else if (e.key === 'ArrowUp') { idx = Math.max(0, idx - 1); draw(); e.preventDefault(); } else if (e.key === 'Enter' && list[idx]) { d.close(); list[idx].f(); } };
  pl.onclick = e => { const r = e.target.closest('[data-i]'); if (r) { d.close(); list[+r.dataset.i].f(); } };
}
ACT.tour = () => startTour(); ACT['tour-stop'] = () => startTour(true);

/* ---------- boot ---------- */
export {go as navigate};
(async function boot() {
  try { if (!initScene($('#gl'), $('#labels'))) throw new Error('WebGL unavailable'); }
  catch (e) { console.error('3D scene disabled:', e); $('#gl').style.display = 'none'; scene.ready = false; for (const k of Object.keys(scene)) if (typeof scene[k] === 'function') scene[k] = () => {}; const b = document.createElement('div'); b.className = 'mono sm'; b.style.cssText = 'position:fixed;bottom:70px;right:14px;z-index:50;background:#2a1a00;border:1px solid #f5a524;border-radius:8px;padding:8px 12px;max-width:380px'; b.textContent = '3D scene disabled (' + (e.message || e) + '). All features still work; the Map tab shows lists instead of the graph.'; document.body.append(b); }
  A.health().then(h => { S.llm = h.llm; }).catch(() => {});
  if (S.cid) { try { await refresh(); } catch (e) { setCase(null); S.case = null; S.sources = []; S.claims = []; } }
  chrome();
  const r = location.hash.replace('#/', ''); go(r && VIEWS[r] && S.cid ? r : S.cid ? 'connect' : 'landing', {instant: true});
  addEventListener('resize', chrome);
})();
