All 16 files read in full. Extraction below — verbatim quotes only, no inference beyond what the text states.

# Skylit Academy Heatseeker — Ticker-Selection / Tradability Doctrine Extraction

**Headline caveat (honest scope statement):** the Heatseeker curriculum is overwhelmingly about *map-reading on SPX/SPY/QQQ*, not per-ticker universe screening. Explicit ticker-universe/selection logic exists in only **two files** (Dark Pool Prints, Talon Prompt Guide). The rest contribute **tradability preconditions, disqualifiers, ranking rules, and numeric thresholds**. Absences noted at the end.

---

## heatseeker-00-reading-the-dark-pool-prints.md

| Quote | Source | Testable rule | Cat |
|---|---|---|---|
| "The feed defaults to a **$1,000,000 notional minimum**, so you're looking at blocks, not the full off-exchange firehose… the small prints are noise for most purposes" | §3 "The Tape: Dark Feed in Flowseeker" | Dark-pool screen: include prints with notional ≥ $1M; below = noise | 4 |
| "A $50M block and a $2B block are different events. The dollar size is the closest thing you have to a measure of how much somebody cared." | §2 "What a Dark Pool Print Actually Is" | Rank dark-pool events by notional dollar size as conviction scale | 3 |
| "A cluster of large prints in one name or one sector tells you attention is concentrated there." | §2 | Ticker/sector attention flag = cluster of large prints in one name or GICS sector | 1 |
| "Notional: Size x price - the dollar value of the block. This is the headline number." | §2 (field list) | Notional = size × price; primary scoring field | 4 |
| "A date (and optional time-of-day) range, notional min/max, size min/max, share-price min/max, and sector filters." | §3 | Feed filter dimensions = date/time, notional, share size, share price, sector | 6 |
| "**Top N** — how many of the largest prints to draw (1, 2, 3, or 5)… **Lookback** — how far back… (30, 45, 90, or 180 days)." | §4 "The Levels: Dark Pool Overlay on Atlas" | Atlas DP overlay selects top-N largest prints (N∈{1,2,3,5}) within lookback ∈{30,45,90,180} days | 4 |
| "A dark pool level that lines up with a dealer positioning node is far more interesting than one sitting in structural no-man's-land." | §5 "Putting the Two Together" | Prioritize DP levels coincident with a GEX/VEX node (confluence) over standalone levels | 3 |
| "scan for unusually large notionals, note _which tickers and sectors_ are printing size, and treat those prices as levels to watch — not as directional signals." | §3 | Workflow: select names by unusually large notional; output = watchable price levels, not direction | 1 |
| "off-exchange equity prints do not carry the bid/ask, side, or options-structure data required for those labels" (quiz answer re: "flow score, sweep tags, Greeks, or sentiment") | §99 Quiz | Product rule: no flow-score/sweep/Greek/sentiment label on dark-pool prints (data lacks side/bid-ask/structure) | 6 |

## heatseeker-00-atlas.md

| Quote | Source | Testable rule | Cat |
|---|---|---|---|
| "the ability to filter out heatmap data directly from heatseeker and apply the most relevant nodes directly on your chart" | §1 Introduction | Product filters heatmap to "most relevant nodes" for chart display | 6 |
| "Atlas will express the top # nodes on the map based on the number of your choosing. 3 to 5 nodes is typically recommended." | §9 "Setting up for 0DTE" | Node display = top-N by exposure; recommended N = 3–5 | 4 |
| "Gamma becomes increasingly dominant as a contract approaches expiration. The **current** expiration column is what 0DTE traders should be most focused on." | §9 | 0DTE selection scope = current expiration only (gamma dominance near expiry) | 5 |
| "For **swing traders**, further expirations may matter more because larger positioning can build several days or weeks out." | §5 "How Traders Should Use It" | Swing scope = current + next N expirations (larger positioning builds further out) | 5 |
| "It is typically good practice to trade when GEX and VEX are in confluence." | §10 "Setting up for Swing Trading" | Tradable swing setup requires GEX (entry) and VEX (target) agreement | 2 |
| "GEX is used for intraday entries / VEX is used for bigger picture price targets." | §10 | Signal routing: GEX→intraday entry, VEX→swing targets | 3 |
| "**ES** borrows levels from **SPXW/SPY** · **NQ** borrows levels from **QQQ**" | §8 "Derived Orbs" | Universe: ES/NQ tradable via derived exposure borrowed from SPXW/SPY/QQQ books | 1 |
| "a king node orb for this week expiration may be at the 200 strike price, but the king node for July OPEX may be 20 dollars higher." | §1 | King node is per-expiration; selection must name expiration scope | 5 |

