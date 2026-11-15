import {$, esc, S, A, ACT, refresh, toast, sfx, stamp, pill, meter, col, fmtDate, REDUCED} from '../core.js';
import {go, chrome, resync} from '../main.js';

let root = null, Q = [], undo = [], kb = null;
const pending = () => S.claims.filter(c => c.status === 'pending' || c.status === 'drifted');

export function enter(el) {
  root = el; Q = pending().sort((a, b) => (b.status === 'drifted') - (a.status === 'drifted') || ({CONFLICT: 0, MISSING: 1, INFERRED: 2, VERIFIED: 3}[a.state] - {CONFLICT: 0, MISSING: 1, INFERRED: 2, VERIFIED: 3}[b.state]));
  draw(); kb = e => { if (!root || e.target.matches('input,textarea,select')) return; const k = e.key; if (k === 'ArrowRight') ACT.dec(null, 'approve'); else if (k === 'ArrowLeft') ACT.dec(null, 'reject'); else if (k === 'ArrowUp') { e.preventDefault(); ACT.edit(); } else if (k.toLowerCase() === 'z') ACT.undo(); };
  document.addEventListener('keydown', kb);
}
export function leave() { root = null; document.removeEventListener('keydown', kb); }

function draw() {
  if (!root) return; const c = Q[0], vers = S.claims.filter(x => x.status === 'approved').length, nv = S.claims.filter(x => x.state === 'VERIFIED' && ['pending', 'drifted'].includes(x.status)).length;
  root.innerHTML = `<h2>Review deck</h2><p class="lead">Nothing reaches the successor until you decide. <kbd>→</kbd> approve · <kbd>←</kbd> reject · <kbd>↑</kbd> edit · <kbd>Z</kbd> undo.</p>
  <div class="row" style="margin-bottom:14px"><span class="mono sm mut">${Q.length} to decide · ${vers} approved</span><span class="sp"></span>${nv ? `<button class="btn ghost" data-act="bulk">Approve ${nv} VERIFIED at once</button>` : ''}<button class="btn ghost" data-act="undo" ${undo.length ? '' : 'disabled'}>Undo (Z)</button></div>
  ${c ? deck(c) : done()}`;
}
function deck(c) {
  const conflict = c.state === 'CONFLICT';
  return `<div class="deck"><div class="glass dcard ${c.state}" id="dc">${Q[2] ? '<div class="dback b2"></div>' : ''}${Q[1] ? '<div class="dback b1"></div>' : ''}
    <div class="row"><span class="mono sm mut">${c.ref} · ${c.type}${c.date ? ' · ' + fmtDate(c.date) : ''}</span><span class="sp"></span>${pill(c.access)}${c.status === 'drifted' ? '<span class="badge drifted">DRIFTED</span>' : ''}${stamp(c.state)}</div>
    <p style="font:600 clamp(19px,2.4vw,28px)/1.3 var(--ui);margin:16px 0">${esc(c.text)}</p>${c.note ? `<p class="mono sm" style="color:var(--amb)">${esc(c.note)}</p>` : ''}
    <div class="row">${meter(c.confidence, col(c.state))}<b>${Math.round(c.confidence * 100)}%</b></div>
    <div class="why">${c.factors.map(f => `<div><span class="${f.delta >= 0 ? 'p' : 'n'}">${f.delta >= 0 ? '+' : ''}${Math.round(f.delta * 100)}</span> ${esc(f.label)}</div>`).join('')}</div>
    ${c.evidence.map(e => `<div class="paper"><div class="ln hit"><em>${e.line + 1}</em><span>${esc(e.quote)}</span></div><button class="chip" data-act="open-src" data-sid="${e.sid}" data-line="${e.line}">${esc(e.source)}:${e.line + 1}${e.variant ? ' · ' + esc(e.variant) : ''}</button></div>`).join('')}
    ${conflict ? `<p class="mono sm">Pick the current value to resolve:</p><div class="row">${(c.variants || []).map(v => `<button class="btn" data-act="pick" data-v="${esc(v)}">Keep “${esc(v)}”</button>`).join('')}</div>` : ''}
    <div class="deckbar">${conflict ? '' : '<button class="btn" data-act="dec" data-d="approve">Approve →</button>'}<button class="btn ghost" data-act="edit">Edit ↑</button><button class="btn ghost" data-act="dec" data-d="reject" style="color:var(--red)">← Reject</button></div></div></div>`;
}
const done = () => `<div class="glass card" style="text-align:center;padding:40px"><h2>Deck cleared</h2><p class="mut">${S.readiness.percent}% ready. Next: hand over with a role-redacted briefing and collect a receipt.</p><button class="btn xl" data-act="go" data-r="handover">Open handover →</button></div>`;

async function act(c, body, label) {
  const dc = $('#dc', root); if (dc && !REDUCED) { dc.classList.add(body.action === 'reject' ? 'out-l' : 'out-r'); await new Promise(r => setTimeout(r, 220)); }
  await A.review(c.id, body); undo.push({id: c.id}); sfx('stamp'); await refresh(); resync(); Q = Q.filter(x => x.id !== c.id); if (root) draw(); toast(label);
}
ACT.dec = async (t, d) => { const c = Q[0]; if (!c) return; d = typeof d === 'string' ? d : t.dataset.d; if (d === 'approve' && c.state === 'CONFLICT') return toast('Resolve the conflict first: pick the current value', true); await act(c, {action: d}, d === 'approve' ? `${c.ref} approved` : `${c.ref} rejected`); };
ACT.pick = async t => { const c = Q[0]; await act(c, {action: 'resolve', choice: t.dataset.v}, `${c.ref} resolved: ${t.dataset.v}`); };
ACT.edit = () => {
  const c = Q[0]; if (!c || c.state === 'CONFLICT') return; const d = $('#dlg');
  d.innerHTML = `<form method="dialog" class="card" style="min-width:min(560px,90vw)"><h3>Edit ${c.ref}</h3><textarea id="et" rows="5">${esc(c.text.split('  >>')[0])}</textarea><p class="mono sm mut">The edit is versioned, hash-chained and approved. Evidence stays attached.</p><div class="row"><button class="btn" value="ok">Save and approve</button><button class="btn ghost" value="x">Cancel</button></div></form>`;
  d.showModal(); d.onclose = async () => { if (d.returnValue === 'ok') await act(c, {action: 'edit', text: $('#et').value}, `${c.ref} edited`); d.returnValue = ''; };
};
ACT.undo = async () => {
  const u = undo.pop(); if (!u) return; try { await A.review(u.id, {action: 'undo'}); } catch (e) { return toast(e.message, true); }
  sfx('tick'); await refresh(); resync(); Q = pending().filter(x => x.id === u.id).concat(Q.filter(x => x.id !== u.id)); if (root) draw(); toast('Undone');
};
ACT.bulk = async () => { const r = await A.bulk(); sfx('stamp'); await refresh(); resync(); Q = pending(); draw(); toast(`${r.approved.length} VERIFIED claims approved`); };
