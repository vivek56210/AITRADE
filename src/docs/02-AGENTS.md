# 02 · Multi-Agent Intelligence Architecture

> **ATIS Design Doc 02 · v0.2-draft · 2026-07-11 · Status: awaiting review (validation pass applied — see [09](09-VALIDATION-REVIEW.md))**
> Upstream: [00-VISION](00-VISION.md), [01-ARCHITECTURE](01-ARCHITECTURE.md) ·
> Related: [04-STRATEGY-ENGINE](04-STRATEGY-ENGINE.md) (detector math), [05-RISK-PORTFOLIO](05-RISK-PORTFOLIO.md) (risk kernel)

---

## 1. Design stance

ATIS uses **specialized agents with a uniform contract**, not one monolithic model and not a
swarm of chatty LLMs. An agent is an independently versioned, independently deployable analyst
that consumes topics and publishes **Evidence** and/or **State** objects.

Three kinds:

| Kind | Nature | Examples | On the hot path? |
|---|---|---|---|
| Quantitative | Deterministic models/detectors; reproducible bit-for-bit | Liquidity, Profile, Order Flow, Regime, Options | Yes |
| LLM-backed | Language understanding, synthesis, critique | News, Sentiment (partly), Fundamental, Trade Review, Research, Devil's Advocate | **Never** — async, TTL'd output only |
| Hybrid | Quant core + LLM enrichment | Sentiment, Macro | Quant part only |

Why multi-agent at all: independent failure domains, per-agent calibration accountability,
independent versioning/promotion, and honest disagreement — the Confidence Engine needs
*uncorrelated* opinions, which a monolith cannot give.

## 2. The common agent contract

Every agent MUST declare and honor:

| Contract element | Meaning |
|---|---|
| Subscriptions | Input topics + required data tier (03 §2) |
| Publications | `signal.evidence` and/or `state.*` with declared schema |
| Cadence | streaming / periodic(τ) / event-triggered |
| Freshness | Every output carries `valid_until` (TTL); consumers MUST treat expired evidence as absent |
| Calibration duty | Any published `p` is tracked; per-agent Brier/ECE computed monthly (06 §5); persistent miscalibration ⇒ automatic weight shrinkage |
| Provenance | Output references the exact input event IDs and detector/model version |
| Health | Heartbeat + self-diagnostics on `ops.heartbeat`; DEGRADED is an explicit published state, never silence |
| Versioning | Semver; new versions ship shadow-first (§8) |
| Determinism | Quant agents: same inputs ⇒ same outputs (enforced by golden-day CI replay) |

### Evidence schema (the atomic unit of opinion)

```jsonc
{
  "evidence_id": "…", "agent": "orderflow@1.7.2",
  "scope": {"instrument": "NFO:NIFTY-FUT", "timeframe": "5m"},
  "type": "absorption_at_value_low",        // from the detector taxonomy (04 §2)
  "direction": "long" | "short" | "neutral" | "veto",
  "p": 0.61,                                 // calibrated P(thesis helps | this pattern)
  "strength": 0.8,                           // pattern quality within type, 0–1
  "valid_until": "…",
  "features": {"cvd_div": 1.9, "vol_z": 2.3},
  "provenance": ["event ids"],
  "validation_ref": "vreg://absorption/2.1", // stats behind p (04 §10)
  "narrative": "one-sentence human-readable summary"
}
```

`direction: "veto"` is special: it is not aggregated — it blocks (e.g., News Agent publishing
`event_embargo` 15 min before an RBI decision).

## 3. Agent roster

Grouped by layer. Each entry: **Mission · Inputs → Outputs · Cadence · Core techniques · Degradation behavior.**

### 3.1 Perception layer (quantitative unless noted)

**1. Market Observer** — *the assembler.*
Merges structure/profile/liquidity/flow/vol outputs into the canonical per-instrument
`state.market` object (01 §5). Inputs: all perception evidence + bars. Cadence: streaming, ≤250 ms.
Techniques: streaming state reduction; conflict flagging (contradictory sub-states are surfaced,
not averaged away). Degradation: publishes with `data_quality` + missing-section flags.