## heatseeker-01-charts-first-market-structure-before-exposure.md

| Quote | Source | Testable rule | Cat |
|---|---|---|---|
| "Without chart structure, exposure data becomes noise." | §1 Chapter Objective | Disqualifier: no chart-based structural thesis → no exposure-based trade | 2 |
| "Before any exposure analysis occurs, traders must answer one simple question: **Where is price located within the market structure?**" | §2 | Precondition: price's position within S/R structure must be classified first | 2 |
| "We trade extremes. We avoid midpoints." / "When price is sitting in the middle of a range, there is no structural edge. Without an edge, the trade should not exist." | §4 "Range-Bound Action" | Disqualifier: price at range midpoint = no trade | 2 |
| "A strong level typically has: **Freshness**… **Visible reactions**… **Multiple timeframe alignment**… **Clean price action around it**… **Magnitude of the reversal**" | §4 "What Makes a Level 'Good'?" | Setup-quality scorecard: freshness + visible reaction + multi-TF alignment + clean reaction + reversal magnitude | 2 |
| "A weak level typically has: Been tapped multiple times (degraded) / Only visible on a very low timeframe / Choppy, unclear reactions around it" | §4 | Disqualifier checklist for levels: tapped multiple times, low-TF-only, choppy reactions | 2 |
| "A level that has not been tapped yet is stronger than one that has been tested multiple times. Each time price touches a level, it **degrades**" | §4 "Prefer Fresh Levels" | Rank levels by freshness; degrade score per tap | 3 |
| "A support level on the daily or hourly chart is more significant than one on the 5-minute chart." | §4 "Use Higher Timeframes First" | Weight levels by timeframe: daily/weekly > hourly > 5-min | 3 |
| "A support level from last week is more relevant than one from six months ago." | §4 "Recent Levels Matter More" | Recency filter: weight recent reactions over older ones | 3 |
| "Mark the ones that are **obvious** — if you have to squint to see it, it probably doesn't matter." / "The best levels are the ones you can spot in under five seconds." | §4 "Keep It Simple" | Subjective clarity gate: only levels visible in <5s on a clean chart | 3 |
| "Structure determines opportunity, not speed." (Mistake 3 — Confusing Momentum With Structure) | §6 Common Mistakes | Disqualifier: fast price movement alone is not a setup | 2 |

## heatseeker-02-dealer-positioning-and-gamma-mechanics.md

| Quote | Source | Testable rule | Cat |
|---|---|---|---|
| "This is known as the **absolute value rule**: The magnitude of the node determines its influence. Always prioritize **node size over node color**." | §5 "The Absolute Value Rule" | Rank nodes by absolute exposure value, not sign/color | 3 |
| "Small nodes often have minimal influence. Large nodes are where dealer exposure concentrates. Always identify the largest nodes first." | Mistake 2 — Ignoring Node Magnitude | Attention order: largest absolute nodes first; small nodes deprioritized | 3 |
| "Nodes act like 'magnets'. The bigger they are, the stronger the pull. The closer they are, the stronger the pull." | §5 | Influence ∝ node magnitude and proximity to spot | 3 |
| "When analyzing a heatmap, traders should ask: 1. What regime are we in? 2. Where are the largest nodes? 3. Where is spot relative to those nodes?" | §6 | Fixed analysis triage order: regime → largest nodes → spot position | 3 |
| "Positive gamma environments suppress volatility… Negative gamma environments amplify volatility." | Key Takeaways | Regime prior: +gamma = chop/mean-revert; −gamma = fast/expanding (day-type expectation) | 5 |

*(No ticker-universe content in this file.)*

## heatseeker-03-node-hierarchy.md

