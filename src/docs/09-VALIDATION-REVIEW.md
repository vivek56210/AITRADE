# 09 · Validation Review & v0.2 Change Log

> **ATIS Design Doc 09 · v0.2-draft · 2026-07-11 · Status: complete (this doc records the validation of docs 00–08)**
> Method: adversarial self-audit + external fact research with citations. Verdict in §1.

---

## 1. Scope, method, verdict

The v0.1 design was validated on five axes:

1. **Internal consistency** — cross-doc contradictions, broken invariants, numeric coherence.
2. **Market reality (India)** — settlement mechanics, shorting rules, expiry regimes, margin
   system, exchange microstructure specifics.
3. **Statistical soundness** — are the gates and metrics actually measurable at our sample sizes?
4. **Operational feasibility** — solo-operator reality, 24×7 crypto, failure ergonomics.
5. **Regulatory & vendor currency** — verified against **July 2026** primary sources via
   external research (SEBI/exchange rules, crypto tax/venue status, broker API and data-vendor
   facts), since several load-bearing facts changed in 2024–2026.

**Verdict: the architecture stands — no structural rework was needed.** The planes, event-sourced
core, independent risk kernel, committee protocol, validation-gated detectors, and graduated
autonomy all survived review. However, the audit found **3 HIGH-severity gaps** (any one of which
could have caused a real-money incident), 18 medium/low corrections, and several external facts
that reshape strategy scope (notably: crypto derivatives-vs-spot taxation, the post-2024 F&O
regime, and an easier-than-assumed SEBI compliance path for P3). All fixes are applied in the
v0.2 docs; this document is the audit trail.

## 2. Internal audit findings (all resolved in v0.2)

