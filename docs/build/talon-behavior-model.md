# Talon AI analyst — behavioral RE model (E0.9)

Behavioral reverse-engineering of Skylit's Talon AI analyst from observable web
session behavior (acct lapcheong, app.skylit.ai/talon, 2026-10-02 13:43–14:07
PT / 16:43–17:07 ET, after hours). Every claim below cites probe records in
`data/e09/probes.jsonl` (`[P01]`…`[P12]`, plus `[P06-card]`). Tags: `[observed]`
= seen in a probe record verbatim; `[derived]` = inferred from observations
(arithmetic checks marked inline). Academy doctrine is tagged `[academy]` only
where referenced from `docs/re/skylit-academy/` — never blended untagged.

Scope note: gentle probing only — 12 queries, ≥80 s between queries, no
prompt-injection, no system-prompt extraction attempts. Feeds
`docs/architecture/talon-ai-framework.md` (framework) and the E0.7
ticker-selection model (scan/gate mechanics).

## 1. Probe inventory

| ID | Query (verbatim) | Response class | Latency label | Record |
|---|---|---|---|---|
| P01 | What's the read on SPXW right now? | T1 verdict + trade-map card | Read 2 sources · 3s | P01 |
| P02 | Give me the structure read on SPY | T1 verdict + trade-map card | Read 2 sources · 23s | P02 |
| P03 | What's the riskiest part of this setup? | T2 prose (context-only) | Answered in 6s | P03 |
| P04 | Should I buy calls on SPXW right now? | T4 refusal-then-ground | (tool read implied by scan cite) | P04 |
| P05 | What do you see? | T2 prose w/ assumption statement | Read 1 source · 9s | P05 |
| P06 | Which tickers should I be watching tomorrow? | T3 scan report | Read 3 sources · 14s | P06, P06-card |
| P07 | read QQQ | T1 verdict + trade-map card | Read 2 sources · 23s | P07 |
| P08 | What's the gamma picture on IWM? | T2 prose (deep numeric) | Read 1 source · 7s | P08 |
| P09 | read PLTR | T1 verdict + trade-map card | Read 2 sources · 2s | P09 |
| P10 | read SOFI | T1 verdict + trade-map card | Read 2 sources · 5s | P10 |
| P11 | What data are these levels based on? | T2 prose (provenance) | Answered in 6s | P11 |
| P12 | read SPXW (23 min after P01) | T1 verdict + trade-map card | Read 2 sources | P12 |

`[observed]` latency labels come in exactly two flavors: `Read N sources · Ns`
(tool-grounded) and `Answered in Ns` (conversation-context only — P03, P11).
Provenance is first-class UI: per-answer "as answered" feedback, "Follow
Results ON", scan results carry "Shared result, computed 268s ago" [P06-card].
Tool traces name their steps: "Building the SPXW trade map / Scanned 1 of 1
SPXW / Checking every level against the book" [P01].

## 2. Response templates

### T1 — verdict + trade-map card (analysis intent on a named symbol)

Chat line, one line, exact shape `[observed P01,P02,P07,P09,P10,P12]`:

    SYM · <setup name> · <Bullish|Bearish> · <status>

status observed: `OTE Watch` (P01,P09,P10,P12), `Watchlist` (P02,P07). Then a
"Trade map · SYM setup" receipt button that opens the full card in the Canvas
pane, plus 2–3 follow-up chips (`Full read on SYM`, `Mark these on the chart`
or symbol-specific).

