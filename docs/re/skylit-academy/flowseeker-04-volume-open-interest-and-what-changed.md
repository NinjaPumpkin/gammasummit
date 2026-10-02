# Volume, Open Interest and What Changed

- Track: flowseeker / category: Foundations
- Level: Beginner · duration: 20 min
- Passing score: 70 · sections: 7 · quiz questions: 17
- Provenance: https://app.skylit.ai/api/nexus/academy/courses/561eed43-fcfe-46b2-bfe4-9a6ebaddf97a (JSON, captured 2026-10-02, read-only) · course id `561eed43-fcfe-46b2-bfe4-9a6ebaddf97a`
- Views/completions at capture: 214/20

## Course description

Volume counts contracts traded today. Open interest counts contracts still open, as of the last clearing. Volume above open interest makes a contract worth a look — it doesn't prove new positions. The next day's open interest can support a read, but it never tells you who traded.

## Section 1: Chapter Objective

Every chapter so far has left one question open: did a print **open** a new position, or **close** an old one?

A print can't tell you. But two numbers — **volume** and **open interest** — give you evidence. This chapter teaches three things:

1. What volume and open interest each count
2. Why volume above open interest is worth a look, but not proof
3. How the next day's open interest supports a read — and where it stops

This is the last chapter of Tier 1.

## Section 2: Volume Versus Open Interest

Two numbers, two different things:

- **Volume** — how many contracts **traded** today. Every trade adds to it.
- **Open interest (OI)** — how many contracts are **still open**, as of the last time trades were cleared. Usually that is yesterday's close.

Think of a parking garage. Volume is how many cars drove through the gate today. Open interest is how many cars were parked inside when it last counted — last night.

Two things follow:

- The same contract can trade many times in a day. Volume can be huge while the number of open positions barely moves.
- Open interest doesn't update live. The OI you see during the day is usually **yesterday's** number. Today's trades show up in OI **tomorrow**.

### Quiz (6 questions)

- Q: What does volume count?
    - The total premium traded
    - How many contracts traded today
    - How many contracts are still open
    - How many traders bought
- Q: What does open interest count?
    - How many contracts traded today
    - How many contracts are still open, as of the last clearing
    - How many sweeps printed
    - How many traders are interested in a contract
- Q: During the trading day, the open interest you see is usually:
    - Updated with every trade
    - Yesterday's number
    - The same as today's volume
    - Tomorrow's estimate
- Q: True or false: open interest updates live with every trade.
    - True
    - False
- Q: In the parking-garage comparison, open interest is:
    - How many cars drove through the gate today
    - How fast the cars were going
    - Who owns the cars
    - How many cars were parked inside at the last count
- Q: Can volume be very high while open interest barely changes?
    - Only on expiration day
    - Only for puts
    - No — volume always adds to open interest
    - Yes — the same contracts can be opened and closed many times in a day

## Section 3: Volume Above OI Is Worth a Look, Not Proof

When today's volume is bigger than yesterday's open interest, something unusual is happening at that contract. More contracts have traded today than were open to begin with.

Flowseeker lets you find these with two toggles in the Live Feed filters:

- **Volume > OI** — contracts where today's volume is above open interest
- **Size > OI** — single prints bigger than open interest

