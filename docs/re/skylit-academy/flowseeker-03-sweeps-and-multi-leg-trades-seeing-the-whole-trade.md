# Sweeps and Multi-Leg Trades: Seeing the Whole Trade

- Track: flowseeker / category: Foundations
- Level: Beginner · duration: 20 min
- Passing score: 70 · sections: 7 · quiz questions: 17
- Provenance: https://app.skylit.ai/api/nexus/academy/courses/650c0480-061e-43db-9e99-c98ad8c73b35 (JSON, captured 2026-10-02, read-only) · course id `650c0480-061e-43db-9e99-c98ad8c73b35`
- Views/completions at capture: 199/22

## Course description

Some prints are pieces of something bigger. A sweep is one order split across several exchanges — it shows urgency, not intent. A multi-leg trade is several contracts traded together — and one leg on its own can look like a completely different bet. Read the whole trade before you name it.

## Section 1: Chapter Objective

So far you have read one print at a time: what traded and where it filled (Chapter 2).

But a print is not always a whole trade. Sometimes it is a **piece** of one. This chapter teaches three things:

1. What a sweep is
2. Why a sweep shows urgency, not intent
3. Why one leg of a multi-leg trade can mislead you

## Section 2: What a Sweep Is

A trader who wants a large number of contracts **right now** often can't get them all at one exchange. There isn't enough size offered at the best price in one place.

So the order is split. It **sweeps** across several exchanges at once, taking what is available at each.

On the tape, that shows up as several prints on the **same contract**, in the **same moment**, at different venues.

Flowseeker puts those pieces back together. Prints on the same contract within **one second** are grouped into a single **sweep**, with the total contracts and total premium. So instead of five small prints, you see one trade.

You can show only sweeps with the **Sweeps Only** toggle in the Live Feed filters:

