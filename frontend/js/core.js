// api client + state + tiny UI toolkit (no framework: template strings + delegated events)
export const $ = (s, r = document) => r.querySelector(s);
export const $$ = (s, r = document) => [...r.querySelectorAll(s)];
export const esc = t => String(t ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
export const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
export const sleep = ms => new Promise(r => setTimeout(r, REDUCED ? Math.min(ms, 80) : ms));

/* ---------- API ---------- */
export async function api(path, {method = 'GET', body} = {}) {
  let r;
  try { r = await fetch('/api' + path, {method, headers: body ? {'Content-Type': 'application/json'} : undefined, body: body ? JSON.stringify(body) : undefined}); }
  catch (e) { throw new Error('Cannot reach the Baton server. Is it running?'); }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(j.error || r.statusText); e.status = r.status; e.restricted = j.restricted; throw e; }
  return j;
}
const C = () => '/cases/' + S.cid;
export const A = {
  health: () => api('/health'),
  newCase: (demo, name) => api('/cases', {method: 'POST', body: {demo, name: name || 'Untitled case'}}),
  getCase: () => api(C()), patchCase: b => api(C(), {method: 'PATCH', body: b}),
  sources: role => api(C() + '/sources?role=' + (role || 'manager')),
  addSource: b => api(C() + '/sources', {method: 'POST', body: b}), github: b => api(C() + '/sources/github', {method: 'POST', body: b}),
  source: (sid, role) => api(`${C()}/sources/${sid}?role=${role || S.role}`),
  patchSource: (sid, b) => api(`${C()}/sources/${sid}`, {method: 'PATCH', body: b}), delSource: sid => api(`${C()}/sources/${sid}`, {method: 'DELETE'}),
  reconstruct: () => api(C() + '/reconstruct', {method: 'POST'}),
  claims: (role, approvedOnly) => api(`${C()}/claims?role=${role || 'manager'}${approvedOnly ? '&approved_only=true' : ''}`),
  claim: (n, role) => api(`${C()}/claims/${n}?role=${role || S.role}`), history: n => api(`${C()}/claims/${n}/history`),
  review: (n, b) => api(`${C()}/claims/${n}/review`, {method: 'POST', body: b}), bulk: () => api(C() + '/claims/bulk-approve', {method: 'POST'}),
  testimony: (n, b) => api(`${C()}/claims/${n}/testimony`, {method: 'POST', body: b}), interview: () => api(C() + '/interview'),
  handover: role => api(`${C()}/handover?role=${role}`), ack: b => api(C() + '/ack', {method: 'POST', body: b}),
  graph: (role, ao) => api(`${C()}/graph?role=${role}${ao ? '&approved_only=true' : ''}`), simulate: (p, role) => api(`${C()}/analysis/simulate?person=${encodeURIComponent(p)}&role=${role}`),
  ask: (question, role) => api(C() + '/ask', {method: 'POST', body: {question, role}}),
  audit: () => api(C() + '/audit'), verify: () => api(C() + '/audit/verify'), tamper: () => api(C() + '/audit/tamper-test', {method: 'POST'}),
  exportUrl: (role, fmt) => `/api/cases/${S.cid}/handover/export?role=${role}&fmt=${fmt}`,
};

/* ---------- state ---------- */
export const S = {cid: null, case: null, sources: [], claims: [], counts: null, readiness: {percent: 0}, role: 'developer', route: 'landing', sel: null, sound: true, llm: false, busy: false};
try { S.cid = localStorage.getItem('baton.cid'); } catch (_) {}
export function setCase(cid) { S.cid = cid; try { cid ? localStorage.setItem('baton.cid', cid) : localStorage.removeItem('baton.cid'); } catch (_) {} }
const subs = new Set();
export const onChange = f => subs.add(f);
export const emit = () => subs.forEach(f => f());
export async function refresh() {
  const j = await A.getCase(); Object.assign(S, {case: j.case, sources: j.sources, counts: j.counts, readiness: j.readiness});
  if (j.case.reconstructed) S.claims = (await A.claims('manager')).claims; else S.claims = [];
  emit(); return j;
}

/* ---------- actions registry + delegation ---------- */
export const ACT = {};
document.addEventListener('click', e => { const t = e.target.closest('[data-act]'); if (t && ACT[t.dataset.act]) { e.preventDefault(); Promise.resolve(ACT[t.dataset.act](t, e)).catch(err => toast(err.message, true)); } });
document.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.matches('[data-enter]')) { e.preventDefault(); ACT[e.target.dataset.enter]?.(e.target, e); } });

/* ---------- feedback ---------- */
export function toast(m, err) { const t = $('#toast'); t.textContent = m; t.className = 'on' + (err ? ' err' : ''); clearTimeout(toast.h); toast.h = setTimeout(() => t.className = '', err ? 4200 : 2400); }
export function caption(html, stop) { const c = $('#cap'); if (!html) { c.classList.remove('on'); return; } c.innerHTML = esc(html) + (stop ? ' <button class="btn sm ghost" data-act="tour-stop">Stop</button>' : ''); c.classList.add('on'); }
let AC = null;
export function sfx(kind = 'stamp') {
  try { navigator.vibrate && navigator.vibrate(kind === 'stamp' ? 14 : 8); } catch (_) {}
  if (!S.sound || REDUCED) return;
  try {
    AC = AC || new (window.AudioContext || window.webkitAudioContext)(); const o = AC.createOscillator(), g = AC.createGain(), t = AC.currentTime;
    const f = {stamp: [150, 42, .16, .2], tick: [880, 660, .06, .05], deny: [220, 110, .22, .12], ok: [520, 780, .12, .08]}[kind];
    o.type = kind === 'stamp' ? 'triangle' : 'sine'; o.frequency.setValueAtTime(f[0], t); o.frequency.exponentialRampToValueAtTime(f[1], t + f[2]);
    g.gain.setValueAtTime(f[3], t); g.gain.exponentialRampToValueAtTime(.001, t + f[2] + .02); o.connect(g).connect(AC.destination); o.start(t); o.stop(t + f[2] + .04);
  } catch (_) {}
}
export function iris(x, y) { const i = $('#iris'); if (REDUCED) return; i.style.setProperty('--x', x + 'px'); i.style.setProperty('--y', y + 'px'); i.classList.remove('go'); void i.offsetWidth; i.classList.add('go'); }
export function countUp(el, to, ms = 700) {
  if (REDUCED) { el.textContent = to; return; } const from = +el.textContent || 0, t0 = performance.now();
  (function f(t) { const u = Math.min(1, (t - t0) / ms); el.textContent = Math.round(from + (to - from) * (1 - Math.pow(1 - u, 3))); if (u < 1) requestAnimationFrame(f); })(t0);
}
export const STATES = ['VERIFIED', 'INFERRED', 'CONFLICT', 'MISSING'];
export const TYPE_ICON = {decision: 'D', owner: 'O', risk: 'R', dependency: 'Dp', question: '?', fact: '$', contact: '@'};
export const fmtDate = s => s ? new Date(s + 'T00:00').toLocaleDateString(undefined, {month: 'short', day: 'numeric', year: 'numeric'}) : 'undated';
export const when = d => d == null ? '' : d < 0 ? `${-d}d before the last day` : d === 0 ? 'on the last day' : `${d}d after the last day`;
export const stamp = s => `<span class="stamp ${s}">${s}</span>`;
export const pill = a => `<span class="pill ${a}">${a}</span>`;
export const meter = (v, c) => `<div class="meter" style="color:${c}"><i style="width:${Math.round(v * 100)}%"></i></div>`;
export const col = s => `var(--${s})`;
