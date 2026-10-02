# Reading The Dark Pool Prints

- Track: heatseeker / category: Skylit - Knowing Your Ecosystem
- Level: Beginner · duration: 10 min
- Passing score: 80 · sections: 6 · quiz questions: 6
- Provenance: https://app.skylit.ai/api/nexus/academy/courses/5b8aa8cf-52a2-4506-af0a-db0eb594d5b6 (JSON, captured 2026-10-02, read-only) · course id `5b8aa8cf-52a2-4506-af0a-db0eb594d5b6`
- Views/completions at capture: 12513/895

## Course description

(none)

## Section 1: Introduction

## **The First Thing You Need To Unlearn**

Here's the belief that ruins most people's relationship with dark pool data before it even starts: _"A big dark pool print means institutions are buying here."_

It doesn't. A dark pool print tells you that a large block of stock changed hands off-exchange at a specific price. It does **not** tell you who was the buyer, who was the seller, or which side was the aggressor. There is no direction attached to it. A $2 billion print is not "a $2 billion buy" — it's a $2 billion _transaction_, and somebody was on each side of it.

This matters because a whole cottage industry exists to sell you the opposite story. "Massive dark pool buying detected!" is a great headline and a terrible description of the data. Once you internalize that a print is directionless, you stop trying to read tea leaves and start using dark pool data for what it's actually good at: showing you **where** large size transacted, and **how much** conviction (measured in dollars) was behind it.

* * *

Dark pool prints show up in 2 different place within the terminal - Dark Feed (in Flowseeker) and the Dark Pool overlay in Atlas. We will learn how to read each one accurately.

No dark pool print carries a side. If a tool tells you a specific dark pool print was "bullish" or "a buy," it's inventing information that doesn't exist in the data. Treat that as a red flag about the tool, not a signal about the stock.

## Section 2: What a Dark Pool Print Actually Is

A dark pool print is an **off-exchange equity trade** — a block of shares that traded away from the public exchanges and was reported afterward. The terminal shows you a small, honest set of fields for each one:

* * *

Date/Time: When the print was reported.

Ticker: The stock that traded.

Price: The exact price the block transacted at.

Size: How many shares.

Notional: Size x price - the dollar value of the block. This is the headline number.

Sector: The GICS sector the ticker belongs to, for context.

* * *

So what _can_ you read from a print?

1.  **Notional = conviction scale.**
    
    1.  A $50M block and a $2B block are different events. The dollar size is the closest thing you have to a measure of how much somebody cared.
        
2.  **Price = a level that mattered.**
    
    1.  Someone moved real size at that exact price. That price level now has meaning — it's a spot where large participants were willing to transact.
        
3.  **Ticker and sector = where the big money is active.**
    
    1.  A cluster of large prints in one name or one sector tells you attention is concentrated there.
        

What you _cannot_ read: who's bullish, who's bearish, or what happens next. The print is evidence that something large happened — not a prediction.

## Section 3: The Tape: Dark Feed in Flowseeker

The **Dark Feed** lives right next to the Live Feed in Flowseeker, and if you've used the Live Feed it'll feel immediately familiar — it's the same tape-reading experience, but for off-exchange equity blocks instead of options trades.

What you see is a live, scrolling table of prints with the columns above. A few things worth knowing:

-   **It's a whale tape by default.** The feed defaults to a **$1,000,000 notional minimum**, so you're looking at blocks, not the full off-exchange firehose. That's a deliberate stance: the small prints are noise for most purposes, and the point of the feed is to surface size. You can lower the floor in the filters if you want everything.
    
-   **Notional is styled to pop.** The Notional column is highlighted so the biggest blocks catch your eye as you scan — the same way the feed is built to make large size impossible to miss.
    
-   **Filters that matter.** A date (and optional time-of-day) range, notional min/max, size min/max, share-price min/max, and sector filters. Set a date range in the past and the feed serves you that history instead of the live stream.
    
-   **The familiar workflow.** Saved tabs (each with its own filters and column layout), ticker search with `!TICKER` to exclude a name, a results cap, pause/resume — when paused, new prints queue up and a counter shows how many are waiting, then flush in when you resume — plus shareable URLs and CSV/image export.
    

How you actually use it: scan for unusually large notionals, note _which tickers and sectors_ are printing size, and treat those prices as levels to watch — not as directional signals.

## Section 4: The Levels: Dark Pool Overlay on Atlas

