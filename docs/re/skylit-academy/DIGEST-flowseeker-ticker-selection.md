# Skylit Academy "Flowseeker" — ticker-selection / tradability doctrine extraction

Scope: all 10 files under `docs/re/skylit-academy/` (flowseeker-01…10), read-only, quotes verbatim ≤300 chars. Quiz stems are flagged as such (quiz options are not marked with correct answers in the source, so body text is treated as primary evidence). No inference beyond quotes.

**Headline honest finding first:** these 10 files contain **no ticker-universe screening model** (no liquidity/spread/sector/event screening criteria) and **no disclosed ranking formulas for Flow Compass or Flow Scanner**. What they do contain is (a) a per-print attention-sorting model (Flow Score, premium rank vs the ticker's own 20-day history, Vol/OI), (b) explicit trade-qualification gates (Trinity 3/3-or-2/3, R:R ≥ 3:1, midpoint exclusion, "weakens if" writability), and (c) the daily routine in file 10. Details below.

---

## flowseeker-01 — Flow After Structure: Where Flowseeker Fits

| # | Verbatim quote | Source | Testable rule | Cat |
|---|---|---|---|---|
| 1 | "We trade extremes. We avoid midpoints. A large print in the middle of a range does not create an edge that the structure doesn't have." | §3 "Charts, Then the Map, Then Flow" | A setup is tradable only at a range extreme (high/low node); mid-range locations are disqualified regardless of flow. | 2 |
| 2 | "At a **range low**, on a heavy node acting as a floor \| It lines up with the structure — possible confluence" | §3 table | A print only counts as confluence if its strike sits at a structural extreme (heavy node floor/ceiling). | 2 |
| 3 | "Charts form the thesis. Heatseeker confirms or challenges it. Flow is evidence — tested against both." | §3 blockquote | Read order is chart → map → flow; flow without a chart/map thesis cannot qualify a trade. | 2 |
| 4 | "A large print earns investigation. It does not identify a profitable trade." | §1 / endnote (repeats in all 10 files) | No premium-size threshold alone makes a ticker/setup tradeable. | 2 |
| 5 | "A **$1.4M** QQQ call print, filled at the ask. They buy calls immediately. Price turns lower within the hour." … "**Confluence:** none. … **Decision:** no trade." | §6 Case Study | Even a $1.4M ask-side call print is a no-trade when chart and map oppose it. | 4, 2 |
| 6 | "enough trading at a strike changes dealer exposure there, which is one of the ways the map **reshuffles**. But one print is not the map." | §4 "Flow Is Not the Map" | A single print never updates map-based qualification; only aggregate repositioning does. | 2 |

Quiz-stem-only mention (not body doctrine): "A trader enters a trade every time a print over $1M appears" is presented as a mistake stem (§3 quiz). No $1M threshold is asserted as doctrine anywhere.

## flowseeker-02 — Reading a Print

| # | Verbatim quote | Source | Testable rule | Cat |
|---|---|---|---|---|
| 1 | "**Premium = fill price × contracts × 100**" | §3 "Premium, Not Size" | Print size metric = fill × contracts × 100 (dollars). | 4 |
| 2 | "Size rewards cheap contracts traded in bulk; premium measures dollars actually committed — so lead with premium." | §3 | Rank prints by premium dollars, never by contract count. | 3 |
| 3 | "Ten thousand contracts at $0.05 is $50,000 — often less than a few hundred contracts nearer the money. Lead with premium." | §7 Mistake 2 | Contract-count-based ranking is invalid; e.g. 10,000 × $0.05 = $50K. | 4 |
| 4 | "**0–7 DTE** — this week: event activity, very short-term positioning / **8–30 DTE** — the classic window for positioning ahead of a move / **31+ DTE** — longer horizons, where hedging becomes more common" | §4 "Distance and Time" | DTE bands: 0–7 = event/weekly context; 8–30 = directional positioning window; 31+ = hedge-dominated. | 4, 5 |
| 5 | "**Moneyness** is the distance from spot as a percentage. $5 is about **0.86%** of a $580 stock and **2.5%** of a $200 stock. In Flowseeker, **positive means out of the money**, negative means in the money" | §4 | Moneyness = % distance from spot; sign convention +OTM/−ITM; normalize distance by spot (not absolute $). | 4 |
| 6 | "**Bid side** — below, at, or just above the bid / **Mid** — at the mid / **Ask side** — just below, at, or above the ask" | §5 "Side: Where the Fill Happened" | Side classification buckets: bid / mid / ask (definitional bands around touch). | 3, 4 |
| 7 | "Fills right at the edges say more than fills near the mid, and in a thin contract a patient buyer can fill at the bid." | §5 | Weight side reads by fill quality (edge > mid); thin contracts disqualify side reads. | 2, 3 |
| 8 | "**Ask side is not the same as bullish.** A put bought at the ask is a bearish first read." | §5 | Direction label = f(side × call/put); side alone never sets polarity. | 3 |
| 9 | "a trade the exchange later voided shows **struck through with a CANCELLED badge**. A cancelled print did not happen." | §2 "Identify the Contract" | Disqualifier: drop CANCELLED prints from all counts/scores. | 2 |
| 10 | "Distance is measured from spot **when the print filled**, not where price sits now." | §7 Mistake 1 | Compute moneyness against spot-at-execution, not current spot. | 3 |
| 11 | "2,000 contracts at $3.10 … **Premium:** 2,000 × $3.10 × 100 = **$620,000** … about **1.5% out of the money**" | §6 Case Study | Worked example values (SPY 590c, 12 DTE, spot 581.40): $620K premium ≈ 1.5% OTM. | 4 |

## flowseeker-03 — Sweeps and Multi-Leg Trades

Ticker-selection/universe content: **none** (contract-level print mechanics only).

| # | Verbatim quote | Source | Testable rule | Cat |
|---|---|---|---|---|
| 1 | "Prints on the same contract within **one second** are grouped into a single **sweep**, with the total contracts and total premium." | §2 "What a Sweep Is" | Sweep aggregation key: same contract (underlying+expiry+strike+type), 1-second window; aggregate contracts + premium. | 3, 4 |
| 2 | "A sweep is urgency. Treat it as a stronger clue than a single print — and still only a clue." | §3 "Urgency, Not Intent" | Priority weight: sweeps sort above single prints, but never auto-qualify a trade. | 3 |
| 3 | "You can show only sweeps with the **Sweeps Only** toggle in the Live Feed filters" … "**Multi-Leg Only** or **Single-Leg Only**" | §2, §4 | Feed filter flags exist: sweeps_only, multi_leg_only, single_leg_only. | 3 |
| 4 | "When a large print appears, look for other prints on the same ticker and expiry in the same moment before you name the trade." | §4 "One Leg Can Mislead" | Before scoring a large print, group same-ticker/same-expiry prints in the same second into structures. | 2, 3 |
| 5 | "detection is not perfect — not every strategy can be identified with certainty" | §4 | Multi-leg grouping is best-effort; ungrouped legs must not be treated as standalone direction. | 2 |
| 6 | "Net cost: $620,000 − $180,000 = **$440,000**" (590/600 bull call vertical) | §5 Case Study | Net premium of a detected vertical = bought-leg premium − sold-leg premium. | 4 | after5).

