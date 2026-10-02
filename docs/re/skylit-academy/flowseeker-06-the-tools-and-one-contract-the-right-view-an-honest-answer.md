# The Tools and One Contract: The Right View, an Honest Answer

- Track: flowseeker / category: Confluence
- Level: Intermediate · duration: 20 min
- Passing score: 70 · sections: 8 · quiz questions: 22
- Provenance: https://app.skylit.ai/api/nexus/academy/courses/0af92718-0699-4e13-b7b4-64c96d3632a2 (JSON, captured 2026-10-02, read-only) · course id `0af92718-0699-4e13-b7b4-64c96d3632a2`
- Views/completions at capture: 186/12

## Course description

Each Flowseeker view answers a different question in a different unit: the Live Feed lists prints, the Scanner summarises contracts, the Tracker follows what you saved, and the Dark Feed shows stock trades with no options side. When one contract matters, open Contract Drilldown with a question you can test — its views all come from the same trades — and finish with a hypothesis, a conflict, or "not enough evidence".

## Section 1: Chapter Objective

So far you have worked mostly in the Live Feed. Flowseeker has more views, and they aren't interchangeable. This chapter teaches four things:

1. Each view answers a different question — and counts a different unit
2. What the Scanner, Tracker and Dark Feed each add
3. Investigate one contract with a testable question — several views aren't several confirmations
4. End with one of three honest answers

## Section 2: Different Questions, Different Units

| View | One row is… | The question it answers |
|---|---|---|
| **Live Feed** | One print | What just traded? |
| **Flow Scanner** | One contract | Which contracts are busiest today? |
| **Flow Compass** | A ranked card | What stands out across the market? |
| **Contract Lookup** | A ticker overview | What is happening in this one name? |
| **Contract Drilldown** | One contract in detail | What exactly traded in this contract? |
| **Flow Tracker** | Something you saved | What has the contract done since that print? |
| **Dark Feed** | One off-exchange stock trade | Where did large stock trades print? |

The unit matters. **Volume in the Live Feed** is one print's size. **Volume in the Scanner** is the contract's whole day. **Size in the Dark Feed** is shares of stock. Same word, different things — check the kind of row before you compare.

### Quiz (5 questions)

- Q: In the Live Feed, one row is:
    - One saved trade
    - One contract's whole day
    - One ticker
    - One print
- Q: In the Flow Scanner, one row is:
    - One print
    - One sector
    - One stock trade
    - One contract, rolled up across its prints
- Q: What does "size" mean in the Dark Feed?
    - Shares of stock
    - Premium in dollars
    - Option contracts
    - Number of trades
- Q: A Live Feed print shows 2,000 contracts; the Scanner shows 2,400 for the same contract. What's the right reading?
    - One of the numbers is wrong
    - The Scanner double-counts prints
    - Two different trades of 2,000 and 2,400
    - The print is one trade; the Scanner number is the contract's whole day, which includes it
- Q: A trader says: "SPY volume is 50,000 in the Dark Feed and 2,400 in the Scanner, so stock traders are twenty times more active." What's wrong?
    - The Scanner number should be multiplied by 1,000
    - Nothing — volume is volume
    - Dark Feed size is shares of stock; Scanner volume is option contracts — they can't be compared directly
    - Dark Feed numbers are always wrong

## Section 3: Scanner, Tracker, Dark Feed

**Flow Scanner — contracts.** Each contract's day in one row: volume and open interest, the change in open interest, premium, IV, and how its activity splits between bullish and bearish. Check **when** the open interest is from — late in the day it can still reflect the last clearing.