**2. Market Regime Agent** — *what market exists now?*
Inputs: multi-TF bars, breadth, vol surface, funding (crypto). Outputs: `state.regime` — regime
probability vector {trend↑, trend↓, range, mean-revert, high-vol, low-vol, event-driven, risk-on,
risk-off} per market + per instrument-class, with dwell time and change-point alerts.
Techniques: HMM (5–7 states) + gradient-boosted classifier ensemble over engineered features
(realized vol, Kaufman efficiency ratio, ADX, Hurst/DFA, autocorrelation, volume regime, breadth,
IV level/skew, funding) + BOCPD for change points (04 §3). Cadence: 1 m + on change-point.
Degradation: stale regime > 15 min ⇒ committee treats regime as "uncertain" (confidence cap).

**3. Liquidity Agent** — *where are the stops and the traps?*
Inputs: bars, swings, depth (tier-dependent). Outputs: liquidity map — pools above/below (equal
highs/lows, prior day H/L, round numbers, VWAP bands), pool scores, sweep events, trap flags.
Techniques: detector suite in 04 §2.3. Cadence: streaming per bar close.
Degradation: without depth data, pool inference is price-based only (declared in evidence).

**4. Market Profile Agent** — POC/VAH/VAL/IB, rotation, acceptance/rejection, value migration,
day-type classification (trend/normal/neutral/double-distribution). Techniques: 04 §2.1.
Cadence: 30 s during session. Degradation: none (bar-based, works at all tiers).

**5. Volume Profile Agent** — session + composite profiles, HVN/LVN, volume distribution shape.
Shares the histogram engine with #4; kept separate because composite profiles update on different
cadence and feed positional (multi-day) strategies. Cadence: 1 m session / EOD composite.

**6. Order Flow Agent** — delta, CVD, absorption, exhaustion, imbalance, (footprint where tier
allows). Inputs: aggressor-flagged trades (crypto: native; India: tick-rule estimate — declared);
depth per tier (crypto full book; NSE 5-level broker WS, **20-level via Dhan for the focus
watchlist** — 03 §2).
Techniques: 04 §2.4. Cadence: streaming. Degradation: tier C (broker-only India) ⇒ agent publishes
nothing for affected instruments; strategies requiring flow evidence auto-disable there.

**7. Options Intelligence Agent** — OI & ΔOI by strike, PCR (OI/volume), IV surface, IVR/IVP,
max pain, GEX (validation-gated: dealer-positioning assumptions are weak in India, 04 §2.7),
expiry dynamics, unusual options activity. Cadence: chain snapshot cadence (1–5 s indexes, 1 m
stocks). Degradation: stale chain ⇒ options strategies pause.

**8. News Intelligence Agent** (LLM-backed) — ingest → dedup (minhash + embedding) → entity
linking (KG) → classification (type, direction, impact, horizon) → **News Score** with freshness,
source reliability, fake-news heuristics (source rep + cross-confirmation requirement for
high-impact claims). Outputs: scored news evidence + `event_embargo` vetoes + event-impact
predictions labeled against realized moves (06). Cadence: continuous, 10–60 s.
Degradation: LLM down ⇒ classic pipeline (keyword/rule + finBERT-class) at reduced confidence;
embargo windows widen (fail-safe).

**9. Sentiment Agent** (hybrid) — X/Reddit/Telegram/YouTube/forums + FII/DII flows + options
positioning ⇒ market/sector/asset sentiment indices, fear-greed, retail-vs-institutional
divergence, crowding flags. Sentiment is primarily a **contrarian/risk input**, not an entry
trigger (04 §4). Cadence: 5–15 m. Degradation: absent sentiment ⇒ no effect on quant families,
capped confidence for news-momentum family.

**10. Macro Agent** (hybrid) — economic calendar (RBI/Fed/CPI/GDP), yields, DXY, USDINR, crude,
global indices ⇒ macro regime tags, event-risk windows, cross-asset stress flags.
Cadence: 15 m + calendar-driven.

