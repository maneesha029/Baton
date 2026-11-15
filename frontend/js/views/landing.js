import {$, esc, S, A, ACT, api, setCase, refresh, toast, sfx, STATES} from '../core.js';
import {go, chrome} from '../main.js';
import {startTour} from '../tour.js';

export function enter(el) {
  const c = S.case;
  el.innerHTML = `<div class="hero">
    <div class="eyebrow">Team ZeroShift · Round 2 build</div>
    <h1>When someone leaves, <span class="grad">knowledge shouldn't.</span></h1>
    <p class="lead">Baton rebuilds a project from scattered evidence, makes a human verify every claim, and hands over only what the successor is cleared to see. Every statement cites the exact line it came from. Nothing is shared until it is approved.</p>
    <div class="row">
      <button class="btn xl" data-act="start-demo">Start the demo case</button>
      <button class="btn xl ghost" data-act="tour">▶ 90-second tour</button>
      ${c ? `<button class="btn xl ghost" data-act="go" data-r="connect">Continue ${esc(c.id)}</button>` : `<button class="btn xl ghost" data-act="start-empty">Empty case</button>`}
    </div>
    <div class="tiles4" aria-label="The four trust states">
      ${[['VERIFIED', 'authoritative or 2+ sources'], ['INFERRED', 'one source, needs a human'], ['CONFLICT', 'sources disagree'], ['MISSING', 'asked of the leaver']].map(([s, d]) => `<div class="tile ${s}" title="${d}"><b>●</b>${s}</div>`).join('')}
    </div>
    <div class="how">
      <div><b>1 Connect</b>repo, notes, tasks, chat, docs with access labels</div><div><b>2 Reconstruct</b>claims extracted, every citation re-read</div>
      <div><b>3 Verify</b>conflicts side by side, gaps asked of the leaver</div><div><b>4 Review</b>approve, edit or reject, versioned and hash-chained</div>
      <div><b>5 Handover</b>role-redacted briefing, first-week plan, cited Q&amp;A</div>
    </div>
    <p class="mono sm mut">${S.llm ? '● Claude-assisted extraction is ON (every proposal is still citation-checked).' : '● Deterministic engine. No API key needed. Set ANTHROPIC_API_KEY to enable Claude-assisted extraction.'} · All demo data is synthetic.</p>
  </div>`;
}

async function create(demo) {
  const j = await A.newCase(demo, demo ? undefined : 'My case'); setCase(j.case.id); await refresh(); sfx('ok'); chrome(); go('connect');
  toast(demo ? 'Demo case "Kestrel Pay" loaded' : 'Empty case created. Add your evidence.');
}
ACT['start-demo'] = () => create(true);
ACT['start-empty'] = () => create(false);
