# SignalForge → GammaSummit Knowledge Transfer

Latest AI-authored work found in `SignalForge/docs/` (swept 2026-09-30). This
file indexes + distills what matters for the new build; SignalForge docs remain
the detailed source until ported. Everything here is **feature knowledge to
carry into gammasummit**, not nostalgia.

## 1. Feature work in flight → our parity workstream

**`SKYLIT_FEATURE_COPY_PLAN.md`** — the feature-copy matrix (capabilities +
math, own names/styles/weights — same IP stance as our parity checklist).
State at 2026-09-24:

| Feature | State | Wave |
|---|---|---|
| Heatmap GEX mode (`gamma×100×0.01×OI×S²`) | done | — |
| Heatmap **VEX mode** (`vanna×100×0.01×OI×S×IV`) | missing | W1 |
| GEX+VEX combo + **Derived mode** (flow_exp model) | missing | W1 |
| Flow-weighted exposure `flow_exp` (fit 2026-09-24 FIT_REPORT) | column built `11091ab1`, unsurfaced | W1 |
| Node classification (king/wall/gatekeeper/significant — own names) | partial (king rows) | W1 |
| 7 color themes + ink switch (RE §8 exact stops) | single theme | W1 |
| Further waves | see file | W2+ |

→ Feeds directly into UltraPlan P0/P4. Formula ground truth:
`SKYLIT_REVERSE_ENGINEERING.md` (already integrated in our docs).

## 2. Flow Alert Quality Loop (new system, live 2026-09-30)

`docs/flow-alert-quality-loop.md`. Four stages: **wide net → track outcomes →
research filters → alert**, loop closes weekly.

- `flow_outcome_tracking`: 28,939 alerts backfilled, outcomes marked from
  Leandata minute bars (+5/15/30m, EOD, MFE/MAE, `hit_50_30m`/`hit_2x_eod`)
- `flow_scores` (28,939 events: direction, flow_score, sweep, premium, size,
  sub-scores) + `flow_tide_5m` — spec `docs/FLOW_SCORE_SPEC.md`
- **Measured truths:** raw stream ~25% win @30m, only 0.5% hit +50%/2x →
  selection is everything. Best filter family = **puts in last hour (2.7% =
  13× lift)**; puts > calls; premium ≥$50k alone = no lift. Filters must pass
  week-split stability check.
- Rules: wide net NEVER narrowed at ingestion; outcomes marked externally (no
  marking our own homework).

→ GammaSummit Flow module = this loop as product (flow feed + score columns +
outcome labels + researched filters surfaced in UI/AI Analyst).

## 3. SPX close-window strategy research

`docs/strategy-research-method.md` + `docs/SPX_CLOSE_WINDOW_PLAYBOOK.md` +
`docs/spx-close-window-position-sizing.md`.

- Method: mechanism questions → hypotheses → **walk-forward mandatory** →
  random-day replay floor → rejection log (never re-test dead theories).
- Lead rule v3 (walk-forward verified): 15:50–15:55 buy contract AT window-low
  break on 4× flood volume, premium ≤$0.50, ≤20 pts from flood cluster → sell
  halves +50%/+100% → hard exit 15:58. Test-2026: +39.3% mean, 72% win (n=18).
- Pin mechanics (n=256): pin is a soft magnet (5 pts = 36%, 10 pts = 64%);
  **reshuffle real** (cluster→settle converges 9.9→7.6 pts into close);
  cluster migration predicts settle side 65–67% (paper-trade only).
- Rejection ladder documented (ladder scale-outs overfit, 50% stops cost 17pts,
  hold-to-expiry −35%, earlier entries = wrong instinct).

→ GammaSummit AI Analyst "Read" + research/replay features build on this; the
rejection log ships with it.

## 4. Ops lessons → data machine requirements

`docs/flow-feed-ops-notes.md` (2026-09-30 incident):

- **Freshness = payload timestamps advancing, NOT rows being written** (a
  vendor freeze looked alive for days). → our freshness metric must compare
  payload `created_at` max vs now, not row counts.
- Verdict mapping (vendor freeze vs ingest down vs cron dead vs scorer dead) —
  explicit alarm states, never let vendor freeze masquerade as our bug.
- "0 rows saved, 0 errors" is a bug report — upsert dedupe bugs swallowed
  duplicate-key failures for months (`on_conflict=""` class).
- Monitor: endpoint-level health (UW paid API dead since June while free
  endpoint kept working; free endpoint froze 09-28).

→ Directly feeds `operations.md` playbooks + the freshness NFR in
master-architecture §10.

## 5. Stack registry + cost directive

`docs/STACK_REGISTRY.md` — adopted tools: **sourcebot** (cross-repo code
search, localhost:3100), **duckle** (UW ETL pipelines on VPS, 30 pipelines),
**UW data fleet** (24 light PHX datasets → Supabase `uw_*`; 5 heavy datasets →
parquet archive `X10 Pro/SignalForge Archive/uw-archive/` via Mac launchd),
wal-g deferred.

**User cost-split directive (validated by our tiering):** "Supabase = web-product
only; heavy history (candles_1m/daily, greek_flow, net_flow_second, periscope)
→ parquet on X10." = exactly our T0–T3 plan. The 5 heavy UW datasets are the
seed list for `gammasummit/t3/` imports.

## 6. NOT gammasummit (leave behind)

- `RECEIPT_SPEC.md` — LifeLedger personal-receipt lane
- `DRIVE_OVERHAUL_PLAN.md` — Google Drive cleanup (read-only proposal)
- `NEXT_SESSION_BRAIN_BUILD.md`, `PHASE5_BRAIN_ACTIVATION_PLAN.md` — brain lane
- `EMAIL_TRIAGE_SPEC.md`, `AGENT_PROFILES_PROPOSAL.md` — other lanes

## Carry-over queue (into UltraPlan phases)

| Item | Phase |
|---|---|
| VEX + GEX+VEX + Derived modes, node tiers, 7 themes (copy-plan W1) | P0 spec / P4 build |
| flow_exp surfacing (built, unsurfaced) | P4 |
| Flow quality loop as product (scores, outcomes, filters) | P4/P2 data |
| Freshness = payload-ts + verdict alarms | P2 |
| UW heavy-dataset parquet import → `gammasummit/t3/` | P2 |
| Close-window research + rejection log as AI Analyst knowledge | v2 |
