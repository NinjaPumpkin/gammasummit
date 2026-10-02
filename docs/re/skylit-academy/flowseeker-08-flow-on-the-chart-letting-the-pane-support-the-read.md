# Flow on the Chart: Letting the Pane Support the Read

- Track: flowseeker / category: Advanced
- Level: Advanced · duration: 20 min
- Passing score: 70 · sections: 7 · quiz questions: 24
- Provenance: https://app.skylit.ai/api/nexus/academy/courses/3f4c04d6-7476-4429-ab63-d8fb2fdfc243 (JSON, captured 2026-10-02, read-only) · course id `3f4c04d6-7476-4429-ab63-d8fb2fdfc243`
- Views/completions at capture: 122/10

## Course description

Atlas can show flow in a pane under the price chart. The bars show premium — dollars — not contracts, with calls and puts kept separate. Filter the pane the way you filter a feed, and use it to ask "did premium show up at my level?" — not to find entries on its own.

## Section 1: Chapter Objective

Everything so far has kept flow and the chart in separate windows. Atlas puts them together: price on top, flow underneath, on the same timeline.

That is genuinely useful — you can see whether money arrived **at** the level you care about. It is also the easiest place to fool yourself, because anything lined up under a candle starts to look like the reason the candle moved.

This chapter teaches three things:

1. What the flow pane shows — and what its bars measure
2. Filter the pane like a feed
3. Use the pane to support the read, not replace it

## Section 2: What the Pane Shows

Add the **Flow** pane in Atlas and it appears under the price chart, on the same time axis.

Two things to know before you read it:

- **The bars show premium, not volume.** A tall bar is a lot of **dollars**, not necessarily a lot of contracts. Chapter 2 applies: a few expensive contracts can make a taller bar than thousands of cheap ones.
- **Calls and puts are shown separately** — calls above the zero line, puts below. Atlas can also show a call-minus-put Net, but that is a difference, not "total bullish flow". Don't add them up in your head into one "flow" number — a big call bar next to a big put bar could be two sides of a hedge or a straddle (Chapter 3).

Because the pane shares the chart's timeline, you can ask a precise question: **when price reached my level, what flow arrived there?**

### Quiz (8 questions)

- Q: What do the bars in the Atlas flow pane show?
    - Premium — dollars
    - Number of contracts
    - Number of trades
    - Open interest
- Q: True or false: the flow pane's bars show premium, so a few expensive contracts can make a taller bar than thousands of cheap ones.
    - True
    - False
- Q: How does the pane show calls and puts?
    - Added together into one bar
    - Separately
    - Only puts
    - Only calls
- Q: A big call bar and a big put bar print at the same moment. What could that be?
    - Both sides of a hedge or a straddle — look at the whole trade
    - Definitely bearish
    - A data error
    - Definitely bullish
- Q: Why is it useful that the pane shares the chart's timeline?
    - It removes the need for the map
    - You can see what flow arrived when price reached your level
    - It shows who traded
    - It predicts the next candle
- Q: A short bar of expensive contracts sits next to a tall bar of cheap ones. What should the trader remember?
    - Cheap contracts are always smart money
    - The tall bar is always more important
    - Short bars should be ignored
    - Bar height is dollars — compare premium, not assumed contract counts
- Q: A trader adds the call bar and the put bar together and calls it "total bullish flow." What's wrong?
    - Nothing — the Net line already does this, so adding them is fine
    - They should subtract puts from calls and call the result conviction
    - Nothing, as long as the Side filter is set to Ask
    - Put premium isn't bullish by default, and a call-and-put pair may be one hedged trade — keep them separate
- Q: What question is the pane best at answering?
    - "Where will price be at the close?"
    - "Who is trading?"
    - "Which bar should I trade?"
    - "When price reached my level, what flow arrived there?"

## Section 3: Filter the Pane Like a Feed

The pane has its own filters, set as **pill groups**:

| Group | Pills |
|---|---|
| Legs | Single · Multi |
| Moneyness | ITM · ATM · OTM |
| Side | Bid · Mid · Ask |
| Sweeps | Sweep · Non-Sweep |
| DTE | Minimum / maximum |
| Premium | Minimum / maximum |
| Flow Score | Minimum strength |

Each group keeps **at least one pill on**. With every pill in a group on, that group isn't filtering anything.

Everything from Chapter 5 carries over:

- Build the pane around one question.
- Change one group at a time.
- Remember the pane shows what you let through. Switch Side to **Ask** only and the pane will look like buying — because you filtered out the bid and mid prints, not because nobody sold.

### Quiz (8 questions)

- Q: How are the flow pane's filters set?
    - As pill groups
    - They can't be filtered
    - Only by ticker
    - With a single on/off switch
- Q: In a pill group, what happens when every pill is on?
    - Nothing shows
    - Only calls show
    - The pane resets
    - That group isn't filtering anything
- Q: Can you turn every pill in a group off?
    - Yes — it shows everything
    - No — at least one stays on
    - Only in the Side group
    - Yes — it hides the pane
- Q: A trader sets the Side group to Ask only and sees mostly buying in the pane. What should they conclude?
    - Bid-side prints don't exist
    - The market is only buying today
    - The filter is broken
    - The pane looks like buying partly because the filter removed bid- and mid-side prints