| ID | Sev | Finding | Resolution (doc §) |
|---|---|---|---|
| F-01 | **HIGH** | **Stock F&O physical delivery unhandled.** All single-stock derivatives settle physically; an ITM option or future held into expiry creates a delivery obligation of full contract notional — orders of magnitude beyond planned trade risk. v0.1 had no guard. | New risk check 16: hard veto inside T-4 sessions of expiry + forced-flatten plans (05 §3, 07 §7); strategy constraint (04 §4.2); risk register #11 (08 §13) |
| F-02 | **HIGH** | **Equity short-selling constraint missing.** Retail cash-equity shorts are intraday-only (no SLB in v1); v0.1 strategy families implied positional equity shorts that are simply impossible. | Risk check 17 + instrument-master capability matrix (05 §3, 03 §4.1); families constrained to F&O instruments for positional shorts (04 §4.1) |
| F-03 | **HIGH** | **Calibration gates statistically unsound.** At ~3 plans/day, monthly trade-level ECE (target ≤0.05) is noise — the gate as written was unfalsifiable theater. | Hierarchical calibration: evidence level (n≈thousands/month) carries the power; decision level uses bootstrap CIs on ≥200 samples; gates are sample-aware (02 §5, 06 §5, 08 G1); register #12 |
| F-04 | MED | Weekly-expiry/F&O-regime facts in v0.1 were pre-reform generic ("weekly index expiries") — the 2024–25 SEBI measures changed the landscape materially. | Verified externally (§3.1) and encoded: single-weekly regime, expiry-day policy, lot sizes (00 §5, 04 §4.4) |
| F-05 | MED | **News-momentum family cannot be honestly backtested** — point-in-time news archives are scarce/expensive; a historical "backtest" would be hindsight fiction. | Family validates live-forward only (extended PAPER); platform archives its own news stream from day one to build PIT history (04 §4.3, 03 §3.4); register #13 |
| F-06 | MED | **No unattended-hours policy** — crypto trades 24×7 but the operator sleeps; v0.1 had no doctrine for autonomous nights/weekends. | Unattended windows: risk mult ≤0.5, no dead-liquidity entries, protection pre-verified; one-click safe mode → P1 (05 §8, 07 §1) |
| F-07 | MED | **Contract rolls & continuous futures unspecified** — front-month selection, roll execution, and back-adjusted research series didn't exist in v0.1. | Instrument master & contract lifecycle section: roll policy, rolls as risk-checked TradePlans, panama+unadjusted series (03 §4.1) |
| F-08 | MED | Order-rate limits unmodeled — broker API caps and the SEBI algo-registration threshold interact with order slicing. | Order-rate governor (token bucket per broker/venue) with headroom below the algo threshold (07 §3); thresholds per §3.1 |
| F-09 | MED | Gap-through-stop risk unbudgeted — positional stops are not guarantees; overnight gaps blow through them. | Overnight risk accounted at 2× stop distance; stop floor vs p95 overnight gap; fraud-gap stress binds single names (05 §4) |
| F-10 | LOW | Replay could theoretically emit live orders (no stated isolation). | Environment-scoped command topics; live adapters subscribe to prod scope only (01 §7) |
| F-11 | LOW | Cash/ledger mechanics unmodeled (T+1 sale proceeds, blocked vs free margin, MTM debits). | Ledger reconciliation added; margin checks use *available* funds (07 §9, 05 §3.9) |
| F-12 | LOW | Options backtest fills too optimistic (mid-fills on wide spreads). | Quote-driven fills with spread haircut + min-quote-size screen; illiquid strikes untradeable (04 §9) |
| F-13 | LOW | NSE options: SL-M order type unavailable — protection design must not assume market stops. | Protective-offset limit ladder encoded (07 §3); verified §3.3 |
| F-14 | LOW | Exchange freeze-quantity limits not encoded (large parent orders get rejected). | Freeze-quantity-aware slicing (07 §3) |
| F-15 | LOW | Corporate-action ex-dates silently break resting stops. | Ex-date flags in instrument master; protective orders re-based pre-open (03 §4.1, 07 §7) |
| F-16 | LOW | Committee trigger semantics undefined (busy-loop vs event-driven ambiguity). | Event-driven with per-instrument debounce + periodic sweep (02 §4.6) |
| F-17 | LOW | TOTP auto-login sits in a broker-ToS grey zone; treated too casually in v0.1. | Written broker confirmation is a P0 onboarding checklist item (01 §11, 08 §2) |
| F-18 | LOW | P1 recommendations had no delivery SLA or validity window — stale recommendations are dangerous. | ≤5 s decision→notification; explicit visible expiry on every card (07 §1) |
| F-19 | LOW | Historical backfill wasn't on the critical path — P1 strategy validation would have stalled. | Backfill starts in Phase 0 (03 §10, 08 §2) |
| F-20 | LOW | Single-account scope never stated. | Non-goal added: one account per venue in v1 (00 §10) |
| F-21 | MED | **v0.1 itself contained a stale contract spec** — the sizing example used NIFTY lot 75; the Jan-2026 series cut it to 65 (second change in ~14 months). Exactly the failure mode the design warns about. | Example corrected; hard rule stated: contract specs only ever from exchange masters via the instrument master, never hardcoded (05 §4, 03 §4.1) |

## 3. External research findings (July 2026, with sources)

### 3.1 SEBI / NSE / F&O landscape