| Quote | Source | Testable rule | Cat |
|---|---|---|---|
| "Skylit doctrine requires a **3:1 minimum R:R** for any trade to qualify. A midpoint entry does not meet that standard." | §6 "Midpoints" | Hard gate: R:R ≥ 3:1 for any trade to qualify | 4 |
| "The **King Node** is the strike with the **largest absolute exposure value** on the Heatseeker map." | §4 "Step 2 — King Node" | King node = argmax \|exposure\| over strikes (named product construct) | 6 |
| "The king node represents the strike where Market Makers are most likely to pin price at when the NYSE closes." | §4 | King node as expected NYSE-close pin (session-timing anchor) | 5 |
| "The strongest floor is usually the largest exposure node beneath spot." / "The strongest ceiling is typically the **largest exposure node above spot**." | §5 | Floor/ceiling selection = argmax exposure below/above spot | 3 |
| "The risk-to-reward profile is poor — at best, a midpoint entry offers **1:1 R:R**" | §6 | Midpoint entries quantified as ≤1:1 R:R → fails 3:1 gate | 4 |
| "Air Pockets occur when maps show a zone of low volume and/or small sized nodes that price can move easily through due to the lack of resistance/activity within that zone." | §8 "Air Pockets" | Air-pocket detection: zone of low node volume / small node size between strikes | 4 |
| "We fade extremes, not midpoints. If price is between nodes, the risk-to-reward is against you." | §6 | Disqualifier: price between nodes = untradeable location | 2 |

## heatseeker-04-gamma-regime-awareness-and-day-forecasting.md

| Quote | Source | Testable rule | Cat |
|---|---|---|---|
| "Maps with nodes far from spot price, with rapid accumulation… ***Massive king node that grows rapidly with time***" (Type 2 — Trend Day tells) | §4 "Types of Days" | Trend-day classifier: nodes far from spot + rapid one-directional accumulation + fast-growing king node + air pockets | 5 |
| "Price usually sitting on key level, anticipating news events" (Type 1 — Range/Choppy Day) | §4 | Range-day classifier includes "price pinned at key level ahead of news events" (event-calendar context) | 5 |
| "Play the EXTREME ends of ranges ONLY" | §4 Type 1 "How to think" | Tradable locations on range days = range extremes only | 2 |
| "If missed entry point, sit out until clear pivot appears - like a king node price target getting hit." / "When in doubt, sit out" | §4 Type 2 / Type 3 | Disqualifier: no valid entry present → no trade; doubt → stand down | 2 |
| "Don't chase reversals" (Type 1) / "Don't fade strength blindly" (Type 2) | §4 | Disqualifiers: chasing reversals in chop; fading trend-day strength | 2 |
| "***Rolling of ceilings*** - Considered strong presumptive evidence of a bearish thesis… ***Rolling of floors*** - …bullish thesis" | §4 "Rolling of ceilings/floors" | Directional priority signal: ceiling roll down = bearish bias; floor roll up = bullish bias | 3 |
| "Velocity mode (% change of nodes) sees rapid accumulation in one direction" | §4 Type 2 | Velocity mode metric = % change of node exposure; one-directional surge = trend-day signal | 6 |
| "Regime does **not** tell you where price goes… node accumulation and map reshuffles tell you where price is likely to go next." | §2 "Key Rule" | Prioritization: direction from node accumulation/reshuffle, not regime label | 3 |

## heatseeker-05-heatseeker-pattern-recognition.md