- Q: A trader changes Legs, Side and Premium at once, and the pane goes almost empty. What's the best next step?
    - Turn off the pane
    - Add more filters
    - Change one group at a time and look after each
    - Assume nothing traded
- Q: Which pill group would you use to hide multi-leg trades from the pane?
    - Sweeps — Sweep only
    - Legs — Single only
    - Moneyness — OTM only
    - Side — Ask only
- Q: Why might a trader deliberately keep Multi legs on while studying a level?
    - Multi-leg prints are excluded from premium totals anyway
    - To make sure the Flow Score filter has enough prints to rank
    - Because multi-leg trades are usually closing trades
    - A big print at the level might be one leg of a spread — seeing the other legs changes the read
- Q: What's the best way to set up the pane?
    - Copy someone else's settings without a question
    - Around one question, changing one group at a time
    - Every pill off except Ask and Calls
    - Whatever makes the pane look most active

## Section 4: Support the Read, Don't Replace It

The chart forms the thesis. The pane can support it.

**Good uses:**

- *"Price tested the range low — did meaningful premium show up there?"*
- *"Is today's activity at this level bigger than it was on earlier tests?"*
- *"Did flow change after price broke the level?"*

**Bad uses:**

- *"A tall call bar printed — buy."*
- *"Every rally started with a call spike, so spikes predict rallies."*

That last one is the **hindsight trap**. Looking back, you remember the spikes that came before moves and forget the ones that came before nothing. On a chart, every coincidence looks like cause.

So keep the order: find the level on the chart, confirm it on the map, **then** look at the pane to see whether flow supports it. Entries and invalidation still come from structure.

### Quiz (8 questions)

- Q: Where do entries and invalidation come from?
    - The Flow Score
    - Chart structure
    - The pane's colors
    - The tallest flow bar
- Q: Which is a good use of the pane?
    - Replacing the chart
    - Checking whether premium showed up when price tested a level
    - Buying every tall call bar
    - Predicting the close
- Q: What is the hindsight trap?
    - Remembering spikes before moves and forgetting spikes before nothing
    - Using the Historical mode
    - Looking at yesterday's chart
    - Filtering by DTE
- Q: A tall call bar prints while price sits in the middle of the range. What's the read?
    - No setup — location comes first, and a bar can't create one
    - Short — midpoint bars always fail
    - Buy — a tall bar means a rally
    - Confluence
- Q: Price tests the range low, which is a floor on the map, and a tall call bar prints there. What does the bar add?
    - Support for the floor read — the trade still needs price to hold, with invalidation below
    - Nothing, because a call bar can't tell you who bought it
    - A reason to move the invalidation lower to give the trade room
    - A reason to enter now — premium at the level is the confirmation
- Q: In what order should the chart, the map and the pane be read?
    - Chart, then map, then the pane
    - Pane only
    - Map, then pane, then chart
    - Pane, then chart, then map
- Q: A trader says: "On my last five winning days, a call spike came first — so spikes predict rallies." What's missing?
    - A higher premium floor
    - The days a spike came before nothing — they looked only at the winners
    - More filters
    - Nothing — five days is proof
- Q: Which question gets the most honest use out of the pane?
    - "Is today's activity at this level bigger than on earlier tests of it?"
    - "Will this spike cause a rally?"
    - "Who is behind the bar?"
    - "Which bar should I buy?"

## Section 5: Case Study Example

*Hypothetical — constructed for teaching.*

SPY on a 5-minute Atlas chart. The range from Chapter 7: 578 to 590, floor at 578.

**What the chart shows:** price sells off into 578 and wicks below it, then closes back above.

**What the pane shows:** as price tests 578, a tall **call** bar appears. Clicking that bucket shows most of it is the 590 calls, filled at the ask. The put bars around it stay small.

**The read:** premium arrived **at** the level the chart and the map already marked. That supports the floor holding. It doesn't create the trade — the trade still needs price to hold 578, with invalidation on acceptance below it.

**The trap, from the same chart:** earlier that morning, a similar tall call bar printed in the **middle** of the range — and price did nothing. If the trader only remembered today's bar at the floor, they'd think call spikes always lead to rallies. The midpoint bar is the reminder: location first.

## Section 6: Common Mistakes

### Mistake 1 — Reading bar height as contracts

The bars show premium. A tall bar is a lot of dollars, which may be few contracts.

---

### Mistake 2 — Trading the bar

A tall bar under a candle is evidence at a place and time. The entry and invalidation still come from the chart.

---

### Mistake 3 — Learning from hindsight

Spikes before moves are memorable; spikes before nothing are forgotten. Judge the pane at levels, not in hindsight.

## Section 7: Key Takeaways

- The Atlas flow pane shares the chart's timeline. Its bars show premium, with calls and puts separate.
- The pane has pill-group filters — at least one pill per group stays on; all on means no filter.
- Chapter 5 still applies: the pane shows what you filtered.
- Ask "did premium show up at my level?" — not "which bar do I trade?"
- Keep the order: chart, map, then the pane. Beware the hindsight trap.

***Remember:***

***A large print earns investigation. It does not identify a profitable trade.***
