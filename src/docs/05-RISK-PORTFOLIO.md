# 05 · Risk Management & Portfolio Intelligence

> **ATIS Design Doc 05 · v0.2-draft · 2026-07-11 · Status: awaiting review (validation pass applied — see [09](09-VALIDATION-REVIEW.md))**
> Upstream: [00-VISION](00-VISION.md) §3 (priority stack) · Peers: [04-STRATEGY-ENGINE](04-STRATEGY-ENGINE.md), [07-EXECUTION-ENGINE](07-EXECUTION-ENGINE.md)
> *This doc was added beyond the original six phase docs: institutional design separates risk from alpha.*

---

## 1. Risk doctrine

1. **Independence.** The risk kernel is a deterministic C0 service with its own minimal codebase
   (Rust, auditable line-by-line, no ML, no LLM, no external API calls). It consumes plans and
   portfolio state; it outputs verdicts. **No agent, strategy, model, or config path can raise
   risk above registry limits.** Humans can only *lower* risk without process; raising any limit
   requires a governance change (versioned registry edit + sign-off + audit event).
2. **Fail-closed.** Kernel unreachable ⇒ no new trades platform-wide. Uncertainty of any kind ⇒
   the multiplier moves down, never up.
3. **Every number lives in the limits registry** (01 §14) — values below are proposed defaults (P).

## 2. Risk taxonomy (what we explicitly manage)

| Risk | Primary controls |
|---|---|
| Market | Sizing, stops, exposure & correlation limits, VaR/ES, drawdown ladder |
| Liquidity | Capacity caps (%ADV, % of touch), spread gates, market-health floor |
| Execution | Price collars, order-rate caps, TCA feedback, broker health gates (07) |
| Model | Validation gates (04 §10), calibration monitors, drift alarms (06) |
| Data | DQ tiers & halts (03 §5) |
| Operational | Kill switches, dead-man design, reconciliation, runbooks (07, 08) |
| Counterparty/venue | Broker pair failover, crypto venue exposure caps, withdrawal hygiene |
| Regulatory | Mode gates, SEBI algo compliance path, audit retention (08 §10) |
| Event | Embargo calendar, expiry rules, earnings exclusions |

## 3. Pre-trade checks (deterministic, ordered, all-or-nothing)

Every plan gets a `RiskVerdict {APPROVE | APPROVE_RESIZED | VETO}` with per-check results —
the veto reason is always explicit.

| # | Check | Rule (P) |
|---|---|---|
| 1 | Kill switches / mode | No active switch at any level covering scope; mode permits action |
| 2 | Market health | health ≥ 0.6 for instrument & market (§9) |
| 3 | Data quality | Tier & freshness satisfy strategy requirements (03 §5) |
| 4 | Event embargo | No veto-class event within window (RBI/Fed/budget/earnings for single names; expiry-day rules) |
| 5 | Instrument sanity | Not in F&O ban list (MWPL); not circuit-locked; not in auction |
| 6 | Fat finger | qty ≤ max_order_qty; notional ≤ max_order_value (₹25L P); price within ±3% of LTP collar |
| 7 | Stop present & sane | Stop distance ∈ [0.3×ATR, 3×ATR]; stop not inside a scored liquidity pool (04 §2.3) |
| 8 | Per-trade risk | risk_R ≤ risk_pct_cap × equity (0.5% P; 0.25% first live month) |
| 9 | Margin/capital | Post-trade margin utilization ≤ 60% (F&O SPAN+exposure; peak-margin compliant); free cash floor ≥ 20% |
| 10 | Position/exposure limits | §5 table — per-instrument, per-underlying, sector, gross/net, Greeks |
| 11 | Correlation-adjusted addition | Marginal risk contribution cap (§5); effective-bets floor |
| 12 | Loss budgets | Daily/weekly loss ladder state permits new risk (§7) |
| 13 | Strategy budget | Strategy's allocated risk budget not exhausted (§6); attempt caps |
| 14 | Liquidity capacity | qty ≤ 8% of 1-min volume (P) & ≤ 2% ADV; spread ≤ family cap |
| 15 | Venue/counterparty | Broker healthy (07 §5); crypto venue exposure ≤ cap |
| 16 | **Stock F&O delivery guard** | Stock derivatives are physically settled: no position may remain within T-4 sessions of expiry (hard veto + forced-flatten plan generated); no new stock F&O entries inside that window. Index derivatives (cash-settled) exempt |
| 17 | Short-capability check | Overnight short cash-equity positions prohibited (no SLB in v1); positional shorts only via F&O instruments per the instrument-master capability matrix (03 §4.1) |

## 4. Position sizing

