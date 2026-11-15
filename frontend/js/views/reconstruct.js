import {$, esc, S, A, ACT, refresh, toast, sfx, sleep, STATES, countUp, REDUCED} from '../core.js';
import {go, chrome, resync} from '../main.js';
import {scene} from '../scene.js';

let root = null, last = null, token = 0;
const NAMES = ['Ingest', 'Extract', 'Verify citations', 'Trust states', 'Contradictions'];
const WHY = {Ingest: 'parse + mask secrets', Extract: 'ontology-driven claims', 'Verify citations': 're-read every cited line', 'Trust states': 'score + explain confidence', Contradictions: 'keep disagreements side by side'};

export function enter(el, opts = {}) {
  root = el;
  if (opts.run || !S.case.reconstructed) run(); else show(last, true);
}
export function leave() { root = null; token++; }

function frame(body) {
  root.innerHTML = `<div style="display:grid;grid-template-columns:minmax(300px,480px) 1fr;gap:20px;align-items:start;min-height:70vh">
    <div><h2>Reconstructing the case</h2><p class="lead">Each stage runs on the server. The timings below are the measured durations it reports; the 3D scene grows from the same ledger.</p>${body}</div><div></div></div>`;
}
async function run() {
  const my = ++token;
  frame(`<div class="pipe" id="pipe">${NAMES.map((n, i) => `<div class="glass stg" data-i="${i}"><i>${i + 1}</i><div><b>${n}</b><small>${WHY[n]}</small></div><span class="ms"></span></div>`).join('')}</div><div class="glass console" id="con"></div>`);
  const con = $('#con', root), log = (t, m) => { if (!root) return; con.insertAdjacentHTML('beforeend', `<div><span class="t">[${t}]</span> ${esc(m)}</div>`); con.scrollTop = 1e9; };
  log('start', `case ${S.cid}: ${S.sources.filter(s => s.included).length} sources`);
  let res;
  try { res = await A.reconstruct(); } catch (e) { if (my !== token) return; root.querySelector('.pipe').insertAdjacentHTML('afterend', `<div class="glass card" style="border-color:var(--red)"><b>Reconstruction failed</b><p class="mono sm">${esc(e.message)}</p><button class="btn" data-act="go" data-r="connect">Back to sources</button></div>`); return; }
  if (my !== token) return;
  last = res;
  for (let i = 0; i < res.stages.length; i++) {
    if (my !== token) return; const st = res.stages[i], row = $(`.stg[data-i="${i}"]`, root); if (!row) return;
    row.classList.add('run'); await sleep(430); if (my !== token) return;
    row.classList.remove('run'); row.classList.add('ok'); $('i', row).textContent = '✓'; $('.ms', row).textContent = st.ms + ' ms'; $('small', row).textContent = `${st.count} · ${st.note}`;
    log(st.name.toLowerCase(), `${st.count} (${st.ms} ms) ${st.note}`); sfx('tick');
    if (i === 1) { await refresh(); await resync(); scene.reveal(); }
  }
  await refresh(); chrome(); await sleep(300); if (my !== token) return; show(res);
}
function show(res, replay) {
  if (!root) return; const cnt = S.counts.state;
  frame(`<div class="tiles4" style="grid-template-columns:repeat(2,1fr);max-width:480px">${STATES.map(s => `<div class="tile ${s}"><b data-n="${cnt[s] || 0}">0</b>${s}</div>`).join('')}</div>
    <div class="glass card" style="margin-top:14px"><div class="mono sm"><b style="color:var(--txt)">${S.counts.total}</b> claims · every one cites at least one re-read line.${res ? ` Pipeline ${res.total_ms} ms.` : ''}</div>
    ${res && res.rejected.length ? `<div class="mono sm" style="margin-top:8px;color:var(--amb)">${res.rejected.length} candidate(s) rejected because the cited text did not support them:<br>${res.rejected.slice(0, 4).map(r => '· ' + esc(r.text)).join('<br>')}</div>` : '<div class="mono sm mut" style="margin-top:8px">0 candidates rejected by the citation check.</div>'}</div>
    <div class="row" style="margin-top:16px"><button class="btn xl" data-act="go" data-r="verify">Open the ledger →</button><button class="btn ghost" data-act="rebuild">Re-run</button></div>`);
  root.querySelectorAll('[data-n]').forEach(e => countUp(e, +e.dataset.n, replay ? 1 : 900));
  sfx('ok');
}
