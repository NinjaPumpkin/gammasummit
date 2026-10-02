# Node Hierarchy

- Track: heatseeker / category: Baby Wick
- Level: Beginner · duration: 30 min
- Passing score: 80 · sections: 10 · quiz questions: 10
- Provenance: https://app.skylit.ai/api/nexus/academy/courses/b0000001-0000-0000-0000-000000000003 (JSON, captured 2026-10-02, read-only) · course id `b0000001-0000-0000-0000-000000000003`
- Views/completions at capture: 12926/1456

## Course description

Skylit Academy Chapter 3

## Section 2: Chapter 3 — Node Hierarchy

## Learning Goal

By the end of this chapter, traders should be able to open a **Heatseeker map** and immediately identify:

- Where **spot price** is located
- Where the **largest nodes** exist
- Where **floors** and **ceilings** are likely located
- Which strike represents the **King Node**
- Which strikes function as **Gatekeepers**

This is the first step toward developing **Heatseeker literacy**.

Heatseeker maps represent **dealer exposure across strikes**.

Each node reflects a concentration of positioning that influences how dealers hedge as price moves.

The key principle to understand is simple:

**Not all nodes carry the same influence.**

---

## Section 3: Step 1 — Node Hierarchy

When traders open a Heatseeker map, they are looking at a **structure of exposure nodes**.

- Each node represents a strike where dealer positioning exists.

However, the **size of that positioning varies significantly**.

Some nodes contain relatively small exposure.

Others contain **large concentrations of exposure that heavily influence dealer hedging behavior**.