**11. Fundamental Agent** (LLM-backed) — quarterly results, filings, promoter/insider activity,
valuation & quality scores; feeds position-trade universe screening and the KG. Cadence: daily +
event-driven (earnings). Not on any intraday path.

**12. Commodity Intelligence Agent** — inventories (EIA/API for energy), COMEX/LME cues, weather,
policy/import-export, USDINR pass-through for MCX pricing. Cadence: daily + event-driven.

**13. Crypto Intelligence Agent** — exchange flows, whale transfers, stablecoin flows, funding
rates & basis, liquidation heatmaps, dev activity; L1/L2 ecosystem health via KG.
Cadence: 5–15 m. Degradation: on-chain vendor down ⇒ funding/basis (exchange-native) still flow.

### 3.2 State layer

**14. Market Health Agent** — composite tradability: liquidity score, vol state, spread quality,
news risk, execution risk, data quality ⇒ `state.health` per market/instrument with gate bands
(05 §9). C1: health below floor ⇒ no new entries there, automatically.

### 3.3 Decision layer

**15. Strategy Manager Agent** — activates/deactivates strategies by regime affinity × validation
status × recent live health (06 drift signals); owns the live strategy roster; enforces "no
strategy trades outside its validated envelope."

**16. Trade Planner Agent** — converts top-ranked opportunities into complete TradePlans:
entry style/zone/max-chase, stop basis, target ladder, size *proposal* (risk kernel has final
say), management policy binding, full reasoning block (thesis, evidence, invalidation,
alternatives). Deterministic templates per strategy family (04 §7).

**17. Devil's Advocate Agent** (LLM-backed, grounded) — builds the strongest contra-case for
every plan from the *same* evidence store: contradicting evidence, absent confirmations,
regime mismatch, crowding, event proximity, historical failure analogs (vector memory).
Output: contra-case document + `confidence_penalty ∈ [0, 0.15]` (P) + optional escalation flag
(forces human review in P2/P3). Strictly grounded: every claim must cite evidence IDs or memory
records; unverifiable claims are dropped by the verifier. Pre-computes per-instrument contra
material continuously so committee latency stays in budget.

**18. Portfolio Manager Agent** — portfolio fit: correlation vs existing book, sector/asset
concentration, netting effects, Greeks impact (options), capital efficiency; proposes
allocation adjustments (05 §5–6). Can downgrade an opportunity's rank but not bypass risk.

**19. Risk Manager (Risk Kernel)** — **not an AI agent**: deterministic C0 service (05).
Listed here because it holds a committee seat with veto power. Pre-trade checks, sizing caps,
portfolio limits, drawdown governor state.

### 3.4 Execution layer

**20. Execution Agent** — algo selection (passive/aggressive/TWAP/iceberg), slicing, venue
choice (crypto), live order babysitting, trade-management execution (07). Quantitative + rules.

### 3.5 Learning & governance layer (all C2/C3, detailed in 06)

**21. Trade Review Agent** (LLM-backed) — post-trade forensics per trade + daily/weekly synthesis;
structured findings feed the research backlog.
**22. Learning Agent** — calibration tracking, drift detection, weight re-estimation,
retraining triggers.
**23. Research Agent** (LLM-backed) — hypothesis generation from reviews/anomalies/literature;
maintains the research backlog with expected-information-gain priorities (06 §9).
**24. Governance Agent** — mandate compliance on every DecisionRecord: complete reasoning?
limits respected? mode rules honored? detector versions all VALIDATED? Anomalies ⇒ block + escalate.
Also runs the periodic self-reflection audits (06 §5).

## 4. The Trade Committee — collaboration protocol

Every trade idea passes one gauntlet. Sequence (budget ≤ 5 s, LLM steps use pre-computed material):