```
risk_amount = equity × base_risk_pct × conf_scalar × regime_mult × health_mult × dd_mult × alloc_mult
qty         = risk_amount / stop_distance_per_unit          (lot-rounded down)

then capped by (whichever binds first):
  kelly_cap   : f ≤ 0.25 × Kelly(p_win, payoff)   — fractional Kelly ceiling
  liquidity   : ≤ 8% of 1-min vol, ≤ 2% ADV
  exposure    : §5 limits, margin ≤ 60%
  notional    : max position ≤ 10% equity (delta-adjusted for options)
```

- `base_risk_pct`: 0.5% (P); 0.25% in any strategy's first live month.
- `conf_scalar`: maps confidence 0.60→0.75 onto 0.6→1.0 (never >1.0 from confidence).
- `regime_mult`: strategy's regime affinity (0–1).
- `health_mult`, `dd_mult`: §9 and §7 states.
- `alloc_mult`: strategy budget utilization (§6).
- **Options:** risk = max structure loss (defined-risk only in v1); Greeks caps in §5 bind too.

Worked example: equity ₹25,00,000, base 0.4%, confidence 0.66 (scalar 0.84), range regime 1.0,
health 0.9→mult 1.0, no drawdown, alloc 1.0 ⇒ risk ≈ ₹8,400. NIFTY-FUT stop 45 pts, lot 65
(Jan-2026 series — lot sizes change; **always read from exchange masters via the instrument
master, never hardcode**, 03 §4.1) ⇒ risk/lot ₹2,925 ⇒ 2 lots (₹5,850 actual risk). Caps
re-checked on final qty.

**Gap risk (positional):** stops are not guarantees. Overnight positions budget risk at **2× stop
distance** (P) for ladder/loss accounting; stop distances must clear the instrument's p95
overnight gap; single-name positional exposure is additionally bounded by the fraud-gap stress
scenario (§10) passing at book level.

## 5. Portfolio intelligence

**Live views (portfolio-svc, 1 Hz + on change):** positions, per-market & gross/net exposure,
sector exposure, factor tilt (beta to NIFTY/BTC), currency sensitivity, options Greeks
(net Δ, Γ, Vega, Θ per underlying and book), margin utilization, correlation matrix
(EWMA λ=0.97 + Ledoit-Wolf shrinkage), **effective number of bets** (ENB via PCA of
position-risk covariance).

**Limits (P):**

| Limit | Value |
|---|---|
| Max open positions | 8 platform-wide; 3 per strategy |
| Per-underlying net risk | ≤ 1.0% equity |
| Sector gross exposure | ≤ 25% equity |
| Gross exposure | ≤ 150% equity (delta-adjusted); net ≤ 100% |
| Crypto sleeve | ≤ 20% equity gross; per-venue ≤ 60% of sleeve |
| Overnight vs intraday risk budgets | Overnight open risk ≤ 1.5% equity total |
| Net Greeks per underlying | |Δ| ≤ 0.6% equity/1% move; Γ floor ≥ −(configured); Vega ≤ 0.3% equity/vol-pt; short-Θ structures always defined-risk |
| Marginal risk contribution | New position ≤ 25% of current portfolio risk; ENB ≥ 3 when ≥ 5 positions |
| Correlated-cluster cap | Positions with pairwise ρ > 0.7 count as one cluster; cluster risk ≤ 1.5% equity |

Cross-market correlation awareness is native: BTC and crypto-beta equities are one cluster;
MCX gold and USDINR interact via the KG's `sensitive_to` edges (03 §8).

**Crypto venue counterparty hygiene (added v0.2):** on-venue balances are minimized — required
margin plus a small buffer only, excess swept out on schedule; a withdrawal-first emergency
playbook (07 §10 R7) covers venue freeze/hack scenarios. Indian venues have had material
incidents (see [09 §3](09-VALIDATION-REVIEW.md)); counterparty caps in the table above are not
theoretical.

## 6. Capital Allocation Engine

- Each strategy gets a **risk budget** (% of total risk, not notional), from:
  `budget ∝ shrunk(live expectancy, dossier expectancy) × regime_affinity(current) × capacity`,
  bounded [min 5%, max 30%] (P), renormalized; recomputed weekly + on regime change.
- New strategies enter at PILOT budget (0.25× standard) regardless of dossier strength.
- Performance weighting uses decayed live results shrunk toward research priors — no
  chasing hot streaks (shrinkage prevents allocating on noise).
- Drawdown at strategy level (−4R rolling 20 trades P) ⇒ budget halved pending review (06).
- Unallocated risk stays unallocated. **There is no pressure to deploy.**

## 7. Drawdown governance (the ladder)

Measured on equity including open PnL, from session start / rolling / high-water mark:

| Trigger (P) | Automatic action |
|---|---|
| −1.5% day | `dd_mult` → 0.5 for remainder of day |
| −2.5% day | **No new trades today**; manage exits only |
| −4% rolling 5 sessions | All position sizes halved; mandatory written review before restore |
| −6% from HWM | Flatten discretionary positions; 48 h cool-off; governance review |
| −8% from HWM | Soft stop: platform to P1 (recommendation-only) pending human decision |
| **−10% from HWM** | **Hard stop: L4 kill switch; restart requires full governance sign-off** |

