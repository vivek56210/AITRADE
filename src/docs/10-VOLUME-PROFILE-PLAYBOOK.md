# Market Profile & Volume Profile Playbook for Nifty 50 and Bank Nifty Options (October 2026 Edition)

The core idea in *Power Trading with MarketProfile and Orderflow* comes down to one rule: first decide whether the market is in **balance** (rotating inside accepted value) or **imbalance** (moving to find new value). Then match the option strategy to that state. Buy ATM/ITM options only when price leaves value and value follows. Sell hedged premium only when price stays inside value and the Initial Balance holds. When you can't tell which state you're in, don't trade.

**Important note on the source:** my tools could not open the uploaded PDF (/mnt/user-data/uploads/power-trading-with-marketprofile-and-orderflow.pdf). So I have **not read the book's text directly**, and I give no page references. The setups below are built from three sources: the book's publicly described framework, the author's own published teaching material (Shai Coelho, founder of Vtrender), and standard Steidlmayer/Dalton Market Profile concepts that the book builds on.\[1\] Where a concept comes from Dalton-style theory and not from the author, I say so. Before trading, check each setup against the matching section of your copy.

## TL;DR

- **Map the market state before picking a trade.** Market state means: where the open is versus the prior Value Area, the opening type, and whether the Initial Balance (9:15–10:15 IST) gets extended. Imbalance setups (Open Drive, Open Test Drive, IB range extension, balance breakout) call for buying ATM or one-strike-ITM CE/PE. Balance setups (open inside value, wide IB, multi-day balance) call for *defined-risk* premium selling such as credit spreads and iron condors. Failed breakouts and rejections back into value (Open Rejection Reverse, the 80% rule) give the best risk-to-reward of all, targeting the POC and then the opposite value edge.
- **India-specific rules as of October 2026:**
  - **Nifty 50** has weekly options expiring every Tuesday (monthly on the last Tuesday). **Bank Nifty** is **monthly-only** (last Tuesday).
  - Lot sizes are **65 (Nifty)** and **30 (Bank Nifty)**.
  - STT on options premium rose from 0.10% to **0.15%** from 1 April 2026. Finance Minister Nirmala Sitharaman announced it in the Union Budget on 1 February 2026, and it was enacted through Clause 143 of the Finance Bill, 2026.
  - Since 3 August 2026, expiry settlement has come from a **Closing Auction Session (3:15–3:35 pm)**. SEBI is consulting until 3 October 2026 on changing this.
  - Build your profiles on **futures volume**, not the spot index.
- **Most retail F&O traders lose.** SEBI's August 2026 study found **87.7% of individual equity-derivatives traders lost money in FY26**. Aggregate net losses were **₹91,685 crore**, against a revised ₹1,11,788 crore in FY25. Secondary summaries of the study put about 92% of those losses in options. Treat everything here as education, not advice. Use hard stops: about 1% of capital per trade, 2–3% per day, and at most 2–3 trades a day.

---

## Key Findings

1. **The book is a context-first reference, not a signal system.** The author describes it as a desk-side workbook for NSE/BSE derivatives traders who already trade. It covers Market Profile mechanics (value areas, session structure, initiative vs responsive activity), order flow (volume at price, delta, absorption, exhaustion), "balance vs imbalance, continuation vs reversal setups," excess, range extension and profile types, with case studies from Nifty and Bank Nifty sessions.\[1\]\[2\] His published method runs in this order: **location first (Market Profile) → pressure second (gamma/options positioning) → intent third (order flow) → review after the session.**\[3\] The playbook below follows the same order.

2. **The author's day-type rules are concrete enough to trade from.** In his published summary:
   - **Normal day:** price stays inside the IB. He says that unless you scalp, this is "a trading holiday."\[4\]
   - **Normal Variation:** extends one side of the IB, with a target of **2× the IB range**.\[4\]
   - **Neutral:** extends both sides of the IB; watch for a failed auction.\[4\]
   - **Neutral Extreme:** extends both sides and closes at one extreme. The **K period (2:15–2:45 pm)** often confirms direction.\[4\]
   - **Trend and Double Distribution:** the remaining two types.\[4\]
   - **Timing:** he says recognising the day type **by 11:30 am** sets the strategy, target and stop for the rest of the day.\[4\]

3. **The 80% rule only counts once acceptance is visible.** The author's own guide treats a re-entry into the prior Value Area as an *observation*. You watch whether price holds inside value, whether the developing POC migrates, and whether order flow confirms.\[3\] In the classic Dalton-era wording, the rule triggers when price opens outside value and then trades inside it for two consecutive 30-minute periods. At that point the opposite edge of value becomes the high-probability target.\[5\]

4. **The Indian market structure now favours fewer, better trades.**
   - Bank Nifty no longer has weekly expiries.\[6\]
   - Option STT went up 50%.\[7\]
   - SEBI's FY26 data shows option buying dominated retail losses.\[8\]\[9\]
   - Together, these punish the high-frequency, low-quality option buying that Market Profile is meant to filter out.

---

## Part 1 — The Book's Framework in Plain Language

| Concept | What it means | How the playbook uses it |
|---|---|---|
| **Auction / value** | Price advertises; time and volume show whether that price is accepted | Every trade asks: "Is value following price?" |
| **Value Area (VA), VAH, VAL** | Range holding about 70% of the session's activity | Prior-day VA is the first level you mark |
| **POC / developing POC (DPOC)** | Price with the most time or volume; the "fairest" price | Main target for rejection trades; a moving DPOC confirms trend |
| **Initial Balance (IB)** | First-hour range (9:15–10:15 IST on NSE) | Breakout, extension and premium-selling boundaries |
| **Range extension** | Trade beyond the IB | Decides whether the day is Normal, Normal Variation, Neutral or Trend |
| **Single prints** | Prices with only one TPO, left by fast one-sided moves | Support/resistance on pullbacks; also "unfinished business" |
| **Excess / tails** | Sharp rejection at an extreme (a buying or selling tail) | Shows an auction is finished, which makes a good stop anchor |
| **Poor high / poor low** | Flat extreme with no tail | Unfinished business; likely to be revisited |
| **HVN / LVN** | High- and low-volume nodes on a volume profile | Price stalls at HVNs and moves fast through LVNs |
| **Balance vs imbalance** | Bell-shaped, overlapping value vs elongated, migrating value | Picks selling vs buying |
| **Initiative vs responsive** | Buying above value / selling below value (initiative) vs fading back toward value (responsive) | Initiative supports breakout trades; responsive supports fades |
| **Profile shapes** | P shape (short covering or late acceptance higher), b shape (long liquidation), D (balance) | Tells you the next day's bias |
| **Composite / multi-day** | Several sessions merged into one profile | Positional balance edges and breakout levels |
| **Order flow** | Delta (aggressive buys minus sells), cumulative delta, divergence, absorption, footprint imbalances | Confirms the trigger only; it never overrides location |