```
 perception agents ──▶ signal.evidence ──▶ ┌────────────────────┐
                                           │ CONFIDENCE ENGINE  │  aggregate, calibrate
                                           └─────────┬──────────┘
                                                     ▼
                                           ┌────────────────────┐
                                           │ OPPORTUNITY RANKER │  EV, fit, top-K
                                           └─────────┬──────────┘
                                                     ▼
                                           ┌────────────────────┐
                                           │   TRADE PLANNER    │  full TradePlan
                                           └─────────┬──────────┘
                          contra-case                ▼
             ┌──────────────────┐          ┌────────────────────┐
             │ DEVIL'S ADVOCATE │─────────▶│  confidence adjust │
             └──────────────────┘          └─────────┬──────────┘
                                                     ▼
                                           ┌────────────────────┐
                                           │    RISK KERNEL     │  APPROVE / RESIZE / VETO
                                           └─────────┬──────────┘
                                                     ▼
                                           ┌────────────────────┐
                                           │  GOVERNANCE AGENT  │  mandate & record check
                                           └─────────┬──────────┘
                                                     ▼
                                     mode-manager routes the approved plan:
                                     P1 → recommendation to human (notifier + console)
                                     P2 → staged order awaiting one-click approval
                                     P3 → safety pipeline → execution
```

**Committee rules**

1. **Quorum:** each strategy family declares mandatory evidence classes (e.g., sweep-reversal
   requires liquidity + structure + flow-or-profile). Missing mandatory class ⇒ no opportunity.
2. **Contra-case is mandatory.** No plan reaches risk without a Devil's Advocate pass; its
   penalty applies before threshold checks.
3. **Abstention is the default.** Confidence < θ, EV_net < floor, health < floor, conflict > cap,
   embargo active — any one ⇒ NO TRADE, logged with reason (these logs train the meta-layer).
4. **Risk verdict is final** (upward override impossible; human may only *reduce* further).
5. **Everything becomes a DecisionRecord** — including abstentions and vetoed plans.
6. **Evaluation cadence:** committee runs are event-driven on evidence/state changes with a
   per-instrument debounce (max one run per instrument per 5 s, P) plus a slow periodic sweep —
   no busy-loop scanning, no missed triggers.

## 5. Confidence Engine

**Aggregation (log-odds, weighted, regime-conditional):**

```
For thesis τ (instrument, direction, horizon) with evidence set E:

  L(τ) = b_regime + Σ_{e ∈ E}  w(agent_e, type_e, regime) · g(age_e) · logit(p_e)

  P_raw = σ(L)                       # sigmoid
  conflict C = dispersion of direction-signed p_e (weighted)
  P_adj  = P_raw − penalty(C) − penalty_DA        # Devil's Advocate penalty
  confidence = P_adj  if all mandatory classes present, else min(P_adj, cap_missing)
```

- `w(·)` — learned per (agent, evidence-type, regime) from historical predictive contribution
  (regularized logistic regression over past evidence→outcome pairs, refit monthly, shrunk
  toward equal weights; 06 §6). Bootstrap phase uses equal weights + wide uncertainty.
- `g(age)` — freshness decay to 0 at `valid_until`.
- `b_regime` — regime base rate (e.g., long-breakout theses start lower in range regimes).
- **Veto evidence bypasses aggregation** entirely (embargo, health floor, DQ floor).

**Decision thresholds (P, per limits-registry):** trade requires
`confidence ≥ θ(regime, family)` **and** `EV_net ≥ 0.15R` **and** `health ≥ 0.6` **and**
`conflict ≤ C_max`. Default θ: 0.60 trend-following families, 0.62 mean-reversion, 0.65
news-momentum, +0.05 during first live month of any strategy.

**Calibration program (hierarchical — honest at small samples):** trade-level data is scarce
(a few plans/day), so calibration is measured where the statistical power actually is:

1. **Evidence level** — thousands of instances/month; per-agent reliability diagrams, ECE, and
   Brier decomposition (resolution vs calibration) run here with real power.
2. **Strategy level** — pooled with hierarchical shrinkage toward family priors.
3. **Final-confidence level** — assessed on rolling windows of ≥ 200 decisions using bootstrap
   CIs, never point-ECE on a thin month.

