import {$, esc, S, A, ACT, refresh, toast, sfx, stamp, pill, fmtDate, when, countUp, col} from '../core.js';
import {go, chrome} from '../main.js';

let root = null, H = null, qa = [];
export function enter(el) { root = el; load(); }
export function leave() { root = null; }
export function onRole() { qa = []; load(); }

async function load() { try { H = await A.handover(S.role); } catch (e) { return root && (root.innerHTML = `<p class="mono" style="color:var(--red)">${esc(e.message)}</p>`); } draw(); }
function draw() {
  if (!root || !H) return; const h = H, r = h.readiness;
  const plan = h.plan.length ? h.plan.map(g => `<div class="bucket"><h3>${esc(g.title)}</h3>${g.items.map(i => `<div class="act" style="--c:${col(i.state)}"><div><b>${esc(i.title)}</b><div class="mono sm mut">${i.ref}${i.deadline ? ' · due ' + fmtDate(i.deadline) + ' (' + when(i.days_after) + ')' : ''}${i.leaver_only ? ' · only the leaver knew this' : ''}${i.unowned.length ? ' · unowned: ' + esc(i.unowned.join(', ')) : ''}</div>${i.unverified ? '<span class="badge pending">UNVERIFIED</span>' : ''}</div><button class="chip" data-act="cite" data-n="${i.claim}" data-role="${S.role}">evidence</button>${stamp(i.state)}</div>`).join('')}</div>`).join('') : '<p class="mut">No actions at this clearance yet.</p>';
  root.innerHTML = `<div class="brief"><div>
    <div class="eyebrow mono sm mut">Handover briefing · ${esc(S.role)} clearance · ledger v${h.version}</div><h2 style="margin:4px 0">${esc(h.case.name)}</h2>
    <div class="hpath"><span class="av">${esc((h.case.leaver || '?')[0].toUpperCase())}</span><span>${esc(h.case.leaver || 'n/a')}</span><span class="bt"></span><span>successor (${esc(S.role)})</span><span class="av">→</span></div>
    <h3>Start here: first-week plan</h3>${plan}
    ${h.sections.map(s => `<h3>${esc(s.title)}</h3>${s.claims.map(c => `<div class="glass card" style="margin:8px 0;border-left:4px solid ${col(c.state)}"><div class="row"><div style="flex:1;min-width:0">${esc(c.text)}<div class="mono sm mut">${c.ref} · ${c.evidence.map(e => esc(e.source) + ':' + (e.line + 1)).join(', ')}</div></div>${stamp(c.state)}<button class="chip" data-act="cite" data-n="${c.id}" data-role="${S.role}">evidence</button></div></div>`).join('')}`).join('')}
    <h3>Ask the evidence</h3><div class="glass card term"><div class="out" id="tlog">${qa.map(msg).join('') || '<div class="mut sm">Ask: “who owns billing?”, “what is the database?”, “what expires in December?”. Answers cite lines or refuse. Switch to Guest and ask about the vendor price.</div>'}</div>
    <div class="row"><input id="qi" data-enter="ask" placeholder="Ask a question about the project…" autocomplete="off" style="flex:1"><button class="btn" data-act="ask">Ask</button></div></div><div style="height:60px"></div></div>
  <aside class="dock">
    <div class="glass card"><div class="row"><b style="font-size:34px" id="rd">0</b><span class="mono sm">% ready</span></div>${r.parts.map(p => `<div class="mono sm mut" style="display:flex;justify-content:space-between"><span>${esc(p.label)}</span><span>${Math.round(p.value * 100)}%</span></div>`).join('')}</div>
    ${h.pending ? `<div class="glass card mono sm" style="border-color:var(--amb)">${h.pending} claim(s) are not approved yet and are excluded from this briefing.</div>` : ''}
    ${h.hidden ? `<div class="redact" style="padding:14px"><span><b>${h.hidden} approved item(s)</b> are restricted at <b>${esc(S.role)}</b> clearance. Their content was never sent to this browser. Request access from the reviewer.</span></div>` : ''}
    <div class="glass card"><h3 style="margin-top:0">Deadline radar</h3>${radar(h)}</div>
    <div class="glass card"><h3 style="margin-top:0">Who knows what</h3>${h.bus_factor.filter(p => p.claims).map(p => `<div style="padding:6px 0;border-bottom:1px dashed var(--line)"><b>${esc(p.name)}</b> <span class="mono sm mut">${p.claims} claims · </span><span class="mono sm" style="color:${p.solo_count ? 'var(--red)' : 'var(--grn)'}">${p.solo_count} known only to them</span></div>`).join('') || '<p class="mut sm">No ownership data.</p>'}</div>
    <div class="glass card"><h3 style="margin-top:0">Receipt</h3>${h.ack ? `<div class="received">RECEIVED</div><p class="mono sm">${esc(h.ack.name)} (${esc(h.ack.role)} view, ledger v${h.ack.version}) · ${new Date(h.ack.at * 1000).toLocaleString()}</p>` : `<div class="row"><input id="an" data-enter="ack" placeholder="Successor's name" style="flex:1"><button class="btn" data-act="ack">Acknowledge</button></div>`}</div>
    <div class="glass card"><h3 style="margin-top:0">Export</h3><div class="row"><a class="btn sm ghost" href="${A.exportUrl(S.role, 'md')}" download>Markdown</a><a class="btn sm ghost" href="${A.exportUrl(S.role, 'json')}" download>Evidence bundle</a><button class="btn sm ghost" onclick="print()">Print / PDF</button></div><p class="mono sm mut">Exports honour the current clearance and are generated server-side.</p></div>
  </aside></div>`;
  countUp($('#rd', root), r.percent, 800);
}
function radar(h) {
  const rs = h.radar.filter(d => d.days_after != null); if (!rs.length) return '<p class="mut">No dated items at this clearance.</p>';
  const lo = Math.min(-5, ...rs.map(d => d.days_after)), hi = Math.max(30, ...rs.map(d => d.days_after)), p = d => ((d - lo) / (hi - lo) * 100).toFixed(1);
  return `<div class="radar glass"><div class="rline"><i class="now" style="left:${p(0)}%"><span>last day</span></i>${rs.map(d => `<button class="rdot ${d.state}" style="left:${p(d.days_after)}%" data-act="cite" data-n="${d.claim}" data-role="${S.role}" title="${esc(d.line)}"><span>${fmtDate(d.iso)}</span></button>`).join('')}</div>${rs.filter(d => d.unowned.length).map(d => `<div class="mono sm" style="color:var(--amb)">${fmtDate(d.iso)}: no owner for ${d.unowned.length} dependency gap(s) tied to this date</div>`).join('')}</div>`;
}
const msg = m => `<div class="msg me">› ${esc(m.q)}</div><div class="msg ${m.r.refused ? 'no' : 'ok'}">${m.r.refused ? `<b>REFUSED.</b> ${esc(m.r.reason)}${m.r.hidden_matches ? ` ${m.r.hidden_matches} match(es) exist above your clearance (contents withheld).` : ''}${m.r.pending_matches ? ` ${m.r.pending_matches} match(es) await reviewer approval.` : ''}` : `${esc(m.r.answer)}${m.r.caution ? `<div class="mono sm" style="color:var(--amb)">${esc(m.r.caution)}</div>` : ''}<div class="row">${m.r.claims.map(c => `<button class="chip" data-act="cite" data-n="${c.id}" data-role="${S.role}">${c.ref} ${c.state}</button>`).join('')}</div>`}</div>`;
ACT.ask = async () => { const i = $('#qi'), q = i.value.trim(); if (!q) return; i.value = ''; const r = await A.ask(q, S.role); qa.push({q, r}); sfx(r.refused ? 'deny' : 'ok'); $('#tlog').innerHTML = qa.map(msg).join(''); $('#tlog').scrollTop = 1e9; };
ACT.ack = async () => { await A.ack({name: $('#an').value, role: S.role}); sfx('stamp'); await refresh(); await load(); toast('Receipt recorded in the audit chain'); };
