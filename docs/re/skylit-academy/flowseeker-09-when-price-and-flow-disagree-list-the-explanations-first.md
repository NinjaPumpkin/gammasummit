# When Price and Flow Disagree: List the Explanations First

- Track: flowseeker / category: Advanced
- Level: Advanced · duration: 20 min
- Passing score: 70 · sections: 7 · quiz questions: 24
- Provenance: https://app.skylit.ai/api/nexus/academy/courses/7ceab45d-76c8-43ca-9a83-63e509f532b0 (JSON, captured 2026-10-02, read-only) · course id `7ceab45d-76c8-43ca-9a83-63e509f532b0`
- Views/completions at capture: 106/8

## Course description

Sometimes price goes one way and the flow points the other. Don't pick a winner. State the mismatch, list every explanation that fits it, then look for the evidence that tells them apart. Until something separates them, a disagreement is a reason to reduce size or wait — not a signal.

## Section 1: Chapter Objective

Chapter 7 showed what happens when chart, map and flow agree. This chapter is about when they don't.

Disagreement is where traders make their most confident mistakes. Some decide *"the flow knows something price doesn't."* Others decide *"price is the truth, flow is noise."* Both are guesses dressed as rules.

This chapter teaches three things:

1. State the mismatch precisely
2. List the explanations before choosing one
3. Find the evidence that separates them — and act on the conflict until you do

## Section 2: State the Mismatch

Write the disagreement as an observation, the same way Chapter 1 taught you to write a print:

> *"SPY rejected at 590 twice and is back at it. Over the last 20 minutes, $4M of calls printed at the ask."*

Not:

> *"Smart money is betting on a breakout."*

The first sentence is checkable. The second already picked an answer.

Be precise about **which** flow and **which** price: the ticker, the expiry, the time window, and where price is in the structure. A lot of "disagreements" disappear once you notice the flow is in a different expiry, or was one leg of a spread.

### Quiz (8 questions)

- Q: Which is the better way to state a price–flow disagreement?
    - "Flow says up, so it's going up."
    - "SPY rejected at 590 twice; $4M of calls printed at the ask in the last 20 minutes."
    - "Price is lying."
    - "Smart money is betting on a breakout."
- Q: What should a stated mismatch include?
    - Only the premium
    - The ticker, expiry, time window and where price is in the structure
    - A price target
    - Who the trader was
- Q: Bearish flow seems to disagree with a rally — until the trader notices the puts expire in three months. What happened?
    - The puts are a bet against today's rally that hasn't paid yet
    - The rally is being driven by those puts' dealer hedging
    - The flow was a different time horizon — possibly longer-dated protection, not a bet against today's move
    - It's a disagreement — puts of any expiry are bearish
- Q: A "bearish" call print at the bid turns out to be the sold leg of a bull call spread. What does that do to the disagreement?
    - It gets stronger
    - The spread is bearish
    - That part of the disagreement disappears — the whole trade was bullish
    - Nothing changes
- Q: Why write the mismatch as an observation rather than a conclusion?
    - It doesn't matter
    - Conclusions are always wrong
    - Observations are shorter
    - An observation can be checked later; a conclusion has already chosen an explanation
- Q: Price is at a floor on the map; heavy put buying prints at the ask. What's the first step?
    - Ignore the puts
    - Short immediately — puts are bearish
    - Write down the mismatch precisely — strike, expiry, window, location
    - Buy immediately — the floor always holds
- Q: A trader sees bullish flow in next-month QQQ calls while SPY sells off this morning and calls it a disagreement. What should they check first?
    - Whether SPY is broken
    - Nothing — it's clearly a disagreement
    - Whether the flow and the price move are in the same instrument, expiry and time window
    - Whether QQQ is bullish forever
- Q: True or false: the same prints can fit several explanations — a new bet, protection, closing, part of a structure, or a misread side.
    - True
    - False

## Section 3: List the Explanations

Take the example above: price keeps failing at resistance, but calls are being bought at the ask. What could explain it?

| Explanation | What it means |
|---|---|
| New bullish bets | Traders expect a breakout |
| Protection | Traders who are short the stock buy calls to cap their risk if it breaks out |
| Closing | Traders who **sold** calls earlier buy them back — at the ask — to close |
| Part of a structure | The calls are one leg of a spread whose other leg changes the meaning |
| Misread side | Fills near the mid, or a thin contract, make the side read weak |

All five produce the **same prints**. That's the point. The old idea that *"flow is usually right"* has never been measured — no sample backs it — and even if it were true, it wouldn't tell you which of these five you're looking at.

List them **before** you choose. The one you like best is not evidence.

### Quiz (8 questions)

- Q: Price keeps failing at resistance while calls are bought at the ask. Which is one possible explanation?
    - A guaranteed breakout
    - Traders who are short buying calls as protection
    - A data error, always
    - Dealers predicting the close
- Q: Why list every explanation before choosing?
    - Several explanations produce the same prints — the favorite one isn't evidence
    - To make the read longer
    - Because flow is always right
    - Because price is always right
- Q: Calls are bought at the ask by traders who sold those same calls last week. What is that?
    - A put spread
    - A new bullish bet
    - Protection
    - Closing — buying back to exit, not a new bullish bet
- Q: Someone says: "Flow is usually right, so follow it when it disagrees with price." What's the problem?
    - Price is always right instead
    - Flow is right only when the Flow Score is high
    - Nothing — flow leads price, so it should win disagreements
    - There's no measured sample for "usually right" — and it wouldn't say which explanation applies anyway
- Q: Which set lists the explanations for "price failing at resistance, calls bought at the ask"?
    - New bullish bets or a misread side — nothing else fits ask-side calls
    - New bullish bets, dealer hedging, dark-pool buying
    - New bullish bets, protection, closing, part of a structure, misread side
    - Protection and closing only — calls at resistance can't be new bets
