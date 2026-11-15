**Live demo: https://baton-meoi.onrender.com** (free tier: first load can take ~50 s to wake)

# Baton â€” evidence-linked knowledge handover

**Headline: when someone leaves, Baton rebuilds what they knew from the evidence, makes a human verify every claim, and hands over only what the successor is cleared to see. Every statement cites the exact line it came from.**

Team ZeroShift Â· Round 2 full-stack build. Everything below runs from this repo with no API key.

## The insight

Handover tools fail in two ways: they summarise confidently (hallucinated "knowledge") and they leak (the successor sees what they shouldn't). Baton treats handover as an **evidence ledger** problem, not a summarisation problem.

1. **A claim is only real if a re-read of its cited line supports it.** Extraction (rules, or an optional LLM) only *proposes*. A verifier re-reads the stored line and drops anything unsupported. The LLM never assigns trust.
2. **Disagreement is data.** Two sources disagree â†’ `CONFLICT`, both sides kept, a recency *hint* shown, a human decides.
3. **Permissions are enforced on the server, per read.** Restricted items reach the browser as counts or opaque placeholders, never as content. A test asserts the guest/developer JSON never contains the confidential strings.
4. **The leaver's word is testimony, never `VERIFIED`.**

## 2-minute judge path

1. Open the app â†’ **Start the demo case** (synthetic company "Kestrel Pay").
2. **Reconstruct.** Watch the pipeline run with server-measured timings.
3. **Verify.** Three conflicts (PostgreSQL vs MongoDB, Render vs Heroku, deploy-script ownership) shown side by side with the quoted lines. Click any citation to read the source line. Open **Interview mode** and answer a gap.
4. **Review.** `â†’` approve, `â†` reject, `â†‘` edit, `Z` undo. Approving a conflict is refused until resolved.
5. **Handover.** Flip the **Guest / Developer / Manager dial** and watch content disappear (iris blackout). Ask the Q&A terminal about the vendor price as Guest â€” it refuses and only says matches exist above your clearance.
6. **Map.** Orbit the 3D graph, replay the timeline, click **â€œif asha leavesâ€** to see what becomes orphaned.
7. **Audit.** *Forge an entry* â€” the verifier fails at exactly that block (run on a copy, nothing is written).

Shortcut: the **â–¶ Tour** button runs this whole path against the live API. `âŒ˜K` opens a command palette.

**The memorable capability:** departure simulation on a permission-aware 3D knowledge graph, where redacted nodes exist as striped opaque placeholders with no label or text in the payload.

## Architecture

```
                 browser (no build step, ES modules)
  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
  â”‚ views: landing connect reconstruct verify review handover    â”‚
  â”‚        map audit tour      Â·  three.js scene (bloom, GLSL)   â”‚
  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–²â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                  â”‚ JSON (role is a query param; see limits)
  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ FastAPI â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
  â”‚ services: cases ledger analysis handover qa audit            â”‚
  â”‚   ledger.view(case, role)  â† the ONE permission gate         â”‚
  â”‚ engine:  parsers â†’ extract (rules | LLM) â†’ verify â†’ trust    â”‚
  â”‚          â†’ contradictions â†’ persist (idempotent, drift)      â”‚
  â”‚ ingest:  files, paste, GitHub API (commits + issues)         â”‚
  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–²â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                  â”‚ sqlite3 (cases, sources, claims, versions,
                  â”‚ testimony, resolutions, acks, audit hash chain)
```

Pipeline: every source â†’ canonical lines `[date] @author: body` (secrets masked **before storage**) â†’ claim candidates with citations `(source, line)` + required substrings â†’ verifier re-reads the stored line â†’ trust state â†’ contradiction detection â†’ persisted idempotently.

### Trust states
| State | Rule |
|---|---|
| VERIFIED | authoritative task-board record, or â‰¥2 independent sources agree |
| INFERRED | one source; needs a human |
| CONFLICT | different values or owners across sources (cannot be approved until resolved) |
| MISSING | open question or no owner (becomes an interview question) |
| TESTIMONY | the leaver's answer; never promoted to VERIFIED |

Confidence is a sum of explainable factors shown in the inspector.

### Permissions
Source labels `public < team < confidential`; roles `guest < developer < manager`. A claim's level is the **max** of its cited sources. Handover, Map, Q&A, exports and the inspector all go through `ledger.view`.

### Other mechanisms
- **Idempotent re-reconstruct:** approvals, edits, resolutions and testimony survive. If an approved claim's evidence fingerprint changes it becomes `drifted` and re-enters review.
- **Audit:** per-case SHA-256 hash chain, verify endpoint, non-persisting tamper test.
- **Q&A:** BM25-style retrieval over *approved, visible* claims only; refuses without a citation. Optional LLM phrasing is accepted only if every cited id is valid, else falls back to extractive.
- **Bus factor / departure simulation:** NetworkX over personâ€“claim and claimâ€“claim dependency graphs.
- **Readiness** = 40% claims reviewed + 25% conflicts resolved + 20% gaps answered + 15% receipt acknowledged.

## Run

```bash
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
make run            # â†’ http://localhost:8000  (FastAPI also serves the frontend)
make test           # 27 tests
```
Docker: `docker build -t baton . && docker run -p 8000:8000 baton`. Render: `render.yaml` included (one web service).

| Env | Meaning |
|---|---|
| `ANTHROPIC_API_KEY` | enables Claude-assisted extraction and Q&A phrasing (every output is still citation-verified) |
| `BATON_MODEL` | model id (default `claude-sonnet-5-5`) |
| `BATON_LLM=off` | force the deterministic engine |
| `BATON_DB` | sqlite path (default local file) |
| `BATON_FRONT` | frontend directory override |

## Honest limits (read before judging)
- **No authentication.** The role dial is a *preview-as* clearance sent as a query parameter. Redaction is enforced server-side, but anyone can request `role=manager`. Real deployment needs SSO and server-derived roles.
- **The Claude API path was tested only against a stubbed client**, not the live API. The deterministic engine is what the demo and tests exercise.
- Rule extraction is ontology/regex based (databases, hosting, CI, queue, auth, owners, dates, risks). It is precise on the demo data and conservative elsewhere; it will miss claims in free-form prose.
- Retrieval is BM25-style, not embeddings (pgvector was in the Round 1 plan). SQLite replaces a hosted Postgres. Both are deliberate scope cuts for a self-contained judge-runnable repo.
- The audit chain is tamper-evident, not tamper-proof: someone with DB write access can rebuild it. Pin the head hash externally.
- Verified in a headless Chromium click-through of every screen and the tour, with no JS errors. Not tested on Safari/Firefox, real GPUs, or touch devices; the mobile layout is basic.
- GitHub import needs outbound access to `api.github.com` and was tested with a mock transport.
- Demo data is synthetic; the demo secret `sk_live_â€¦` is fake and is masked at ingest.

See `docs/DESIGN.md` for the layout and design rationale.

