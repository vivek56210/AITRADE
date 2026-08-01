# 04 · Strategy Engine & Market Knowledge Foundation

> **ATIS Design Doc 04 · v0.2-draft · 2026-07-11 · Status: awaiting review (validation pass applied — see [09](09-VALIDATION-REVIEW.md))**
> Upstream: [02-AGENTS](02-AGENTS.md), [03-DATA-PLATFORM](03-DATA-PLATFORM.md) ·
> Related: [05-RISK-PORTFOLIO](05-RISK-PORTFOLIO.md), [06-LEARNING-ENGINE](06-LEARNING-ENGINE.md)

---

## 1. Role

The strategy engine turns **MarketState + Evidence** into **ranked, fully specified,
risk-checkable TradePlans**. Its two pillars:

1. **Market Knowledge Foundation** — a library of *detectors*: formal, falsifiable
   implementations of auction/profile/structure/liquidity/flow/SMC/Wyckoff concepts. Detectors
   are hypotheses, not truths — each earns (or loses) the right to publish through the
   **validation registry**.
2. **Strategy framework** — declarative strategies that combine validated evidence into setups,
   entries, exits, and management policies, each with a governed lifecycle.

> **Prime rule:** *No unvalidated concept ever contributes to a trading decision.* A detector in
> CANDIDATE state publishes only to shadow topics; REJECTED detectors publish nothing. The
> validation registry (§10) is the single source of truth for what ATIS currently believes works.

## 2. Market Knowledge Foundation — detector specifications

Every detector ships as:

```yaml
detector: liquidity_sweep
version: 1.3.0
tier_required: B        # data tier (03 §2)
inputs: [swing_map, atr_14, bars_5m]
params: {tolerance_atr: 0.10, max_pierce_atr: 0.5, reclaim_bars: 3}
emits: Evidence(type=liquidity_sweep, direction, p, strength)
validation:            # maintained by the learning engine (06)
  status: VALIDATED | CANDIDATE | REJECTED
  sample: 1841
  hit_rate: 0.57       # thesis-helpful rate at declared horizon
  avg_R: +0.21
  per_regime: {trend: +0.05R, range: +0.34R, high_vol: +0.11R}
  last_review: 2026-06-30
```

Initial parameterizations below are **starting hypotheses (P)** — the registry, not this
document, is authoritative once live.

### 2.1 Market & Volume Profile

- **Profile histogram:** volume-at-price per session (and TPO structure at 30-min periods).
  **POC** = max-volume price; **Value Area** = smallest price set around POC covering 70% of
  volume; **VAH/VAL** = its bounds. **IB** = first 60 min range.
- **HVN/LVN:** prominence-filtered local maxima/minima of the smoothed composite histogram
  (kernel-smoothed, prominence ≥ 15% of POC volume).
- **Acceptance:** ≥ 2 consecutive 30-min periods building volume beyond a reference level
  (VA edge, IB edge, prior day H/L). **Rejection:** pierce + close back within 1 period, leaving
  a low-volume tail.
- **Value migration:** day-over-day displacement of (POC, VA) — direction and overlap
  classification (higher/lower/inside/outside value ⇒ day-type prior).
- **Day type classifier:** trend / normal / normal-variation / neutral / double-distribution,
  from IB extension and rotation counts.

### 2.2 Market structure

- **Swing points:** ATR-filtered zigzag — a swing high requires subsequent retracement
  ≥ 1.5×ATR(14) (per TF); symmetric for lows. Emits the swing map (HH/HL/LH/LL sequence).
- **BOS (Break of Structure):** *body close* beyond the last confirmed swing extreme in the
  prevailing direction. **CHOCH (Change of Character):** first BOS against the prevailing
  structure direction. Wick-only breaks are recorded but not BOS (parameter under validation).
- **Compression:** contracting swing ranges + falling ATR ratio (ATR14/ATR50 < 0.75) + volume
  contraction. **Expansion:** the inverse, usually post-breakout.

### 2.3 Liquidity

- **Equal highs/lows:** ≥ 2 swing extremes within 0.1×ATR tolerance ⇒ inferred stop cluster
  beyond them. **Pool score** grows with touches, age, and TF confluence (plus round numbers,
  prior day/week H/L, VWAP bands as minor components).