| Quote | Source | Testable rule | Cat |
|---|---|---|---|
| "A pattern only has meaning when combined with: Chart structure, Gamma regime, Node magnitude, Cross-index alignment (confluence across the trinity)" | §2 "Core Principle" | Precondition: pattern tradable only with all four context layers present | 2 |
| "**Hierarchy of Influence** 1. **Node magnitude** 2. **Gamma regime** 3. **Pattern structure** 4. **Cross-index alignment**" | §4 "Pattern Interaction" | Explicit priority ranking for conflicting signals (product ranking doctrine) | 3 |
| "Rainbow Road… **No clear directional bias / No dominant nodes**… This is: **No-trade conditions**" | §3 §VI | Disqualifier: no dominant node + no defined floor/ceiling = stand down | 2 |
| "Whipsaw Setup… **A trap environment** The only edge comes from fading the extreme ends of ranges." | §3 §V | Whipsaw (conflicting cross-index signals) → only range-extreme fades; rest disqualified | 2 |
| "❌ Ignoring Chart Structure — No structure = no trade" | §6 Common Mistakes | Hard disqualifier: absent chart structure → no trade | 2 |
| "One pattern is never enough" / "Patterns are… Not standalone trade triggers" | §6 / §2 | Disqualifier: single-pattern basis insufficient to enter | 2 |
| "Which has more magnitude? … **Magnitude overrides everything**" | §4 | Tie-break rule: larger magnitude wins pattern conflicts | 3 |
| "Pika clouds are: **Not bullish or bearish by default**… Larger nodes → stronger pull" | §3 §III | Pika cloud (dense +gamma cluster) = friction/pin only; magnitude graded, no directional tag | 3 |

## heatseeker-06-execution-models-trading-the-deflection.md

| Quote | Source | Testable rule | Cat |
|---|---|---|---|
| "**1st Tap of a major node → ~80% reaction probability** · **2nd Tap → ~66%** · **3rd Tap → ~33%**" | §6 "Node Tap Probability (CRITICAL)" — "one of the most important execution filters" | Setup quality decays per tap: 1st≈80%, 2nd≈66%, 3rd≈33% reaction probability | 4 |
| "First test = highest quality fade / Second test = still tradable / Third test = **low-quality setup**" | §6 | Tradability tiers by tap count; 3rd tap disqualified as low quality | 2 |
| "Deflection zones are +/- 50 cents on QQQ and SPY and +/- 5 dollars on SPX in either direction." | §3 Execution Doctrine | Entry trigger band = node ± $0.50 (QQQ/SPY), ± $5 (SPX) | 4 |
| "**3:1 = standard, aim for higher** / **2:1 = acceptable but not ideal** / Below = avoid" | §9 "Risk Management — A+ Standard" | R:R filter: ≥3:1 standard, 2:1 marginal, <2:1 avoid | 4 |
| "Requirements 1. Chart structure 2. Heatseeker confluence 3. Asymmetric R:R" | §9 | A+ setup = all three required | 2 |
| "We are NOT: … Taking trades without cross-index alignment" | §3 "What This Means" | Disqualifier: absent cross-index alignment → no trade | 2 |
| "Stop losses off node deflections typically get triggered if we break and hold 1 node above/below the node we are playing a deflection off of." | §3 | Stop rule: one node beyond the played node, on break-and-hold | 4 |
| "No setup, no entry. We dont force trades — we let the map bring price to us… If the setup doesnt materialize or price never reaches the node, there is no trade" | §12 "Execution Rules (Non-Negotiable)" | Disqualifier: price never taps node → no trade exists | 2 |
| "Do NOT trade the third tap aggressively ❌" / "Do NOT trade midpoints ❌" / "Do NOT chase moves ❌" | §12 | Explicit execution disqualifier list | 2 |

## heatseeker-07-rolling-floors-and-ceilings.md

| Quote | Source | Testable rule | Cat |
|---|---|---|---|
| "SPX, SPY, and QQQ need to agree more often than not. Mixed reads lower confidence." (§6 citing Skylit Docs: "if one diverges, stand aside") | §6 Common Mistakes #6 | Cross-index agreement majority required; divergence = lower confidence / stand aside | 2 |
| "Fresh nodes matter more than interacted-with nodes, and once a level has been used, its influence drops and the probability of reversion declines." | §5 "Relationship to Chapter 6" | Rank setups by node freshness; reversion probability declines per use | 3 |
| "The trade still needs: chart structure / Heatseeker confluence / asymmetric risk-to-reward / clear entry point off a deflection of a key node" | §3 Step 5 "Wait for the A+ setup" | A+ trade gate = 4 conditions (structure, confluence, asymmetry, deflection entry) | 2 |
| "in negative gamma… greater need for cross-index confirmation" | §4 "Gamma Context" | Confluence bar rises in negative gamma regime | 5 |
| "A Floor Rolling up is strong presumptive evidence of a bullish thesis… downside nodes decrease in value… the floor moves to a **higher strike**" | §1 "Rolling a floor up" | Bullish signal = floor strike rises while downside nodes shrink | 3 |
| "Skylit doctrine is very clear: trade reversals at floors and ceilings, avoid midpoint noise, and do not build a strategy around chasing continuation." | §2 "What Rolling Is NOT" | Disqualifier: continuation-chasing setups out of scope | 2 |

