# Dealer Positioning and Gamma Mechanics

- Track: heatseeker / category: Baby Wick
- Level: Beginner · duration: 30 min
- Passing score: 80 · sections: 7 · quiz questions: 6
- Provenance: https://app.skylit.ai/api/nexus/academy/courses/b0000001-0000-0000-0000-000000000002 (JSON, captured 2026-10-02, read-only) · course id `b0000001-0000-0000-0000-000000000002`
- Views/completions at capture: 13409/1490

## Course description

Skylit Academy Chapter 2

## Section 1: Introduction

# Chapter 2 - Intro to Gamma

---

# Skylit Academy

## Tier 1 — Foundations

### Chapter 2

# Dealer Positioning and Gamma Mechanics

---

# Chapter Objective

In Chapter 1, traders learned that **charts come first**.

Charts provide the structural thesis.

In this chapter we introduce the engine that powers Heatseeker™:

**Dealer positioning and gamma exposure.**

Understanding dealer positioning explains **why price reacts at certain levels** and why markets behave differently depending on the exposure environment.

This chapter teaches traders to recognize:

- positive gamma environments
- negative gamma environments
- how dealer hedging affects price behavior
- how node magnitude influences market reactions

These concepts form the foundation for reading Heatseeker maps correctly.

---

## Section 2: What Dealer Positioning Means

Options dealers constantly hedge their exposure.

When traders buy options, dealers typically take the opposite side of those positions.

To remain neutral, dealers adjust their hedge as price moves.

These adjustments create **buying and selling pressure in the underlying market**.

Heatseeker visualizes this exposure using nodes across strikes.

These nodes show where dealer positioning is concentrated.

Understanding dealer positioning allows traders to anticipate **how dealers are likely to hedge when price moves**.

---

## Section 3: Positive Gamma Environments

When dealers are **long gamma**, the market enters what we call a **positive gamma regime**.

This environment is typically represented by **yellow (pika) nodes** on the heatmap.

In a positive gamma regime:

- dealers hedge by **buying dips**
- dealers hedge by **selling rips**

***This behavior suppresses volatility.***

- Yellow (*Pika*) nodes have a volatility dampening effect, slowing down price action and leading to chop.

![image.png](https://d95fp8dfaxyli.cloudfront.net/academy/ch2-image.png)

Instead of large directional moves, price tends to:

- chop
- stall
- remain within a contained range

This is why positive gamma environments often feel slow or “pinned.”

Markets become **mean-reverting systems**.

Price oscillates between support and resistance rather than trending aggressively.

---

# ***Section 3 — Negative Gamma Environments***

When dealers are **short gamma**, the market behaves very differently.

Negative gamma environments are typically represented by **purple (barney) nodes**.

In this regime:

- dealers hedge **with the move**
- rising prices force dealers to buy
- falling prices force dealers to sell

This amplifies price movement.

Instead of suppressing volatility, the hedging process **accelerates it**.

- Purple (*barney*) nodes have a volatility increasing effecting, speeding up price action

![image.png](https://d95fp8dfaxyli.cloudfront.net/academy/ch2-image-1.png)

Negative gamma environments often produce:

- fast directional moves
- node overshoots
- “wicky” price action
- air pockets between nodes

---

## Section 4: Node Color and What It Represents

Heatseeker uses color to help traders quickly identify the exposure environment.

In general:

Yellow nodes indicate **positive gamma exposure**.

Purple nodes indicate **negative gamma exposure**.

However, color alone is not enough to determine how important a node is.

Which brings us to one of the most important rules when reading heatmaps.

---

## Section 5: The Absolute Value Rule

![image.png](https://d95fp8dfaxyli.cloudfront.net/academy/ch2-image-2.png)

One of the most common mistakes new traders make is focusing only on color.

In reality, the largest absolute value **nodes can be either purple or yellow.** The larger the absolute value = the more intense the color will be. Larger values hold more strength.

- Nodes act like “magnets”. The bigger they are, the stronger the pull. The closer they are, the stronger the pull.
- Large nodes represent areas where dealers have the most exposure.
- These areas are more likely to influence price behavior.

For example:

A very large purple node may exert more influence than a small yellow node.

- Vice versa can also be true.

Similarly, a large yellow node may create strong support or resistance regardless of surrounding nodes.

This is known as the **absolute value rule**:

> The magnitude of the node determines its influence.
> 

Always prioritize **node size over node color**.

---

## Section 6: Connecting Dealer Positioning to Price Behavior

Now we can combine these concepts.

When analyzing a heatmap, traders should ask:

1. What regime are we in?
2. Where are the largest nodes?
3. Where is spot relative to those nodes?

This provides the first layer of Heatseeker interpretation.

Later chapters will introduce additional layers such as:

- King Nodes
- Gatekeepers
- Patternpedia setups
- Trinity Mode alignment

But first, traders must understand the mechanics behind dealer positioning.

---

# Case Study Example

Consider the following scenario:

SPY heatmap shows multiple **large yellow nodes stacked around spot price**.

This indicates a **positive gamma environment**.

![image.png](https://d95fp8dfaxyli.cloudfront.net/academy/ch2-image-3.png)

What should traders expect?

In this situation:

- dealers buy dips
- dealers sell rips
- price is likely to mean revert

This often produces **range-bound market behavior**.

![image.png](https://d95fp8dfaxyli.cloudfront.net/academy/ch2-image-4.png)

Breakouts become less likely unless the exposure structure changes.

---

# Common Mistakes

### Mistake 1 — Assuming Purple Means Bearish

Purple nodes indicate negative gamma.

They do not indicate direction.

Negative gamma simply means **volatility can expand**.

Price can trend upward or downward in this environment.

---

### Mistake 2 — Ignoring Node Magnitude

Small nodes often have minimal influence.

Large nodes are where dealer exposure concentrates.

Always identify the largest nodes first.

---

### Mistake 3 — Ignoring Chart Structure

Dealer positioning must always be interpreted **within chart structure**.

Heatseeker confirms a thesis.

It does not replace it.

---

# Key Takeaways

- Dealer hedging influences price behavior.
- Positive gamma environments suppress volatility.
- Negative gamma environments amplify volatility.
- Yellow nodes typically represent positive gamma.
- Purple nodes typically represent negative gamma.
- Node magnitude matters more than node color.

Understanding these mechanics is the first step toward reading Heatseeker maps correctly.

---

## Section 99: Quiz

Test your understanding of the concepts covered in this chapter.

### Quiz (6 questions)

- Q: A heatmap shows large yellow nodes stacked around spot price. What environment does this represent?
    - Trending breakout environment
    - Choppy environment
    - Liquidity collapse
    - Directional crash setup
- Q: A heatmap shows large purple nodes dominating the exposure profile. What should traders expect?
    - Stable price action
    - Volatility expansion and aggressive moves
    - Guaranteed reversals
    - Range-bound trading
- Q: Which factor is most important when evaluating nodes?
    - Node color
    - Node label
    - Absolute value
    - Time of day
- Q: In a positive gamma environment, how do dealers typically hedge?
    - Buy rips and sell dips
    - Buy dips and sell rips
    - Avoid hedging entirely
    - Only hedge overnight
- Q: Which statement about negative gamma environments is correct?
    - Price always falls
    - Volatility decreases
    - Dealer hedging amplifies movement
    - Markets become pinned
- Q: If a small yellow node and a very large purple node exist near each other, which should traders prioritize?
    - The purple node
    - The yellow node
    - Both equally
    - Ignore both nodes
