import {$, $$, esc, S, A, ACT, refresh, toast, sfx, stamp, pill, meter, col, STATES, TYPE_ICON, fmtDate, countUp} from '../core.js';
import {go, chrome, resync} from '../main.js';
import {scene} from '../scene.js';

let root = null, f = {state: 'ALL', q: ''}, mode = 'ledger', IV = null, ix = 0, focus = null;

export function enter(el, o = {}) {
  root = el; focus = o.focus || null; mode = o.interview ? 'interview' : 'ledger';
  if (mode === 'interview') return startInterview();
  draw(); if (focus) setTimeout(() => { const n = $(`[data-c="${focus}"]`, root); if (n) { n.scrollIntoView({block: 'center', behavior: 'smooth'}); n.classList.add('flash'); } }, 80);
}
export function leave() { root = null; }

const sel = () => S.claims.filter(c => c.status !== 'rejected' || f.state === 'ALL').filter(c => (f.state === 'ALL' || c.state === f.state) && (!f.q || (c.text + ' ' + c.type + ' ' + c.ref).toLowerCase().includes(f.q)));
function draw() {
  if (!root) return; const cnt = S.counts.state;
  root.innerHTML = `<h2>The ledger</h2><p class="lead">Every claim is a statement with receipts. Conflicts keep both sides; gaps become questions for the leaver. Click any citation to read the exact line.</p>
  <div class="tiles4" style="margin-bottom:16px">${STATES.map(s => `<button class="tile ${s} ${f.state === s ? 'on' : ''}" data-act="vf" data-s="${s}"><b>${cnt[s] || 0}</b>${s}</button>`).join('')}</div>
  <div class="row" style="margin-bottom:14px"><input id="vq" placeholder="Search claims…  (/)" value="${esc(f.q)}" style="max-width:340px"><button class="chip ${f.state === 'ALL' ? 'on' : ''}" data-act="vf" data-s="ALL">All ${S.counts.total}</button><span class="sp"></span>
    <button class="btn ghost" data-act="interview">Interview mode (${S.claims.filter(c => ['MISSING', 'CONFLICT'].includes(c.was || c.state) && c.status !== 'rejected').length})</button><button class="btn" data-act="go" data-r="review">Review deck →</button></div>
  <div id="vl">${list()}</div>`;
  const q = $('#vq', root); q.oninput = () => { f.q = q.value.toLowerCase(); $('#vl', root).innerHTML = list(); };
}
function list() { const r = sel(); return r.length ? r.map(card).join('') : '<p class="mut mono">No claims match.</p>'; }
const cites = c => c.evidence.map(e => `<button class="chip" data-act="open-src" data-sid="${e.sid}" data-line="${e.line}" title="${esc(e.quote)}">${esc(e.source)}:${e.line + 1}</button>`).join('');
function card(c) {
  const head = `<div class="row"><span class="ti">${TYPE_ICON[c.type] || '•'}</span><span class="mono sm mut">${c.ref} · ${c.type}${c.date ? ' · ' + fmtDate(c.date) : ''}</span><span class="sp"></span>${pill(c.access)}<span class="badge ${c.status}">${c.status}</span>${stamp(c.state)}</div>`;
  if (c.state === 'CONFLICT') return `<div class="glass claim CONFLICT" data-c="${c.id}">${head}<p class="tx">${esc(c.text)}</p>${sides(c)}${c.hint && c.hint.newest ? `<p class="mono sm mut">NEWEST dated evidence says <b style="color:var(--txt)">${esc(c.hint.newest)}</b>. A hint, not a verdict. You decide.</p>` : ''}${tCard(c)}
    <div class="row" style="margin-top:10px">${(c.variants || []).map(v => `<button class="btn sm" data-act="resolve" data-n="${c.id}" data-v="${esc(v)}">Keep “${esc(v)}”</button>`).join('')}<button class="btn sm ghost" data-act="why" data-n="${c.id}">Why this?</button></div></div>`;
  return `<div class="glass claim ${c.state}" data-c="${c.id}">${head}<p class="tx">${esc(c.text)}</p>${c.note ? `<p class="mono sm" style="color:var(--amb)">${esc(c.note)}</p>` : ''}
    <div class="row">${meter(c.confidence, col(c.state))}<b class="mono sm">${Math.round(c.confidence * 100)}%</b><span class="sp"></span>${cites(c)}</div>${c.state === 'MISSING' ? tForm(c) : ''}</div>`;
}
function sides(c) {
  const vs = c.variants || [];
  return `<div class="cf2">${vs.map((v, i) => `<div class="side"><div class="mono sm mut">${esc(v)}</div>${c.evidence.filter(e => e.variant === v).map(e => `<div class="paper"><div class="ln hit"><em>${e.line + 1}</em><span>${esc(e.quote)}</span></div><button class="chip" data-act="open-src" data-sid="${e.sid}" data-line="${e.line}">${esc(e.source)}</button></div>`).join('') || '<p class="mut sm">no quoted line</p>'}</div>${i < vs.length - 1 ? '<div class="thread" aria-hidden="true"></div>' : ''}`).join('')}</div>`;
}
const tCard = c => (c.testimony || []).map(t => `<p class="mono sm">${esc(t.author)} (leaver testimony${t.choice ? ', says ' + esc(t.choice) : ''}): ${esc(t.answer)}</p>`).join('');
const tForm = c => `<div class="row" style="margin-top:10px"><input data-enter="tsay" data-n="${c.id}" id="t${c.id}" placeholder="${S.case.leaver ? S.case.leaver : 'leaver'}'s answer (recorded as testimony, never VERIFIED)"><button class="btn sm" data-act="tsay" data-n="${c.id}">Record</button></div>`;