## heatseeker-08-air-pockets-liquidity-vacuums-and-velocity-mode.md

| Quote | Source | Testable rule | Cat |
|---|---|---|---|
| "Notice how SPX had a 15 point dump from the open because of the **100% increase on those downside nodes**." | §6 "Rate of Change" (image caption) | Concrete trigger scale: ~100% node magnitude increase → directional move (15-pt SPX dump example) | 4 |
| "Air Pocket = **space** / Rate of Change = **fuel**… Space without fuel = drift / Space with fuel = acceleration" | §6 | Air pocket alone insufficient; need node rate-of-change (growth) to qualify momentum setups | 2 |
| "**Do NOT Fade Velocity**… If price is: In an air pocket AND accelerating… Fading here is not 'contrarian' It is **undisciplined**" | §9 "Execution" | Disqualifier: air pocket + acceleration = fade forbidden | 2 |
| "They identify an air pocket… But nothing happens… Because **space alone is not enough**." | §6 | Disqualifier: static air pocket without positioning shift = no setup | 2 |
| "Velocity Mode is most dangerous in negative gamma… - Theta burn" | §8 "Gamma Regimes and Velocity" | Regime caveat: velocity + negative gamma = chase/fade both penalized | 5 |
| "Position BEFORE Velocity… Identify weakening structure / Spot rolling of ceilings or floors / Anticipate expansion" | §9 | Entry timing rule: position pre-expansion off rolling structure, never mid-move | 3 |
| "A **Liquidity Vacuum** is: A **wide region of weak or sparse exposure**… *These are rare*." | §5 | Vacuum classifier: wide sparse/thin/widely-spaced node region; flagged rare | 4 |

## heatseeker-09-node-lifecycle-delivery-and-target-validity.md

| Quote | Source | Testable rule | Cat |
|---|---|---|---|
| "**We do not target used levels** / **We target fresh positioning**" | §4 "The Node Lifecycle" | Target selection: exclude tapped/delivered nodes; target untested nodes | 2 |
| "**Hedge Nodes (The Trap)** - Often far OTM / Large in size / Look important… **They are protection — not intent**… Do NOT grow / Fade over time" | §7 "Real Nodes vs Hedge Nodes" | Disqualifier: large far-OTM non-growing node = hedge, not a valid target | 2 |
| "**Growth = intent** / **Decay = protection**" | §7 | Classify nodes: growing magnitude = directional intent; fading = protection noise | 3 |
| "**Not all large nodes are targets** / Only growing nodes with structure are" | §9 "VEX — Context and Confluence" | Target-validity rule: size alone insufficient; require growth + structural pathway | 2 |
| "Far nodes = **possibility** / Near nodes = **pathway**" / "Price does not teleport" | §8 "Targeting Logic" | Target ladder: nearest structure first; far nodes only as terminal possibility | 3 |
| "1. Fresh Node - Untested / Full strength / Highest probability reaction… 4. Decaying Node - Influence weakens over time" | §2 Node Lifecycle | Setup scoring by lifecycle state: fresh > tested > delivered > decaying | 3 |
| "Stairstepping Defined: Nodes stacked week over week gradually rising in price… **Stairstepping = trend formation**" | §10 | Trend-formation detector: week-over-week upward node stacking (structure shift) | 3 |
| "Common mistakes: … Confusing size with importance / Chasing far OTM nodes / … Getting theta burned on distant targets" | §9 | Disqualifier list for target selection | 2 |
| "Use it [VEX] to understand **directional pressure** / Then confirm: Node growth, Structural pathway" | §9 | VEX = directional-pressure context; confirm with node growth + pathway before targeting | 3 |

## heatseeker-10-cross-index-confluence.md