iffelf, by2'1ist":##toSC|
|1481300 |40 |

|,30# | "590 calls … 12 DTE" worked throughout as the canonical print | 4 |  |

## flowseeker-04 — Volume, Open Interest and What Changed

Ticker-selection content: only contract-level "worth a look" screen (Volume > OI).

| # | Verbatim quote | Source | Testable rule | Cat |
|---|---|---|---|---|
| 1 | "**Volume** — how many contracts **traded** today. … **Open interest (OI)** — how many contracts are **still open**, as of the last time trades were cleared." | §2 | Definitions: volume = today's traded contracts; OI = open contracts at last clearing (usually prior close). | 3 |
| 2 | "**Volume > OI** — contracts where today's volume is above open interest / **Size > OI** — single prints bigger than open interest" | §3 "Volume Above OI Is Worth a Look" | Contract screen 1: today volume > yesterday OI; screen 2: single-print size > OI. Both = "worth investigating", not proof. | 3, 4 |
| 3 | "When today's volume is bigger than yesterday's open interest, something unusual is happening at that contract." | §3 | Unusualness at contract level is measured relative to that contract's own OI. | 3 |
| 4 | "The OI you see during the day is usually **yesterday's** number. Today's trades show up in OI **tomorrow**." | §2 | Any OI-based rule must use OI-as-of-date; intraday OI is stale by one session. | 4, 5 |
| 5 | "Volume today: **1,000** — ten times the OI / Open interest tomorrow: still **100**" | §3 worked example | Volume/OI ratio up to 10× can occur with zero net position build (open-then-close same day). | 4 |
| 6 | "when OI **rises** the next day, more positions were opened than closed at that contract. That **supports** a read" | §4 "Next-Day OI Supports" | Confirmation rule: next-day ΔOI > 0 supports position-building read; ΔOI < 0 consistent with closing. | 3 |
| 7 | "**Yesterday's OI** on the 590 call: **1,200** / **Today's volume**: **2,400** … **Volume > OI**" … "OI … updates to **3,100** — up **1,900**" | §5 Case Study | Worked values: vol:OI = 2.0 flags the contract; +1,900 next-day ΔOI supports the read. | 4 |

