import {$, $$, esc, S, A, ACT, toast, sfx, stamp, sleep} from '../core.js';
import {scene} from '../scene.js';

let root = null, G = null, people = [], timer = null, simP = null;
const TYPES = ['all', 'decision', 'owner', 'risk', 'dependency', 'question', 'fact', 'contact'];

export function enter(el) {
  root = el; simP = null; scene.setFilter({type: 'all', cut: ''}); scene.simulate(null);
  el.innerHTML = `<h2 style="margin-bottom:8px">Knowledge map <span class="mono sm mut">· ${esc(S.role)} clearance</span></h2>
  <div class="mapwrap" id="mw"><div id="ml"></div>
    <div class="mapui tl glass card"><div class="mono sm mut">filter</div><div class="row" style="gap:5px">${TYPES.map(t => `<button class="chip ${t === 'all' ? 'on' : ''}" data-act="m-type" data-t="${t}">${t}</button>`).join('')}</div>
      <input id="ms" placeholder="find node…" style="margin-top:8px"><div class="mono sm mut" style="margin-top:8px">Drag to orbit · scroll to zoom · click a node. Restricted nodes render as opaque, striped placeholders: no label, no text.</div></div>
    <div class="mapui tr glass card" id="mp"><div class="mono sm mut">Select a node, or simulate a departure below.</div></div>
    <div class="mapui bl glass card"><div style="flex:1"><div class="mono sm mut">timeline replay <b id="mt" style="color:var(--txt)"></b></div><input type="range" id="mr" min="0" max="0" value="0" style="width:100%"></div><button class="btn sm" data-act="m-play">▶ Replay</button>
      <div class="sim" id="sim"></div></div></div>`;
  scene.dock($('#mw', el), $('#labels'));
  scene.handlers.select = d => panel(d);
  const s = $('#ms', el); s.oninput = () => { const q = s.value.trim().toLowerCase(); if (!q || !G) return; const n = G.nodes.find(n => !n.restricted && ((n.label || n.name || '') + ' ' + n.id).toLowerCase().includes(q)); n && (scene.focus(n.id), scene.select(n.id)); };
  const r = $('#mr', el); r.oninput = () => cut(+r.value);
  A.graph(S.role, false).then(g => onGraph(g)).catch(() => {});
}
export function leave() { clearInterval(timer); scene.handlers.select = null; scene.setFilter({type: 'all', cut: ''}); scene.simulate(null); scene.select(null); root = null; }
export function onRole() { if (root) { scene.undock(); enter(root); } }
export async function onGraph(g) {
  G = g; if (!root) return; const d = $('#mr', root); if (!d) return; d.max = Math.max(0, scene.dates.length); d.value = d.max; cut(+d.max);
  const ppl = g.nodes.filter(n => n.kind === 'person' && !n.restricted); people = ppl.map(p => p.name || p.id.replace('P:', ''));
  $('#sim', root).innerHTML = (people.length ? '<span class="mono sm mut" style="align-self:center">if leaves:</span>' : '') + people.map(p => `<button data-act="m-sim" data-p="${esc(p)}">${esc(p)}</button>`).join('');
}
function cut(i) { const ds = scene.dates, c = i >= ds.length ? '' : ds[i]; scene.setFilter({cut: c}); $('#mt', root).textContent = c || 'now'; }
ACT['m-type'] = t => { $$('.chip', root).forEach(c => c.classList.toggle('on', c === t)); scene.setFilter({type: t.dataset.t}); sfx('tick'); };
ACT['m-play'] = () => { const r = $('#mr', root); if (!+r.max) return; clearInterval(timer); r.value = 0; cut(0); timer = setInterval(() => { r.value = +r.value + 1; cut(+r.value); if (+r.value >= +r.max) clearInterval(timer); }, 380); };
ACT['m-sim'] = async t => {
  const p = t.dataset.p; if (simP === p) { simP = null; scene.simulate(null); $$('.sim button', root).forEach(b => b.classList.remove('on')); return panel(null); }
  simP = p; $$('.sim button', root).forEach(b => b.classList.toggle('on', b === t));
  const r = await A.simulate(p, S.role); scene.simulate({person: p, orphaned: r.orphaned.map(o => o.ref), ripple: r.ripple.map(x => 'C' + x)}); sfx('deny');
  $('#mp', root).innerHTML = `<h3 style="margin:0">If ${esc(p)} leaves</h3><p class="mono sm"><b style="color:var(--red)">${r.orphaned.length}</b> claim(s) become orphaned · <b>${r.survive}</b> of ${r.holds} survive · ${r.ripple.length} downstream ripple</p>${r.orphaned.map(o => `<div class="mono sm" style="margin:6px 0">${stamp(o.state)} ${esc(o.text.split('  >>')[0])} <button class="chip" data-act="cite" data-n="${o.id}" data-role="${S.role}">evidence</button></div>`).join('') || '<p class="mut sm">Nothing is known only to them.</p>'}${r.deadlines.length ? `<p class="mono sm" style="color:var(--amb)">${r.deadlines.length} dated item(s) tied to their knowledge</p>` : ''}`;
};
function panel(d) {
  const p = $('#mp', root); if (!p) return;
  if (!d) return void (p.innerHTML = '<div class="mono sm mut">Select a node, or simulate a departure below.</div>');
  if (d.restricted) return void (p.innerHTML = `<div class="redact" style="padding:14px"><span><b>Restricted node.</b> Exists, but your clearance (${esc(S.role)}) does not allow its content. Nothing about it was sent to this browser.</span></div>`);
  if (d.kind === 'claim') return void (p.innerHTML = `<div class="mono sm mut">${esc(d.id)} · ${esc(d.type || '')}</div><p style="font:600 15px/1.35 var(--ui)">${esc(d.label || d.text || '')}</p>${stamp(d.state)} <button class="chip" data-act="cite" data-n="${d.num}" data-role="${S.role}">open evidence</button><div class="mono sm mut" style="margin-top:8px">${scene.neighbours(d.id).map(n => esc(n.label || n.name || n.id)).slice(0, 6).join('<br>')}</div>`);
  p.innerHTML = `<div class="mono sm mut">${esc(d.kind)}</div><b>${esc(d.name || d.id)}</b>${d.kind === 'src' ? `<div><button class="chip" data-act="open-src" data-sid="${d.id}" data-line="-1">read source</button></div>` : ''}<div class="mono sm mut" style="margin-top:8px">${scene.neighbours(d.id).length} connections</div>`;
}