| Quote | Source | Testable rule | Cat |
|---|---|---|---|
| "→ **Reduced confidence but still playable - 2/3 confluence is bare minimum for trinity.**" | §7 Step 5 "Classify the Environment — Scenario B" | Quantified confluence gate: ≥2 of 3 indices (SPX/SPY/QQQ) aligned to be tradable | 4 |
| "Scenario C — Divergence / Indices disagree / Structure conflicts / → **No trade or reduced size**" | §7 Step 5 | Disqualifier: 0–1/3 alignment → no trade or reduced size | 2 |
| "A target is only valid if the system supports delivery" | §8 "Targeting Across Indices" | Target validity requires cross-index delivery support | 2 |
| "If SPX shows a target but: QQQ lacks momentum / SPY lacks liquidity / → The move is fragile" | §8 | Fragility flag: target without cross-index momentum/liquidity support | 2 |
| "A move on one chart is a signal / A move across all charts is confirmation" | §3 "Key Insight" | Confirmation only when move replicates across all three books | 3 |
| "You are not trading SPX / You are trading the system behind SPX, SPY, and QQQ" | §2 | Universe doctrine: the tradable system = SPX+SPY+QQQ exposure network (indices, "three expressions of the same exposure engine") | 1 |
| "**Trinity Mode — SPX / SPY / QQQ combined heatmap view**… Is the system aligned?" | §6 "Trinity Mode — The Alignment Engine" | Product feature: Trinity Mode = 3-index alignment engine (named product construct) | 6 |
| "SPX → institutional hedging / SPY → liquidity + flow / QQQ → tech weighting" | §3 | Role assignment per index book used in confluence reads | 1 |
| "Do NOT force the trade / Either: Reduce size / Wait for alignment / Pass entirely" | §7 Step 6 | Divergence response ladder: shrink → wait → pass | 2 |

## heatseeker-11-tying-it-all-together.md

| Quote | Source | Testable rule | Cat |
|---|---|---|---|
| "Everything lines up: Structure makes sense / Node is valid / Reaction is clear / Indices agree / → **You can take the trade!**" | §4 Step 9 | Tradable = structure ∧ node validity ∧ clear reaction ∧ index agreement | 2 |
| "If something is off: Weak node / Conflicting indices / Messy structure / → **You wait or pass.**" | §4 Step 9 | Disqualifier ladder: any one fails → wait or pass | 2 |
| "Not all nodes matter… Ask: Is this node strong? Has it already been used? Is it likely to react?" | §4 Step 4 | Node triage: strength + unused + reaction-likelihood | 3 |
| "Be quick to take profits. Positive gamma regimes lead to chop and theta burn." | §4 Step 6 | +gamma regime: shorten hold time / take profits quickly (theta-burn penalty) | 5 |
| "Most interactions = **direct tap** / Negative gamma nodes = higher chance of **overshoot first**" | §4 Step 5 | Reaction-type prior: direct tap default; −gamma node = overshoot-first expectation | 5 |

## heatseeker-12-practicum.md

| Quote | Source | Testable rule | Cat |
|---|---|---|---|
| "**A+ Setup Framework** 1. **Charts / structure come first** 2. **Heatseeker provides confluence** 3. **Asymmetric risk-to-reward (minimum 3:1)** 4. **Execution is based on reaction — not anticipation**" | §1 | Canonical A+ gate: structure → confluence → R:R≥3:1 → reaction-based entry | 2 |
| "If there is no alignment: **There is no trade**" | §1 (Cross-Index Confluence) | Hard disqualifier: zero cross-index alignment → no trade | 2 |
| "We prioritize **fresh nodes** / Tested nodes lose influence / Delivered nodes weaken over time… We trade what is active — not what was relevant" | §1 (Node Quality) | Selection priority: fresh/active nodes; exclude stale ones | 3 |
| "When velocity / rate of change shows aggressive accumulation, be wary of fading." | §2 Case Study #1 (Feb 25, 2026) | Disqualifier: aggressive one-directional accumulation → fades invalid | 2 |
| "No one should be bullish if upside targets are decreasing." | §3 Case Study #2 (Feb 12, 2026) | Directional veto: shrinking upside targets (ceiling rolls) kills bullish setups | 3 |
| "Ceiling at 692 SPY, floor at 690. Fade either edge of the range." (case study) | §2 | Execution pattern: identified tight range → fade only its defined edges | 2 |