![image.png](https://d95fp8dfaxyli.cloudfront.net/academy/ch3-image.png)

This creates a natural **hierarchy of nodes**.

Nodes with larger exposure values tend to have **greater influence on price behavior**, because dealer hedging flows increase near those strikes.

In practical terms:

- Traders should always prioritize **magnitude** when reading a Heatseeker map.
- The strongest nodes become the **structural anchors** of the exposure map.

---

## Section 4: Step 2 — King Node

Within the exposure structure, one node typically stands above the rest.

This node is referred to as the **King Node**.

### Definition

The **King Node** is the strike with the **largest absolute exposure value** on the Heatseeker map.

Because dealer positioning is most concentrated at this strike, it often becomes the **center of structural gravity** for price.

- The king node represents the strike where Market Makers are most likely to pin price at when the NYSE closes.

![image.png](https://d95fp8dfaxyli.cloudfront.net/academy/ch3-image-1.png)

When price approaches the King Node, dealer hedging flows increase.

- This often causes price to **react more strongly around that level** compared to smaller nodes.

The King Node does not guarantee that price will stop there.

- However, it is typically the **most influential node in the entire structure**, and traders should always identify it first when opening a map.

Understanding where the King Node sits provides an immediate sense of where the **largest concentration of dealer exposure exists**.

***The king node can be either positive gamma or negative gamma.*** 

---

## Section 5: Step 3 — Floors and Ceilings

After identifying the King Node, traders should determine where **structural boundaries** exist around the current price.

These boundaries are commonly referred to as **floors** and **ceilings**.

![image.png](https://d95fp8dfaxyli.cloudfront.net/academy/ch3-image-2.png)

### Floors

A **floor** is a large node located **below spot price**.

- Because large exposure nodes below price can increase dealer hedging activity as price declines, these areas often behave like **support zones**.
- When price approaches a strong node below spot, dealer hedging may slow the move and cause price to stabilize (chop) or reverse.
    - Floors can sometimes give way, if it is a level that has been tested multiple times.

![image.png](https://d95fp8dfaxyli.cloudfront.net/academy/ch3-image-3.png)

***The strongest floor is usually the largest exposure node beneath spot.***

---

### Ceilings

A **ceiling** is a strong node located **above spot price**.

![image.png](https://d95fp8dfaxyli.cloudfront.net/academy/ch3-image-4.png)

When price approaches these nodes, dealer hedging activity may increase in the opposite direction.

This can create **resistance zones**, where price movement slows or reverses.

The strongest ceiling is typically the **largest exposure node above spot**.

---

### Identifying Structural Boundaries

To quickly identify floors and ceilings:

1. Locate **spot price**
2. Find the **largest node below spot** → potential floor
3. Find the **largest node above spot** → potential ceiling

These nodes help define the **immediate structural range** where price is likely to interact with dealer positioning.

---

## Section 6: Midpoints

Once you've identified the floor and ceiling around spot price, there is a natural zone between them — the **midpoint**.

The midpoint is the area roughly halfway between two major nodes. This is where dealer hedging pressure is at its weakest — exposure is not concentrated here, so price has no structural reason to react.

This creates a problem for execution:

- Price behavior at midpoints is **choppy and indecisive**
- The risk-to-reward profile is poor — at best, a midpoint entry offers **1:1 R:R**
- Skylit doctrine requires a **3:1 minimum R:R** for any trade to qualify. A midpoint entry does not meet that standard.
- Midpoints are **not decision zones** — they are dead space between levels that matter

The strongest reads come from price interacting with **actual nodes** — floors, ceilings, King Nodes, and Gatekeepers — not from the space between them.

Think of it this way: nodes are where dealers are forced to act. Midpoints are where nobody is forced to do anything. Trading there means accepting poor asymmetry with no structural edge.

A full execution rule around midpoints is covered in Chapter 6. The foundational principle is simple:

> **We fade extremes, not midpoints. If price is between nodes, the risk-to-reward is against you.**
> 

---

## Section 7: Step 4 — Gatekeepers

Between large nodes often sit **smaller intermediary nodes**.

These nodes play an important role in the exposure structure.

They are commonly referred to as **Gatekeepers**.

![image.png](https://d95fp8dfaxyli.cloudfront.net/academy/ch3-image-5.png)

### Definition

A **Gatekeeper node** is a strike that sits between two larger structural nodes and influences whether price can move from one region to another.

- Gatekeepers often function as **checkpoints** within the structure.
- If price clears the Gatekeeper node, it can move into the next exposure zone.
- If price fails to move through it, the market may return to the previous region.

While Gatekeepers are usually smaller than the King Node or major floor/ceiling nodes, they can still play an important role in **how price transitions between structural zones**.

- Understanding where these nodes sit helps traders interpret **how price may move between areas of larger exposure**.

---

## Section 8: Air Pockets

Air Pockets occur when maps show a zone of low volume and/or small sized nodes that price can move easily through due to the lack of resistance/activity within that zone.

![image.png](https://d95fp8dfaxyli.cloudfront.net/academy/ch3-image-6.png)

The quality of the nodes (negative gamma vs positive gamma) can affect how sharp a move price can have.

-   If price action is moving through a negative gamma air pocket region, the moves can be much more violent / sharp.
    

-   If price action is moving through a positive gamma air pocket region, the moves can be much more mild / slow.
    

![image.png](https://d95fp8dfaxyli.cloudfront.net/academy/ch3-image-7.png)

## Section 9: Reading a Heatseeker Map (Practical Workflow)

When opening a Heatseeker map, traders should follow a consistent process:

1. **Locate spot price**
2. **Identify the King Node**
3. **Determine the largest node below spot (floor)**
4. **Determine the largest node above spot (ceiling)**
5. **Determine potential air pockets**
6. **Identify intermediary nodes that act as Gatekeepers**

This process allows traders to quickly understand the **hierarchy of the exposure structure**.

---

## Section 10: Key Takeaways

Nodes vary significantly in **magnitude and influence**.

The **King Node** represents the strike with the largest exposure and often acts as the structural center of the map.

Large nodes **below spot** can function as **floors**, while large nodes **above spot** may behave as **ceilings**.

Intermediate nodes between major levels often act as **Gatekeepers**, influencing whether price can transition into the next region.

Developing the ability to quickly identify these levels is the first step toward **interpreting Heatseeker maps effectively**.

---

## Section 99: Quiz

Test your understanding of the concepts covered in this chapter.

### Quiz (10 questions)

- Q: What defines the **King Node**?
    - The highest strike price
    - The node closest to spot
    - The node with the largest absolute exposure value
    - The first node above spot
- Q: Why are larger nodes more influential than smaller nodes?
    - They appear brighter on the map
    - They contain more dealer exposure and therefore stronger hedging pressure
    - They are always located near spot price
    - They always determine market direction
- Q: If spot price is 410 and the largest node below price is at 405, that level most likely acts as:
    - A ceiling
    - A floor
    - A gatekeeper
    - A breakout trigger
- Q: If spot price is 410 and the largest node above price is at 420, that level most likely acts as:
    - A floor
    - A ceiling
    - A volatility trigger
    - A neutral zone
- Q: What is the first step when opening a Heatseeker map?
    - Identify the King Node
    - Identify spot price
    - Look for the largest node
    - Look for the ceiling
- Q: What is the primary purpose of **Gatekeeper nodes**?
    - They determine the King Node
    - They mark the start of the trading session
    - They regulate and often prevent continuation between price zones
    - They represent the largest exposure level
- Q: Which factor determines node strength?
    - They are all equal in strength
    - Node color alone
    - Absolute value
    - Time of day
- Q: A node sitting between two larger nodes most likely acts as:
    - A King Node
    - A Gatekeeper
    - A floor
    - A ceiling
- Q: Why is identifying the King Node important?
    - It identifies the trading session open
    - It determines volatility levels
    - It always predicts market direction
    - It shows where dealer exposure is most concentrated
- Q: What does the overall structure of nodes on the map represent?
    - Dealer exposure positioning
    - Historical volatility
    - Economic indicators
    - Institutional order flow