| ID | Finding (status) | Design impact → change |
|---|---|---|
| R-S1 | **Algo framework fully binding since 2026-04-01** (SEBI circular Feb 4 2025 + Sep 30 2025 extension; glide path completed Jan 2026) (CONFIRMED — sebi.gov.in circulars) | No transition room — platform must be compliant from day one (00 §11.1) |
| R-S2 | **Threshold = 10 orders/sec per client**, set by exchanges (NSE circular May 6 2025). ≤10 OPS ⇒ generic exchange algo-ID, **no strategy registration**; >10 OPS ⇒ registration via broker + strategy algo-ID. Zerodha hard-enforces via HTTP 429 and caps slicing at 10 (CONFIRMED — Zerodha Z-Connect, kite.trade forum) | **P3 path is easier than v0.1 assumed:** under-threshold operation is the default compliance route; order-rate governor set to ≤5/s (07 §3, 08 §5) |
| R-S3 | **Static IP whitelisting per API key** for order APIs (market data exempt), broker-enforced since Apr 2026 (CONFIRMED — kite.trade forum) | Static-IP VPS deployment requirement (07 §4, 08 §5) |
| R-S4 | Human order-by-order confirmed API orders are likely outside the "algo" definition (LIKELY — consistent secondary sources; primary PDF wording not machine-verified) | P2 may carry a lighter regulatory surface — confirm with broker in writing, never assume (00 §11.1) |
| R-S5 | **Weekly expiries: NIFTY Tuesday (NSE) and SENSEX Thursday (BSE) only** since Sep 1 2025; BANKNIFTY/FINNIFTY/MIDCPNIFTY weeklies discontinued Nov 2024 (CONFIRMED — Business Standard, Zerodha) | Expiry logic, embargo calendar, premium-selling family all re-anchored (00 §5, 04 §4.4) |
| R-S6 | **Lot sizes: NIFTY 65, BANKNIFTY 30** from Jan-2026 series (CONFIRMED — HDFC Sky, Ventura) | F-21 fix; no-hardcoding rule (05 §4) |
| R-S7 | **Expiry-day +2% ELM on short index options** (since Nov 2024, in force) + upfront full premium collection (Feb 2025) + no calendar-spread margin offset on expiry day — index Feb 2025, **extended to single-stock May 5 2026** (CONFIRMED — NSE Clearing, SEBI Feb-2026 circular) | Margin projector must model expiry-day spikes for both index and stock spreads (04 §4.4) |
| R-S8 | Intraday MWPL monitoring: ≥4 random snapshots/day since Apr 2025 (CONFIRMED) | Ban-list + intraday position discipline unchanged (05 §3.5) |
| R-S9 | Delta/FutEq index-option position limits (₹1,500 cr net EOD etc.) — irrelevant at pilot capital by ~4 orders of magnitude (CONFIRMED — SEBI May 2025 circular) | No design change; documented so no one panics later |
| R-S10 | Stock F&O physical settlement confirmed; **delivery margins ramp from E-4** (~10%→70%); brokers force square-off ITM options expiry afternoon (CONFIRMED policy; exact ramp percentages broker-variable) | Validates the T-4 delivery-window guard (F-01); E-4 margin ramp added to margin model (05 §3.16, 07 §4) |
| R-S11 | SEBI *exploring* F&O investor-suitability criteria — proposal stage only (UNVERIFIED beyond press) | Watch item (§5.8) |

### 3.2 Broker APIs, data vendors, tooling