ACT.vf = t => { f.state = t.dataset.s; draw(); };
ACT.resolve = async t => { await A.review(+t.dataset.n, {action: 'resolve', choice: t.dataset.v}); sfx('stamp'); await refresh(); resync(); toast('Conflict resolved. Both sources remain as evidence.'); if (mode === 'ledger') draw(); };
ACT.why = t => window.inspectClaim(+t.dataset.n, 'manager');
ACT.tsay = async t => {
  const n = +t.dataset.n, i = $(`#t${n}`) || $('#iv-a'); if (!i || !i.value.trim()) return toast('Type an answer first', true);
  await A.testimony(n, {author: S.case.leaver || 'leaver', answer: i.value.trim(), choice: IV && IV.questions[ix]?.options ? $('#iv-c')?.value : null}); sfx('stamp'); await refresh(); chrome();
  if (mode === 'interview') { IV = await A.interview(); next(); } else draw();
};

/* ---------- interview mode: the leaver's last 10 minutes ---------- */
async function startInterview() { IV = await A.interview(); ix = Math.max(0, IV.questions.findIndex(q => !q.answered)); showQ(); }
function next() { const i = IV.questions.findIndex((q, k) => k > ix && !q.answered); if (i < 0) { ix = IV.questions.length; return showQ(); } ix = i; showQ(); }
function showQ() {
  if (!root) return; const n = IV.questions.length, q = IV.questions[ix], done = IV.questions.filter(x => x.answered).length;
  if (!n || !q) { root.innerHTML = `<div class="interview"><h2>Interview complete</h2><p class="lead">${done}/${n} questions answered. Answers are recorded as <b>testimony</b>: the leaver's own word, flagged as unverified until a reviewer decides.</p><div class="row"><button class="btn xl" data-act="go" data-r="review">Review the answers →</button><button class="btn ghost" data-act="go" data-r="verify">Back to ledger</button></div></div>`; return; }
  root.innerHTML = `<div class="interview"><div class="progress"><i style="width:${Math.round(done / n * 100)}%"></i></div><div class="mono sm mut">Question ${ix + 1} of ${n} · about ${IV.estimate_minutes} min total · ${q.kind}${q.deadline != null ? ` · deadline ${q.deadline}d after last day` : ''}</div>
  <h1 style="font-size:clamp(22px,3.2vw,38px);margin:12px 0">${esc(q.prompt)}</h1><p class="mut">${esc(q.why)}</p>
  ${q.evidence.map(e => `<div class="paper"><div class="ln hit"><em>${e.line + 1}</em><span>${esc(e.quote)}</span></div><span class="mono sm mut">${esc(e.source)}</span></div>`).join('')}
  ${q.options ? `<label class="f">Which is current?<select id="iv-c">${q.options.map(o => `<option>${esc(o)}</option>`).join('')}</select></label>` : ''}
  <label class="f" style="margin-top:10px">Your answer<textarea id="iv-a" rows="4" autofocus></textarea></label>
  <div class="row" style="margin-top:12px"><button class="btn xl" data-act="tsay" data-n="${q.claim}">Record answer</button><button class="btn ghost" data-act="iv-skip">Skip</button><button class="btn ghost" data-act="go" data-r="verify">Exit</button></div></div>`;
}
ACT['iv-skip'] = () => { ix = Math.min(IV.questions.length, ix + 1); showQ(); };
