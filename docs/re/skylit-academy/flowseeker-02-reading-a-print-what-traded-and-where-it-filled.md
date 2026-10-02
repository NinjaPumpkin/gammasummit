# Reading a Print: What Traded and Where It Filled

- Track: flowseeker / category: Foundations
- Level: Beginner · duration: 20 min
- Passing score: 70 · sections: 8 · quiz questions: 20
- Provenance: https://app.skylit.ai/api/nexus/academy/courses/959cfbc3-2c87-42e6-b5a3-67547e89ea1d (JSON, captured 2026-10-02, read-only) · course id `959cfbc3-2c87-42e6-b5a3-67547e89ea1d`
- Views/completions at capture: 482/29

## Course description

Read a print correctly before you interpret it: the exact contract, the premium (not just the size), how far from spot and expiration it traded — and where it filled against the bid and ask. Those fields narrow what a trade could be. They never tell you who made it.

## Section 1: Chapter Objective

Chapter 1 set the order: the chart, then the map, then flow — and flow as evidence, not a verdict.

Evidence is only useful if it is read correctly. This chapter takes one print apart and teaches four things:

1. Identify the exact contract — and the spot it traded against
2. Lead with premium, not size
3. Use distance and time to narrow the possibilities
4. Read where the fill happened — and read it together with call or put

## Section 2: Identify the Contract

A print is a record of one executed options trade. Think of it as a receipt: it tells you exactly what changed hands, how much, and when. It does not tell you why.

A contract is defined by four fields:

1. **Underlying** — the ticker, such as SPY or TSLA
2. **Expiration** — the date it expires
3. **Strike** — the price it is written against
4. **Type** — call or put

Change any one of them and it is a **different contract**. A TSLA 260 call expiring Friday and one expiring next month have different horizons and usually very different reasons behind them. Don't add them together.

Flowseeker also records **spot at execution** — where the underlying was trading when the print filled. Always read the strike against *that* price. The print doesn't change when the market moves later.

