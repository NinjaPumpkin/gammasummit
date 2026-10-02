# Talon Prompt Guide

- Track: heatseeker / category: Skylit - Knowing Your Ecosystem
- Level: Beginner · duration: 20 min
- Passing score: 80 · sections: 9 · quiz questions: 0
- Provenance: https://app.skylit.ai/api/nexus/academy/courses/9756e229-a704-4a35-a3e2-afe803cc596d (JSON, captured 2026-10-02, read-only) · course id `9756e229-a704-4a35-a3e2-afe803cc596d`
- Views/completions at capture: 1536/0

## Course description

What to ask Talon, where to ask it, and the small habits that turn a thin answer into a useful one. A reference you can keep open beside the terminal — every example maps to something Talon can do today.

## Section 1: 1. How Talon Sees You — Page, Ticker, and Context

Talon knows **where you are** and **what you're looking at**. The page you're on and the ticker it's focused on ride along with every message you send.

Three rules follow from that. They explain most good answers, and most bad ones.

---

> **Talon already knows what you're looking at. Say a ticker only when you want something else.**

---

### **1. You Don't Have to Repeat the Ticker**

On an NVDA chart, "what are the levels?" is a complete question.

Talon resolves "this ticker" from the page in front of you.

---

### **2. Naming a Ticker Beats the Page, Every Time**

On an SPX board, "levels for MSFT" gets you MSFT — Talon fetches it rather than answering about the page you happen to be standing on.

This is the escape hatch whenever you want to ask about something that isn't on screen.

---

### **3. Talon Answers Short on Purpose**

A read is a few tight sentences, not an essay.

Ask for the decision, not the data dump — and if you do want the full ladder, say so.

## Section 2: 2. Commands — The Slash Menu

Type `/` in the terminal to see the menu. These are the ones with real behavior behind them.

| Command | What it does |
| --- | --- |
| `/levels` | Key GEX/VEX levels for the instrument this page is focused on |
| `/levels TICKER` | Levels for *that* instrument, whatever page you're standing on |
| `/trinity` | All three index books together — SPXW, SPY, QQQ — and whether they agree |
| `/talon` | Setup scan on this page's instrument |
| `/talon TICKER` | Setup scan on one name |
| `/talon sector NAME` | Setup scan across a sector basket |
| `/talon theme NAME` | Setup scan across a cross-sector theme |
| `/talon market` | Setup scan across the index and volatility basket |
| `/clear` | Clear the chat and start a fresh thread |
| `/help` | Terminal commands |

---

### **Scan Scopes**

**Sectors** — `semiconductors` (or `semis`), `energy`, `financials`, `healthcare`, `consumer`, `industrials`. Each basket carries its liquid sector ETFs alongside the names.

**Themes** — `ai`, `crypto`, `china`. These cut across sectors deliberately: the AI basket spans semis, hyperscalers and power.

**Market** — the index and volatility complex: SPXW, SPY, QQQ, IWM, RUT, VIX, SMH, SOXX and the leveraged/vol names.

Ask for a basket Talon doesn't carry and it will tell you the ones it has rather than assembling a list of its own.

---

### **Listed in the Menu, Not Wired Yet**

`/scan`, `/flow`, `/risk`, `/alert` and `/track` appear when you type `/` but have no handling behind them yet.

> **Scan and flow still work if you just ask in plain English.** Risk, alert and track don't do anything today.

## Section 3: 3. Levels and Market Structure

The gamma and vanna book, on demand, for whatever you're looking at.

---

### **Ask**

- `what are the levels?`
- `where's the wall?`
- `what's above and below spot?`
- `/levels TSLA`
- `read the trinity`
- `what's the vanna picture here?`

---

### **What Comes Back**

Spot, the dominant nodes, and which of them sit above and below price.

On a multi-symbol read Talon names the ticker on every level, so "the 1234 pin" is never left floating.

---

### **Sharper**

Ask for the decision rather than the ladder:

- *where does this turn?*
- *which side of the wall are we on?*
- *what has to break for this to run?*

## Section 4: 4. Is That Level Still Good?

A level is not a fixed object. It gets used up.

---

### **Ask**

- `is that node still fresh?`
- `has 227.5 been tested today?`
- `how many times have we tapped that level?`

---

### **What Comes Back**

How many times price has tapped that strike today, and where the level sits in its lifecycle:

**fresh → tested → delivered → spent**

Levels weaken with each tap. That is the difference between a level that should hold and one that has already given you its move.

---

### **Read It Right**

Taps accrue while price is *at* the level, not only when it leaves and comes back.

Price resting on a strike keeps accumulating taps, so a level can read as worked-over without ever having traded away from it.

---

> **Talon will never report a false zero.** If the tap data can't be fetched it says the reading is unavailable — "untested" is the most actionable state, and therefore the most dangerous thing to get wrong.

## Section 5: 5. Options Flow — Three Different Questions

Flow has three levels of resolution. Asking at the wrong one is the most common way to get a thin answer.

---

### **1. The Day's Flow**

- `what's the flow?`
- `is flow bullish or bearish in AMD?`
- `what's active in GOOGL today?`
- `is that a lot for this name?`

Today's totals, how today stacks against the trailing week, and the premium leaders — each carrying volume, open interest, vol/OI ratio, sweep share, and the buy/sell split.

---

### **2. One Strike — The Level You're Staring At**