- **Liquidity sweep:** trade pierces a pool by ≤ 0.5×ATR then *reclaims* (closes back on the
  pool's origin side) within 3 bars. Direction of resulting evidence: against the sweep.
- **Institutional trap heuristic:** sweep + failed follow-through + opposing delta surge
  (Tier A/B) — composite detector, separately validated.
- **Stop-run risk flag:** for *our* positions — when our stop sits inside a scored pool, the
  planner widens/relocates the stop basis (risk kernel re-checks size).

### 2.4 Order flow (Tier A native; Tier B estimated via tick rule — stamped on output)

- **Delta / CVD:** aggressive buy − sell volume per bar; cumulative along session.
- **Delta divergence:** price new extreme, CVD fails to confirm (≥ 20-bar swing basis).
- **Absorption:** heavy aggressive volume into a level with price progress < 0.25×ATR and
  delta/price efficiency in the bottom decile — passive side is absorbing.
- **Exhaustion:** climactic volume (top decile) + range expansion + immediate stall/reversal
  bar; often terminal for the move.
- **Imbalance (footprint, Tier A only):** ≥ 3:1 bid/ask stacked imbalances at consecutive levels.

### 2.5 Smart Money Concepts (validation-gated — these are the first candidates for REJECTED)

- **Displacement:** move ≥ 1.5×ATR within ≤ 3 bars, low overlap.
- **FVG:** 3-bar gap (bar1.high < bar3.low bullish; inverse bearish) created *by displacement*;
  tracked until mitigated (50% or full fill — both variants under validation).
- **Order block:** last opposite candle before a displacement that produced BOS; zone = candle
  body (variant: full range); invalidated on body-close through.
- **Breaker / mitigation block:** failed OB that flips role after being traded through.
- **Premium/discount:** position within the active dealing range (above/below 50%); only defined
  when a range exists; used as a *filter*, not a signal.
- **Liquidity run continuation:** post-sweep expansion targeting the next pool.

### 2.6 Wyckoff

Phase classifier over trading ranges: detects **accumulation/distribution ranges**, and events —
**spring** (sweep below range support + reclaim), **upthrust** (inverse), **SOS** (range breakout
on expanding spread/volume), **LPS** (higher-low retest after SOS), markup/markdown transitions.
Implementation: rule-scored event grammar + HMM over range states; publishes only when phase
confidence ≥ 0.7 (P). Expected to be low-frequency, higher-timeframe evidence.

### 2.7 VWAP & options analytics

- **VWAP suite:** session, weekly, anchored (anchor registry: swing extremes, earnings/events,
  high-volume days); ±1σ/±2σ bands (volume-weighted). Evidence: band interactions, VWAP
  reclaim/loss, slope.
- **Options:** OI/ΔOI support-resistance inference, PCR extremes (z-scored, contrarian),
  IV rank/percentile (52-week window), max pain (expiry-week gravitation — CANDIDATE),
  **GEX** (dealer-gamma regime: positive ⇒ mean-reverting pin risk, negative ⇒ acceleration —
  CANDIDATE in India; dealer-positioning assumptions weaker than US), IV crush calendar
  awareness (event → post-event vol behavior).

### 2.8 Statistical annotations (mandatory on every Evidence/Opportunity)

Every published signal carries: calibrated probability, confidence, expected value (net, in R),
sample size behind the stats, per-regime win rate/avg-R, and the validation reference. Portfolio
metrics (Sharpe/Sortino/PF/maxDD/Kelly) attach at strategy and book level, not per-signal.

## 3. Regime engine (consumed from 02 §3.1-2; math lives here)

- **Feature set:** realized vol (Yang-Zhang, multi-window), vol-of-vol, Kaufman ER(20),
  ADX(14), Hurst via DFA, return autocorr(1–5), volume regime z, range/expansion ratios, breadth
  (adv/dec, % above 20/50-DMA for indices), IV level + skew + term slope (options markets),
  funding + basis (crypto), cross-asset stress (USDINR, yields, DXY, crude).
- **Models:** 5–7 state Gaussian HMM (interpretable dwell/transition structure) + gradient-boosted
  classifier trained on *rule-labeled* historical regimes; ensemble by probability averaging;
  **BOCPD** on vol+ER stream for change-point alarms.
- **Output:** `state.regime` probability vector + dwell time + changepoint flag. Regime taxonomy
  maps the master-prompt list {trending, sideways, mean-reverting, high/low vol, breakout,
  distribution, accumulation, news/event-driven, risk-on/off, bull/bear} onto
  direction × volatility × efficiency × context-flag axes (breakout/fake-breakout are *event*
  labels, used post-hoc for learning, not standing states).
- **Acceptance test:** regime engine must beat naive persistence on 5+ years replay, and
  strategy families must show statistically distinct performance across its states (else it's
  decoration and gets rebuilt).

## 4. Strategy framework

A strategy is a **declarative YAML spec + referenced code + a validation dossier**, e.g.:

```yaml
strategy: nifty_sweep_reversal
version: 2.1.0
status: PAPER                     # lifecycle §10
markets: [NFO:NIFTY-FUT, NFO:BANKNIFTY-FUT]
horizon: intraday
regime_affinity: {range: 1.0, high_vol: 0.6, trend: 0.3, event_window: 0.0}
evidence_quorum:                  # mandatory classes (02 §4)
  all_of: [liquidity_sweep, structure_context]
  any_of: [delta_divergence, absorption, profile_rejection]
setup: sweep of session/prior-day extreme pool into VAL/VAH zone with reclaim
entry: {style: limit_zone, zone: reclaim_band, max_chase_atr: 0.25, expire_bars: 5}
stop:  {basis: beyond_sweep_extreme, buffer_atr: 0.35}
targets: [{basis: POC, size_pct: 50}, {basis: opposite_value_edge, size_pct: 50}]
management_policy: range_reversal_v3      # §8
risk: {max_concurrent: 2, max_daily_attempts: 3}
capacity: {max_pct_1min_vol: 8, max_lots: 40}
costs_model: nfo_futures_v2
validation_dossier: vreg://strategies/nifty_sweep_reversal/2.1.0
```

### Seed strategy families (v1 candidates — each still must pass §9–10 gates)

| Family | Hypothesis (edge source) | Regimes | Markets | Key evidence quorum |
|---|---|---|---|---|
| Trend pullback continuation | Established trends resume after orderly pullbacks to value (participation persistence) | trend | Equities, index futures, crypto | structure(BOS chain) + pullback-to-zone (VWAP/OB/HVN) + flow-or-volume confirm |
| Value-edge mean reversion | In balanced markets, excursions to value extremes revert to POC (auction rotation) | range | Index futures, liquid equities, crypto | profile(VA edge rejection) + no-acceptance + flow divergence |
| Liquidity sweep reversal | Stop runs into pools without follow-through mark short-term extremes (trapped traders) | range, high-vol | Index futures, BTC/ETH | sweep + reclaim + delta confirm |
| Breakout with acceptance | Breakouts that *build acceptance* beyond prior value continue (initiative activity) | compression→expansion | Equities, crypto, MCX | compression + break + acceptance(volume/profile) — anti-fake-breakout filter is the point |
| Opening playbook (India) | Gap + pre-open auction context creates repeatable open types (gap-go / gap-fade) | session-open | Index futures | gap size class + overnight context + IB behavior |
| Defined-risk premium selling | High IVR + range regime + no events ⇒ IV overstates realized (variance risk premium) | range, IVR>60, ex-event | Index options (spreads/condors only — **never naked**) | IVR + regime + GEX(if validated) + event calendar clear |
| Funding carry (crypto) | Persistent positive funding pays delta-neutral short-perp/long-spot (leverage demand premium) | any, funding-persistent | BTC/ETH majors | funding percentile + basis + venue risk checks |
| News/event momentum | Validated event types produce continuation drift (post-event underreaction) | event-driven | Equities, crypto | news score + type-specific validated playbook + liquidity floor |

Sentiment/fundamental evidence acts as **filters and risk modifiers** across families (crowding
flag ⇒ smaller size; fundamental red flag ⇒ no longs), not as standalone entries in v1.

**Reality constraints binding all families (added by validation review, [09](09-VALIDATION-REVIEW.md)):**

1. **Equity shorts are intraday-only** (no SLB in v1) — positional short expression must use
   stock futures/options, which exist only for F&O-list names (risk check 05 §3.17).
2. **Stock F&O positions never enter the physical-delivery window** — flat or rolled by T-4
   sessions before expiry (risk check 05 §3.16). Index derivatives are cash-settled and exempt.
3. **News/event momentum cannot be honestly backtested** without point-in-time news archives —
   this family validates **live-forward only**: extended PAPER (12 weeks, P) replaces historical
   backtest gates until a PIT archive is acquired (03 §3.4).
4. **Premium selling** must respect the verified expiry regime ([09 §3.1](09-VALIDATION-REVIEW.md)):
   NIFTY weekly (Tue) and SENSEX weekly (Thu) are the only weeklies — BANKNIFTY is monthly-only;
   +2% additional ELM on short index options on their expiry day; calendar-spread margin benefit
   vanishes on expiry day (index since Feb 2025, single-stock since May 2026) — margin
   projections must model these spikes. Expiry-session policy: no fresh short-gamma on expiry
   sessions unless separately validated. Options management policies operate in premium/Greeks
   terms, not price-only.
5. **Funding carry** is contingent on the venue-policy decision (00 §11.4); the cross-venue
   variant (spot and perp on different venues) is research-track only — transfer latency, basis
   risk, and TDS mechanics make it materially harder than single-venue carry.

## 5. Signal → Opportunity

When a strategy's quorum satisfies on live evidence, it emits an **Opportunity**:
`{strategy, instrument, direction, entry_zone hypothesis, invalidation hypothesis, structural
targets, p_win (calibrated per-strategy model), EV_net_R (after full cost model), horizon,
capacity_check, evidence_bundle}`. All opportunities — including those later rejected — are
logged for counterfactual learning (06 §2).

## 6. Opportunity Ranking Engine

```
score = w₁·EV_net_R + w₂·p_win + w₃·liquidity_score + w₄·capital_efficiency
      + w₅·portfolio_fit − w₆·crowding_penalty − w₇·correlation_overlap
```

- `portfolio_fit` from Portfolio Manager (marginal risk contribution, diversification benefit).
- Constraints before scoring: capacity floor, health floor, embargo, per-underlying/per-sector
  live-position caps.
- Top-K (default 3 concurrent new plans platform-wide, P) proceed to the Trade Committee; ranks
  and scores are logged for every candidate (missed-opportunity learning).
- Weights `w` start heuristic (P), then re-fit quarterly from realized outcomes (06 §6) —
  subject to the same validation gates as everything else.

## 7. Trade Decision Engine

The committee (02 §4) produces, for each surviving opportunity, a decision among:
**TRADE / NO-TRADE / WATCH** (re-arm on condition). A TRADE decision requires the full TradePlan
(01 §5) with every field populated — side, order style, entry zone + max entry, stop + basis,
target ladder + bases, size + caps applied, horizon, confidence, p_win, RR, EV_net, management
policy — plus the **reasoning block**:

1. Thesis (one paragraph, human-readable)
2. Supporting evidence (IDs + weights + one-liners)
3. Contra-case (Devil's Advocate output — strongest argument against)
4. Invalidation (what makes this wrong, precisely — maps to stop basis)
5. Alternative scenarios ("if X instead, then Y" — at least the opposite-direction read)
6. Why now / why this instrument vs alternatives (ranking context)

**No-trade reasons are first-class outputs** — published to the console with the same structure
(what was close, what was missing). This is half the product in P1.

## 8. Dynamic trade management

Management policies are versioned rule-tables bound per strategy; the Execution Agent enforces
them; the committee is re-invoked only for reversals.

| Trigger (examples) | Action |
|---|---|
| T1 hit | Take size_pct, stop → breakeven + costs |
| Structure BOS against position | Exit remainder |
| Evidence decay: confidence < θ_hold (0.45 P) | Reduce 50% |
| Regime flip against family affinity | Tighten stop to last swing / exit at next favorable rotation |
| Adverse news shock (score > threshold against position) | Immediate reduce/exit (veto-class event) |
| Time stop (no progress in N bars, family-specific) | Exit |
| Trailing | Structure-based (behind last confirmed swing), never fixed ticks |
| Scale-in | Only at plan-predefined add zones with fresh evidence; **never average losers** (hard rule, risk-enforced) |
| Target extension | Allowed only on new confirming evidence + committee quick-pass |
| Re-entry | Fresh setup required; max attempts per day per strategy |
| Reversal | Full committee re-run; counts against both strategies' attempt budgets |

Managed-exit RL (offline RL over management decisions) is a **research-track item** (06 §9),
not v1: rules first, learned policies only after the rule baseline is measured.

## 9. Backtesting framework

- **Engine parity:** the event-driven replayer feeds the *same* committee/risk/execution code
  (01 §7). A separate vectorized pre-screener (polars) exists for coarse research scans only —
  nothing is promoted from vectorized results alone.
- **Fill realism by tier:** Tier A — queue-position-pessimistic L2 replay; Tier B/C — no
  intra-bar limit-fill optimism: limit fills require traded-through price; market orders pay
  spread + impact model (calibrated from our own TCA data as it accumulates); partial fills
  modeled from displayed size (P: ≤ 20% of touch volume). Options fills are quote-driven with a
  spread haircut (cross a configured fraction of the touch spread — never mid-fills) plus a
  minimum-quote-size screen; illiquid strikes are untradeable in backtests by construction.
- **Cost model (mandatory, per venue-segment):** brokerage, STT/CTT, exchange txn charges, SEBI
  fee, stamp duty, GST, slippage model, crypto maker/taker + funding; India intraday vs delivery
  distinctions; expiry STT rules for ITM options (auto-square-off policy in 07).
- **Protocols:** walk-forward (default train 18 m → validate 6 m → step 3 m) for rule strategies;
  **purged K-fold with embargo** for ML components; **regime-stratified reporting** mandatory —
  a strategy must publish per-regime results, not just aggregates.
- **Multiplicity control:** every parameter trial is logged (the research workbench does this
  automatically); promotion requires **Deflated Sharpe Ratio** accounting for trials, PSR > 0.95
  vs zero, and (for families with many variants) White's Reality Check/SPA on the family.
- **Robustness requirements:** parameter-plateau (performance stable across ±20% parameter
  neighborhood — no cliff optima); cost/slippage stress ×1.5 must keep expectancy > 0;
  Monte Carlo (block-bootstrap trade sequences) ⇒ drawdown distribution, p5 path must respect
  the risk budget (05 §7); minimum 100 trades or 3 years, whichever binds harder.

**Backtest report template:** equity curve + per-regime table + rolling expectancy + DSR/PSR +
MC drawdown fan + capacity estimate + cost sensitivity + failure-mode narrative ("when does this
lose, and do we detect that condition live?").

## 10. Statistical validation gates & strategy lifecycle

```
IDEA → RESEARCH → VALIDATED → PAPER → PILOT → SCALED
                     │            │       │       │
                     └──────────── WATCH ◀┴───────┘ → RETIRED (dossier archived, never deleted)
```

| Transition | Gate (all required, P) |
|---|---|
| RESEARCH → VALIDATED | §9 protocol passed: DSR > 0, PSR ≥ 0.95, plateau, cost-stress, per-regime coherence, ≥100 trades OOS, written dossier + Governance sign-off |
| VALIDATED → PAPER | Runs on live data in paper env ≥ 4 weeks; live evidence distributions match research (PSI < 0.2); no engineering faults |
| PAPER → PILOT | Paper expectancy within 1σ of research expectation; calibration holds; human approval |
| PILOT (capped: 0.25× normal size, max 3 concurrent) → SCALED | ≥ 30 live trades; realized costs within 1.25× model; expectancy > 0; no risk breaches; TCA clean |
| any → WATCH | Drift alarm (06 §6): rolling expectancy CI excludes research value, calibration decay, regime dependency shift |
| WATCH → RETIRED | Confirmed deterioration over defined window, or edge explained away (crowding/structural change). Retirement is a *success* of the process — target ≥ 1/year (00 §9) |

**Registry:** every strategy/detector version, its dossier, promotion history, and live
performance live in the strategy registry (PG + MLflow). **Hot parameter edits are forbidden** —
any change is a new version entering at VALIDATED-gate minimum. The Strategy Manager only ever
runs registry-ACTIVE versions inside their validated regime envelope.

## 11. Open questions for review

1. Confirm seed families (§4) — anything to add/remove? (Notably: premium *selling* comfort level; funding carry requires the crypto venue decision from 00 §11.)
2. Concurrent new-plan cap K=3 and pilot sizing 0.25× — acceptable starting points?
3. Walk-forward windows (18/6/3 months) vs faster iteration (12/3/1) for intraday families?
4. Minimum-evidence bar for SMC detectors: keep them CANDIDATE-only until each shows ≥55% hit rate on ≥300 OOS instances (P), or set stricter?
5. Do you want WATCH-state strategies visible in the console (recommended) or silent?