## heatseeker-13-final-examination.md (quiz-only; no prose sections)

| Quote | Source | Testable rule | Cat |
|---|---|---|---|
| "What defines an A+ setup? — **Structure + positioning + alignment + asymmetric R:R**" | Quiz Q2 | A+ definition (canonical, tested): 4-factor conjunction | 2 |
| "What are the retest probability numbers for fresh, vs tested nodes? — **1st tap 80%, 2nd tap ~66%, 3rd tap 33%**" | Quiz Q12 | Tap-decay curve confirmed as canonical doctrine numbers | 4 |
| "What is the minimum recommended R:R for trading with Skylit? — **3:1**" | Quiz Q13 | R:R floor = 3:1 | 4 |
| "A king Node value drops from **$680M —> $430M in 15 minutes**… — Keep an eye on the maps for potential king node reshuffle to another strike" | Quiz Q14 | King-node magnitude is dollar-scaled (~$680M example); large rapid drops → reshuffle watch, not target | 4 |
| "What defines node quality? — **Freshness, magnitude, and relevance**" | Quiz Q11 | Node-quality score = freshness + magnitude + relevance | 3 |
| "If there is no alignment across indices, the correct action is: — **Do not trade**" | Quiz Q9 | Disqualifier reaffirmed | 2 |
| "Price is approaching a strong node that has *already been tested twice*… — **Decreased chance of reversal due to multiple tests**" | Quiz Q15 | Multi-test decay reaffirmed | 4 |

## heatseeker-100-talon-prompt-guide.md (the ticker-selection core)

| Quote | Source | Testable rule | Cat |
|---|---|---|---|
| "**Sectors** — `semiconductors` (or `semis`), `energy`, `financials`, `healthcare`, `consumer`, `industrials`. Each basket carries its liquid sector ETFs alongside the names." | §2 "Scan Scopes" | Universe = 6 curated sector baskets of liquid names + liquid sector ETFs | 1 |
| "**Themes** — `ai`, `crypto`, `china`. These cut across sectors deliberately: the AI basket spans semis, hyperscalers and power." | §2 | Universe = 3 cross-sector theme baskets (ai, crypto, china) | 1 |
| "**Market** — the index and volatility complex: SPXW, SPY, QQQ, IWM, RUT, VIX, SMH, SOXX and the leveraged/vol names." | §2 | Market basket = index + vol complex incl. leveraged/vol products | 1 |
| "A scan with strict thresholds. **An empty scan is a real answer.** Talon names what it read and reports that nothing qualified rather than loosening the bar." | §7 "Setup Scans" | Hard-threshold screen: nothing qualifying → empty result; thresholds never loosened | 2 |
| "Scan baskets are curated. Talon won't scan your personal watchlist and won't assemble a ticker list of its own." | §9 Beta Limits | Universe is closed/curated; no dynamic list assembly, no user watchlists | 1 |
| "the premium leaders — each carrying **volume, open interest, vol/OI ratio, sweep share, and the buy/sell split**." | §5 "The Day's Flow" | Ranking fields for flow leaders: volume, OI, vol/OI ratio, sweep share, buy/sell split | 6 |
| "Ask \"is that unusual?\" That phrasing is what pulls in the baselines: **volume against the daily average, volume against open interest**." | §5 "Sharper" | Unusualness score = volume vs ADV (trailing baseline) and volume vs OI | 4 |
| "Today's totals, how today stacks against the **trailing week**, and the premium leaders" | §5 | Baseline window for "is that a lot for this name?" = trailing week / daily average | 4 |
| "Premium is directionless… buying leaves dealers short gamma there and the level tends to break; selling leaves them long gamma and it tends to hold." | §5 "Ask who initiated" | Side-weighted ranking: customer buy → level break-tendency; sell → hold-tendency | 3 |
| "Premium alone tracks what a contract *costs* as much as how busy it is — an expensive contract on an ordinary day can print a big dollar number and mean nothing." | §5 | Disqualifier for premium-only ranking: premium $ alone is not a screening signal | 2 |
| "Ask *who's buying it?* or *is that opening?*" | §5 | Priority: initiator/side + opening-vs-closing over size | 3 |
| "A gamma node belongs to one expiry. Without a date, Talon scopes to the nearest expiry traded — a different chain, described with the same confidence." | §8 "Habits" | Expiry scoping rule: strike queries must name expiry; default = nearest traded expiry | 5 |
| "Off-exchange block size over a **fixed five-session window**. There's no lookback argument" | §6 "Dark Pool and Blocks" | Dark-pool context window = exactly 5 sessions | 5 |
| "index symbols — SPX, SPY, QQQ, VIX and friends — have no issuer behind them, so no earnings date and no peers." | §7 "Company Context" | Event-calendar/peer screening only applies to single-name issuers, not index products | 1 |
| "There's no before/after-market timing in the underlying data, so Talon gives you the date and won't claim a session." | §7 | Earnings timing: date-only; session (pre/post) not a data field | 5 |
| "`what's the put/call ratio?` / `where's max pain?`" | §6 "Positioning Metrics" | Product exposes P/C ratio and max pain as positioning context fields | 6 |
| "`/talon sector NAME` | Setup scan across a sector basket" / "`/talon theme NAME`" / "`/talon market` | Setup scan across the index and volatility basket" | §2 Commands | Product scan command taxonomy = single ticker / sector / theme / market basket | 6 |
| "On a single named ticker with nothing qualifying, it falls back to that name's structure and tells you plainly that's what it's doing." | §7 | Fallback behavior: failed scan on named ticker → structure read, clearly labeled | 6 |