- `what's the flow at that wall?`
- `show me the flow behind 227.5`
- `is that level being bought or sold?`
- `what's the flow at 600 for the Oct 17 expiry?`

The buy/sell split at that rung, the strikes around it, open interest, average daily volume, and the multiples that make "is this unusual" an answerable question.

---

### **3. The Individual Prints**

- `show me the trades`
- `show me the prints`

Raw prints: time, strike, expiry, type, side, premium, days to expiry, size.

---

### **Sharper — The Three Habits That Matter Most**

**Name the expiration on any strike question.** A gamma node belongs to one expiry. Without a date, Talon scopes to the nearest expiry traded — a different chain, described with the same confidence.

**Ask who initiated, not how big.** Premium is directionless. "$828K on the 32 calls" is the same number whether customers bought them or wrote them, and those two readings point opposite ways — buying leaves dealers short gamma there and the level tends to break; selling leaves them long gamma and it tends to hold.

Ask *who's buying it?* or *is that opening?*

**Ask "is that unusual?"** That phrasing is what pulls in the baselines: volume against the daily average, volume against open interest.

Premium alone tracks what a contract *costs* as much as how busy it is — an expensive contract on an ordinary day can print a big dollar number and mean nothing.

## Section 6: 6. Dark Pool, Positioning, and the Tape

Three quick reads that sit beside the flow.

---

### **Dark Pool and Blocks**

- `any dark pool prints?`
- `any block trades in this name?`

Off-exchange block size over a fixed five-session window.

There's no lookback argument — ask for three months and Talon will tell you it can't rather than guess.

---

### **Positioning Metrics**

- `what's the put/call ratio?`
- `where's max pain?`

---

### **The Tape and the News**

- `how's the tape today?`
- `what's the market doing?`
- `any news on this?`
- `why is it moving?`

Market-wide flow context, or up to five recent articles with the publisher and publication time printed on each.

> **News runs about a week back, from an open set of publishers** — not a whitelist of outlets. That is exactly why the publisher sits beside every headline. Check it.

## Section 7: 7. Company Context and Setup Scans

Everything that isn't the book or the tape: the issuer behind the ticker, the scan that goes looking for setups, and the docs behind the product.

---

### **Company Context**

- `when do they report?`
- `is there event risk this week?`
- `did they beat last quarter?`
- `who are its peers?`
- `how does it compare to the sector?`

**Two things to expect.** There's no before/after-market timing in the underlying data, so Talon gives you the date and won't claim a session.

And index symbols — SPX, SPY, QQQ, VIX and friends — have no issuer behind them, so no earnings date and no peers. Asking gets an honest empty answer rather than an invented one.

---

### **Setup Scans**

- `any setups?`
- `scan semis`
- `what looks good in AI names?`
- `/talon theme crypto`

A scan with strict thresholds.

> **An empty scan is a real answer.** Talon names what it read and reports that nothing qualified rather than loosening the bar.

On a single named ticker with nothing qualifying, it falls back to that name's structure and tells you plainly that's what it's doing.

---

### **Learning the Product**

- `what is a gamma node?`
- `what does a red node mean?`
- `how do I use Atlas?`
- `what's the difference between GEX and VEX?`

Cited answers out of the Skylit docs — including this guide.

If the docs don't cover it, Talon says so instead of improvising, and the gap gets logged so it can be written.

## Section 8: 8. Habits That Pay — Phrasing That Gets Better Answers

Most thin answers are a phrasing problem, not a data problem. These are the habits that fix them.

---

- **Name the expiry** on anything strike-specific.
- **Ask for the side.** "Bought or sold?" beats "how much?"
- **Ask "is that unusual?"** to get the baselines instead of a bare number.
- **Bound your window.** Strike flow defaults to the whole session; say "right now" or "in the last fifteen minutes" if that's what you mean.
- **Switch tickers out loud.** Follow-ups inherit the last name discussed, so say the new one when you move on.
- **Ask for the verdict.** "So what do I do at 600?" gets a decision; "give me the levels" gets a ladder.
- **Push back.** If a number looks wrong, say so — Talon re-fetches and cites rather than defending its last answer.

---

> **Ask for a decision, not a data dump.** That one habit is worth more than the other six.

## Section 9: 9. Beta Limits, and Telling Us It Got Something Wrong

Talon is in Beta. These are the edges you'll hit, stated up front so they don't read as bugs.

---

- **Dark pool is a fixed five-session window.** No custom lookback.
- **Flow totals are single-leg only.** They won't tie out with the all-legs underlying block on the contract chart. Both are right for their own scope, and either one quoted without its scope makes the other look broken.
- **Earnings gives dates, not sessions** — no before or after the bell.
- **News runs about a week back**, from an open set of publishers.
- **Scan baskets are curated.** Talon won't scan your personal watchlist and won't assemble a ticker list of its own.
- **No position sizing, alerts or trade tracking** from chat yet.
- **Talon won't invent a level.** If a read fails it names the instrument it couldn't read. That's a refusal working correctly — but tell us when you hit one.
- **On the Heatseeker and Trinity map pages** Talon runs a trimmed toolset for speed. Everything above works there except raw prints — ask for those from a research, Atlas or flow page.

---

### **Reporting a Bad Answer**

The most useful report is the exact prompt, the page you were on, and what you expected instead.

> *"Talon said the flow at 227.5 was thin, but that strike traded $10M"* — that's a fix.

> *"Talon was wrong about NVDA"* — that isn't actionable.

---

This guide is V1 and will grow as Talon does.