| ID | Finding (status) | Design impact → change |
|---|---|---|
| R-B1 | **Kite Connect pricing:** free "Personal" execution key (orders/GTT, no data) + ₹500/mo Connect key now bundling live WS **and** historical candles (old ₹2k historical add-on scrapped Feb–Mar 2025) (CONFIRMED — Zerodha support + kite pricing pages, fetched 2026-07-11) | Cost table corrected (08 §12); dual-key pattern: free key for execution, paid key for data |
| R-B2 | Kite rate limits: 10 orders/s per client (SEBI-aligned), REST ~3/s, historical ~3/s; minute/day order caps forum-sourced (~200–400/min) (CONFIRMED for 10/s; LIKELY for minute caps) | Governor defaults ≤5/s, ≤150/min (07 §3) |
| R-B3 | Kite WS: 3,000 instruments × 3 connections per key, **5-level depth only** (CONFIRMED — kite docs) | Tier-B for NSE needs vendor tick or Dhan depth; watchlist sizing math (03 §3.1) |
| R-B4 | Kite GTT: full CRUD API incl. two-leg OCO (CONFIRMED) | Dead-man protection design is viable as specified (07 §7) |
| R-B5 | **Zerodha discourages TOTP login automation** — daily interactive login is the stated policy ("mandatory… at least once a day; we don't recommend automating") (CONFIRMED — kite.trade forum staff) | **Design default flipped:** daily login is a human pre-open ritual step; automation demoted to documented contingency (01 §11, 08 §9) |
| R-B6 | **Dhan:** trading APIs free; data ₹499/mo (waived with activity); orders 10/s, 250/min, 7,000/day; WS 5×5,000 instruments; **20-level depth feed for NSE EQ+NFO, ~50 instruments/connection**; dedicated order-update WS; Forever/OCO orders (CONFIRMED — dhanhq.co docs) | India order-flow upgrade for a focus watchlist (03 §2, 02 §3.1-6); failover broker capabilities confirmed (07 §4) |
| R-B7 | **TrueData** = the tick-by-tick option (push ticks + option-chain greeks/IV, 5-level depth, ~₹2–10k/mo quote-based); **GDFL = 1-second snapshots**, EOD history to 2010 but tick archive ~1 week (CONFIRMED features; archive depths partly UNVERIFIED) | P0-D2 reframed: TrueData for ticks, GDFL only if 1s-bars suffice; **GDFL is not a backfill source**; self-archiving from day 0 is the structural plan B (03 §3.1, §10) |
| R-B8 | **NautilusTrader** v1.230.0 (Jun 2026): Rust core, 20 stable adapters (Binance, Bybit, IBKR, Coinbase…), **no Indian broker adapter exists**, recent releases shipped breaking API changes (CONFIRMED — GitHub releases, docs) | P0-D1 spike sharpened: adoption = writing/maintaining Kite+Dhan adapters against a fast-moving API; spike timeboxed 2 weeks; crypto-only Nautilus + in-house India path is a live hybrid option (§5.4) |
| R-B9 | GIFT Nifty: best-effort via Kite quotes (personal use), else delayed web sources; mainstream vendors don't carry NSE IX (LIKELY) | Added as context-only source — never a hard dependency (03 §3.1) |
| R-B10 | **SL-M blocked for options** on NSE and BSE (since 2021, still current) (CONFIRMED — Zerodha bulletins) | Validates F-13: synthetic stop-market = SL-limit with aggressive offset (07 §3) |

### 3.3 India crypto tax, venues, regulatory direction

| ID | Finding (status) | Design impact → change |
|---|---|---|
| R-C1 | 30% VDA tax (no loss offset) **in force**; carried into the new Income-tax Act 2025 effective Apr 2026 (CONFIRMED — taxguru.in, cleartax.in 2026) | High-turnover **spot** strategies are structurally penalized → derivatives-first posture (00 §11.4) |
| R-C2 | 1% TDS retained; Budget 2026 refused reduction (CONFIRMED — Yahoo/Cointelegraph Feb 2026) | ~1% skim per spot sell → spot restricted to low-turnover positions (04 §4.5, 00 §11.4) |
| R-C3 | Budget 2026 added exchange transaction-reporting with penalties (old §285BAA → §509(1); CARF alignment 2027) (CONFIRMED — Trade Brains Feb 2026) | Assume full tax-authority visibility; clean audit trails are a feature, not overhead (08 §10) |
| R-C4 | **Crypto derivatives taxation has no CBDT ruling.** Prevailing practitioner position: INR-settled F&O ≠ VDA "transfer" ⇒ business income, loss offset, **no TDS** (Delta India / CoinDCX F&O). Untested in court (CONFIRMED absence of guidance; business-income treatment LIKELY — coinswitch.co, carajput.com, mudrex.com) | **Largest strategy-shaping finding:** crypto sleeve pivots to INR-settled derivatives on FIU venues; funding-carry inherits business-income assumption; a reclassification reserve is a new open question (§7) |
| R-C5 | Venue landscape: Binance FIU-registered 2024, Bybit fully restored Sep 2025, Delta India dominant INR-F&O venue, CoinDCX registered; **25 offshore platforms blocked Oct 2025** (BitMEX, Phemex, Poloniex…) (CONFIRMED — The Block, CoinDesk, TechCrunch) | Venue universe = FIU-registered only (default policy, 00 §11.4); offshore = FEMA/bank-freeze exposure |
| R-C6 | INR rails functional; CoinDCX absorbed a $44M hack (Jul 2025) from reserves (CONFIRMED/LIKELY — finowings, press) | Venue-balance minimization + withdrawal-first playbook added (05 §5, 07 R7) |
| R-C7 | Funding income tax treatment unsettled; follows trader's classification (LIKELY — KoinX) | Funding-carry EV computed under business-income assumption with 30% downside sensitivity (04 §4.5) |
| R-C8 | **Regulatory direction hostile-leaning:** DEA discussion paper shelved; RBI pitched containment/prohibition to the Parliamentary Standing Committee (2026-07-02); committee report expected Monsoon Session 2026 (CONFIRMED — cryptotimes.io 2026-07-08, Business Standard 2026-07-03) | Standing watch item + risk register #14: crypto is a *revocable* sleeve; capital there must be withdrawable in days, strategies must die gracefully (08 §13) |

