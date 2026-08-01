# 00 · Vision & Operating Doctrine

> **ATIS Design Doc 00 · v0.2-draft · 2026-07-11 · Status: awaiting review (validation pass applied — see [09](09-VALIDATION-REVIEW.md))**
> Downstream: all other docs derive their priorities from this one.

---

## 1. Mission

Build an **Autonomous Trading Intelligence Platform (ATIS)** for Indian equities, Indian F&O,
cryptocurrency, and MCX commodities that:

1. **Understands markets before acting** — maintains a continuously updated, evidence-based model
   of market structure, participants, liquidity, and regime.
2. **Trades only measured edge** — every action is justified by calibrated probabilities and
   positive net expected value, or it does not happen.
3. **Treats risk as an independent authority** — a deterministic risk kernel that no signal,
   agent, or model can override.
4. **Earns autonomy gradually** — recommendation first, assisted execution second, constrained
   autonomy only after statistical proof.
5. **Learns from everything** — every trade, every skipped trade, every failure becomes permanent
   institutional memory that improves the next decision.

The benchmark for behavior is a disciplined institutional trading firm, scaled down to a single
operator: research rigor of a quant fund, risk culture of a bank prop desk, execution hygiene of
a market maker, and the paranoia of a compliance officer.

## 2. What ATIS is / is not

| ATIS is | ATIS is not |
|---|---|
| A market-understanding system that sometimes trades | A trading bot that sometimes thinks |
| Evidence-aggregating, probability-calibrated | Indicator-crossover / fixed-rule signal generator |
| Mid-frequency (minutes → weeks) | HFT, latency arbitrage, market making |
| Expectancy- and drawdown-optimized | Win-rate or trade-count optimized |
| Explainable by construction | A black box |
| Human-governed, machine-operated | Set-and-forget |
| Permanent-memory, self-improving | Static strategy collection |

## 3. Prime directive and priority stack

When objectives conflict, the higher item always wins:

1. **Capital preservation**
2. **Risk control**
3. **Long-term stability**
4. **Explainability**
5. **Robustness**
6. **Adaptability**
7. **Returns**

Returns rank last deliberately: they are the *output* of doing 1–6 well, not an input to optimize
directly. Corollary — **the platform must never need a trade**. Insufficient evidence, degraded
data quality, unhealthy market, low confidence, breached limits, or agent disagreement all resolve
to the same safe answer: NO TRADE.

## 4. The question loop (core philosophy)

ATIS runs a continuous observe–orient–decide–act loop. Each standing question is owned by a
subsystem, so the philosophy is traceable to architecture:

| Standing question | Owner | Doc |
|---|---|---|
| What market exists right now? | Market Regime Agent → MarketState | 02, 04 |
| Why is price moving? | News/Macro/Order Flow attribution | 02, 03 |
| Which participants control the market? | Order Flow, Options, FII/DII, Crypto Intel agents | 02 |
| Where is liquidity? | Liquidity Agent (pools, sweeps, stop clusters) | 02, 04 |
| What evidence supports this trade? | Confidence Engine (evidence aggregation) | 02 §5 |
| What evidence contradicts it? | Devil's Advocate Agent (mandatory contra-case) | 02 §3 |
| Which strategy currently has edge? | Strategy Manager + validation registry | 04 |
| Has market behavior changed? | Regime change detection + drift monitors | 04, 06 |
| Should risk increase or decrease? | Adaptive risk multiplier + drawdown governor | 05 |
| Should no trade be taken? | Default answer unless all gates pass | everywhere |

## 5. Target markets and instruments