![The Live Feed special toggles — Sweeps Only, Multi-Leg Only and Single-Leg Only are here](https://mintcdn.com/skylit-490c28ef/QU4Pk6SK-6-klbCr/images/image-20.png?fit=max&auto=format&n=QU4Pk6SK-6-klbCr&q=85&s=c90864529aec9190fbcdf8b3effcf769)

### Quiz (5 questions)

- Q: What is a sweep?
    - A trade on the most active ticker of the day
    - A position closed at the end of the day
    - A trade that filled below the bid
    - One order split across several exchanges at once
- Q: Why does an order get split into a sweep?
    - One exchange doesn't have enough contracts at the best price
    - To guarantee a better price
    - Because the trade is a spread
    - Exchanges require every order to be split
- Q: Flowseeker groups prints into one sweep when they are:
    - On any contract, within one minute
    - On the same strike, any expiration
    - On the same contract, within one second
    - On the same ticker, within one day
- Q: Five small prints on the same contract hit five exchanges in the same second. How does Flowseeker show them?
    - As five unrelated trades
    - As one sweep, with the total contracts and premium
    - As a multi-leg spread
    - As a cancelled trade
- Q: Where can you show only sweeps in the Live Feed?
    - The Heatseeker map
    - The Sweeps Only toggle in the filters
    - The ticker search box
    - Sweeps can't be filtered

## Section 3: Urgency, Not Intent

A sweep tells you one thing clearly: **someone didn't want to wait.** They took size from several places at once rather than work the order slowly.

That is useful. It is also where the clue stops.

An urgent trader can be:

- opening a new bet
- closing a position they already had
- hedging something else
- filling one piece of a bigger trade

All four can sweep. The sweep shows **how** the order was filled — not **why**.

You will hear claims like *"sweeps always mean smart money"* or *"sweepers always know something."* Those are stories, not observations. A sweep is urgency. Treat it as a stronger clue than a single print — and still only a clue.

### Quiz (6 questions)

- Q: What does a sweep tell you most clearly?
    - The trader is opening a new position
    - Someone didn't want to wait
    - Someone knows where price is going
    - The trade will be profitable
- Q: True or false: a sweep proves the trader is opening a new bet.
    - True
    - False
- Q: Which of these could be a sweep?
    - A new bet, a close, a hedge, or one piece of a bigger trade
    - Only a new bearish bet
    - Only a new bullish bet
    - Only a hedge
- Q: Someone says: "Sweeps always mean smart money." What's the problem?
    - Sweeps are too small to matter
    - Sweeps only happen on puts
    - Nothing — sweeps are always smart money
    - It's a story, not an observation — a sweep shows urgency, not who traded or why
- Q: Compared with a single print, a sweep is best treated as:
    - Proof of the trader's intent
    - A stronger clue — but still only a clue
    - Less meaningful than a single print
    - A trade signal
- Q: A large call sweep prints. Before acting, what should the trader check?
    - Nothing — a call sweep is a buy signal
    - Whether it fits the chart and the Heatseeker map
    - Whether it is over $1M
    - Whether a second sweep prints

## Section 4: One Leg Can Mislead

Many traders don't buy a single contract. They trade **several contracts together** as one position. That is a **multi-leg trade**.

The danger: each leg prints on its own. Read one leg by itself and you can get the whole trade wrong.

Two common examples:

| Trade | What it is | What one leg looks like on its own |
|---|---|---|
| **Vertical spread (bull call)** | Buy one call, sell a higher call — same expiry | The bought leg looks like a big bullish bet; the sold leg looks like call selling. Together: a **bullish trade with a capped upside** |
| **Long straddle** | Buy a call and a put — same strike, same expiry | The call looks bullish; the put looks bearish. Together: a bet on a **big move either way** |

A bull call vertical is still bullish — just limited. (Verticals can also be bearish — e.g. buy a put, sell a lower put.) A long straddle isn't really bullish or bearish at all.

Flowseeker tries to detect multi-leg trades and group the legs, and you can filter with **Multi-Leg Only** or **Single-Leg Only**. But detection is not perfect — not every strategy can be identified with certainty. When a large print appears, look for other prints on the same ticker and expiry in the same moment before you name the trade.

### Quiz (6 questions)

- Q: What is a multi-leg trade?
    - Several contracts traded together as one position
    - One contract traded several times in a day
    - A trade held for several days
    - A trade split across exchanges
- Q: A trader buys a SPY 590 call and sells a SPY 600 call, same expiry. What is the whole trade?
    - A bullish spread with capped upside
    - Two unrelated trades
    - A bet on a big move either way
    - A bearish bet
- Q: A trader buys a call and a put at the same strike and expiry. What is the whole trade?
    - A straddle — a bet on a big move either way
    - A hedge that cancels out to nothing
    - A bullish bet
    - A bearish bet
- Q: True or false: a bull call vertical spread is still a bullish trade, even though it has two legs.
    - True
    - False
- Q: A big call print appears. What should you look for before naming the trade?
    - Other prints on the same ticker and expiry in the same moment
    - Nothing — one print is the whole trade
    - The day's biggest put print
    - Yesterday's close
- Q: How reliable is Flowseeker's multi-leg detection?
    - Only for puts
    - Helpful, but not every strategy can be identified with certainty
    - It doesn't detect multi-leg trades
    - Perfect — every spread is always detected

## Section 5: Case Study Example

*Hypothetical — constructed for teaching, not a historical trade.*

Back to the SPY print from Chapter 2: 2,000 SPY 590 calls, 12 DTE, filled at the ask for $620,000. First read: *possible call buying.*

Now look at what else printed **in the same second**:

- **2,000 SPY 600 calls**, same expiry, filled **at the bid** at $0.90 — $180,000

Read alone, that second print looks like someone *selling* calls. Read together, the picture changes:

- Bought the 590 calls, sold the 600 calls, same size, same expiry
- That is a **bull call vertical spread**
- Net cost: $620,000 − $180,000 = **$440,000**

The trade is still bullish. But the most it can make is capped at the 600 strike — a very different trade from "$620K of calls."

And still, following Chapter 1: before any of this matters, does it fit the chart and the Heatseeker map?

## Section 6: Common Mistakes

### Mistake 1 — Treating a sweep as proof

A sweep shows urgency. It does not show whether the trader was opening, closing or hedging. Keep it as a strong clue, not a verdict.

---

### Mistake 2 — Reading one leg as the whole trade

A big call print might be half of a spread. Look for other prints on the same ticker and expiry in the same moment before naming it.

---

### Mistake 3 — Calling every multi-leg trade neutral

Some are, some aren't. A bull call spread is still bullish. A straddle is a bet on movement, not direction. Name the structure before you name the direction.

## Section 7: Key Takeaways

- A sweep is one order split across several exchanges. Flowseeker groups prints on the same contract within one second into one sweep.
- A sweep shows urgency — not whether the trader was opening, closing or hedging.
- A multi-leg trade is several contracts traded together. One leg on its own can look like a different bet.
- A vertical spread is directional but capped. A straddle is a bet on movement either way.
- Multi-leg detection helps, but it isn't perfect. Look at the whole trade before naming it.

***Remember:***

***A large print earns investigation. It does not identify a profitable trade.***