### Day types (when to use each)

| Day type | How it looks | Which option approach fits |
|---|---|---|
| **Trend day** | Opens at one extreme, closes at the other; DPOC migrates; single prints | Buy ATM/ITM in the trend direction and trail; never sell premium against it |
| **Double-distribution trend day** | One balance, a fast move, then a second balance | Buy on the breakout from the first distribution; the single-print zone becomes support |
| **Normal variation** | IB, then a one-sided extension (often 1.5–2× IB) | Buy the IB break once it's accepted; target 2× IB |
| **Normal day** | Wide IB, little or no extension | Sell hedged premium outside the IB; no directional buying |
| **Neutral / neutral extreme** | Extension on both sides of the IB | Stay flat until the K period; a neutral extreme close carries direction into the next day |
| **Non-trend day** | Narrow range, fat profile, low participation | Don't buy options, because theta eats them; small hedged selling only, or no trade |

### Opening types

| Open | How to recognise it | What it means |
|---|---|---|
| **Open Drive (OD)** | Opens and moves straight in one direction; doesn't trade back to the open | Strongest conviction; trend-day candidate |
| **Open Test Drive (OTD)** | Tests a reference (prior VAH/VAL/POC/high/low), fails there, then drives the other way | High conviction, with a defined stop at the test extreme |
| **Open Rejection Reverse (ORR)** | Early move away from value is rejected; price comes back through the open | Failed auction; expect rotation into or through value |
| **Open Auction (in range / out of range)** | Rotates around the open; no early control | In range means a balance or rotational day; out of range means watch for a later breakout |

---

## Part 2 — India-Specific Practical Rules (verified for October 2026)

### 2.1 Expiry schedule
- **Nifty 50:**
  - Weekly options expire every **Tuesday**; the monthly contract expires on the **last Tuesday** of the month.\[10\]
  - If Tuesday is a holiday, expiry moves to the **previous trading day**.\[11\]
- **Bank Nifty:**
  - **Monthly only**, expiring on the **last Tuesday** of the month.\[10\]
  - SEBI's October 2024 framework allows each exchange **one weekly benchmark index** from 20 November 2024. NSE kept Nifty, so Bank Nifty, FinNifty and Midcap Select weeklies ended.\[10\]\[12\]
  - The current Tuesday schedule took effect on **1 September 2025**. BSE's Sensex weekly moved to Thursday at the same time.\[10\]
- **Upcoming dates (per published calendars):**
  - Nifty weeklies on 6, 13, 20 and 27 October 2026; 27 October is also the monthly.\[13\]
  - Bank Nifty monthlies on 27 October and 24 November 2026.\[13\]
- **Will weeklies be scrapped?** As of the latest available reporting, **SEBI has not issued any consultation paper or decision to end weekly index options**. On 3 March 2026, SEBI Chairman Tuhin Kanta Pandey said the concern "has been with short-dated weekly index options where excessive activity was seen," but did not confirm a discontinuation.\[14\] Treat any claim that weeklies are ending as speculation until a circular appears.

**What this means for your setups:**
- Nifty gives a fresh weekly expiry every Tuesday. That means steep theta and gamma from Friday to Tuesday.
- Bank Nifty options have more time value for most of the month. They decay more slowly, are less suited to quick intraday premium selling, and are friendlier to directional buying early in the series.
- Bank Nifty's sharp "expiry-day" behaviour now happens only once a month.\[15\]

### 2.2 Lot sizes and contract value
- **Current lots:**
  - **Nifty 50 = 65**\[16\]
  - **Bank Nifty = 30**\[16\]
  - FinNifty = 60; Midcap Select = 120.\[17\]
- **When they changed:**
  - Set by NSE circular NSE/FAOP/70616 (3 October 2025).\[16\]
  - The first weekly expiry with the new lot size was 6 January 2026; the first monthly was 27 January 2026.\[18\]
  - NSE reviews lot sizes periodically, so check the NSE contract page before each series.\[19\]
- **Minimum contract value:** SEBI raised the minimum index-derivatives contract value to **₹15 lakh** (from ₹5 lakh), effective for contracts introduced after 20 November 2024.\[20\] At Nifty ≈ 24,000, one lot is about ₹15.6 lakh notional.

### 2.3 Market hours, Initial Balance and the new closing auction
- **Normal session:** 9:15–15:30 IST.
- **Standard IB:** the first hour, **9:15–10:15** (the A and B 30-minute brackets).\[3\]\[21\]
- **Fast IB variant:** some Indian traders use a 15-minute bracket profile, with the IB ending at **9:45**.\[22\] It's fine for scalping, but this playbook uses the first-hour IB unless stated.
- **TPO letters, using 30-minute brackets from 9:15:**