| Market | Venues | Instruments | Session (IST) | Data / access reality |
|---|---|---|---|---|
| Indian equities | NSE (primary), BSE | Cash equities, ETFs | 09:15–15:30 (+ pre-open auction 09:00–09:08) | Broker WebSocket gives conflated ticks + 5-level depth; true tick history via paid vendor; T+1 settlement |
| Indian F&O | NSE (NFO); BSE optional later | Index & stock futures, index & stock options | 09:15–15:30 | Single-weekly-expiry regime (verified 2026-07, [09 §3.1](09-VALIDATION-REVIEW.md)): NIFTY weekly expires **Tuesday**; other NSE indices monthly-only (BANKNIFTY has no weekly); SENSEX weekly on BSE (Thu). Expiry-day +2% ELM on short index options; expiry-day calendar-spread margin spikes; SPAN+exposure margins; MWPL ban periods; stock F&O physically settled; SEBI algo framework fully binding since Apr 2026 |
| Commodities | MCX (via broker) | Futures, options (crude, natural gas, gold, silver, base metals, select agri) | 09:00–23:30/23:55 (non-agri evening session) | Driven by global benchmarks (COMEX/NYMEX/LME); currency (USDINR) interaction |
| Crypto | Binance, Bybit, Delta Exchange India, Coinbase (configurable) | Spot, perpetual futures | 24×7 | Full L2 order book + aggressor-flagged trades freely available; funding rates; Indian tax/TDS constraints (see §11) |

**Expansion principle:** adding a market = new connector + venue config (calendar, tick size, lot
size, cost model, data-tier declaration) + risk limits entry. No core redesign. The contract that
guarantees this is defined in [01 §3](01-ARCHITECTURE.md) and [03 §3](03-DATA-PLATFORM.md).

## 6. Operating frequency — honest scope

- **Decision horizon:** minutes to weeks. Scalping below ~1-minute holding time is out of scope.
- **Reaction latency targets:** sub-second market-state updates; seconds-scale trade decisions;
  order submit→broker-ack bounded by broker API (~50–300 ms).
- **Explicitly not HFT.** No co-location, no exchange-native connectivity in v1. Indian retail/API
  access and SEBI's algo framework make sub-millisecond competition unwinnable and unnecessary —
  our edge is *understanding*, not speed.
- We still adopt HFT-grade **engineering discipline**: determinism, idempotent orders, kill
  switches, continuous reconciliation, TCA, event-sourced audit. The architecture keeps a
  fast-path upgrade open (Rust gateway, vendor co-lo) without redesign.

## 7. The institutional metaphor

| Institutional function | ATIS subsystem |
|---|---|
| Research desk / quant researchers | Research Engine, Strategy Lab (06, 04) |
| Portfolio manager | Portfolio Manager Agent + Capital Allocation Engine (05) |
| Risk desk (independent) | Risk Kernel — deterministic, veto-holding (05) |
| Execution desk | Execution Engine + broker adapters (07) |
| Compliance / audit | Governance Agent + hash-chained audit log (02, 08) |
| Market data team | Data Platform + Data Quality Engine (03) |
| Middle office | Reconciliation + TCA services (07) |
| Investment committee | Trade Committee protocol (02 §4) |
| COO / operations | Control plane: modes, limits, kill switches (01 §14) |

## 8. Graduated autonomy — operating modes

Mode is set **per market**, is instantly revocable, and only ever advances through governance
gates (full gate criteria in [08 §2–5](08-IMPLEMENTATION-ROADMAP.md)):

| Mode | Name | Platform does | Human does | Advance gate (summary) |
|---|---|---|---|---|
| P1 | Recommendation | Full analysis → complete TradePlan with reasoning, evidence, contra-case, alternatives. Records user action & market outcome, including trades not taken. | Reads, decides, executes manually (or ignores) | ≥60 sessions of live recommendations; calibration ECE ≤ 0.05 (P); positive paper expectancy; zero unexplained decisions |
| P2 | Assisted execution | Everything in P1 + stages ready-to-fire orders with all risk checks passed | One-click approve/reject per order; every approval/rejection logged as training data | ≥3 months; execution error rate < 0.5% (P); recon breaks = 0 unresolved; TCA within model |
| P3 | Constrained autonomy | Auto-executes within hard caps (small capital slice, tight limits, event embargoes) after 10-point pre-flight safety pipeline | Sets policy, watches dashboards, holds kill switch, reviews daily | Scales capital only via performance gates; never exits human governance |

