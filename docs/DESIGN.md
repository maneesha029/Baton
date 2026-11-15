# Baton — design plan

## What is actually hard
Knowledge handover is a trust problem. Summaries are cheap; knowing *which statements are safe to rely on and who may see them* is hard. The core insight: model handover as an **append-only ledger of cited claims** with a trust state, a clearance level and a human decision on each.

## Experience map ("forensic lab")
One persistent WebGL scene is the backdrop for every screen and docks into the Map tab, so the 3D graph is the same object the user has been watching grow.

```
┌ top: BATON · case chip · Tour · [Guest|Developer|Manager] · readiness ring · ⌘K · sound ┐
│ rail │                      stage (glass panels over live scene)                     │
│ 1 Connect   Evidence wall: source cards, ACL labels, drop / paste / GitHub           │
│ 2 Rebuild   Pipeline theatre: 5 stages with server timings, scene grows from ledger  │
│ 3 Verify    Ledger: state tiles, side-by-side conflicts, testimony, interview mode  │
│ 4 Review    Keyboard deck: → approve ← reject ↑ edit Z undo, confidence factors      │
│ 5 Handover  Briefing (plan buckets, radar, who-knows-what) + cited Q&A + receipt     │
│ ◉ Map       Docked 3D graph, type filter, timeline replay, departure simulator       │
│ ⛓ Audit     Hash-chain blocks, verify sweep, forge-a-block                            │
└ next-best-action bar: always one concrete next step ─────────────────────────────────┘
```
Right-hand paper **inspector** shows the exact cited line with its neighbours, as an evidence sheet under a lamp.

## Visual language
Dark glass over a living scene; rubber-stamp trust states (VERIFIED green, INFERRED amber, CONFLICT red, MISSING grey, TESTIMONY violet); redaction = diagonal stripes, in both the 2D UI and on 3D nodes; clearance change = iris blackout. Space Grotesk / JetBrains Mono / Special Elite.

## Key decisions and tradeoffs
- **Server is the only permission authority.** Restricted claims in the graph are `{id, kind, restricted}` — no label, no text. Chosen over client-side hiding because DevTools exists.
- **LLM proposes, code disposes.** The verifier mechanically checks every citation; LLM failure degrades to rules, never breaks reconstruction.
- **Idempotent reconstruct** with fingerprint drift, because evidence changes after people approve things.
- **No build step.** ES modules + importmap + vendored three r160; the judges' setup is `pip install` and `make run`.
- **Single process** serves API and UI, so one container deploys it.

## Breaks at scale
SQLite global connection + lock (single writer); BM25 recomputed per question; graph layout is O(n²)-ish and tuned for hundreds of nodes; no auth/tenancy; rule engine needs per-domain ontologies.
