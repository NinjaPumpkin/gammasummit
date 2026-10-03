# KICKOFF.md — hand GammaSummit to a fresh Hermes session

Give this file to a new session. It says what to build, how to run the build
with `/botmode` + `/kanban` + subagents + bot profiles, and where the specs are.

---

## 0. Orient (5 minutes)

- Repo: `~/Desktop/Github-Projects/gammasummit` (git, planning complete).
- Read first: `docs/build/README.md` (builder guide) → `docs/build/code-structure-and-release.md`
  → `docs/build/ultraplan.md` (phases P0–P5, workstreams A–F).
- Status (2026-10-01 owner ruling): **build proceeds in parallel with P0
  calc-parity work.** P0 gate (`docs/build/p0-acceptance-report.md`) is NOT
  signed (oracle bound: weight-model class tops at 68.6% king exact — see
  `docs/build/e05b-king-parity.md` §5) and remains the cutover milestone with
  bars honest (king exact ≥90% over ≥20 session-days, node error ≤10%).
  Owner priorities: (1) keep collecting Skylit + UW + leandata data,
  (2) RE Skylit per-cell gamma-heatmap calcs from UW extraction until very
  close (goal card E0.6), (3) build out the project meanwhile (E1+ unblocked).
- Hard rules (violating = wrong): clean-room calcs (no SignalForge code copies);
  `--dry-run` default for destructive ops; frontend → API only (no DB keys in
  browser); secrets never in git/chat; never write to SignalForge prod;
  Skylit API = temporary RE tool (sub ends ~Nov 2026), production runs UW-only;
  **UW PHX is the ONLY production data source going forward (source of truth) —
  Skylit + leandata = RE/reference/backtest archives only** (owner 2026-10-02);
  **rate limits are NEVER hit on any source** (≤50%-of-limit pacing with jitter,
  backoff + cooldown on any rate signal, daily caps, incident comment + pause).

## 1. Bot profiles (the team)

Profiles = isolated Hermes instances (own config, skills, memory). Discover
first — never invent names (kanban dispatcher silently drops unknown assignees):

```bash
hermes profile list
```

If the build team doesn't exist yet, create it (clone for config parity):

```bash
hermes profile create gammasummit-pm       --clone   # orchestrator
hermes profile create gammasummit-backend  --clone   # FastAPI/core/ingest/jobs
hermes profile create gammasummit-frontend --clone   # Vite+React parity UI
hermes profile create gammasummit-research --clone   # RE/fit/analysis
# CRITICAL pitfall — every new profile needs credentials copied or 401s:
cp ~/.hermes/auth.json ~/.hermes/profiles/<name>/
cp ~/.hermes/.env      ~/.hermes/profiles/<name>/
```

Profiles must also be **Bot-Mode-managed**: `ui_meta['hermes-bots']` in each
profile.yaml (desktop: profiles UI; CLI: edit profile.yaml). Toggle
`agent.bot_mode_protocol: true`.

## 2. /botmode — teammate messaging (the daily driver)

Bot Mode gives each bot a canonical **"Bot Chat"** session with a
`message_agent(target, message)` DM tool — fire-and-forget, reply arrives as a
completion notification. Only the "Bot Chat" session carries the protocol.

```bash
hermes -p gammasummit-pm chat -c "Bot Chat"          # open PM's bot chat
hermes -p gammasummit-backend chat -c "Bot Chat"     # open backend bot's chat
# transport under the hood (do not run manually):
#   hermes -p <name> chat --in ~ -c "Bot Chat" --create-if-missing -Q --query-file <tmp>
```

**How we use it on this build:** PM bot decomposes and DMs specialists
(`message_agent(target="gammasummit-backend", message="card t_12 ready:
implement db/migrations/0001…")`); specialists report back + escalate blockers
the same way. Human (owner) interjects anytime in any Bot Chat.

## 3. /kanban — the durable board (work that must survive crashes)

In any session: `/kanban` or `hermes kanban`. Board = SQLite, auditable.