## 9. Success metrics

Targets are initial proposals **(P)** — review in 08 §14. All performance figures are **net of
costs** (brokerage, STT/CTT, exchange charges, GST, stamp, SEBI fees, slippage), pre-tax.

**Performance**

| Metric | Target (P) |
|---|---|
| Expectancy per trade | ≥ +0.15 R |
| Profit factor | ≥ 1.4 |
| Sharpe (annualized, net) | ≥ 1.5 |
| Sortino | ≥ 2.0 |
| Positive months | ≥ 65% |
| Payoff ratio (avg win / avg loss) | ≥ 1.2 |

**Risk**

| Metric | Target (P) |
|---|---|
| Max drawdown (design target) | ≤ 8% of equity |
| Hard platform stop | 10% from high-water mark (05 §7) |
| Daily loss soft/hard | 1.5% / 2.5% of equity |
| 1-day VaR(97.5) | ≤ 1.5% of equity |
| Single-position risk | ≤ 0.5% of equity per trade (P1–P3 pilot) |

**Process & learning**

| Metric | Target (P) |
|---|---|
| Calibration error (ECE) of confidence scores | ≤ 0.05 |
| Decisions with complete DecisionRecords | 100% (hard requirement) |
| Post-trade reviews generated | 100% of trades + sampled no-trades |
| Regime-change detection lag (measured in replay) | ≤ 1 session |
| Strategies retired per year (healthy pruning) | ≥ 1 (a zero here is a red flag) |

**Operations**

| Metric | Target (P) |
|---|---|
| Uptime during market hours | ≥ 99.5% |
| Clean-data rate (post DQ engine) | ≥ 99.9% |
| Reconciliation breaks unresolved > T+1 | 0 |
| Kill-switch drill cadence | monthly, 100% pass |

**Anti-metrics** — never optimized, monitored only for anomaly: win rate, trade count, signal
count, gross (pre-cost) returns.

## 10. Non-goals (v1)

- HFT, market making, latency arbitrage
- Managing third-party capital (triggers PMS/AIF licensing in India — out of scope)
- Multi-tenant SaaS / selling signals
- Social/copy trading
- Tax optimization advice
- Multi-account / multi-entity operation (one account per venue in v1)
- Any guarantee of returns

## 11. Constraints and compliance reality

These shape the design and the roadmap; ignoring them is how retail "institutional" projects die.

1. **SEBI retail algo framework — verified in force (Apr 2026 binding; [09 §3.1](09-VALIDATION-REVIEW.md)).**
   The load-bearing number: **10 orders/second per client** (exchange-set threshold). At or below
   it, API orders carry a generic exchange algo-ID and self-developed algos need **no strategy
   registration**; above it, registration via broker + strategy-specific algo-ID tagging.
   Order-placement APIs must originate from a **static IP whitelisted per API key**. ATIS is
   mid-frequency by design — the platform's order-rate governor holds ≤5 orders/s (07 §3),
   making the **under-threshold path the default P3 compliance route** (broker's written
   concurrence is a P0 checklist item). Human order-by-order confirmation (P2) is likely outside
   the "algo" definition entirely — to be confirmed with the broker, not assumed. Audit trails
   are mandatory regardless (5-year retention, 08 §10).
2. **Data licensing.** Real-time NSE tick-by-tick and full depth are exchange-licensed and
   expensive. Broker WebSockets provide conflated snapshots with 5-level depth — sufficient for
   profiles and structure, *not* for true footprint order flow. Detectors are therefore
   **data-tier aware** and degrade gracefully (03 §2, 04 §2). Crypto has no such constraint.