## 4. Changes considered and explicitly rejected

| Considered | Rejected because |
|---|---|
| Adopt Flink for stream processing now | Ops weight for a 1–2 person team; custom consumers + Bytewax suffice at design load; revisit trigger already defined (01 §10) |
| Full L3 order-book simulation for NSE backtests | No data exists to calibrate it (no TBT feed in v1) — pessimistic Tier-B fill model is *more* honest than a fake queue model (04 §9) |
| Devil's Advocate hard-veto power | Keeps decision authority ambiguous vs risk kernel; penalty + escalation preserved; revisit at P3 (02 Q1 open) |
| Naked option selling / options market making | Permanently out — tail risk incompatible with priority stack (00 §3) |
| RL-based trade management in v1 | No baseline to beat yet; rules first, offline RL as research track (04 §8, 06 §9) |
| Simultaneous multi-broker routing (India) | Reconciliation complexity outweighs benefit at pilot size; primary+failover pair retained (07 §5) |
| Building a custom feature store | Feast covers PIT-correct serving; effort belongs in detectors (01 §9) |
| Skipping the digital twin to ship faster | Twin *is* the validation, audit, and parity mechanism — removing it collapses the design's honesty guarantees (06 §10) |
| SLB (securities lending) to enable positional equity shorts | Operationally heavy, poor availability at pilot size; F&O expression suffices (F-02) |
| Treating GEX/dealer-positioning as validated input | India lacks reliable dealer-positioning data; stays CANDIDATE until it earns weight (04 §2.7) |

## 5. Residual risks & standing watch items

1. **Crypto tax reclassification** (R-C4): business-income treatment of INR-settled F&O could be
   challenged — maintain a contingency reserve policy (open question §7) and re-check quarterly.
2. **Monsoon-Session committee report** (R-C8): potential regime change for the crypto sleeve —
   watch item with a pre-written de-risk playbook.
3. **Further SEBI F&O tightening**: the 2024–26 direction is restrictive; index-options
   strategies must tolerate parameter changes (lot sizes, expiries, margins) without redesign —
   the limits-registry/config-as-data architecture is the mitigation.
4. **Chassis decision (P0-D1)**: no Indian broker adapter exists for NautilusTrader and its API
   still ships breaking changes (R-B8) — the spike is timeboxed to 2 weeks, and a **hybrid** is a
   live option: Nautilus for crypto venues (stable adapters exist) + in-house event core for
   India. If the spike fails outright, in-house core adds ~4–6 weeks to Phase 0.
5. **Vendor dependency**: TrueData/GDF licensing or pricing shifts could downgrade India to
   Tier C — detector tier-degradation is designed in, but strategy breadth would narrow.