| Period | Time |
|---|---|
| A | 9:15–9:45 |
| B | 9:45–10:15 |
| C | 10:15–10:45 |
| … | … |
| K (the author's "confirmation" period) | 14:15–14:45 |

- **New since 3 August 2026: the Closing Auction Session (CAS).**
  - Stocks with derivatives now set their closing price in a **3:15–3:35 pm** auction.\[23\]
  - For index derivatives, the settlement price is the index's closing value, which is built from those CAS prices.\[24\]
  - Business Standard reported that the Nifty's move during the auction window was 82.4 basis points on the first day and had narrowed to 5.5 bps by the end of that week. Volatility came back at the 29 September 2026 monthly expiry: IANS reported the Nifty's indicative closing level briefly fell 2.2% during the auction, to a low of 22,267, before the index closed 0.28% lower at 22,716.20.
  - On **12 September 2026**, SEBI issued a consultation paper with these options:
    - a "blended VWAP" settlement (the last 30 minutes of continuous trading plus the 10 minutes of CAS), where, per ANI's report of the paper, "the contribution of each period would be based on its actual traded value, rather than a fixed weighting." SEBI calls this the intended long-term framework. Or
    - a return to a last-30-minute continuous-trading VWAP as an interim arrangement, and
    - revised timings. These would cut the switch from continuous trading to CAS from 5 minutes to about 1, and shorten derivatives trading after CAS from 10 minutes to 5. Derivatives would trade until 3:45 pm under one option or end at 3:30 pm under the other. These timing details come from a social-media summary of the paper (RedboxGlobal India), not the paper itself.
  - **Comments close on 3 October 2026.** Nothing has changed yet.\[25\]\[26\]
  - On 10 September 2026, Chairman Pandey said CAS itself will stay.\[27\]\[28\]
- **Practical rule:** **do not hold short or long options into the settlement auction on expiry day.** Exit by about 3:00–3:10 pm until the methodology is settled.

### 2.4 Getting volume profile data (the spot index has no volume)
- **Why futures:** the Nifty 50 and Bank Nifty spot indices are calculated values and have no traded volume. So **build volume profile, HVN/LVN, POC and order flow on the current-month index futures** (NIFTY FUT, BANKNIFTY FUT). TPO (time-based) profiles can be built on spot, but volume-based levels must come from futures.
- **Converting futures levels to spot:** futures trade at a premium (the basis), and it shrinks toward expiry. Either convert levels using today's basis, or read levels on futures and trade options off them consistently.
- **Rollover:** near the last Tuesday, move your profiles to the next-month future, or use a continuous-futures chart.

| Platform | What it offers Indian index traders |
|---|---|
| **Vtrender Charts** (the author's platform) | NSE-approved direct data vendor; Market Profile on the free plan; order flow (IB/IS initiative bars, VPOC, COT), gamma and options-flow layers on paid tiers\[1\]\[4\]\[29\] |
| **GoCharting** | Native TPO/Market Profile with developing profiles, custom bracket size, value-area shading, naked-POC tracking, split/merge composites; footprint and volume profile on the same chart\[22\] |
| **TradingView** | Built-in Session Volume / Volume Profile; TPO on paid plans plus many community TPO/IB scripts; needs a real futures volume feed\[30\]\[31\] |
| **Others** | Sierra Chart, ATAS, NinjaTrader-style tools through Indian data vendors (check vendor licensing) |

### 2.5 Option Greeks and which setups suit buying vs selling
- **Theta (time decay):**
  - It speeds up sharply in the final 1–2 sessions before a Nifty weekly expiry.
  - Option buyers need **speed**, so only buy on imbalance days where you expect range extension *today*.
  - Sellers earn theta on balance days.
- **Implied volatility (IV):**
  - IV usually comes down after a gap open once the auction settles. Buying right at the open after a big gap often means paying inflated IV.
  - On Open Drive days, IV can expand in the direction of the move, especially on downside puts.
  - Watch India VIX. Rising VIX on a range day is a warning sign for premium sellers.
- **Gamma (expiry day):**
  - Near-ATM gamma explodes on expiry day. A 50-point Nifty move can multiply a cheap OTM premium, or wipe out a short position.
  - Expiry-day selling must be **defined-risk** (spreads), and expiry-day buying must be small and quick.
- **Delta and strike choice:**
  - **For buying:** use ATM or one strike ITM (delta about 0.5–0.65). Avoid far OTM "lottery" strikes.
  - **For selling:** put short strikes **beyond profile levels** (outside the IB extreme, prior VAH/VAL or prior day high/low), at about 0.15–0.30 delta, with a hedge wing 2–4 strikes further out.
- **Strike intervals:** Nifty uses 50-point strikes and Bank Nifty 100-point strikes for near-the-money contracts.

### 2.6 SEBI F&O rule changes affecting retail options traders (status as of October 2026)

| Measure | Status |
|---|---|
| One weekly benchmark index expiry per exchange (Nifty on NSE) | In force since 20 Nov 2024\[10\]\[20\]\[32\]\[33\] |
| Minimum contract value ₹15 lakh (larger lots) | In force since 20 Nov 2024; lots now 65/30 |
| Additional 2% ELM on short index options on expiry day | In force since 20 Nov 2024 |
| Upfront collection of option premium from buyers | In force (phase two of the Oct 2024 framework, Feb 2025)\[34\] |
| No calendar-spread margin benefit on expiry day | Index derivatives since Feb 2025; **extended to single-stock derivatives** by SEBI circular dated 5 Feb 2026 (effective about May 2026)\[35\]\[36\]\[37\] |
| Intraday monitoring of index position limits | Exchanges take at least 4 intraday snapshots. From 1 Oct 2025, entity-level intraday limits are ₹5,000 crore net / ₹10,000 crore gross (futures-equivalent), with expiry-day penalties from 6 Dec 2025.\[38\]\[39\] This matters for large players, not normal retail size\[40\]\[41\] |
| Expiry days limited to Tuesday/Thursday | Nifty Tuesday, Sensex Thursday, from 1 Sep 2025\[42\]\[43\] |
| STT hike (Union Budget 2026) | From 1 Apr 2026: options premium 0.10% → **0.15%**; exercised options 0.125% → 0.15%; futures 0.02% → 0.05%\[7\]\[44\] |
| Closing Auction Session for derivative stocks | Live since 3 Aug 2026; settlement-method consultation open until 3 Oct 2026\[25\]\[27\]\[45\]\[46\] |
| Ending weekly expiries | **Not proposed formally**; only regulator commentary |

**Source caution:** some aggregator sites cite a "SEBI circular SEBI/HO/MRD/TPD/CIR/2026/034 effective 1 May 2026" that supposedly changed position limits, margins, lot sizes and STT.\[47\] I found **no primary-source evidence** that this circular exists. STT is set by the Union Budget, not by SEBI. Ignore it unless your broker shows the actual circular.

---

## Part 3 — The Setups (grouped by market condition)

**Common conventions for all setups:**
- Levels are read on the **current-month futures profile**.
- "Acceptance" means at least **two consecutive 30-minute TPO periods** (or about 30 minutes of 5-minute closes) holding beyond a level.
- All examples use **hypothetical** prices: Nifty ≈ 24,000, Bank Nifty ≈ 52,000. They are illustrations, not current market levels.
- Option premiums in the examples are rough illustrations.

### GROUP A — IMBALANCE / TREND (buy options)

#### Setup A1: Open Drive Trend Day
- **Context:** price opens **outside the prior day's Value Area**, ideally outside the prior day's range, and drives away in the first 15–30 minutes without coming back to the open. Global cues and a gap line up with the direction.
- **Key levels:** prior VAH (for longs) or VAL (for shorts), the prior day high/low, the opening price, and the A-period extreme.
- **Entry trigger:**
  - After the first 15-minute candle (9:15–9:30) closes in the drive direction and price has **not traded back to the open**, enter on a break of that candle's extreme.
  - More conservative: enter on the first pullback that holds above the open and above the prior VAH (or below, for shorts).
- **Option strategy:**
  - Buy an **ATM or one-strike-ITM CE** (bullish) or **PE** (bearish).
  - Nifty: current weekly if it's 3+ sessions to expiry, otherwise next week.
  - Bank Nifty: current monthly.
- **Stop-loss:** whichever comes first:
  - the futures price trades back **through the opening price**, or
  - the premium falls 30–35% from entry.
- **Targets:**
  - T1 = 1× IB extension once the IB forms.
  - T2 = 2× IB, or the next HVN or prior swing high/low on the composite.
  - Trail under each new 30-minute low (or above each new high for shorts) as the DPOC migrates.
- **Invalidation (don't trade):**
  - The open is inside the prior value.
  - The first 30 minutes trade on both sides of the open.
  - India VIX is spiking against your direction.
  - A major event is due within the hour (RBI policy, Fed, budget).
- **Example (hypothetical):**
  - Prior Nifty futures VA: 23,880–23,960. Today opens at 24,010 and drives to 24,060 by 9:30 without revisiting 24,010.
  - Buy the 24,050 CE at about ₹120.
  - Stop if futures return to 24,010.
  - If the IB is 24,005–24,095 (90 points), T1 ≈ 24,185 and T2 ≈ 24,275.

#### Setup A2: Open Test Drive
- **Context:** price opens near or outside value, **tests a known reference** (prior VAH, POC or day high/low) against the eventual direction, finds no business there (it stalls or shows a quick tail), then drives the other way.
- **Key levels:** the tested reference, the test extreme (this often becomes the day's high or low), and the opening price.
- **Entry trigger:** price reverses from the test and moves **back through the opening price** in the drive direction. Order-flow confirmation: delta flips in the drive direction, and/or you see absorption at the test (heavy volume, but price doesn't progress).
- **Option strategy:** buy ATM or one-strike-ITM in the drive direction.
- **Stop-loss:** a futures price beyond the **test extreme** (a clean, defined stop), or the premium down 30%.
- **Targets:** T1 = the opposite side of the IB; T2 = 1.5–2× IB, or the next HVN or prior single prints.
- **Invalidation:** price returns to the test extreme within the next 30 minutes; the test happens in the middle of value instead of at a reference.
- **Example (Bank Nifty, hypothetical):**
  - Opens at 52,150, dips to test the prior POC at 52,020, and prints a quick tail.
  - Price climbs back above 52,150. Buy the 52,200 CE.
  - Stop below 52,000 on futures.
  - Target the prior day high at 52,450, then 2× IB.

#### Setup A3: IB Breakout / Normal Variation Extension
- **Context:** the IB (9:15–10:15) is **narrow to average** compared with the last 10 sessions. Price then extends beyond one side, and value starts to build outside the IB.
- **Key levels:** IB high/low, IB midpoint, 1.5× and 2× IB projections, the prior VAH/VAL.
- **Entry trigger:**
  - Price closes a 30-minute TPO period beyond the IB extreme, **or** a 15-minute close beyond it is followed by a retest that holds.
  - The DPOC should shift toward the breakout side.
- **Option strategy:**
  - Buy an ATM CE or PE.
  - If the IB is already wide, price in a **debit spread** instead: buy ATM, sell 2–3 strikes OTM. This caps theta and IV cost.
- **Stop-loss:** back inside the IB by more than about 25% of the IB range, or below the IB midpoint (aggressive version); or the premium down 30%.
- **Targets:** the author's Normal Variation guidance is a **target of 2× the IB range**.\[4\] Book half at 1.5×.
- **Invalidation:**
  - The breakout happens after 2:30 pm with no follow-through.
  - The breakout runs straight into a prior-day HVN or the composite VAH/VAL just beyond the IB.
  - The IB is unusually wide; on wide-IB days, extensions often fail.
- **Example:** Nifty IB is 23,950–24,010 (60 points). At 10:45, C period closes at 24,025. Buy the 24,000 CE. Stop at 23,995 on futures. T1 = 24,040 (1.5× IB). T2 = 24,070 (2× IB).

#### Setup A4: Balance-Area Breakout (multi-day composite, intraday to positional)
- **Context:** 3–7 sessions of **overlapping value** form a composite with clear VAH/VAL and edges. Price breaks out, and the next sessions **build value outside** the old balance.
- **Key levels:** the composite VAH/VAL, the balance high/low, the composite POC, and the LVN just outside the balance (price moves fast through LVNs).
- **Entry trigger:**
  - Intraday: a close beyond the composite edge **plus** a successful retest from outside (old resistance holds as support).
  - Positional: the first daily close with the developing value area outside the balance.
- **Option strategy:**
  - Intraday: an ATM option.
  - Positional (2–5 days): a **debit spread**, or ITM options. Use next-week Nifty or current-month Bank Nifty, to limit theta.
- **Stop-loss:** price is accepted back inside the balance, i.e. two 30-minute periods back inside the composite VA.
- **Targets:** a measured move equal to the balance height projected from the breakout edge, or the next composite HVN.
- **Invalidation:** the breakout comes on falling participation (low futures volume or delta disagreement), or it fails to hold beyond the edge in the first hour of the next day. The second case flips you to Setup B3.

#### Setup A5: Single-Print / Double-Distribution Continuation
- **Context:** a trend or double-distribution day has left **single prints** between two value zones (today or yesterday).
- **Key levels:** the single-print zone, the upper distribution's VAL (in an uptrend), and the developing POC.
- **Entry trigger:** price pulls back **into the top of the single prints** and is rejected there, with a tail or responsive buying (positive delta, absorption of sellers).
- **Option strategy:** buy ATM in the trend direction.
- **Stop-loss:** price fills the single prints completely and trades into the lower distribution.
- **Targets:** a retest of the day's or prior extreme, then a 2× IB projection.
- **Invalidation:** single prints filled smoothly with value building inside them. That's a repair, not support.

### GROUP B — REJECTION / FAILED BREAKOUT (return to value)

#### Setup B1: Open Rejection Reverse / Failed Gap
- **Context:** price gaps **outside** prior value, makes an early move further away, then gets rejected (a tail forms, delta diverges) and trades **back through the opening price**.
- **Key levels:** the opening price, the rejected extreme, the prior VAH/VAL, and the prior POC.
- **Entry trigger:** a 15-minute close back through the opening price **and** back inside the prior day's range.
- **Option strategy:** buy an ATM option in the reversal direction. Gap opens often carry inflated IV that falls as the auction settles, so a **debit spread** works better than a naked buy here.
- **Stop-loss:** beyond the rejected extreme (the early high or low).
- **Targets:** T1 = the prior day's VAH/VAL edge; T2 = the **prior POC**; T3 (if the 80% rule activates) = the opposite value edge.
- **Invalidation:** the gap aligns with a strong multi-day trend and the rejected extreme is only marginal; or there is no tail and no delta divergence.
- **Example:** Nifty gaps up to 24,080 above prior VAH 23,960. It pushes to 24,110, prints a selling tail, and drops back below 24,080. Buy the 24,050 PE. Stop above 24,115. Targets 23,960 (VAH), then 23,920 (POC).

#### Setup B2: The 80% Rule (re-entry into prior value)
- **Context:** price opens **outside the prior Value Area** (above VAH or below VAL), then trades back inside and **holds there for two consecutive 30-minute TPO periods**. This is the Dalton-era rule.\[5\] The author adds that you should only act when acceptance is visible: DPOC migration and order-flow confirmation.\[3\]
- **Key levels:** the prior VAH, VAL and POC.
- **Entry trigger:** the close of the second consecutive 30-minute period inside value. Better: enter on the first pullback toward the edge you re-entered from, provided it holds inside value.
- **Option strategy:**
  - Buy ATM toward the opposite edge, **or** use a debit spread with the short strike near the opposite edge (the target is known, so a spread fits).
  - Bank Nifty's value areas are wide, so a spread is usually better value.
- **Stop-loss:** price is accepted back outside value (a 30-minute close beyond the re-entry edge).
- **Targets:** T1 = the prior POC (book half); T2 = the opposite VA edge.
- **Invalidation:**
  - The prior VA is unusually wide (low probability of a full traverse).
  - Re-entry happens after 1:30 pm (not enough time left).
  - Major news is pending.
- **Example (Bank Nifty, hypothetical):**
  - Prior VA: 51,700–52,100, POC 51,900.
  - Opens at 51,620, and the A and B periods both close inside VAL (above 51,700).
  - Buy a 51,800/52,100 call debit spread.
  - Stop on a 30-minute close below 51,680.
  - Targets 51,900, then 52,100.

#### Setup B3: Failed IB / Failed Balance Breakout ("look above and fail")
- **Context:** price breaks above the IB high (or a composite VAH) but **can't build value outside**: there is a tail, a poor follow-through period, or delta divergence (new price high on weaker or negative delta). It then returns inside.
- **Key levels:** the breakout extreme, the IB high/low, the IB midpoint, and the composite POC.
- **Entry trigger:** a 30-minute close back inside the IB (or balance), after a failed extension.
- **Option strategy:** buy ATM in the fade direction, or sell a credit spread with the short strike at or above the failed extreme (see C1).
- **Stop-loss:** beyond the failed breakout extreme.
- **Targets:** the IB midpoint, then the opposite IB extreme. On composites, the composite POC, then the opposite edge.
- **Invalidation:** the failure is only one period long while broader value is migrating in the breakout direction.

#### Setup B4: Poor High / Poor Low Repair (low priority, small size)
- **Context:** the prior session left a **poor high or poor low**: a flat extreme with no tail, i.e. unfinished business.
- **Trigger:** price trades toward it with initiative order flow.
- **Option strategy:** a small ATM buy toward the poor extreme, or use it as a target for other setups.
- **Stop:** a profile level behind the entry.
- **Target:** just beyond the poor extreme. **Don't** expect a big continuation after the repair.

### GROUP C — BALANCE / ROTATIONAL (sell defined-risk premium)

**Rule for this group:** always use **hedged** structures. With 2% extra ELM and no expiry-day calendar-spread benefit,\[32\]\[48\] naked shorts tie up large margin and carry gap and gamma risk.

#### Setup C1: Open Inside Value (Open Auction In Range)
- **Context:** price opens **inside the prior Value Area and the prior day's range**, rotates around the open, and the IB forms **inside** the prior VA. Read: balance until proven otherwise.
- **Key levels:** the prior VAH/VAL, the prior day high/low, the IB high/low, and the prior POC (rotation magnet).
- **Entry trigger:** after the IB completes at 10:15, if price is still inside the prior VA and the IB hasn't broken out:
  - sell a **call credit spread** with the short strike above the greater of the IB high, prior VAH or prior day high, **and**
  - sell a **put credit spread** with the short strike below the lesser of the IB low, prior VAL or prior day low.
  - Together these form an **intraday iron condor**.
- **Strikes:**
  - Nifty: short strikes about 0.15–0.25 delta, wings 100–150 points further out.
  - Bank Nifty: wings 300–500 points.
- **Alternative (directional fade):** buy a small ATM option at VAH (toward the POC) or at VAL (toward the POC), with a stop just outside value.
- **Stop-loss:**
  - Exit the threatened side when price is **accepted beyond the IB extreme** (a 30-minute close outside), or when that spread's premium doubles.
  - Exit everything if the day turns into Setup A3.
- **Targets:** collect 50–70% of the credit by 2:30–3:00 pm; don't hold for the last rupee.
- **Invalidation:**
  - The IB is very narrow (under about 60% of the 10-day average). Narrow IBs often lead to breakouts.
  - India VIX is rising.
  - An event is scheduled.
  - It's a Nifty expiry Tuesday after 1:30 pm (see D1).

#### Setup C2: Wide-IB Normal Day
- **Context:** the IB is **wide** (over about 130% of its 10-session average), often after a volatile open. Wide IBs tend to contain the day. The author calls the resulting Normal day a holiday for non-scalpers.\[4\]
- **Entry trigger:** after 10:15, with no extension in the C period (10:15–10:45), sell an **iron condor** with short strikes just **outside the IB high and low**.
- **Stop-loss:** a 30-minute close outside the IB on either side. Close that side, and consider flipping into A3.
- **Target:** 50–60% of credit or a time exit by 3:00 pm.
- **Invalidation:** the wide IB came from a gap that is still being repaired, i.e. price is still trending inside the IB.

#### Setup C3: Multi-Day Balance (positional premium selling)
- **Context:** 3+ sessions of overlapping value, a flat POC, and declining range. Usually a quiet-VIX, pre-event lull.
- **Key levels:** the composite VAH/VAL and balance high/low.
- **Entry trigger:** when price is near the composite POC with no breakout under way, sell an **iron condor** with shorts **outside the composite balance high/low**:
  - Nifty: weekly, entered 3–5 sessions before the Tuesday expiry.
  - Bank Nifty: the monthly, 2–3 weeks out.
- **Stop-loss:** close the threatened side on a daily close outside the composite VA, or when a short strike reaches about 0.40 delta.
- **Target:** 50% of max credit, or exit the day before expiry.
- **Invalidation:**
  - A scheduled event inside the holding period (RBI, budget, US CPI/Fed).
  - The balance is already very old and compressed. Long balances resolve into big breakouts, which is Setup A4.

### GROUP D — EXPIRY-DAY BEHAVIOUR

#### Setup D1: Nifty Weekly Expiry Tuesday (and Bank Nifty last Tuesday)
- **Context:** expiry-day pinning around high open-interest strikes that line up with the profile POC or HVN, then gamma-driven bursts late in the day.
- **Morning (9:15–12:00):**
  - Use the normal playbook.
  - Inside-value opens favour C1, using **same-day credit spreads** with short strikes beyond the IB and prior value. These decay fastest.
- **Midday (12:00–14:00):** if price is pinned near a high-OI strike that matches the developing POC, a tight credit spread (or an iron fly with wings) around it can work. Keep size small.
- **Afternoon (after 14:00):**
  - Close or cut all shorts by about 14:30–14:45.
  - The only buy setup is A3, a breakout from the day's balance with initiative order flow, using **small, fixed-rupee-risk** ATM buys.
  - Remember that SEBI's 2% extra ELM applies to short index options expiring that day.\[33\]
- **CAS rule:** exit everything by about **15:00–15:10**. Don't let the 3:15–3:35 closing auction decide your settlement while SEBI's methodology review is open.\[27\]
- **Invalidation:**
  - Never sell naked on expiry.
  - Never buy far-OTM "lottery" options after 2 pm. SEBI's FY26 data shows option buying drove the bulk of retail losses.\[8\]\[9\]

#### Setup D2: Day after Nifty expiry and Bank Nifty early-series
- After expiry, the new weekly carries more time value. A3 and A4 buys get slightly cheaper in theta terms, and C setups pay less.
- Bank Nifty early in the month: favour directional setups (A1–A4, B1–B2) with ITM options or debit spreads. Late in the month (final week): treat it like Nifty's weekly dynamics.

### GROUP E — ORDER-FLOW CONFIRMATION (overlay, never a stand-alone signal)

| Signal | What it means | How to use it |
|---|---|---|
| **Delta in the trade direction** at a breakout | Initiative participation | Confirms A1, A3 and A4 |
| **Price new high, cumulative delta lower** (divergence) | Breakout lacks buyers | Supports B1/B3 fades; skip A3 |
| **Absorption** (heavy volume at a level, price stalls) | Passive orders soaking up aggression | At a VAL/VAH, supports the responsive fade; at a test extreme, supports A2 |
| **Stacked footprint imbalances** (3+ levels) | Aggressive one-sided flow | Confirms drive and continuation; their zone becomes the stop area |
| **Exhaustion** (thin volume at the extreme) | Auction ending | Supports excess and tail-based reversals |

---

## Part 4 — Daily Decision Flow and Checklist

### Pre-market (8:30–9:10)
1. **Mark the prior session on futures:** VAH, VAL, POC, high, low, any **tails, poor highs/lows and single prints**.
2. **Label the prior day type** (trend, normal, normal variation, neutral, neutral extreme, double distribution) and its profile shape (P, b, D).
3. **Build the 3–5 day composite:** is value overlapping (balance) or migrating (trend)? Mark the composite VAH/VAL/POC and nearby HVN/LVN.
4. **Check the calendar:**
   - Is it a Nifty expiry Tuesday, or the last Tuesday (Bank Nifty and monthly)?
   - Are there events (RBI, US data, earnings of HDFC Bank or ICICI Bank for Bank Nifty)?
5. **Check overnight cues:** GIFT Nifty indication, US and Asian markets, crude, USD/INR, India VIX. Estimate where the open will land: **above value, inside value or below value**.
6. **Write one line per scenario:**
   - "If open above VAH and drives → A1."
   - "If it returns inside VA for two periods → B2."
   - "If open inside → wait for IB, then C1."

### Open and first hour (9:15–10:15)
7. **9:15–9:45 (A period):** classify the open as OD, OTD, ORR or Open Auction. Only A1/A2/B1 entries are allowed here.
8. **9:45–10:15 (B period):** watch for the two-period 80% rule activation (B2). Note the developing IB width against the 10-day average.
9. **10:15:** the IB is complete. Classify it as narrow, normal or wide.
   - Narrow → expect a breakout (A3).
   - Wide → expect containment (C2).
   - Inside value → C1.

### Matching conditions to setups

| Observed condition | Setup | Option approach |
|---|---|---|
| Open outside value + drive, no return to open | A1 | Buy ATM/ITM |
| Open tests reference, fails, drives opposite | A2 | Buy ATM/ITM |
| Narrow/normal IB + accepted extension | A3 | Buy ATM or debit spread |
| Multi-day balance broken + retest holds | A4 | Debit spread / ITM, positional |
| Pullback into single prints, rejected | A5 | Buy ATM |
| Gap outside value rejected back through open | B1 | Debit spread / ATM |
| Two 30-min periods back inside prior VA | B2 | Debit spread to opposite edge |
| IB/balance breakout fails, back inside | B3 | Buy fade or credit spread |
| Open inside value, IB inside value | C1 | Iron condor / credit spreads |
| Wide IB, no extension by 10:45 | C2 | Iron condor outside IB |
| 3+ days overlapping value, quiet VIX | C3 | Positional iron condor |
| Expiry Tuesday | D1 | Defined-risk only; exit before CAS |
| Neutral / unclear by 11:30 | — | **No trade** |

### Mid-session (10:15–14:15)
10. Re-check the day type **by 11:30 am**, following the author's timing. Adjust targets: on Normal Variation, target 2× IB; on Normal days, reduce directional exposure.\[4\]
11. Track the DPOC. If it migrates with price, hold trend trades. If price moves but the DPOC doesn't, tighten stops.

### Late session (14:15–15:30)
12. Use the **K period (14:15–14:45)** to confirm neutral-extreme direction.\[4\]
13. Exit intraday options by about 15:00–15:10, and **always before CAS on expiry days**.

### Post-session review
14. Save the profile. Label the day type, the open type, the setup you took (or skipped), and the outcome. The author's method ends every day with replay and pattern memory.\[3\]

### Risk management rules (non-negotiable)

| Rule | Guideline |
|---|---|
| **Risk per trade** | 0.5–1% of trading capital (the rupee loss at your stop) |
| **Daily loss limit** | 2–3% of capital; stop trading for the day when you hit it |
| **Weekly loss limit** | 5–6%; cut size in half the next week |
| **Max trades per day** | 2–3; one setup per market state |
| **Position sizing** | Lots = (capital × risk%) ÷ (premium stop in points × lot size) |
| **Option buying stop** | Profile level **or** 30–35% of premium, whichever comes first |
| **Option selling** | Always hedged; max loss per spread defined before entry; no naked shorts on expiry |
| **No-trade conditions** | Neutral/unclear structure by 11:30; major event within the hour; India VIX spiking; after hitting the daily limit |
| **Costs** | Include 0.15% STT on the sell-side premium, brokerage, exchange fees and GST. Frequent small scalps rarely survive the costs\[49\] |

**Sizing example:** capital ₹5,00,000 × 1% = ₹5,000 risk. You buy the Nifty 24,000 CE at ₹120 with a 35-point premium stop. Risk per lot = 35 × 65 = ₹2,275, so trade **2 lots** (₹4,550 at risk). For Bank Nifty with an 80-point premium stop: 80 × 30 = ₹2,400 per lot, so 2 lots.

---

## Caveats

- **The book itself was not read.** The uploaded PDF couldn't be accessed. The setups are original constructions based on the author's published framework (Vtrender guides and posts) and standard Steidlmayer/Dalton concepts. Listings also disagree on the book's length: 336 pages (Amazon/Google Books) versus 366 pages (the author's site).\[1\]\[50\]
- **Probabilities are not guarantees.** "80% rule," "2× IB target" and similar heuristics come from practitioner literature, not from verified statistics on today's NSE microstructure. Backtest them on Nifty and Bank Nifty futures data before trading real money.
- **Rules are changing.** The CAS settlement consultation (comments due 3 October 2026), lot-size reviews and possible future changes to weekly expiries can all alter expiry-day behaviour. Check the NSE and SEBI circulars at the start of each month.
- **Cost of retail participation.** SEBI's studies released on 20 August 2026 (covering the top 15 brokers, about 90% of individual traders) found:\[51\]\[52\]\[53\]\[54\]
  - **87.7%** of individual traders had net losses in FY26, compared with **90.9%** in FY25 (revised; earlier reported as 91%).\[8\]\[55\]
  - Aggregate losses were **₹91,685 crore** in FY26, down from a revised **₹1,11,788 crore** (about ₹1.12 lakh crore) in FY25.
  - The average loss per trader was about **₹1.17 lakh**.\[56\]
  - Transaction costs were about **₹25,000 crore**.\[51\]\[53\]
  - About **92%** of losses came from options trading, according to secondary summaries of the SEBI data. I could not confirm this figure in the study text itself.
  - Reported participation figures differ by source: an 18% decline to 87.5 lakh traders, versus 98.1 lakh to 78.6 lakh "active" traders.\[8\]\[9\]\[54\]\[57\] These likely use different definitions.
- **This is educational material, not financial advice, and not a SEBI-registered research recommendation.** Index options can lose your entire premium quickly, and short options can lose more than the credit received. Trade only with risk capital, use stops, and consider speaking to a SEBI-registered investment adviser.

## Sources

1. [Power Trading with MarketProfile and Orderflow - The NSE Trader's Workbook - Decode the markets with Vtrender](https://vtrender.com/ebook)
2. [Power Trading with MarketProfile and Orderflow: A Practical Reference for NSE and BSE Derivatives Traders eBook : Coelho, Shai: Kindle Store](https://www.amazon.com/Power-Trading-MarketProfile-Orderflow-Derivatives-ebook/dp/B0G95HY3W6)
3. [Market Profile Charts for NSE - The Complete Guide](https://vtrender.com/pillar/market-profile)
4. [Shai](https://x.com/Am_Shai/status/2049094090701099085)
5. [Market Profile](https://www.marketcalls.in/market-profile/market-profile-how-to-play-80-percentage-rule.html)
6. [SEBI New Rules for F&O Trading](https://www.jainam.in/blog/sebi-new-rules-for-fo-trading/)
7. [Explained: How the STT hike on equity futures and options affects traders and investors](https://upstox.com/news/personal-finance/tax/explained-how-the-stt-hike-on-equity-futures-and-options-affects-traders-and-investors/article-189260/)
8. [SEBI study: 88% F&O traders lost money in FY26](https://www.multibagg.ai/market-pulse/articles/sebi-study-fo-trader-losses-cmt4p9lemqnj20zqlffjat01k)
9. [PRADEEP GOYAL on X: "📉🚨 87.7% OF INDIVIDUAL DERIVATIVE TRADERS LOST MONEY IN FY26: SEBI STUDY 📊 A new SEBI study on equity derivatives reveals that despite moderation in retail participation, 87.7% of individual traders incurred losses in FY 2025-26, with aggregate net losses of nearly ₹91,685" / X](https://x.com/GoyalPradeepCA/status/2091004217024815234)
10. [India F&O Expiry Schedule 2026 — Which Index Expires Which Day](https://strota.in/india-expiry-schedule)
11. [F&O Weekly Expiry Days in India](https://www.share.market/buzz/insights/weekly-expiry-days-in-indian-fo-markets/)
12. [nse to discontinue weekly index derivatives for bank nifty nifty midcap select nifty financial services](https://newsonair.gov.in/nse-to-discontinue-weekly-index-derivatives-for-bank-nifty-nifty-midcap-select-nifty-financial-services)
13. [F&O Lot Sizes & Expiry Dates 2026 (Nifty, Bank Nifty, Sensex)](https://onetradejournal.com/fno-lot-size-expiry-calendar)
14. [Zee Business Exclusive: Weekly F&O expiry under lens — Here’s what SEBI Chairman Tuhin Kanta Pandey said](https://www.zeebiz.com/market-news/news-zee-business-exclusive-weekly-fo-expiry-under-lens-here-s-what-sebi-chairman-tuhin-kanta-pandey-said-391404)
15. [Bank Nifty weekly expiry change: what really changed](https://www.multibagg.ai/market-pulse/articles/bank-nifty-weekly-expiry-change-cmua51nkj000i2znt70vvai3v)
16. [National Stock Exchange of India Limited Circular](https://nsearchives.nseindia.com/content/circulars/FAOP70616.pdf)
17. [NSE Revises Market Lot Sizes for Major Index Derivatives Effective January 2026 - Stocko](https://stocko.in/bulletins/nse-revises-market-lot-sizes-for-major-index-derivatives-effective-january-2026/)
18. [NSE Implements Revised Lot Sizes for Index F&O Contracts from January 2026 Series](https://scanx.trade/stock-market-news/stocks/nse-implements-revised-lot-sizes-for-index-f-o-contracts-from-january-2026-series/28620746)
19. [Bank Nifty Lot Size Explained: 2026 NSE Update for Traders](https://www.kotakneo.com/investing-guide/articles/bank-nifty-lot-size/)
20. [SEBI Announces New Measures To Curb F&O Trading, Strengthen Equity Markets](https://www.sarkaritel.com/sebi-announces-new-measures-to-curb-fo-trading-strengthen-equity-markets/)
21. [Market Profile Explained — TPO Charts, Value Area, IB](https://volumelens.com/learn/market-profile-explained/)
22. [Market Profile Trading: The Complete Guide](https://gocharting.com/blog/market-profile-indicator/market-profile-complete-guide)
23. [Your Expiry P&L Is Now Set in a 20-Minute Auction. SEBI Wants It Back.](https://marketseasy.in/blog/sebi-expiry-settlement-price-cas-review-2026)
24. [NSE Launches Closing Auction Session, Marking Major Shift in Price Discovery](https://kashmirdespatch.com/nse-launches-closing-auction-session-marking-major-shift-in-price-discovery/)
25. [SEBI proposes changes to expiry-day settlement price methodology; floats consultation paper - OrissaPOST](https://www.orissapost.com/sebi-proposes-changes-to-expiry-day-settlement-price-methodology-floats-consultation-paper/)
26. [SEBI CAS Review Reopens Expiry Settlement](https://lapaasvoice.com/sebi-cas-expiry-settlement)
27. [SEBI Reviews Derivatives Settlement Price; Closing Auction Session Stays](https://www.kotakneo.com/news/regulations/closing-auction-session-sebi-derivatives-settlement-price/)
28. [SEBI Proposes New Expiry-Day Rules](https://kihikila.in/exam-prep/batori/sebi/)
29. [Live Charts for Nifty & Bank Nifty](https://vtrender.com/live-charts)
30. [Initialbalance — Indicators and Strategies — TradingView — India India](https://in.tradingview.com/scripts/initialbalance/)
31. [Market Profile & TPO](https://crosstrade.io/learn/technical-indicators/market-profile-tpo)
32. [What other changes has SEBI introduced in the F&O segment?| ICICI Direct](https://www.icicidirect.com/faqs/fno/what-other-changes-has-sebi-introduced-in-the-f-o-segment)
33. [Market regulator Sebi rolls out 6 measures to rein in F&O speculation](https://www.business-standard.com/amp/markets/news/sebi-announces-six-key-changes-to-curb-speculation-in-derivatives-trading-124100101316_1.html)
34. [SEBI Intraday Trading Regulations 2026: What You Need to Know](https://www.investingcube.com/shares/sebi-intraday-trading-regulations-2026-what-you-need-to-know/)
35. [Moneycontrol News Break confirmed, SEBI bars calendar spread margin benefit for single-stock derivatives on expiry day — TradingView News](https://www.tradingview.com/news/moneycontrol:4a5b72e5b094b:0-moneycontrol-news-break-confirmed-sebi-bars-calendar-spread-margin-benefit-for-single-stock-derivatives-on-expiry-day/)
36. [SEBI](https://www.sebi.gov.in/legal/circulars/feb-2026/review-of-calendar-spread-margin-benefit-in-single-stock-derivatives-on-expiry-day_99533.html)
37. [SEBI's Intraday Position Limits Monitoring for Equity Index Derivatives: The Framework Still Shaping F&O Trading](https://www.oquilia.com/news/sebi-intraday-position-limits-index-derivatives-sep-2025)
38. [Sebi Ups Intraday Limits For Index Options but Tightens Grip on Scrutiny](https://www.outlookbusiness.com/markets/sebi-ups-intraday-limits-for-index-options-but-tightens-grip-on-scrutiny)
39. [Sebi tightens norms for intraday position limits in index options](https://www.business-standard.com/markets/news/sebi-stricter-intraday-position-limits-options-market-regulation-125090200971_1.html)
40. [National Stock Exchange of India Circular Department: SURVEILLANCE](https://nsearchives.nseindia.com/content/circulars/SURV67436.pdf)
41. [SEBI’s New Rules for Intraday Derivatives Trading](https://www.namsecurities.in/blog/sebi%E2%80%99s-new-rules-for-intraday-derivatives-trading)
42. [SEBI Regulates Expiry Day Clash Between NSE and BSE - ICICI Direct](https://www.icicidirect.com/research/equity/finace/sebi-clears-expiry-day-clash-between-nse-and-bse)
43. [Thursday, December 11, 2025 | 09:13 AM ISTहिंदी में पढें](https://www.business-standard.com/markets/news/nse-defers-switching-to-monday-expiry-after-sebi-s-consultation-paper-125032800183_1.html)
44. [STT hike on F&O: Budget 2026 impact on markets, volumes](https://www.multibagg.ai/market-pulse/articles/stt-hike-fo-market-impact-cmupduooc00052urwm6m9cd8s)
45. <https://www.business-standard.com/markets/news/sebi-derivatives-settlement-closing-auction-cas-market-timings-126091200337_1.html>
46. [Closing Auction Session: NSE & BSE's New Closing Price Mechanism Explained](https://stockk.trade/blogs/closing-auction-session-a-new-era-in-indias-closing-price-discovery)
47. [SEBI F&O Limits: Margin, Lot Size, STT Changes](https://www.multibagg.ai/market-pulse/articles/sebi-fo-limits-margin-stt-cmsgh322a046b0zl3fi1zl5ht)
48. [Page 1 of 213 CHAPTER 5: EXCHANGE TRADED DERIVATIVES 1.](https://www.sebi.gov.in/sebi_data/commondocs/dec-2024/RE_Chapter%205%20-%20Exchange%20Traded%20Derivatives%20FINAL_1_p.pdf)
49. [STT Changes in Budget 2026: What F&O Traders Need to Know - ICICI Direct](https://www.icicidirect.com/futures-and-options/articles/stt-changes-in-budget-2026-what-f-o-traders-need-to-know)
50. [Power Trading with MarketProfile and Orderflow: 9789356020665: Coelho, Shai: Books](https://www.amazon.com/Power-Trading-MarketProfile-Orderflow-Coelho/dp/9356020663)
51. [SEBI Released 2 Analytical Studies](https://www.fintechbiznews.com/govtregulators/sebi-released-2-analytical-studies)
52. [SEBI FY26 F&O Study: 88% Traders Lost Money](https://www.riddhisiddhisharebrokers.com/sebi-fo-traders-loss-study-fy26)
53. [SEBI Studies Retail Equity Derivatives Trading Trends FY25-FY26](https://taxguru.in/sebi/sebi-studies-key-trends-retail-participation-trading-behaviour-profitability-equity-derivatives.html)
54. [SecuritiesandExchangeBoardofIndia on X: "SEBI has released a study on “Profitability of Individual Traders in the Equity Derivatives Segment (FY25–FY26)”. The study examines profitability, participation, transaction costs and loss outcomes of individual traders in the equity derivatives segment. … / X](https://x.com/SEBI_updates/status/2090451964626894921)
55. [Nearly 90% Retail F&O Traders Lost Money In FY26. Why Do They Keep Coming Back?](https://www.outlookbusiness.com/markets/nearly-90-retail-fo-traders-lost-money-in-fy26-why-do-they-keep-coming-back)
56. [Why 87.7% of Individual F&O Traders Lost Money in FY26: SEBI Data Explained](https://www.finnovate.in/learn/blog/sebi-fno-trader-losses-fy26-individual-derivatives)
57. [SEBI Equity Derivatives Study FY26](https://www.corplawupdates.in/updates/sebi-equity-derivatives-retail-trader-study-fy26)