3. **Cost drag.** Indian F&O and intraday equity carry STT/CTT, exchange charges, GST, stamp duty,
   SEBI fees, brokerage. The cost model is mandatory in every backtest and every live EV
   computation (04 §9). At small capital, flat costs materially move expectancy.
4. **Crypto taxation & regulation (India) — validated 2026-07, see [09 §3](09-VALIDATION-REVIEW.md).**
   The 30% VDA tax (no loss offset) and 1% TDS remain in force post-Budget-2026, with new
   exchange-level transaction reporting (CARF-aligned) — assume full tax-department visibility.
   **Design consequence: derivatives-first.** INR-settled crypto F&O on FIU-registered venues
   (Delta Exchange India, CoinDCX futures) is treated by prevailing practitioner consensus as
   business income — loss offset allowed, no TDS — though this is *untested in court* and carries
   reclassification risk. Spot is viable only for low-turnover positions. 25 offshore platforms
   were blocked in Oct 2025; venue universe defaults to **FIU-registered only** (FEMA and
   bank-freeze exposure otherwise). RBI signaled a prohibition-leaning stance to the parliamentary
   committee in July 2026 — regulatory continuity is a live tail risk: venue balances are
   minimized (working margin only), a withdrawal-first emergency playbook exists, and the
   Monsoon-Session committee report is a standing watch item (08 §13.14).
5. **Market microstructure specifics** the platform must respect natively: pre-open auction,
   per-stock circuit bands and index circuit breakers, F&O ban periods (MWPL 95%), expiry-day
   dynamics and auto square-off cutoffs, peak-margin rules, MCX evening-session/US-DST shifts,
   crypto exchange maintenance windows and funding timestamps.
6. **Capital assumption.** Pilot band assumed ₹10L–₹50L (P). All sizing math scales, but
   capacity floors and cost drag differ by band — confirm in review.

## 12. Guiding principles

1. **Survive first, compound second.**
2. **No trade is the default.** Every gate failure resolves to abstention, never to "trade smaller and hope."
3. **Evidence over opinion.** Every input carries provenance, a calibrated probability, and a validation history.
4. **No concept is sacred.** Market Profile, SMC, Wyckoff, order-flow patterns — each detector earns
   confidence weight only through statistical validation; unvalidated detectors publish nothing (04 §2, §10).
5. **One codepath.** Backtest, replay, paper, and live trading run the same engine — the backtest *is* the system in replay mode.
6. **Independent risk.** The risk kernel can veto or shrink anything; nothing overrides a risk rejection except a human through governance, with audit.
7. **Determinism and replay.** Any decision must be reproducible from the event log, byte for byte.
8. **Graceful degradation.** Missing input ⇒ wider uncertainty ⇒ smaller size or abstention — never silent guessing.
9. **Humans govern, machines operate.** Humans set policy, limits, and promotions; machines execute policy. LLMs never touch price/size arithmetic (02 §7).
10. **Explainable by construction.** A decision that cannot be explained cannot be executed.
11. **Small reversible steps.** Capital scales only after out-of-sample proof at the previous size.
12. **Institutional memory is permanent.** Nothing is deleted; failures are the most valuable data we own.

## 13. Open questions for review

1. Pilot capital band (₹10L–₹50L assumed) and split across the four markets?
2. Crypto policy — **validation review now recommends:** FIU-registered venues only,
   derivatives-first (INR-settled perps/futures), spot for low-turnover only, venue balances
   minimized ([09 §3](09-VALIDATION-REVIEW.md)). Confirm or override.
3. Are the §9 targets acceptable as v1 gates, or tighten/loosen any?
4. Priority order of markets for Phase 1 (proposal: NSE F&O index derivatives + top-100 equities first, crypto second, MCX third)?
5. Is options *selling* (defined-risk) in scope for v1 strategy families, or long-premium/futures only (04 §4)?
