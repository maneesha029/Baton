import {S, A, ACT, setCase, refresh, caption, sleep, toast, sfx} from './core.js';
import {go, setRole, chrome} from './main.js';

let live = false;
export async function startTour(stop) {
  if (stop === true || live) { live = false; caption(null); return; }
  live = true; const say = async (t, ms = 2600) => { if (!live) throw 0; caption(t, true); await sleep(ms); if (!live) throw 0; };
  try {
    await say('Tour: every step below calls the real API. Nothing is mocked.', 1800);
    const j = await A.newCase(true); setCase(j.case.id); await refresh(); chrome(); go('connect'); await say('1/8 Evidence from five sources. One chat export is CONFIDENTIAL and had a secret masked before storage.');
    go('reconstruct', {run: true}); await say('2/8 Reconstruct: every claim is re-read against its cited line. Unsupported ones are dropped.', 5200);
    go('verify'); await say('3/8 Three conflicts (database, hosting, deploy ownership). Both sides stay visible; Baton never picks silently.', 3600);
    const c = S.claims.find(x => x.state === 'CONFLICT' && x.variants);
    if (c) { await A.review(c.id, {action: 'resolve', choice: c.variants[0]}); await refresh(); await say('A reviewer resolved one conflict. The decision is versioned and hash-chained.', 2200); }
    await A.bulk(); await refresh(); go('review'); await say('4/8 Review deck: VERIFIED claims approved in bulk; the rest need a human (→ approve, ← reject).', 3200);
    for (const k of S.claims.filter(x => x.status === 'pending' && x.state !== 'CONFLICT' && x.state !== 'MISSING')) { await A.review(k.id, {action: 'approve'}); }
    await refresh(); go('handover'); await say('5/8 Handover as DEVELOPER: confidential items appear only as a count.', 3400);
    await setRole('guest'); await sleep(900); await say('Guest clearance: less content, same server-side rule. Preview as Manager to compare.', 2600);
    await setRole('manager'); await sleep(900);
    go('map'); await say('6/8 The map: orbit it, replay the timeline, simulate a departure to see what is orphaned.', 3400);
    go('audit'); await say('7/8 Audit chain: forge an entry and watch the verifier catch it.', 3000);
    await say('8/8 That is Baton: evidence-linked, human-approved, permission-aware.', 2400);
  } catch (e) { if (e !== 0) toast(e.message || 'Tour stopped', true); }
  live = false; caption(null);
}