![The Live Feed column headers — each field has its own column](https://mintcdn.com/skylit-490c28ef/QU4Pk6SK-6-klbCr/images/image-14.png?fit=max&auto=format&n=QU4Pk6SK-6-klbCr&q=85&s=e4394e026719ea364cda272411cf3f41)

One last check: a trade the exchange later voided shows **struck through with a CANCELLED badge**. A cancelled print did not happen.

### Quiz (5 questions)

- Q: What is a print?
    - A forecast of where price is heading
    - An order waiting to be filled
    - A summary of the day's flow
    - A record of one executed options trade
- Q: Which four fields define an options contract?
    - Underlying, strike, size, and premium
    - Underlying, expiration, strike, and call or put
    - Ticker, spot, strike, and side
    - Underlying, premium, time, and size
- Q: A TSLA 260 call expiring Friday and a TSLA 260 call expiring next month both print. Are they the same contract?
    - Yes — same ticker, strike and call
    - Yes, if they are the same size
    - Only if they filled at the same price
    - No — a different expiration makes it a different contract
- Q: You are reviewing a print from earlier in the day. Which price do you measure its strike against?
    - The spot price when the print filled
    - The day's opening price
    - Yesterday's close
    - The current price
- Q: A print is struck through with a CANCELLED badge. What should the trader do with it?
    - Count it at half weight
    - Treat it as bearish
    - Ignore it — the trade was voided and did not happen
    - Treat it as bullish

## Section 3: Premium, Not Size

- **Size** is the number of contracts.
- **Premium** is the total dollars exchanged.

> **Premium = fill price × contracts × 100**

| | Print A | Print B |
|---|---|---|
| Contracts | 1,000 | 500 |
| Fill | $0.25 | $8.00 |
| **Premium** | **$25,000** | **$400,000** |

Print A has twice the size. Print B has sixteen times the money. Size rewards cheap contracts traded in bulk; premium measures dollars actually committed — so lead with premium.

Two limits: **premium is not risk** (a seller, a hedge or a spread leg carries different risk at the same premium), and **premium doesn't prove who traded** — a large print is a large print.

### Quiz (5 questions)

- Q: How is premium calculated for a standard equity option?
    - Fill price × contracts
    - Fill price × contracts × 100
    - Strike × contracts
    - Strike × 100
- Q: A print fills 300 contracts at $2.40. What is the premium?
    - $720,000
    - $72,000
    - $720
    - $7,200
- Q: Print A is 5,000 contracts at $0.10. Print B is 400 contracts at $6.50. Which committed more premium?
    - It cannot be worked out
    - They are about the same
    - Print B — $260,000 against $50,000
    - Print A — it has more contracts
- Q: True or false: a large print proves an institution made the trade.
    - True
    - False
- Q: What does size mean on a print?
    - The strike price
    - The days until expiration
    - The total dollars exchanged
    - The number of contracts

## Section 4: Distance and Time Narrow; They Don't Name

**Moneyness** is the distance from spot as a percentage. $5 is about **0.86%** of a $580 stock and **2.5%** of a $200 stock. In Flowseeker, **positive means out of the money**, negative means in the money, and near zero means close to spot.

**DTE** — days to expiration — is the time horizon:

- **0–7 DTE** — this week: event activity, very short-term positioning
- **8–30 DTE** — the classic window for positioning ahead of a move
- **31+ DTE** — longer horizons, where hedging becomes more common

These are **filters, not labels**. A 60-day put can be a hedge, a directional view, or one leg of a package. A 0DTE print isn't automatically retail.

### Quiz (5 questions)

- Q: In Flowseeker, what does a positive moneyness percentage mean?
    - The trade was profitable
    - The contract is out of the money
    - The contract is a call
    - The contract is in the money
- Q: What does DTE tell you?
    - How far the strike is from spot
    - How many days until the contract expires
    - How much premium traded
    - Whether the trade was a buy or a sell
- Q: True or false: DTE and moneyness narrow what a print could be, but they do not tell you who traded it.
    - True
    - False
- Q: A large put prints. What does the print alone tell you about why it was traded?
    - It is always a hedge
    - It is a bet that price will crash
    - Nothing — it could be a hedge, a bearish bet, or part of a bigger trade
    - The buyer knows price will fall
- Q: A moneyness reading is close to zero. What does that tell you?
    - The contract has no premium
    - The contract has expired
    - The strike is close to spot
    - The strike is far from spot

## Section 5: Side: Where the Fill Happened

Every option has a **bid** (the highest price someone will pay) and an **ask** (the lowest price someone will sell at). The **mid** is halfway between.

A trader who needs to buy *now* pays the ask. A trader who needs to sell *now* hits the bid. Flowseeker labels each print with where it filled, and groups those labels into three buckets:

- **Bid side** — below, at, or just above the bid
- **Mid** — at the mid
- **Ask side** — just below, at, or above the ask

Side tells you **who was in a hurry** — it is a clue, not proof. Fills right at the edges say more than fills near the mid, and in a thin contract a patient buyer can fill at the bid.

Side only means something **together with call or put**:

| Print | First read |
|---|---|
| Call at the ask | Possible call buying |
| Call at the bid | Possible call selling |
| Put at the ask | Possible put buying |
| Put at the bid | Possible put selling |
| At the mid | Not enough for a clean read |

**Ask side is not the same as bullish.** A put bought at the ask is a bearish first read.

### Quiz (5 questions)

- Q: A trader needs to buy an option right now. Where are they most likely to fill?
    - At the ask
    - Below the bid
    - At the strike
    - At the bid
- Q: What does side tell you?
    - Exactly who bought and who sold
    - Where the trade filled against the bid and ask — a clue about who was in a hurry
    - Whether the trade opened or closed a position
    - Where price will go next
- Q: A put filled at the ask. What is the first read?
    - Bullish, because it filled at the ask
    - No read is possible for puts
    - Possible put buying — a bearish first read
    - Possible put selling
- Q: True or false: filtering the Live Feed to ask side only shows bullish trades.
    - True
    - False
- Q: You've read a print correctly — contract, premium, moneyness, DTE and side. What comes next, before acting?
    - Buy the same contract
    - Double your usual size
    - Treat it as a trade signal
    - Check it against the chart and the Heatseeker map

## Section 6: Case Study Example

*Hypothetical — constructed for teaching, not a historical trade.*

A large SPY print hits the Live Feed. Read it field by field:

- **Contract:** SPY 590 call, 12 DTE
- **Spot at execution:** 581.40
- **Size and fill:** 2,000 contracts at $3.10 — with the bid at $3.00 and the ask at $3.10
- **Premium:** 2,000 × $3.10 × 100 = **$620,000**
- **Moneyness:** about **1.5% out of the money**
- **Side:** filled at the ask — a **call at the ask**: *possible call buying*

What the trader still doesn't know: whether it's part of a bigger trade (Chapter 3), whether it opened or closed a position (Chapter 4), and — first of all — whether it fits the chart and the map (Chapter 1).

The print is worth investigating. It is not yet worth acting on.

## Section 7: Common Mistakes

### Mistake 1 — Reading the strike against current price

Distance is measured from spot **when the print filled**, not where price sits now.

---

### Mistake 2 — Treating size as the headline

Ten thousand contracts at $0.05 is $50,000 — often less than a few hundred contracts nearer the money. Lead with premium.

---

### Mistake 3 — Reading "ask side" as "bullish"

Ask side means someone paid up. If it's a put, the first read is bearish. Always read side with call or put.

## Section 8: Key Takeaways

- Four fields define a contract: underlying, expiration, strike, call or put. Read the strike against **spot at execution**.
- Premium = fill × contracts × 100. Lead with premium, not size — and premium is not risk.
- Positive moneyness is out of the money. DTE and moneyness narrow the possibilities; they never name the trader.
- Side shows who was in a hurry — a clue, not proof. Read it with call or put; ask side is not bullish.

***Remember:***

***A large print earns investigation. It does not identify a profitable trade.***