## flowseeker-05 — Scores and a Readable Feed ★ (core ranking file)

| # | Verbatim quote | Source | Testable rule | Cat |
|---|---|---|---|---|
| 1 | "**Flow Score** … Runs from **−100 to +100** / Positive means classified **bullish**; negative, **bearish**; near zero, **unclear**" | §2 "Two Scores, Two Questions" | Print direction score ∈ [−100, +100]; sign = polarity, |value| = classification strength. | 3, 4 |
| 2 | "It draws on the Tier 1 clues — side, sweeps, moneyness, DTE and premium — plus implied volatility" | §2 | Flow Score feature set: side, sweep flag, moneyness, DTE, premium, IV (weights undisclosed). | 3 |
| 3 | "The **Premium vs Ticker History** filter ranks a print's premium against that ticker's own trades over the last 20 days — a $1M print is routine on SPY and rare on a quiet name" | §2 | Print unusualness = percentile of premium within the same ticker's trailing 20-day print history (per-ticker normalization). | 1, 3, 4 |
| 4 | "A high **Vol/OI** says today's activity is large relative to open interest. … Neither says anything about direction." | §2 | Unusualness metric 2 = Vol/OI ratio; orthogonal to direction. | 3 |
| 5 | "You may also see Skylit's **FlowBonus** ('how unusual') quoted by Flow AI. It isn't a column on the Live Feed" | §2 | FlowBonus exists as an internal "how unusual" score surfaced via Flow AI; formula not disclosed in course. | 3 |
| 6 | "Strong (either way) \| High \| Directional **and** unusual — look first … Near zero \| Low \| Lowest priority." | §2 table | Attention priority is a 2×2: direction-strength × unusualness; (strong, high) looked at first, (near-zero, low) last. | 3 |
| 7 | "A Flow Score of **+80** does **not** mean an 80% chance … It means the print was classified strongly bullish." | §3 "Scores Sort; They Aren't Probabilities" | Score magnitude is a class label, not a probability — never use as win-rate. | 3, 4 |
| 8 | "Use scores like a search result: to decide what to read next." | §3 | Scores are sort keys for attention only; the qualification decision is elsewhere. | 3 |
| 9 | "a drawer of filter groups — ticker, calls or puts, Flow Score, side, DTE, premium, open interest, moneyness and more" | §4 "One Tab, One Question" | Live Feed filter fields: ticker, call/put, flow_score, side, dte, premium, open_interest, moneyness. | 3 |
| 10 | "Build a tab **one change at a time** — premium floor, then universe, then sweeps, then score, then DTE and moneyness" | §4 | Canonical filter-construction order: premium floor → universe → sweeps → score → DTE/moneyness. | 3 |
| 11 | "**A premium floor isn't an institution filter.** A $500K minimum shows large prints — not funds." | §5 "Your View Reads the Way You Filtered It" | A $500K premium floor selects large prints only; it is not an actor-type filter. | 4 |
| 12 | "The **summary bar** across the top — directional sentiment, net premium, FIR, calls and puts, put/call ratio and RVOL — is **market-wide**." | §5 | Market-wide aggregate metrics: directional sentiment, net premium, FIR, calls, puts, put/call ratio, RVOL; not filter-responsive. | 3, 4 |
| 13 | "filters to ask-side calls only, sweeps only and a $1M floor — all at once. Their feed shows only bullish prints" | §6 Case Study | $1M premium floor appears as a worked filter value; combined filters create selection bias. | 4 |
| 14 | "Premium rank and Vol/OI measure how unusual a print is, not which way it points." | §7 Mistake 2 | Never derive direction from premium rank or Vol/OI. | 3 |