Miscalibrated agents get automatic weight shrinkage + a review ticket. Final-confidence
miscalibration (CI excludes tolerance for 2 consecutive windows) ⇒ thresholds auto-raise +0.05
until restored (self-throttling). **No calibration gate binds before its minimum sample exists**
— until then bootstrap-CI checks apply (this rule also reshapes gate G1, 08 §3).

## 6. Communication rules

- Agents communicate **only via topics** (evidence/state) — no point-to-point RPC between
  analysts. Exceptions: trade-committee orchestrator invokes Planner/DA/Risk synchronously
  (they are steps, not peers); feature-store reads.
- Shared **blackboard** = MarketState in Redis (hot) + ClickHouse (history). Agents read the
  blackboard; only Market Observer writes the merged object.
- Rationale: decoupling, independent replay, per-agent audit, and the ability to run any agent
  against the twin with zero code change.

## 7. LLM usage policy

| Agent | Default model | Cadence / volume | Hard rules |
|---|---|---|---|
| News scoring | claude-haiku-4-5 (bulk) → claude-sonnet-5 (high-impact escalation) | continuous | Structured JSON only; enum severities; every claim cites source span; verifier drops unverifiable output |
| Sentiment synthesis | claude-haiku-4-5 | 5–15 m batches | Aggregates only; no per-post trading signals |
| Fundamental extraction | claude-sonnet-5 | daily/event | Citations mandatory; numbers cross-checked vs source doc parse |
| Devil's Advocate | claude-sonnet-5 | per-plan (pre-computed base) | Grounded to evidence store + memory; bounded penalty; no new "facts" |
| Trade Review | claude-fable-5 | EOD/weekly | Output is analysis doc + structured findings; feeds research backlog |
| Research Agent | claude-fable-5 | weekly deep runs | Hypotheses only — nothing it writes trades without full validation pipeline |

**Invariants:** LLMs never emit numbers that flow into price/size arithmetic; LLM outputs are
classifications, scores in bounded enums, and cited text. All prompts live in the model registry
(versioned, eval-harnessed with golden sets before promotion, 06 §7). Daily token budget with
automatic degradation to classic NLP on breach. Provider-agnostic gateway; logs of all
prompts/responses retained (audit + retraining).

## 8. Agent lifecycle

`SPEC → OFFLINE EVAL (golden sets + replay) → SHADOW (publishes to *.shadow, scored ≥ 4 weeks) →
CANARY (weight ε in confidence engine) → ACTIVE → (DEGRADED ↔ ACTIVE) → RETIRED`

- Promotion criteria per stage live in the registry (min sample, min calibration, min marginal
  contribution vs incumbent). Demotion is automatic on drift/calibration triggers (06 §6).
- DecisionRecords pin exact agent versions — any historical decision names the code that made it.

## 9. Degradation matrix (committee behavior when an agent is absent/stale)

| Agent down/stale | Committee behavior |
|---|---|
| Regime | Confidence capped at 0.55 (P); no new swing entries; intraday families in "reduced" |
| Liquidity / Profile / Structure | Families with that class mandatory ⇒ disabled; others unaffected |
| Order Flow | Flow-dependent families disabled per instrument (expected & permanent at Tier C) |
| News | **Fail-safe:** embargo windows widen (±30 min around calendar events); news-momentum family off |
| Sentiment / Fundamental / Macro | No hard block; related confidence contributions → 0 |
| Options Intel | Options strategies pause; futures/equity unaffected |
| Market Health | **Fail-closed:** no new entries anywhere in that market |
| Devil's Advocate | Plans proceed with max penalty applied (0.15) — absence of critique is treated as critique |
| Risk kernel | **Everything halts** (01 §13) |

## 10. Open questions for review

1. Devil's Advocate authority: penalty-only (proposed) or hard-veto power in P3?
2. Mandatory evidence classes per family — review the quorum table in 04 §4 once strategies are agreed.
3. LLM budget ceiling per month (drives news coverage breadth) — bands in 08 §12.
4. Sentiment sources: X API paid tier vs scrape-free alternatives (Reddit/Telegram only) for v1?
5. Any additional agent you want in v1 (e.g., a dedicated FII/DII flow agent split out of Sentiment)?
