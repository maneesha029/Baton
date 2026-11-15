import {$, esc, S, A, ACT, sfx, toast, sleep} from '../core.js';

let root = null, D = null;
export function enter(el) { root = el; load(); }
export function leave() { root = null; }
async function load() { D = await A.audit(); draw(); }
const short = h => h.slice(0, 8);
function draw(forged, bad) {
  if (!root) return; const v = D.verify;
  root.innerHTML = `<h2>Audit chain</h2><p class="lead">Every approval, edit, resolution, testimony and receipt is appended to a per-case SHA-256 hash chain on the server. Change any past entry and every later hash fails. <b>Tamper-evident, not tamper-proof</b>: an attacker with database write access could rebuild the whole chain, so pin the head hash somewhere external.</p>
  <div class="row" style="margin-bottom:16px"><span class="stamp ${v.ok ? 'VERIFIED' : 'CONFLICT'}">${v.ok ? 'CHAIN INTACT' : 'BROKEN AT #' + v.broken_at}</span><span class="mono sm mut">${v.length} entries · head ${short(v.head)}</span><span class="sp"></span><button class="btn" data-act="a-verify">Verify now</button><button class="btn ghost" data-act="a-forge">Forge an entry (on a copy)</button></div>
  <div class="chain">${D.entries.map(e => `<div class="blk ${bad && e.seq >= bad ? 'bad' : ''} ${forged === e.seq ? 'forged' : ''}" data-seq="${e.seq}"><div class="mono sm mut">#${e.seq} · ${new Date(e.at * 1000).toLocaleTimeString()} · ${esc(e.actor)}</div><b>${esc(e.action)}</b><div class="mono sm mut">prev ${short(e.prev)} → <span style="color:var(--cy)">${short(e.hash)}</span></div></div>`).join('') || '<p class="mut">No entries.</p>'}</div>`;
}
ACT['a-verify'] = async () => { const v = await A.verify(); D.verify = v; draw(); const bl = [...root.querySelectorAll('.blk')]; for (const b of bl) { b.classList.add('chk'); sfx('tick'); await sleep(40); } toast(v.ok ? `All ${v.length} links verified` : 'Chain broken', !v.ok); };
ACT['a-forge'] = async () => { const t = await A.tamper(); if (!t.ok) return toast(t.reason, true); draw(t.forged_seq, t.detected_at); const b = root.querySelector(`[data-seq="${t.forged_seq}"]`); b && b.scrollIntoView({block: 'center'}); sfx(t.detected ? 'deny' : 'ok'); toast(t.detected ? `Forged #${t.forged_seq} → verifier failed at exactly #${t.detected_at}. Nothing was written.` : 'Not detected (bug)', !t.detected); };