## flowseeker-06 — The Tools and One Contract

| # | Verbatim quote | Source | Testable rule | Cat |
|---|---|---|---|---|
| 1 | "**Flow Scanner** \| One contract \| Which contracts are busiest today? / **Flow Compass** \| A ranked card \| What stands out across the market?" | §2 view table | Product surfaces are defined only by unit and question — **no ranking formula given** (see gaps). | 3 |
| 2 | "Each contract's day in one row: volume and open interest, the change in open interest, premium, IV, and how its activity splits between bullish and bearish." | §3 "Scanner, Tracker, Dark Feed" | Scanner row schema: volume, oi, oi_change, premium, iv, bullish/bearish activity split. | 3, 4 |
| 3 | "Check **when** the open interest is from — late in the day it can still reflect the last clearing." | §3 | OI freshness check is part of contract ranking; intraday oi_change can be stale. | 5 |
| 4 | "Tracked Flow shows a **P/L %: the current mid against the original print's fill price** — a mark, not your fill" | §3 | Tracked-print P/L% = current mid / original fill − 1 (mark-to-mid). | 3, 4 |
| 5 | "Large off-exchange stock trades: time, ticker, price, size in shares, notional, **sector**. A dark-pool print has no call or put … **not bullish or bearish by default**." | §3 | Dark Feed rows carry a sector field (only sector mention in the corpus) and are direction-neutral context. | 3 |
| 6 | "**Contract Flow** (volume by bid, mid and ask over time …), **Net Premium** …, **Strike Distribution**, **Underlying (Vol / $)**, **Vol/OI History** and **Flow Orders**." | §4 "One Contract, a Testable Question" | Drilldown view set (fields implementable per contract): bid/mid/ask volume timeline, net premium, strike distribution, underlying vol/$, vol/OI history. | 3 |
| 7 | "every one of these views is built from **the same options tape** … that's **one kind of evidence seen several ways**, not several confirmations." | §4 | Anti-double-count rule: agreement across Drilldown views counts as ~1 evidence unit. | 2 |
| 8 | "End with one of three honest answers: **A hypothesis worth keeping** … **A conflict** … **Not enough evidence**" | §5 | Every contract investigation terminates in one of 3 states; "not enough evidence" blocks trade. | 2 |

## flowseeker-07 — Flow Meets the Map and the Trinity

| # | Verbatim quote | Source | Testable rule | Cat |
|---|---|---|---|---|
| 1 | "Compare it with **that ticker's** map, scoped to **that expiry** … How large is the exposure there — **magnitude matters more than color**." | §2 "Same Ticker, Same Expiry" | Match print to same-ticker/same-expiry exposure; rank node significance by exposure magnitude, not color class. | 2, 3 |
| 2 | "keep each index separate — a SPY print is read against SPY's map" | §2 | No cross-instrument map matching (QQQ strike ≠ NQ price; conversions must be time-stamped). | 2 |
| 3 | "**3 of 3 aligned** — full confluence / **2 of 3** — … reduced confidence; the bare minimum, at reduced size / **1 of 3 or fewer** … — no trade" | §5 "Divergence Is a Warning" | Trinity gate: alignment count across SPX/SPY/QQQ on chart+map+flow — 3→full size, 2→reduced size minimum, ≤1→no trade. | 2, 4 |
| 4 | "**SPX and SPY track the same index** — their agreement is close to **one** piece of evidence. **QQQ** is more independent" | §4 "The Trinity, Side by Side" | De-duplicate correlated instruments: SPX+SPY agreement ≈ 1 evidence unit; QQQ is the independent leg. | 1, 3 |
| 5 | "**positive gamma** tends to dampen moves, **negative gamma** tends to amplify them. Regime shapes **behavior**, not direction." | §3 "Flow Is One Reason the Map Reshuffles" | Regime (sign of gamma) modulates expected move magnitude only — never direction. | 2, 3 |
| 6 | "Divergence is not opportunity. Divergence is a warning. … Reduce size or pass" | §5 | Instrument divergence → reduce size or pass; never cherry-pick the agreeing index. | 2 |
| 7 | "When the chart gives no edge — a midpoint — flow can't create one." | §5 | Midpoint location is a hard disqualifier independent of flow strength. | 2 |
| 8 | "**chart · map · flow · read · weakens if** — with 'weakens if' concrete: a level lost, a node that shrinks, open interest that falls back." | §5 | A tradable read must carry falsifiers expressible as level-loss / node-shrink / OI-fall-back. | 2, 3 |