Recovery protocol: after any ladder trip ≥ level 3, risk restores stepwise (0.5× for 10 trades,
then 0.75× for 10, then 1.0×) — no instant re-leverage. Anti-gaming: ladder state persists across
restarts (stored in PG, checked by kernel at boot).

## 8. Adaptive risk multiplier

`global_risk_mult ∈ [0, 1.1]` recomputed continuously from: realized-vs-expected vol spread,
liquidity conditions, regime confidence (uncertain regime ⇒ down), news-risk index, recent
platform calibration (ECE trend), correlation tightening (risk-off contagion), and the ladder
state. Asymmetry is structural: fast to cut (minutes), slow to restore (days). It multiplies
into §4 sizing; it can never exceed 1.1 and only governance can change that bound.

**Unattended-hours policy (24×7 crypto vs a sleeping operator):** during configured unattended
windows (default 00:30–07:00 IST, P) the multiplier caps at 0.5, no new entries fire in
designated dead-liquidity hours, and the protection invariant (07 §7) is re-verified before each
window opens. A one-click **safe mode** drops the entire platform to P1 (recommendation-only)
for vacations/illness — designed so ignoring the platform is always safe.

## 9. Market Health Engine

Per market & instrument: `health = weighted(liquidity score, spread quality, volatility state
vs strategy envelope, data quality, news risk, execution risk (recent slippage vs model, broker
latency))`. Bands: **≥0.8 normal · 0.6–0.8 reduced (sizing ×0.7, no low-capacity strategies) ·
0.4–0.6 exit-only · <0.4 halt + protect positions.** Health is a *veto-class* input — it cannot
be argued with by confidence (02 §5).

## 10. VaR, ES & stress testing

- **Measures (daily):** parametric + historical (2 y) + Monte Carlo VaR(95/97.5), ES(97.5),
  per-position component VaR. Limits: 1-day VaR97.5 ≤ 1.5% equity; ES97.5 ≤ 2.2% (P).
  VaR models are backtested (Kupiec POF + traffic-light); a failing VaR model is itself a
  governance incident.
- **Stress library (run nightly against live book + candidate plans):**

| Scenario | Shock spec (examples) |
|---|---|
| COVID-Mar-2020 | Index −13% day, vol ×4, spreads ×5, F&O margin spike |
| Taper-2013 / INR crisis | USDINR +3%, FII outflow regime, rates +50 bps |
| Election-Jun-2024 | Index −8% intraday swing with vol crush after |
| Single-name fraud gap | Any held stock −40% open (Yes Bank/Satyam class) |
| Crypto May-2021 / FTX | BTC −30% day, alts −50%, funding whipsaw, one venue frozen |
| Expiry pin + squeeze | Index ±2% into weekly expiry close, gamma flip |
| Venue outage mid-move | Primary broker down during −5% move (recovery per 07 §10) |
| Rate shock | RBI surprise ±50 bps; yield curve ±75 bps |
| Stagflation regime shift | 3-month adverse regime for all trend families simultaneously |

Pass criterion: worst scenario loss ≤ 2× daily hard-loss limit with all stops honored at
stressed slippage (×3 model), and no margin call under exchange stress margins.
**Reverse stress test quarterly:** "what book kills us?" — documented, discussed, limits adjusted.

## 11. Kill switches & emergency controls

- **Levels:** L1 instrument · L2 strategy · L3 market · L4 platform (01 §14). Trip = cancel
  resting entries, block new plans, policy-defined flatten (L3/L4 default: flatten intraday,
  protect positional with broker-side stops).
- **Trip authority:** any human one-click (console + hardware-key CLI + phone bot); risk kernel
  (automatic: ladder, VaR breach, margin, recon break); safety pipeline; dq-sentinel.
  **Reset authority: human only**, with written checklist, cooling period ≥ 30 min, audit event.
- **Dead-man design:** every open position always has broker-side protection (SL / GTT order)
  such that total platform death leaves no unprotected exposure (07 §7). Verified continuously
  by recon-svc; a position without live protection is a P1 page within 30 s.
- Monthly kill drills are mandatory ops ritual (08 §9) — including one "pull the plug" drill in
  paper env.

## 12. Open questions for review

1. Ladder numbers (§7) and base risk 0.5%/trade — comfortable, or start tighter (0.25% until 100 live trades)?
2. Overnight risk budget 1.5% total — do you want overnight positions at all in P1/P2?
3. Crypto sleeve cap 20% — confirm given tax/TDS drag (00 §11.4)?
4. Defined-risk-only options confirmed (no naked short options ever)? Recommend yes permanently.
5. Flatten policy on L3/L4: flatten everything vs protect-and-hold positional — pick default.