![The Live Feed special toggles — Volume > OI and Size > OI are here](https://mintcdn.com/skylit-490c28ef/QU4Pk6SK-6-klbCr/images/image-20.png?fit=max&auto=format&n=QU4Pk6SK-6-klbCr&q=85&s=c90864529aec9190fbcdf8b3effcf769)

These are good ways to find contracts **worth investigating**. But they don't prove new positions were opened.

Here is why. Say a contract has **100** open yesterday. This morning, **500** new contracts are opened (buyer and seller both opening). This afternoon, those same **500** are closed (buyer and seller both closing).

- Volume today: **1,000** — ten times the OI
- Open interest tomorrow: still **100**

Huge volume, big prints — and nothing new stayed open. The afternoon prints were closes — even a single afternoon print of 500 would have been five times yesterday's OI.

### Quiz (5 questions)

- Q: What does it mean when today's volume is above yesterday's open interest?
    - The trade will be profitable
    - New positions were definitely opened
    - The contract is worth a closer look
    - The contract is about to expire
- Q: True or false: contracts opened earlier today can be closed later today, adding volume without adding open interest.
    - True
    - False
- Q: A contract has 100 open. In the morning, 500 new contracts are opened with both sides opening; in the afternoon, those same 500 are closed with both sides closing. What is tomorrow's open interest?
    - 0
    - 600
    - 100
    - 1,100
- Q: Which Live Feed toggle shows single prints bigger than open interest?
    - OTM Only
    - Size > OI
    - Sweeps Only
    - Multi-Leg Only
- Q: A contract shows up under Volume > OI. What should the trader do first?
    - Check whether it fits the chart and the Heatseeker map
    - Buy the same contract immediately
    - Ignore it — volume doesn't matter
    - Assume new positions were opened

## Section 4: Next-Day OI Supports; It Doesn't Identify

The clearer evidence comes a day later, when open interest updates.

Every contract traded has a buyer and a seller. Whether OI moves depends on whether each side was opening or closing:

| Buyer | Seller | Open interest |
|---|---|---|
| Opening | Opening | Goes **up** |
| Opening | Closing | No change |
| Closing | Opening | No change |
| Closing | Closing | Goes **down** |

So when OI **rises** the next day, more positions were opened than closed at that contract. That **supports** a read that someone built a position there.

It still doesn't tell you:

- **who** opened it
- **which side** they were on — buyer or seller
- **why** — a bet, a hedge, or part of a spread

Next-day OI makes a read stronger. It doesn't finish it.

### Quiz (6 questions)

- Q: When does open interest usually reflect today's trades?
    - Instantly
    - Never
    - The next day
    - At the end of the week
- Q: A buyer opens a new position and the seller also opens a new position. What happens to open interest?
    - It goes down
    - It stays the same
    - It resets to zero
    - It goes up
- Q: A buyer opens a new position and the seller closes an old one. What happens to open interest?
    - It stays the same
    - It goes down
    - It goes up
    - It doubles
- Q: Open interest on a contract rises the next day. What does that support?
    - A specific fund bought the calls
    - Every print yesterday was a buyer
    - Price will rise
    - More positions were opened than closed at that contract
- Q: True or false: rising next-day open interest supports a read that positions were built, but it does not say who built them.
    - True
    - False
- Q: Which of these can next-day open interest not tell you?
    - The net change in open positions
    - Whether open positions rose or fell
    - Whether the new positions were bets, hedges or parts of spreads
    - That more contracts are open than yesterday

## Section 5: Case Study Example

*Hypothetical — constructed for teaching, not a historical trade.*

The SPY 590 call from Chapters 2–3 one last time. So far: 2,000 contracts at the ask, $620,000, and in Chapter 3 it turned out to be the bought leg of a bull call spread.

Now the numbers around it:

- **Yesterday's OI** on the 590 call: **1,200**
- **Today's volume**: **2,400** — including our 2,000

Volume is twice yesterday's OI, so the contract shows up under **Volume > OI**. Worth a look — not proof.

**The next day**, OI on the 590 call updates to **3,100** — up **1,900**.

That supports the read that most of today's trading **opened** positions that were still held overnight. It fits the spread from Chapter 3 staying on.

It still doesn't say who, and it came a day late. And — as always — before any of it matters, the trade has to fit the chart and the Heatseeker map.

**That is Tier 1.** You can now read a print, its side, whether it is part of something bigger, and what volume and OI add. Tier 2 puts those pieces to work.

## Section 6: Common Mistakes

### Mistake 1 — Treating Volume > OI as proof of new positions

Contracts opened earlier today can be closed later today. Big volume against OI makes a contract worth a look. It doesn't prove anything stayed open.

---

### Mistake 2 — Reading today's OI as live

The OI you see during the day is usually yesterday's number. Today's trades show up in tomorrow's OI.

---

### Mistake 3 — Thinking rising OI names the trader

Rising OI means more positions opened than closed. It doesn't tell you who, which side, or why.

## Section 7: Key Takeaways

- Volume counts contracts traded today. Open interest counts contracts still open as of the last clearing — usually yesterday.
- Volume above OI makes a contract worth investigating. It doesn't prove new positions.
- Positions opened and closed on the same day add volume but leave OI unchanged.
- Rising OI the next day supports a read that positions were built. It doesn't identify who, which side or why.
- Evidence builds up. No single number finishes the read — and the chart and the map still come first.

***Remember:***

***A large print earns investigation. It does not identify a profitable trade.***