## flowseeker-08 — Flow on the Chart

Ticker-selection content: **none** (pane operates on an already-chosen ticker).

| # | Verbatim quote | Source | Testable rule | Cat |
|---|---|---|---|---|
| 1 | "**The bars show premium, not volume.** A tall bar is a lot of **dollars**, not necessarily a lot of contracts." | §2 "What the Pane Shows" | Chart flow pane aggregates premium $, not contract counts. | 3, 4 |
| 2 | "**Calls and puts are shown separately** — calls above the zero line, puts below. … Net … is a difference, not 'total bullish flow'." | §2 | Keep call/put premium series separate; Net = call − put is a difference metric only. | 3 |
| 3 | "Legs \| Single · Multi / Moneyness \| ITM · ATM · OTM / Side \| Bid · Mid · Ask / Sweeps \| Sweep · Non-Sweep / DTE \| Minimum / maximum / Premium \| Minimum / maximum / Flow Score \| Minimum strength" | §3 "Filter the Pane Like a Feed" | Exact pane filter schema: legs, moneyness buckets (ITM/ATM/OTM), side, sweep flag, dte min/max, premium min/max, flow_score min. | 3, 4 |
| 4 | "Each group keeps **at least one pill on**. With every pill in a group on, that group isn't filtering anything." | §3 | Filter semantics: per-group OR with ≥1 active; all-on = no-op. | 4 |
| 5 | "**Good uses:** *'Price tested the range low — did meaningful premium show up there?'* … **Bad uses:** *'A tall call bar printed — buy.'*" | §4 "Support the Read, Don't Replace It" | Premium-at-level is admissible only as support for a pre-existing structural level read. | 2 |
| 6 | "find the level on the chart, confirm it on the map, **then** look at the pane … Entries and invalidation still come from structure." | §4 | Order: chart level → map confirm → pane support; entry/invalidation never from flow bars. | 2, 6 |
| 7 | "A tall call bar prints while price sits in the middle of the range. What's the read? — No setup — location first, and a bar can't create one" (quiz) | §4 quiz | Quiz-consistent with cat-2 midpoint disqualifier; flagged as quiz text. | 2 |

## flowseeker-09 — When Price and Flow Disagree

| # | Verbatim quote | Source | Testable rule | Cat |
|---|---|---|---|---|
| 1 | "Be precise about **which** flow and **which** price: the ticker, the expiry, the time window, and where price is in the structure." | §2 "State the Mismatch" | Any flow/price comparison must be keyed on (ticker, expiry, time window, structural location). | 2, 3 |
| 2 | "New bullish bets \| … Protection \| … Closing \| … Part of a structure \| … Misread side … All five produce the **same prints**." | §3 "List the Explanations" | Every directional flow read has ≥5 latent explanations producing identical prints; classification must not assume "new bet". | 2, 3 |
| 3 | "The old idea that *'flow is usually right'* has never been measured — no sample backs it" | §3 | No doctrine of "follow the flow" — no flow-following rank/trigger may be justified by win-rate claims. | 3 |
| 4 | "**Next-day open interest** — a net drop is consistent with closing; a net rise with new positions … **Side quality** — fills at the ask edge versus near the mid" | §4 "Separate Them" | Disambiguation features: next-day ΔOI, same-second legs, expiry length, side-edge quality, price acceptance, node change. | 3 |
| 5 | "Until the evidence separates the explanations, you have a **conflict**, not a read. … **Reduce size**, or **Wait** …, or **Pass**" | §4 | Conflict state → only allowed actions: reduced size / wait / pass. | 2 |
| 6 | "repeated calls bought at the ask, totalling **$4M** over twenty minutes, in the 590 strike, **2 DTE**." … "The disciplined trader **waits**" | §5 Case Study | Even $4M ask-side 2-DTE call flow at a King-Node ceiling is a no-trade until rejection/acceptance resolves. | 4, 2 |
| 7 | "It's 2 DTE, right at the ceiling — consistent with breakout bets **or** protection, less so with long-term positioning." | §5 | Short-DTE + at-extreme flow is ambiguous between breakout bets and protection; not dispositive. | 5 |