![The Flow Scanner — one row per contract](https://mintcdn.com/skylit-490c28ef/QU4Pk6SK-6-klbCr/images/image-24.png?fit=max&auto=format&n=QU4Pk6SK-6-klbCr&q=85&s=b240537d51d962b02808c8cddd1caf28)

**Flow Tracker — what you saved.** **Tracked Flow** holds prints you saved from the feed; **Tracked Contracts** holds contracts, saved with the bookmark in Contract Drilldown or **Save Contract** in Contract Lookup. Tracked Contracts shows the contract's current mid and spot. Tracked Flow shows a **P/L %: the current mid against the original print's fill price** — a mark, not your fill and not proof of what the original trader made — plus a status label (still in, partial, exited…) that is the platform's estimate.

**Dark Feed — stock, not options.** Large off-exchange stock trades: time, ticker, price, size in shares, notional, sector. A dark-pool print has no call or put and no bid/ask read — so it's **not bullish or bearish by default**. Use it as context: a price where size traded.

### Quiz (6 questions)

- Q: What are the Flow Tracker's two modes?
    - Tracked Flow and Tracked Contracts
    - Live and Historical
    - Bid and Ask
    - Calls and Puts
- Q: True or false: the Dark Feed shows stock trades, so there is no options side (bid/ask call or put) to read from it.
    - True
    - False
- Q: A print in Tracked Flow shows P/L +40%. What does that mean?
    - The contract's current mid is about 40% away from the print's fill price — a mark, not anyone's realized result
    - The trader's own position made exactly 40%
    - The contract is up 40% since the moment you saved it
    - The original trader made 40%
- Q: Late in the day, the Scanner shows a big "OI change" on a contract. What should the trader check?
    - Nothing — OI updates live
    - Whether the contract is a call
    - Whether the row is green
    - When that open interest is from — it may still reflect the last clearing
- Q: A huge SPY block prints in the Dark Feed near the level the trader is watching. How should they use it?
    - As a bearish signal
    - As context — a price where size traded — alongside the chart and the map
    - As proof that support will hold
    - As a reason to buy calls immediately
- Q: How do you track a contract?
    - By setting a premium floor
    - With the bookmark in Contract Drilldown
    - By typing it into the Dark Feed
    - Contracts can't be tracked

## Section 4: One Contract, a Testable Question

When one contract matters, open **Contract Drilldown** — with a question the evidence could answer **either way**:

| Testable | Not testable |
|---|---|
| "Did open interest grow after the big print?" | "Is this a whale I should follow?" |
| "Is today's activity unusual for this contract?" | "Does someone know something?" |

Look back further than today — a "new buy" can be closing a trade opened weeks ago.

Drilldown gives you several views: **Contract Flow** (volume by bid, mid and ask over time — not a price candlestick), **Net Premium** (check whether it's per bar or a running total), **Strike Distribution**, **Underlying (Vol / $)**, **Vol/OI History** and **Flow Orders**. Select any flow bar to see the prints behind it.

![Contract Drilldown — contract flow, net premium and history](https://mintcdn.com/skylit-490c28ef/QU4Pk6SK-6-klbCr/images/image-31.png?fit=max&auto=format&n=QU4Pk6SK-6-klbCr&q=85&s=e70eee8e60338491f60cf2b13a61522e)

Here's the trap: every one of these views is built from **the same options tape**. Contract Flow shows this contract's trades; Net Premium and Strike Distribution show the whole ticker's chain, which includes them. When they agree, that's **one kind of evidence seen several ways**, not several confirmations. Real confirmation comes from something **different** — next-day open interest, the chart, the map.

### Quiz (6 questions)

- Q: Which question is testable?
    - "Is this going to work?"
    - "Did open interest grow after the big print?"
    - "Does someone know something?"
    - "Is this a whale I should follow?"
- Q: True or false: Contract Flow is a candlestick chart of the option's price.
    - True
    - False
- Q: Why look back further than today when investigating a contract?
    - Today's data isn't available
    - Old data is always more accurate
    - A print that looks like a new buy can be closing an older trade
    - To find a price target
- Q: Contract Flow, Net Premium and Strike Distribution all point bullish after one big ask-side print. How many independent pieces of evidence is that?
    - Three
    - Six
    - About one — they are all views of the same options flow
    - None
- Q: Which of these is different evidence from the Drilldown flow views?
    - Next-day open interest
    - Strike Distribution
    - Net Premium
    - Contract Flow
- Q: Before reading a rising Net Premium line as accumulation, what should you check?
    - Whether the volume is high
    - Whether it is per bar or a running total
    - Whether it is green
    - Whether the contract is a put

## Section 5: End With One of Three Answers

1. **A hypothesis worth keeping** — the evidence fits. Write it down with what would weaken it.
2. **A conflict** — evidence points both ways. Name it and what would settle it.
3. **Not enough evidence** — often the honest answer. It's what stops a story becoming a trade.

A hypothesis without an "I'm wrong if…" can't be checked.

### Quiz (5 questions)

- Q: Which is one of the three honest ways to end an investigation?
    - A guaranteed trade
    - Not enough evidence
    - A price prediction
    - Follow the whale
- Q: What should you write alongside a hypothesis worth keeping?
    - What would weaken it
    - How much you'll make
    - Nothing else
    - Who you think traded
- Q: The flow looks bullish, but open interest fell the next day and price is at the midpoint of its range. What's the best ending?
    - A hypothesis worth keeping — the flow is bullish
    - A conflict — name it and what would settle it
    - Buy calls — flow beats everything
    - Nothing — ignore the contract forever
- Q: The investigation produced a hypothesis worth keeping. What must still happen before any trade?
    - Nothing — the investigation is enough
    - Double the usual size
    - It has to fit the chart and the Heatseeker map
    - Wait for the Flow Score to hit +100
- Q: Which is the best-written hypothesis?
    - "SPY is going to 600."
    - "Big money is bullish on SPY."
    - "New bullish spread positioning at 590–600, supported by open-interest growth; it weakens if OI falls back or price loses the range low."
    - "This is a whale — follow it."

## Section 6: Case Study Example

*Hypothetical — constructed for teaching.*

The SPY 590 call from Tier 1, through the tools:

- **Live Feed:** one row — 2,000 contracts at the ask, $620,000.
- **Scanner:** the contract's whole day — volume 2,400, yesterday's open interest 1,200. The big print is inside that total.
- **Dark Feed:** a large SPY stock block near 581. Tempting to read as support — but it has no side. Context, not a signal.

The trader opens **Drilldown** with a testable question: *"Is this new bullish positioning?"* Contract Flow is mostly ask-side, Net Premium is rising, Strike Distribution clusters at 590 and 600 — but that's **one** kind of evidence — flow — seen three ways. The **open-interest growth** the next day is the independent piece.

Answer: **a hypothesis worth keeping** — *"new bullish spread positioning at 590–600, supported by open-interest growth; it weakens if open interest falls back or price loses the range low."* Then the chart and the map.

## Section 7: Common Mistakes

### Mistake 1 — Comparing numbers from different views

A print's size, a contract's daily volume and a stock block in shares are different units.

---

### Mistake 2 — Reading dark-pool prints as bullish or bearish

They're stock trades with no options side. Context, not direction.

---

### Mistake 3 — Counting Drilldown views as confirmations

They're all built from the same options tape. Agreement is expected, not extra proof.

## Section 8: Key Takeaways

- Each view answers a different question in a different unit. Check the kind of row before comparing.
- Scanner = contracts (check the OI date). Tracker = saved prints marked against their fill, and saved contracts' current mid. Dark Feed = stock trades with no options side.
- Open Drilldown with a testable question, and look back further than today.
- Views built from the same options tape are one kind of evidence.
- End with a hypothesis worth keeping, a conflict, or not enough evidence — with what would change your mind.

***Remember:***

***A large print earns investigation. It does not identify a profitable trade.***