- Q: Why doesn't a large premium settle which explanation is right?
    - Protection, closing and new bets can all be large — size doesn't reveal intent
    - Large premium always means protection
    - Premium is never large enough
    - Large premium always means new bets
- Q: A trader lists explanations but writes only the bullish one down "because it's most likely." What went wrong?
    - Lists aren't useful
    - They should have written only bearish ones
    - Likelihood wasn't measured — dropping the others turns a list into a story
    - Nothing — the most likely one is enough
- Q: Fills in a disagreeing print are right at the mid. What does that add?
    - It confirms the flow is bullish
    - The side read is weak — the "disagreement" may be a misread
    - Nothing
    - It confirms the flow is bearish

## Section 4: Separate Them, and Act on the Conflict Until You Do

Each explanation predicts something different. Look for what would tell them apart:

- **Next-day open interest** — a net drop is consistent with closing; a net rise with new positions (bets or protection). It's net across everyone in that contract, so it's evidence, not proof (Chapter 4)
- **The whole structure** — other legs in the same second (Chapter 3)
- **Expiry** — short-dated calls into resistance read differently from long-dated protection
- **Side quality** — fills at the ask edge versus near the mid (Chapter 2)
- **Price itself** — acceptance above the level versus another rejection
- **The map** — does the ceiling node shrink, or hold?

Some of these arrive today; some, like open interest, arrive tomorrow. Until the evidence separates the explanations, you have a **conflict**, not a read.

And a conflict has a disciplined response:

- **Reduce size**, or
- **Wait** for price to resolve the level, or
- **Pass** — no trade is a valid outcome.

What you don't do is ignore the flow because it's inconvenient, or follow it because it's large.

### Quiz (8 questions)

- Q: Which evidence helps tell buying-to-close from new positions?
    - Next-day open interest
    - The time of day
    - The color of the bar
    - The Flow Score
- Q: Until evidence separates the explanations, what do you have?
    - A guaranteed trade
    - A conflict
    - A confirmed read
    - A signal
- Q: Which is a disciplined response to a conflict?
    - Ignore the flow
    - Reduce size, wait, or pass
    - Double size
    - Follow the biggest print
- Q: SPY has rejected twice at 590, the King Node ceiling, and is back at it. $4M of 2-DTE calls print at the ask. What's the disciplined next step?
    - Buy calls — $4M outweighs two rejections
    - Ignore the chart and the map, and trade with the flow
    - Treat it as a conflict — wait for a clean rejection or acceptance above 590 before committing
    - Short at reduced size now — two rejections and the King Node outweigh one flow burst
- Q: In that setup, what would support the short?
    - Acceptance above 590
    - A clean rejection at 590 with the call flow fading
    - More call buying
    - The ceiling node shrinking
- Q: In that setup, what would support the breakout instead?
    - Price falling to the midpoint
    - A third rejection
    - The call flow stopping
    - Acceptance above 590 with the ceiling node shrinking
- Q: Some separating evidence — like open interest — only arrives tomorrow. What does that mean for today?
    - Trade full size and adjust later
    - Guess today and check tomorrow
    - Today's decision has to respect the conflict — reduce size, wait or pass
    - Open interest doesn't matter
- Q: Which statement is the Skylit way to handle a price–flow disagreement?
    - Split the difference at half size, always
    - Price wins ties
    - State it, list the explanations, find what separates them — and treat it as a conflict until something does
    - Flow wins ties

## Section 5: Case Study Example

*Hypothetical — constructed for teaching.*

**Chart:** SPY has rejected twice at 590 — daily resistance — and is back at it.

**Map:** the **King Node** at 590 is acting as a ceiling. Little exposure below until the midpoint.

**Flow:** repeated calls bought at the ask, totalling **$4M** over twenty minutes, in the 590 strike, 2 DTE.

**The mismatch:** the chart and map favor another rejection; the flow is bullish-looking.

**The explanations:** new breakout bets · shorts buying protection · call sellers buying back · part of a spread · weak side reads.

**What separates them:**

- The Contract Drilldown shows no matching leg — probably not a spread, though a blank field can't rule out a related trade elsewhere.
- Fills are at the ask edge — the side read is solid.
- It's 2 DTE, right at the ceiling — consistent with breakout bets **or** protection, less so with long-term positioning.
- Tomorrow's OI would help separate buying-to-close from new positions — as net evidence, not proof — but that's tomorrow.

**The decision:** a conflict. Shorting a third rejection at full size ignores real evidence. Buying the breakout ignores two rejections and the King Node. The disciplined trader **waits**: a clean rejection with the flow fading supports the short at reduced size; acceptance above 590 with the ceiling node shrinking supports the breakout. Until then — no trade.

## Section 6: Common Mistakes

### Mistake 1 — "The flow knows"

Large prints feel informed. Five different explanations produce the same prints. Size doesn't tell you which one.

---

### Mistake 2 — "Price is the truth, ignore the flow"

Ignoring inconvenient evidence is the same mistake from the other side. A conflict is information — it says reduce size or wait.

---

### Mistake 3 — Choosing an explanation before listing them

The first story you think of feels like the answer. List them all, then look for evidence.

## Section 7: Key Takeaways

- State the mismatch as an observation: which flow, which price, which expiry, which window.
- List every explanation — new bets, protection, closing, structure, misread side — before choosing.
- Look for evidence that separates them: OI, structure, expiry, side quality, price acceptance, the map.
- Until something separates them, it's a conflict: reduce size, wait, or pass.
- No trade is a valid outcome.

***Remember:***

***A large print earns investigation. It does not identify a profitable trade.***