6. **Operator concentration**: one human governs everything — mitigated by fail-closed defaults,
   safe mode, dead-man invariant; not eliminable at this scale.
7. **LLM cost/behavior drift**: budget guards + eval-gated prompt registry mitigate; degrade path
   to classic NLP tested monthly.
8. **SEBI F&O investor-suitability proposal** (R-S11): could add eligibility gating for F&O
   participation — proposal-stage only; quarterly check.
9. **Daily-login operational dependency** (R-B5): the human login step is now a hard daily
   dependency for India sessions — mitigated by pre-open alerting and safe-mode default if no
   session exists by 09:00 IST.

## 6. v0.1 → v0.2 change log (per doc)

- **00-VISION:** crypto constraint rewritten from research (derivatives-first, FIU-only,
  regulatory tail-risk watch); SEBI framework constraint rewritten with verified mechanics
  (10 OPS threshold, static IP, under-threshold P3 route); F&O expiry regime verified and
  corrected (NIFTY Tue / SENSEX Thu, BANKNIFTY monthly-only); non-goal added (single account per
  venue); open question Q2 upgraded to a recommendation.
- **01-ARCHITECTURE:** replay isolation invariant; **daily-login ritual made the design default**
  (TOTP automation demoted to documented contingency); broker written-stance as P0 item.
- **02-AGENTS:** hierarchical calibration program (replaces naive monthly ECE); committee
  evaluation cadence rule; Order Flow agent depth tiers updated (Dhan 20-level focus set).
- **03-DATA-PLATFORM:** new §4.1 instrument master & contract lifecycle (capability matrix,
  rolls, continuous series, ex-date flags); source catalog re-verified and corrected (Kite/Dhan/
  TrueData/GDFL rows, GIFT Nifty added); archive reality check + self-archiving plan B;
  PIT-news honesty note; backfill on critical path.
- **04-STRATEGY-ENGINE:** "reality constraints" block on all families (shorts, delivery window,
  news live-forward-only, verified expiry-regime rules incl. expiry-day margin spikes,
  funding-carry contingency); options fill realism in backtests.
- **05-RISK-PORTFOLIO:** risk checks 16 (delivery guard) & 17 (short capability); overnight
  gap-risk budgeting; unattended-hours policy + safe mode; crypto venue-balance hygiene;
  sizing example corrected to NIFTY lot 65 with the no-hardcoding rule (F-21).
- **06-LEARNING-ENGINE:** calibration council aligned to hierarchical scheme.
- **07-EXECUTION-ENGINE:** P1 delivery SLA + validity windows; safe mode; SL-M reality for NSE
  options; order-rate governor with verified numbers (≤5/s, ≤150/min vs the 10-OPS threshold) +
  freeze-quantity slicing; verified India compliance section (Path A default); adapter capability
  rows corrected; ex-date stop re-basing; delivery-window flatten plans; ledger reconciliation.
- **08-IMPLEMENTATION-ROADMAP:** P0 additions (backfill kickoff, broker written confirmations);
  G1 calibration gate made sample-aware; P3 compliance reframed to Path A/B; pre-open ritual
  includes the daily broker login; cost table corrected from verified pricing; risk register
  #11–14; open-questions updates.
- **09 (this doc):** new.

## 7. Open-question deltas after validation

- **Answered by research (confirm or override):** crypto venue policy → FIU-registered,
  derivatives-first (00 Q2).
- **New questions:**
  1. Crypto tax-classification reserve: hold back a contingency (e.g., difference between slab
     and 30% treatment) pending clarity? (accounting/policy decision, not platform code)
  2. Unattended-hours window defaults (05 §8) — confirm 00:30–07:00 IST.
  3. BSE (SENSEX weeklies) inclusion timing — adds a second weekly-expiry venue at modest
     connector cost.
- **Unchanged and still needed:** the consolidated list in 08 §14.