Card schema `[observed P01,P02,P07,P09,P10,P12]`:

    SYM setup
    Snapshot <YYYY-MM-DD HH:MM:SS ET>
    <N> names · <tier> · lean <bullish|bearish> — <n> bullish, <n> bearish ·
      risk posture <risk-on|risk-off> — …
    <REGIME HEADLINE IN CAPS>            e.g. STRUCTURE WITHOUT A QUALIFYING ZONE
    <one-line regime gloss>
    SYM  $spot  +$chg (+pct%)
    <setup name>
    ● <Bullish|Bearish> · <status>
    OTE $x            Invalidation $y         R:R (OTE) r.r:1
    Short-term AOI
    $target <exp> GEX · <r.r>:1 OTE
    Invalidation is a structural acceptance boundary; no protective-stop
      trigger is specified.
    TAKEAWAY
      Highest Entry Efficiency      SYM (0.43; 0.2% from OTE)
      Highest Entry Uplift          SYM (2.3x — 1.0:1 at the $7,705 OTE)
      Tightest decision band        SYM (0.6% between …; spot at 0.39 of the band)
      Strongest book lean           SYM (48.1x directional VEX exposure)
      Most extended from structure  SYM (0.2% from OTE)
    ADDITIONAL STRUCTURE
      Status  Watch <reason>
      Best Entry · OTE / Breakout Hold / Retest / Adverse-node checkpoint
      Structural Invalidation  $y accept <below|above> listed-strike structure
      <bullets: gatekeeper, VEX barriers, counter-structure>
    RISK — THE OTHER SIDE
      <opposite-case steps + what invalidates the opposite case>
    STRUCTURAL READ
      Holding: …   Capping: …
      Weight: Whole-board absolute exposure: NN% above spot; NN% below.
        Distance-weighted, all supplied expirations, no tenor decay. This
        describes exposure location, not polarity or trade direction.
      [Participation: <date> traded 1.2x its normal volume, closing up 0.7%.]
      Read: <one-paragraph synthesis>
    Structural reference, not a recommendation. Levels describe dealer
      exposure in the book; a wick through one is not failure — acceptance
      beyond it is what changes the structure. Not financial advice. https://skylit.ai