---

## Per-file "no ticker-selection content" statements

- **heatseeker-02**: no ticker-selection/universe content (node-reading doctrine only; contributes ranking rule "magnitude over color" and regime priors).
- **heatseeker-07**: no ticker-universe content (rolling-structure doctrine; contributes confluence/quality gates).
- **heatseeker-08**: no ticker-universe content (velocity/liquidity doctrine; contributes one numeric trigger example).
- **heatseeker-11**: no ticker-universe content (synthesis checklist only).
- All other files: no *per-ticker screening* either — the tradable universe throughout the curriculum is implicitly the **index trinity (SPX/SPY/QQQ)** plus, per Atlas, derived ES/NQ; only the Talon guide and Dark Pool file discuss selecting individual names.

## Explicit gaps (asked-for factors never quantified in any file)

- **No IV thresholds, bid/ask spread thresholds, market-cap filters, or OI minimums** appear anywhere as selection rules. (Vol/OI ratio and OI appear only as *reported fields* in Talon §5, without cut-offs.)
- **"Strict thresholds" of the Talon setup scan are never disclosed** — the guide states they exist and that an empty result is preferred to loosening them, but gives no numbers.
- Sector membership appears only as (a) GICS context field on dark-pool prints, (b) curated Talon sector baskets — never as a weighting rule.

## Consolidated quantified constants (implementable on UW data)

- Dark-pool feed floor: **$1,000,000 notional**; Atlas overlay: top **N∈{1,2,3,5}** prints over **{30,45,90,180} days**; Talon DP window: **5 sessions** fixed.
- Node tap decay: **80% / 66% / 33%** (1st/2nd/3rd tap); 3rd tap = low-quality.
- R:R gates: **3:1 minimum to qualify** (2:1 marginal, below avoid); midpoint ≤1:1.
- Deflection entry bands: **±$0.50 QQQ/SPY, ±$5 SPX**; stop = **one node beyond** invalidation.
- Trinity confluence: **2/3 minimum** to trade; 3/3 = high probability; ≤1/3 (divergence) = no trade or reduced size.
- Display/relevance: top **3–5 nodes** recommended; king node = argmax \|exposure\| (dollar-scaled, e.g. **$680M**); node-quality = freshness × magnitude × relevance; growth = intent, decay = protection.
- Unusualness baselines (Talon): **volume vs daily average**, **volume vs OI**, today vs **trailing week**; flow rank fields = volume, OI, vol/OI, sweep share, buy/sell split.