```bash
hermes kanban init                                   # once per machine
hermes kanban create "P0: fit cross-expiry layer" --assignee gammasummit-research
hermes kanban create "P1: migrations 0001 schema" --assignee gammasummit-backend
hermes kanban list | show <id> | comment <id> | complete <id> | block <id> "why"
hermes kanban link --parent <research-id> --child <backend-id>   # parent first!
```

Rules that matter:
- **Orchestrates, don't execute:** PM profile routes every concrete task as a
  card. Independent lanes = parallel cards; data deps = `parents=[...]`.
- **Goal-mode cards** for multi-turn work (e.g. "port heatmap UI to 34/34
  parity checklist"): `goal_mode=True`, body = explicit acceptance criteria —
  the judge re-checks each turn.
- **Worker lifecycle:** orient (read body + `kanban_show`) → work → heartbeat
  with real progress ("12/34 parity items") → `kanban_complete` (summary +
  metadata: changed_files, tests_run) or `kanban_block` (actionable question).
- **Block well:** bad "stuck"; good = full context + a concrete decision request.
- Dispatcher (runs in gateway) claims `ready` cards and spawns the assigned
  profile. Stuck worker → `hermes kanban reclaim <id>` / `reassign <id> <profile> --reclaim`.
- Coding lanes may use the **Codex lane** pattern (worktree + `codex exec`) —
  see the `kanban` skill; Hermes owns lifecycle, tests, and acceptance always.

## 4. Subagents — quick fan-out (`delegate_task`)

Use for bounded parallel subtasks that finish in minutes: research reads,
doc distillation, test batches, comparisons. Pattern: `delegate_task(tasks=[…])`
(one entry per child; up to 10 parallel), each with self-contained goal +
context + output schema. Children know nothing — pass paths and constraints.
For anything that must outlive the session → kanban card or cron, NOT delegate.

Long autonomous code missions: spawn real instances (`hermes -w` worktree mode
inside tmux) — see `hermes-agent` skill "Spawning Additional Hermes Instances".

## 5. The build plan as card graph

| Epic | Cards (first pass) | Assignee | Depends on |
|---|---|---|---|
| E0 P0 gate | fit cross-expiry layer vs 1s range frames → `backend/core/exposure.py` + acceptance report | research | — (RE data on X10 `gammasummit/t3/re/raw/` already captured) |
| E1 scaffold | repo CI (ci.yml: lint/tests/migration-lint/contract-sync/gitleaks), GitHub repo public, Vercel wiring | backend | E0 sign-off |
| E2 data | migrations `0001` partitioned schema, ingest writers, rollups+retention jobs, freshness alarms | backend | E1 |
| E3 API | FastAPI routers + schemas + SSE, p95<200ms | backend | E2 |
| E4 heatmap UI | parity shell → 34/34 checklist (goal-mode) | frontend | E3 (mocks in `frontend/mockups/dashboard-v3.html` allow early start) |
| E5 modules | Flow, Vol (Tempest), Charts (Atlas-class) | frontend+backend | E3 |
| E6 AI | doctrine wiring, Jev adapters, analyst scaffolds | research+backend | E3 |
| E7 cutover | offboarding checklist (`docs/ops/offboarding-signalforge.md`) | pm+backend | all |

Create cards lazily per epic — not the whole graph up front.

## 6. Done = verified

Never declare done on plausible output: tests run, checklist items marked with
real evidence, acceptance column in `docs/build/README.md` met. Every RE/fit
number must come from a real script run on real data. Report blockers honestly.

## 7. First 5 moves for the new session

1. `cd ~/Desktop/Github-Projects/gammasummit && cat docs/build/README.md`
2. `hermes profile list` (verify/create team + copy auth.json/.env)
3. `hermes kanban init && hermes kanban list`
4. Open `hermes -p gammasummit-pm chat -c "Bot Chat"` → decompose E0/E1 into cards
5. Kick E0: RE data is on X10; the fit notes are in `docs/build/skylit-value-model.md`
   (verdicts 1–4) — the cross-expiry dynamic layer is the target.