## flowseeker-10 — Playbooks, Routine and Review ★ (daily playbook)

| # | Verbatim quote | Source | Testable rule | Cat |
|---|---|---|---|---|
| 1 | "A playbook is a form with the same fields every time: Question / Location / Map / Flow / Target / Weakens if / Decision … Flow sits fourth. **Flow is never the trigger.**" | §2 "A Playbook Organises a Hypothesis" | Decision form schema with fixed order; flow is evidence slot #4 and can never be a trigger field. | 2, 6 |
| 2 | "structure on the chart, Heatseeker confluence behind the direction, and at least 3-to-1 reward with a clean entry. (The summer bootcamp's stricter version adds a mapped liquidity sweep — all four gates, or no trade.)" | §2 | Tradability gate stack: (1) chart structure, (2) map confluence, (3) R:R ≥ 3:1 + clean entry, bootcamp adds (4) mapped liquidity sweep. | 2, 4 |
| 3 | "The Skylit minimum is **3 to 1 reward to risk** … the distance to target at least three times the distance to invalidation." | §3 "Risk, Size and No Trade" | Quantified gate: (target − entry) ≥ 3 × (entry − invalidation). | 4, 2 |
| 4 | "at 581.40, reward to 590 is 8.60 and risk to 577 is 4.40 — about **2 to 1**, below the minimum. The trader **waits**. At 579 … **5.5 to 1**. Now it qualifies." | §6 Case Study | Worked R:R values: 2:1 disqualifies (wait), 5.5:1 qualifies. | 4 |
| 5 | "Strong flow doesn't earn a bigger position by itself, and the Trinity rule still applies — 2 of 3 means reduced size." | §3 | Position sizing is independent of flow magnitude; Trinity 2/3 → reduced size cap. | 2 |
| 6 | "Pass when price is at a midpoint, the Trinity is totally misaligned …, you can't write a concrete 'weakens if', the risk-to-reward isn't there, or the evidence is an unresolved conflict." | §3 | Five explicit no-trade disqualifiers: midpoint, Trinity ≤1-aligned, no falsifier, R:R < 3:1, unresolved conflict. | 2 |
| 7 | "**Before the open** \| Mark levels on the chart, read the maps, write your questions / **During the session** \| Watch flow **at your planned levels**; fill in playbooks; recheck saved hypotheses when the map reshuffles / **After the close** \| Contract totals in the Scanner — some data is still preliminary / **Next morning** \| Check open interest on what you saved, using the actual OI date / **Weekly** \| Review everything — wins, losses **and skipped trades**" | §4 "A Simple, Repeatable Day" | The daily routine, in order (New York time): pre-open level/map/question prep → intraday flow watched only at planned levels (+reshuffle rechecks) → post-close Scanner totals (preliminary) → next-morning OI check by OI date → weekly review incl. skips. | 6, 5 |
| 8 | "For every setup you act on **or skip**, save: the contract and time, snapshots of the chart, map and feed, your filters, your hypothesis and the alternatives, what you knew **at that moment**, your 'weakens if', and whether you traded it or only watched." | §4 | Minimum saved record per candidate setup (acted or skipped) — the review dataset schema. | 6 |
| 9 | "**Judge the decision, not the outcome.** … **Keep the skipped trades.** They show whether your filter for passing is working." | §5 "Review Honestly" | Review grades process decisions; skipped-trade log is part of the qualification-filter feedback loop. | 6 |
| 10 | "**Floor reversal** — price at a range low, a floor node beneath. Flow supports if bullish flow shows up at the level … Target: the next ceiling. Weakens if price accepts below the floor or the floor node shrinks." | §2 | Playbook template A: floor-reversal setup definition (location=range low + floor node; flow at level is support/challenge). | 6, 2 |
| 11 | "**Ceiling rejection** — price at a range high, a ceiling node above. Flow supports if bullish flow fades or bearish flow appears; persistent call buying at the level is a conflict" | §2 | Playbook template B: ceiling-reversal; opposing flow at level = conflict state, not trigger. | 6, 2 |
| 12 | "A trader's playbook says: 'When a $1M call sweep prints, buy.' What's wrong? — It makes flow the trigger and skips location, the map, the target and invalidation" (quiz) | §2 quiz | Quiz explicitly invalidates pure-dollar sweep triggers (e.g. $1M) as selection rules. | 2 |