Regime headlines observed: `STRUCTURE WITHOUT A QUALIFYING ZONE` (P01,P12),
`QUALIFIED STRUCTURE, SPOT OUTSIDE THE ZONE` (P02,P07). Note the stable
disclaimer idiom: **acceptance, not wicks** — repeated at card footer
[P01,P12], in risk text, and in the P08 prose ("a break of that level is what
confirms the rug rather than a wick through it").

### T2 — prose answer (follow-ups, risk, meta questions)

Dense 1–2 paragraph argument, no card `[observed P03,P05,P08,P11]`. Cites
specific strikes, signs, expiries inline ("$770 … negative-gamma accelerant …
that node is 0DTE so it's live today" [P03]). Follow-up chips are
context-aware and reference entities just discussed ("What's the flow at
$7,730?" [P05], "Is $283 still fresh today?" [P08]).

### T3 — scan report (universe / ticker-suggestion questions)

Receipt "Scan report · Covered Universe Scan → canvas" with method stamp
"Scan method: talon · talon-horizon-map-v2 · horizon: all" [P06]. Card
(P06-card, the second capture — authoritative):

    Covered Universe Scan
    Snapshot 2026-10-02 16:49:16 ET
    5689 requested names · 112 actionable · 118 strict watch · 240 supplemental ·
      4688 context watch · 463 unqualified · lean bullish — 405 bullish, 65 bearish
      of 470 viable maps · risk posture risk-on
    Cleared every gate: 230 (112 actionable · 118 watch) · One gate short: 240
    Listing the top 20 of each by R:R (--all lists every row; --top P90 keeps
      the 10% of books with the most exposure); 21 thin books under $250,000
      GEX king not listed (--min-exposure 0 shows them).
    Market structure — 5,621 books, whole board:
      GEX skew  73% ↑ above spot · 3,905 above · 719 balanced · 688 below
      VEX skew  57% ↑ above spot · 4,222 above · 527 balanced · 563 below
      GEX king  3,529 above spot (66%) · 1,779 below (34%)
      VEX king  4,092 above spot (77%) · 1,220 below (23%)
      Alignment both above 3,233 (61%) · both below 924 (17%) · misaligned 1,155 (22%)
    Evaluated 5621 of 5689; unavailable 68; not evaluated 0; showing 40 of
      5621 matching rows. Shared result, computed 268s ago.
    CLEARED EVERY GATE — ACTIONABLE (20 OF 112)   ← rows, sorted by R:R desc
    ONE GATE SHORT — MISSING A QUALIFYING ENTRY ZONE (2…)  ← second tier

Row schema: `SYM $spot | setup name | ● bias · tier | OTE | Invalidation |
R:R (OTE) | Short-term AOI $target <exp> GEX · r.r:1 OTE` — R:R N/A rows carry
no AOI [P06-card]. Top row: BNO 7.0:1 … bottom shown 2.0:1, then N/A rows.

### T4 — refusal-then-ground (advice requests)

"[Talon doesn't] make that call — that's a position decision, not a structural
read" [P04], immediately followed by the structural answer ("What the SPXW
book actually shows: …"). Never buy/sell/size/hold/exit — refuses the decision
only, never the analysis. Disclaimers are stacked three deep: chat footer
"Talon's analysis — not financial advice.", per-card footer, per-answer
"as answered" feedback loop [all probes].

## 3. Cited-data taxonomy

`[observed P11]` stated data basis verbatim: "the live options book — GEX
(gamma exposure) and VEX (vanna exposure) read per strike and expiry off the
full chain … dealer positioning inferred from open options structure,
refreshed intraday, timestamped … on this read. None of this is price-chart
technicals (pivots, moving averages) or order-flow premium."

| Layer | Data cited | Evidence |
|---|---|---|
| Raw | GEX + VEX per strike × expiry, full chain | P11 |
| Nodes | king (max exposure; "% of king" magnitudes), positive/negative gamma nodes, gatekeeper, accelerant, counter-structure, VEX barrier (signed vanna repulsion: "nets -65.78B of vanna above spot … on the upside that sign repels") | P01,P02,P07,P08 |
| Aggregate | whole-board absolute exposure % above/below spot ("distance-weighted, all supplied expirations, no tenor decay"), directional VEX exposure multiple ("48.1x"), GEX/VEX skew + king-side + alignment counts | P01,P02,P06-card |
| Session | prior session close, participation vs normal volume ("traded 1.2x its normal volume, closing up 0.7%") | P02,P07 |
| Time semantics | 0DTE flagged "live today" [P03], expiry stamps "10/5 GEX", "Dec 2026", per-read ET timestamps, "computed 268s ago" staleness stamp | P01,P03,P06-card,P11 |
| Explicitly excluded | price-chart technicals (pivots, MAs), order-flow premium | P11 |

`[derived]` **R:R (OTE) = distance(OTE → nearest AOI/target) ÷ distance(OTE →
invalidation)** — verified: P01 (7750−7705)/(7705−7660)=1.0 ✓; P02
(771−770)/(770−765)=0.2 ✓; P07 bearish (750−749)/(755−750)=0.2 ✓.

## 4. Decision framework reconstruction

**Setup classification** `[observed]` catalog (named in cards/scan): `Dip Then
Rip / VEX Ladder` (bullish), `GEX Reclaim Ladder`, `VEX Magnet Ladder`
(bearish or bullish), `Early Momentum Ignition`, `GEX Reversal Sniper`, `GEX
Ceiling Structure` (bearish), `GEX Floor + VEX Ladder` [P01,P02,P06-card,
P07,P09,P10]. `rug` = king positive node capped above, negative gamma
immediately beneath ("confirming a rug pattern … the $283 cap holds while
negative gamma directly beneath it accelerates any rejection lower" [P08]).

**Per-symbol map pipeline** `[observed]` (card field order, P01/P02/P07):
classify setup → bias → status (Watch/OTE Watch/Actionable) → OTE level →
invalidation (nearest listed-strike level; **percentage fallback when no
listed-strike gamma level sits close enough** [P11]) → R:R to nearest AOI →
support/capping read from spot-nearest ±gamma nodes → whole-board weight →
risk-on-the-other-side with opposite invalidation → synthesis.

**Gate model for scans** `[observed P04,P06-card]`:
- qualifying entry zone (structure must have a current-column entry; "one
  gate short" tier = missing qualifying entry zone)
- **R:R floor 1.5:1** ("the closest candidate graded only 0.8:1 reward-to-risk
  into $7,740, below the 1.5:1 floor, and the stated reason was structural R:R
  falling short, not direction" [P04])
- exposure floor: books under **$250,000 GEX king** excluded from listing
  (flag `--min-exposure 0` shows them) [P06-card]
- book viability ("470 viable maps" of 5689 names; 68 unavailable) [P06-card]
- output tiers: actionable (cleared every gate) > strict watch (qualified
  structure, spot outside zone) > supplemental > context watch > unqualified;
  one-gate-short called out separately [P06-card, P02]
- listing: top 20 per tier sorted by R:R desc; `--all`/`--top P90` flags leak
  the internal CLI contract [P06-card]

**Determinism** `[observed P01 vs P12]`: 23 minutes apart, identical
structure: OTE $7,705, invalidation $7,660, AOI $7,750/$7,770, gatekeeper
$7,750, VEX barriers $8,030/$8,160, holding $7,710 / capping $7,730. Only
aggregate drifts (book lean 48.1x → 48.9x). Cards are template + live reads,
not per-query improvisation. `[observed]` phrasing variance changes nothing:
"read QQQ" [P07] vs "Give me the structure read on SPY" [P02] produce the
same template.

**Ambiguity handling** `[observed P05]`: explicit assumption statement — "No
ticker is focused on this page right now, so I'll answer for SPXW since that's
what we've been reading." Named symbols override page context (P04 asked
about SPXW while page canvas showed SPY; answer was SPXW) [P04].

**UI context-injection** `[observed]`: page ticker + horizon (`Scalp`) + mode
(`Normal`) + view (`Fit`) ride in the canvas card header; selector buttons
`Balanced` (effort) and `Scalp` (horizon) visible in chat composer; horizon
selector is a popover trigger (`aria-expanded=true`) — automation could not
surface its options, so horizon-switched maps are untested [P12]. Command
chips: Ticker / Levels / Flow / Talon Read / Trinity. Slash commands and
deterministic reads documented in `talon-ai-framework.md` `[academy]`.

## 5. Refusal boundaries

1. Position decisions — buy/sell/size/hold/exit/when: refused by name
   ("that's a position decision, not a structural read"), then grounded in
   structure [P04]. No hedge, no "if you must" escape hatch observed.
2. Never a stop price: invalidation is repeatedly framed as "a structural
   acceptance boundary; no protective-stop trigger is specified" [P01,P02,P07].
3. Data outside its book: refused by exclusion — no chart technicals, no
   premium-flow claims [P11].
4. No probabilistic promises: language is lean/bias/watch, never
   "will"/"should go" [all probes].

## 6. Spec — GammaSummit AI Analyst scaffolds

Replicate (they are good engineering, clean-room re-derivation):

1. **Verdict line**: `SYM · setup · bias · status` — one glance answer before
   any prose [P01 et al.]
2. **Trade-map card schema** in §2 T1 — especially: OTE / invalidation / R:R /
   AOI quad; `RISK — THE OTHER SIDE`; `STRUCTURAL READ` with method footnote
   ("distance-weighted, all supplied expirations, no tenor decay" [P01]);
   acceptance-not-wicks idiom.
3. **Refusal-then-ground**: refuse the decision, answer the structure [P04].
4. **Provenance stamps everywhere**: `Read N sources · Ns` vs `Answered in
   Ns`, per-read ET timestamps, staleness stamps ("computed 268s ago")
   [P01,P06-card,P11].
5. **Gate + tier model for ticker scans**: actionable/strict-watch/supplemental/
   context/unqualified tiers with named reasons ("one gate short — missing a
   qualifying entry zone"), R:R-sorted, thin-book floor disclosed
   [P06-card, P04].
6. **Context-injection with explicit assumptions**: page ticker rides along,
   ambiguity resolved by stating the fallback [P05].
7. **Setup/pattern catalog with named geometries** (rug, gatekeeper,
   accelerant, counter-structure, VEX barrier) — adopt our own names per
   `talon-ai-framework.md` [academy], semantics re-derived here [P01–P08].

Do better (UW PHX = production source of truth):

1. **Outcome-verified doctrine**: every rule carries measured hit-rate from
   `flow_outcome_tracking`/node-touch scoring instead of "rule of thumb"
   (their disclaimer culture stops at structure; ours can carry evidence).
2. **Fallback disclosure as data**: Talon leaks percentage-fallback
   invalidation in prose [P11] — make it a typed field (`basis:
   listed_strike | pct_fallback`) on every level.
3. **Freshness as a first-class field**: "fresh/tested/delivered/spent" +
   node rate-of-change (`/why`) quantified, not just a follow-up chip [P08].
4. **Honest staleness**: surface scan cache age like "computed 268s ago"
   [P06-card] everywhere, including mobile single-UI.
5. **Horizon maps**: same symbol × {Scalp, Day, Swing, Position} proven
   different maps [academy]; our cards should stamp horizon and show the diff.
6. **Exposure floors configurable and shown** — adopt their `--min-exposure`
   transparency as default UI copy, not a CLI leak [P06-card].

## 7. Limits of this model

- 12 queries, one after-hours session; no intraday behavior, no Deep effort,
  no Prose/Concise toggle, no Trinity/Levels/Flow slash reads exercised
  (documented `[academy]` only).
- Horizon-switched reads untested (selector popover not automatable [P12]).
- Latency labels observed once each; caching behavior only seen via "Shared
  result, computed 268s ago" [P06-card].
- `[derived]` R:R formula verified on 3 maps (P01,P02,P07) — AOI choice rule
  ("nearest target above/below OTE") inferred, not stated.

Raw evidence: `data/e09/probes.jsonl` (14 records; P06-card second capture is
the authoritative scan card; first P06-card capture is a noisy chat slice kept
for audit).
