import {$, $$, esc, S, A, ACT, refresh, toast, sfx, pill} from '../core.js';
import {go, inspectSource, resync, chrome} from '../main.js';
import {scene} from '../scene.js';

let root = null, tab = 'drop', stale = false;
const ICON = {git: '⎇', notes: '¶', tasks: '☑', chat: '✉', doc: '❡', text: '≡'};

export function enter(el) { root = el; draw(); }
export function leave() { root = null; scene.highlight(null); }

function draw() {
  if (!root) return;
  const c = S.case, inc = S.sources.filter(s => s.included).length, lines = S.sources.filter(s => s.included).reduce((a, s) => a + s.lines, 0), red = S.sources.reduce((a, s) => a + (s.redactions || 0), 0);
  root.innerHTML = `
  <h2>Evidence wall</h2>
  <p class="lead">Connect the sources the investigation may read, and label how sensitive each one is. Secrets are masked <b>before anything is stored</b>. The label travels with every claim that cites the source.</p>
  <div class="glass card row" style="margin-bottom:16px;gap:18px">
    <label class="f" style="width:200px">Leaver<input id="lv" value="${esc(c.leaver)}" placeholder="e.g. asha" data-enter="save-case"></label>
    <label class="f" style="width:200px">Last day<input id="ld" type="date" value="${esc(c.last_day)}"></label>
    <button class="btn sm ghost" data-act="save-case">Save</button>
    <span class="sp"></span><span class="mono sm mut">${inc} of ${S.sources.length} sources · ${lines} lines · <b style="color:var(--amb)">${red}</b> secrets masked</span>
  </div>
  ${stale ? '<div class="glass card mono sm" style="border-color:var(--amb);margin-bottom:14px">Sources changed since the last reconstruction. Rebuild to update the ledger (approved decisions are kept; changed evidence raises a drift alert).</div>' : ''}
  <div class="grid">${S.sources.map(srcCard).join('') || '<p class="mut">No sources yet. Add one below.</p>'}</div>
  <h3>Add evidence</h3>
  <div class="tabs">${[['drop', 'Drop files'], ['paste', 'Paste text'], ['gh', 'GitHub repo']].map(([k, l]) => `<button data-act="ctab" data-k="${k}" class="${tab === k ? 'on' : ''}">${l}</button>`).join('')}</div>
  <div class="glass card">${addPanel()}</div>
  <div class="row" style="margin:22px 0 40px;justify-content:space-between">
    <span class="mono sm mut">Supported: GitHub API JSON, markdown notes, task-board JSON, chat-export JSON, plain text.</span>
    <button class="btn xl" data-act="rebuild" ${inc ? '' : 'disabled'}>${S.case.reconstructed ? 'Rebuild the case' : 'Reconstruct the case'} →</button>
  </div>`;
  $$('.src', root).forEach(n => { n.onmouseenter = () => scene.highlight(n.dataset.sid); n.onmouseleave = () => scene.highlight(null); });
  const d = $('.drop', root);
  if (d) { ['dragenter', 'dragover'].forEach(ev => d.addEventListener(ev, e => { e.preventDefault(); d.classList.add('over'); })); ['dragleave', 'drop'].forEach(ev => d.addEventListener(ev, e => { e.preventDefault(); d.classList.remove('over'); }));
    d.addEventListener('drop', e => upload([...e.dataTransfer.files])); const f = $('#fi', root); f && (f.onchange = () => upload([...f.files])); }
}
function srcCard(s) {
  if (s.restricted) return '';
  return `<div class="glass card src hover ${s.acl} ${s.included ? '' : 'off'}" data-sid="${s.id}"><div class="row"><div class="ico">${ICON[s.kind] || '≡'}</div><div style="min-width:0;flex:1"><div class="nm">${esc(s.name)}</div><div class="mono sm mut">${s.id} · ${esc(s.kind)} · ${s.lines} lines</div></div>${pill(s.acl)}</div>
  <div class="mono sm mut" style="margin:10px 0">${esc(s.origin)}${s.redactions ? ` · <span style="color:var(--amb)">${s.redactions} secret${s.redactions > 1 ? 's' : ''} masked</span>` : ''}</div>
  <div class="row"><label class="row" style="gap:8px"><input type="checkbox" class="switch" ${s.included ? 'checked' : ''} data-act="toggle-src" data-sid="${s.id}" aria-label="Include ${esc(s.name)}"><span class="sm mono">include</span></label><span class="sp"></span>
  <select data-act="acl-src" data-sid="${s.id}" style="width:auto;padding:6px 8px;font:11px var(--mono)" aria-label="Clearance">${['public', 'team', 'confidential'].map(a => `<option ${a === s.acl ? 'selected' : ''}>${a}</option>`).join('')}</select>
  <button class="btn sm ghost" data-act="read-src" data-sid="${s.id}">Read</button><button class="btn sm ghost" data-act="del-src" data-sid="${s.id}" aria-label="Delete" style="color:var(--red)">✕</button></div></div>`;
}
const aclSel = id => `<label class="f" style="width:170px">Clearance<select id="${id}"><option>public</option><option selected>team</option><option>confidential</option></select></label>`;
function addPanel() {
  if (tab === 'paste') return `<div class="row" style="align-items:flex-end"><label class="f" style="flex:1;min-width:200px">Name<input id="pn" placeholder="notes/standup.md"></label>${aclSel('pa')}</div>
    <label class="f" style="margin-top:10px">Content<textarea id="pt" rows="7" placeholder="## 2026-10-01 Standup&#10;- Asha owns billing&#10;- Risk: licence expires Dec 15&#10;&#10;Dates in headings apply to the lines below them."></textarea></label><button class="btn" data-act="paste-add" style="margin-top:12px">Add source</button>`;
  if (tab === 'gh') return `<div class="row" style="align-items:flex-end"><label class="f" style="flex:1;min-width:220px">Repository<input id="gr" placeholder="owner/repo or https://github.com/owner/repo"></label>${aclSel('ga')}</div>
    <label class="f" style="margin-top:10px">Token (optional, only for private repos; sent to GitHub, never stored)<input id="gt" type="password" autocomplete="off"></label><button class="btn" data-act="gh-add" style="margin-top:12px">Import commits and issues</button>
    <p class="mono sm mut">Needs outbound access to api.github.com from the server. Rate limits apply without a token.</p>`;
  return `<div class="drop"><p style="font:600 17px var(--ui);margin:0 0 6px">Drop files here</p><p class="mut mono sm" style="margin:0 0 14px">.json .md .txt .log · up to 400 KB each</p><div class="row" style="justify-content:center">${aclSel('da')}<label class="btn ghost" style="cursor:pointer;margin-top:18px">Choose files<input id="fi" type="file" multiple accept=".json,.md,.markdown,.txt,.log" hidden></label></div></div>`;
}
async function after(msg) { await refresh(); stale = !!S.case.reconstructed; draw(); chrome(); resync(); if (msg) toast(msg); }
async function upload(files) {
  const acl = $('#da', root)?.value || 'team';
  for (const f of files) { try { const text = await f.text(); const s = await A.addSource({name: f.name, text, acl, origin: 'uploaded file'}); toast(`${f.name}: ${s.lines} lines${s.redactions ? `, ${s.redactions} secrets masked` : ''}`); sfx('ok'); } catch (e) { toast(`${f.name}: ${e.message}`, true); } }
  await after();
}
ACT.ctab = t => { tab = t.dataset.k; draw(); };
ACT['save-case'] = async () => { await A.patchCase({leaver: $('#lv').value, last_day: $('#ld').value}); await after('Saved'); };
ACT['toggle-src'] = async t => { await A.patchSource(t.dataset.sid, {included: t.checked}); await after(); };
ACT['acl-src'] = async t => { if (t.tagName !== 'SELECT') return; await A.patchSource(t.dataset.sid, {acl: t.value}); await after('Clearance updated. Rebuild to apply it to claims.'); };
document.addEventListener('change', e => { if (e.target.matches('select[data-act="acl-src"]')) ACT['acl-src'](e.target); });
ACT['read-src'] = t => inspectSource(t.dataset.sid, -1, 'manager');
ACT['del-src'] = async t => { await A.delSource(t.dataset.sid); await after('Source deleted'); };
ACT['paste-add'] = async () => { const s = await A.addSource({name: $('#pn').value || 'notes/pasted.md', text: $('#pt').value, acl: $('#pa').value, origin: 'pasted text'}); sfx('ok'); await after(`Added ${s.id}: ${s.lines} lines${s.redactions ? `, ${s.redactions} secrets masked` : ''}`); };
ACT['gh-add'] = async t => { t.disabled = true; try { const r = await A.github({repo: $('#gr').value, token: $('#gt').value || null, acl: $('#ga').value}); sfx('ok'); await after(`Imported ${r.info.items} items from ${r.info.repo}`); } finally { t.disabled = false; } };