---

## Per-file ticker-selection verdicts (honest)

- **01:** no ticker-universe content; contributes midpoint/extreme disqualifier and no-print-is-a-signal rule.
- **02:** no ticker-universe content; contributes print-ranking units (premium), DTE bands, moneyness convention, side buckets.
- **03:** **no ticker-selection content** (sweep/multi-leg mechanics only).
- **04:** contract-level screen only (Volume > OI, Size > OI) — the closest thing to a "worth a look" quantified filter.
- **05:** the ranking file; **ticker-relative** unusualness (premium rank over 20 days per ticker) is the only per-ticker normalization in the corpus.
- **06:** surface inventory; explicitly **no formulas** for Scanner/Compass ranking.
- **07:** fixed 3-ticker universe (SPX/SPY/QQQ "Trinity") with a counted alignment gate; no dynamic universe.
- **08:** **no ticker-selection content** (pane filters for an already-chosen ticker).
- **09:** disambiguation doctrine, not selection; blocks "follow the flow" triggers.
- **10:** the qualification gate stack + daily routine; the most implementable "tradability" definition in the corpus.

## Gaps — what the text does NOT give us (do not invent)

1. **Flow Compass card score/rank formula** — described only as "A ranked card | What stands out across the market?" (06 §2). No sort key, no inputs, no weights.
2. **Flow Scanner sort key** — only "Which contracts are busiest today?" (06 §2); "busiest" is undefined (volume vs premium vs count not stated).
3. **Ticker universe / screening criteria** — nothing on liquidity minimums, bid-ask spread width, market-cap, sector rotation, earnings/event calendars, or listing filters. Sector appears once, as a Dark Feed display field (06 §3).
4. **Flow Score / FlowBonus formulas** — inputs listed (side, sweeps, moneyness, DTE, premium, IV), weights and mapping to ±100 not given; FlowBonus "isn't a column on the Live Feed" and no definition given (05 §2).
5. **Session-clock timing doctrine** — no "best hours"; only the routine clock (10 §4) and OI staleness (04 §2, 06 §3). DTE bands (02 §4) are the only event/horizon windows.

## Implementable quantities index (quoted values only, with source)

- Flow Score range [−100, +100]; inputs = side, sweeps, moneyness, DTE, premium, IV (05 §2)
- Premium rank window = ticker's own trades, last 20 days (05 §2)
- Unusualness = premium percentile (per ticker) and Vol/OI (05 §2); screens: volume > OI, print size > OI (04 §3)
- Sweep grouping = same contract within 1 second (03 §2)
- DTE bands 0–7 / 8–30 / 31+ (02 §4); moneyness = % from spot-at-execution, + = OTM (02 §4)
- Premium = fill × contracts × 100 (02 §3); side buckets bid / mid / ask around touch (02 §5)
- Filter fields: ticker, call/put, flow_score, side, dte, premium, open_interest, moneyness + toggles sweeps/multi-leg/single-leg/vol>oi/size>oi; pane adds legs, ITM/ATM/OTM, sweep, flow_score min (05 §4, 03 §2/§4, 04 §3, 08 §3)
- Market-wide bar metrics: directional sentiment, net premium, FIR, calls, puts, put/call ratio, RVOL (05 §5)
- Trinity gate: 3/3 full, 2/3 reduced size, ≤1 no trade (07 §5)
- R:R minimum 3:1 (worked: 2:1 fail, 5.5:1 pass) (10 §3, §6); bootcamp 4th gate = mapped liquidity sweep (10 §2)
- No-trade list: midpoint, Trinity ≤1, no falsifier, R:R < 3:1, unresolved conflict (10 §3)
- Daily routine order: pre-open (levels/maps/questions) → session (flow at planned levels) → after close (Scanner totals) → next morning (OI by date) → weekly (review incl. skips) (10 §4)

**Files created/modified:** none (read-only extraction, as instructed). **Issues:** none — all 10 files read in full; the gaps above are genuine absences in the source text, not search failures.