The same prints show up in a completely different shape on Atlas. Turn on the **Dark Pool** overlay in the chart settings and the largest prints for that symbol render as **horizontal dashed lines** drawn across the price chart, each labeled with its notional and date — something like `DP $2.2B · 5/15`.

This is the spatial view of the same data. Directly on Atlas. Where the feed is a time-ordered list of events, the chart turns the biggest blocks into **price levels** sitting right on top of the candles.

Two controls shape what you see:

-   **Top N** — how many of the largest prints to draw (1, 2, 3, or 5). This keeps the chart clean; you're only looking at the heaviest blocks, not every print.
    
-   **Lookback** — how far back to search for those top prints (30, 45, 90, or 180 days).
    

A few details that keep you honest about what the lines mean:

-   Each line is **one real print** at its **exact transaction price** — not a volume-weighted average, not a price band, not "accumulated volume at this level." It's a single block that happened.
    
-   The **date is in the label**, not on the time axis. The line spans the whole chart horizontally because it represents a _price_, not a moment. Two big blocks at similar prices are told apart by the date in their labels.
    

Why draw them as levels at all? Because a price where someone transacted enormous size is a natural place for the market to react. These lines often behave like soft support or resistance — not because of magic, but because that price proved it could absorb real size once already.

## Section 5: Putting the Two Together

The feed and the chart answer different questions, and they're strongest used in sequence:

-   **The Dark Feed tells you what's happening now.** A fresh, large block just printed in a name you care about.
    
-   **The Atlas overlay tells you where size already transacted.** The biggest historical blocks, sitting as levels on the chart.
    

A simple workflow: spot a large print in the Dark Feed, pull that ticker up on Atlas, and see where the print sits relative to the existing dark pool levels and the current price. Is it printing right at an old block level (a price the market keeps coming back to), or in fresh territory?

And then the step that ties dark pool into the rest of the terminal: check those levels against the **GEX/VEX nodes** on the same Atlas chart. A dark pool level that lines up with a dealer positioning node is far more interesting than one sitting in structural no-man's-land. The dark pool print tells you size transacted there; the dealer map tells you what happens mechanically if price returns. That's confluence — and it's the same principle that makes the flow subgraph on Atlas worth combining with the heatmap rather than reading in isolation.

## Section 6: Heatseeker X Darkpool Confluencce

Here we have a great example of how to tie everything in together.

1.  Charts show a gap fill on SPY into 755.
    
2.  We observe a dark pool print into gap fill.
    
3.  Heatseeker shows a floor being put in, directly in line with the dark pool print, as well as gap fill.
    

_Magic happens when we combine TA with Atlas x Darkpool x Heatseeker confluence._

### Quiz (6 questions)

- Q: A dark pool print gives you six honest fields: time, ticker, price, size, notional, and sector. Which conclusion is structurally valid?
    - A. The print was bullish if it appeared above spot
    - B. The print was bearish if it appeared below spot
    - C. The print identifies a price where large size transacted
    - D. The print confirms dealer hedging pressure
- Q: A trader lowers the Dark Feed notional minimum dramatically and sees many more prints. What risk did they introduce?
    - A. They may turn the feed from a size-focused tape into a noisy firehose
    - B. They will remove historical prints from Atlas
    - C. They will lose sector classification
    - D. They will force prints to show side
- Q: A Dark Feed row shows:

Ticker: MSFT
Price: 421.50
Size: 3,200,000
Notional: $1.35B
Sector: Technology

What is the cleanest first read?
    - A. Large off-exchange size transacted at 421.50; that price may become a level to watch
    - B. MSFT has confirmed institutional buying at 421.50
    - C. Technology is bullish because the notional is over $1B
    - D. The print should be faded because it is too large
- Q: The Atlas dark pool overlay uses Top N and Lookback. If Top N is 3 and Lookback is 90D, what should the trader expect?
    - A. The three most recent prints in the last 90 days
    - B. The three largest prints found within the last 90 days
    - C. Every print from the last 90 days, grouped into three zones
    - D. The three prints nearest current spot
- Q: Why does Skylit avoid assigning flow score, sweep tags, Greeks, or sentiment to dark pool prints?
    - A. Because dark pool prints are too small to classify reliably
    - B. Because flow score only applies to ETFs
    - C. Because dark pool prints only matter after market close
    - D. Because off-exchange equity prints do not carry the bid/ask, side, or options-structure data required for those labels
- Q: Why does the dark pool line span horizontally across the chart?
    - A. Because the print happened across every candle
    - B. Because it represents a price level, not a timestamp
    - C. Because the print is active until expiration
    - D. Because Atlas converts dark pool prints into moving averages
