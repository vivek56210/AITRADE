# ATIS — Autonomous Trading Intelligence Platform

> **Status: DESIGN PHASE.** These documents are the complete architecture and phase plan, written
> for review. The only code so far is the volume-profile playbook detectors (`src/atis/playbook`,
> see [Code](#code-volume-profile-playbook) below) — recommendation mode only, all setups CANDIDATE.
>
> Doc set version: **v0.2-draft** (validation pass applied — see [docs/09-VALIDATION-REVIEW.md](docs/09-VALIDATION-REVIEW.md)) · Date: 2026-07-11 · Markets: Indian Equities, Indian F&O, Crypto, Commodities (MCX)

---

## What ATIS is

ATIS is an institutional-grade trading intelligence platform that continuously observes markets,
builds an evidence-based model of current conditions, evaluates opportunities against measured
statistical edge, manages risk as an independent first-class function, executes under graduated
autonomy (recommend → assisted → autonomous), and learns from every outcome — including trades it
recommended but did not take.

It is designed to behave like a professional trading **organization** (research desk, portfolio
manager, risk desk, execution desk, compliance) — not like a trading bot.

**The default action is NO TRADE.** Everything in this design exists to make the exceptions to
that default safe, explainable, and positive-expectancy.

## What ATIS is not

- Not an indicator-crossover bot or a signal-selling service
- Not an HFT / market-making system (mid-frequency by design; see [00-VISION §6](docs/00-VISION.md))
- Not a win-rate or trade-count maximizer
- Not a black box — every decision carries a full, auditable evidence trail

---

## Document map (review order)

| # | Document | Covers |
|---|----------|--------|
| 0 | [docs/00-VISION.md](docs/00-VISION.md) | Mission, philosophy, priority stack, target markets, operating modes, success metrics, constraints, guiding principles |
| 1 | [docs/01-ARCHITECTURE.md](docs/01-ARCHITECTURE.md) | High-level architecture, planes, microservice decomposition, event backbone, canonical objects, storage, tech stack, security, observability, failure/recovery, scalability |
| 2 | [docs/02-AGENTS.md](docs/02-AGENTS.md) | Multi-agent roster and contracts, Trade Committee protocol, Confidence Engine math, LLM usage policy, agent lifecycle and degradation rules |
| 3 | [docs/03-DATA-PLATFORM.md](docs/03-DATA-PLATFORM.md) | Source catalog per market, ingestion, canonical schemas, Data Quality Engine, stream processing, feature store, knowledge graph, institutional memory, history/backfill |
| 4 | [docs/04-STRATEGY-ENGINE.md](docs/04-STRATEGY-ENGINE.md) | Market-knowledge detector specs (profile, structure, liquidity, order flow, SMC, Wyckoff, VWAP, options), regime engine, strategy framework and lifecycle, opportunity ranking, trade decision engine, dynamic trade management, backtesting and statistical validation |
| 5 | [docs/05-RISK-PORTFOLIO.md](docs/05-RISK-PORTFOLIO.md) | Independent risk kernel, pre-trade checks, position sizing, portfolio intelligence, capital allocation, drawdown governance, market health, VaR/stress testing, kill switches |
| 6 | [docs/06-LEARNING-ENGINE.md](docs/06-LEARNING-ENGINE.md) | Outcome capture, attribution, trade review, self-reflection, drift detection, model lifecycle, strategy evolution, research engine, digital twin and simulation |
| 7 | [docs/07-EXECUTION-ENGINE.md](docs/07-EXECUTION-ENGINE.md) | Operating modes, order lifecycle, execution algos, broker adapter layer, safety pipeline, live trade management, TCA, reconciliation, failure recovery |
| 8 | [docs/08-IMPLEMENTATION-ROADMAP.md](docs/08-IMPLEMENTATION-ROADMAP.md) | Phase-wise roadmap with exit gates, testing strategy, governance and audit framework, DR plan, cost bands, operating rituals, risk register |
| 9 | [docs/09-VALIDATION-REVIEW.md](docs/09-VALIDATION-REVIEW.md) | **The validation audit**: 21 internal findings (3 HIGH), externally verified July-2026 facts with sources (SEBI algo framework, F&O regime, crypto tax/venues, broker APIs, data vendors), rejected alternatives, residual risks, v0.1→v0.2 change log |
| 10 | [docs/10-VOLUME-PROFILE-PLAYBOOK.md](docs/10-VOLUME-PROFILE-PLAYBOOK.md) | Market/volume-profile setups for NIFTY & BANKNIFTY options (Oct 2026): setups A1–A5, B1–B4, C1–C3, D1–D2, India expiry/lot/STT/CAS rules, risk rules — the spec for `src/atis/playbook` |

*Note: `05-RISK-PORTFOLIO.md` was added beyond the originally listed six phase docs — risk is an
independent function in institutional design and warrants its own specification.*

## Master-prompt deliverable coverage

| Deliverable | Where |
|---|---|
| 1. High-level architecture | 01 §1–3 |
| 2. Microservice decomposition | 01 §3 |
| 3. AI agent collaboration | 02 §3–5 |
| 4. Data pipelines | 03 §3–6 |
| 5. Event-driven workflows | 01 §4, 02 §4 |
| 6. Knowledge graph design | 03 §8 |
| 7. Feature store | 03 §7 |
| 8. Model registry | 06 §7 |
| 9. Backtesting framework | 04 §9 |
| 10. Research framework | 06 §9 |
| 11. Strategy lifecycle | 04 §10 |
| 12. Continuous learning workflow | 06 §1–6 |
| 13. Self-improvement workflow | 06 §5, §8 |
| 14. Trade decision workflow | 04 §7, 02 §4 |
| 15. Portfolio management workflow | 05 §5–6 |
| 16. Risk management framework | 05 (entire) |
| 17. Broker integration architecture | 07 §4–5 |
| 18. Monitoring & observability | 01 §12, 07 §11 |
| 19. Security architecture | 01 §11 |
| 20. Phase-wise implementation roadmap | 08 §2–6 |
| 21. Technology stack recommendations | 01 §9 |
| 22. Scalability plan | 01 §10 |
| 23. Testing strategy | 08 §8 |
| 24. Disaster recovery plan | 08 §11, 01 §13 |
| 25. Governance & audit framework | 08 §10, 02 §3 (Governance Agent), 05 §11 |

## Conventions used in these documents

- **MUST / SHOULD / MAY** carry RFC-2119 meaning.
- **(P)** marks a *proposed default* number awaiting your review — every threshold, limit, and
  target so marked is configurable and stored in the versioned limits registry, never hardcoded.
- **R** is the risk unit: the rupee amount risked between entry and stop on one trade.
- **Modes**: P1 = Recommendation, P2 = Assisted execution, P3 = Constrained autonomy.
- **Criticality tiers**: C0 = must never be wrong (risk, orders); C1 = trading halts without it;
  C2 = quality degrades without it; C3 = offline/batch.
- Every doc ends with **Open questions for review** — decisions only you can make.

## Glossary

| Term | Meaning |
|---|---|
| Evidence | Typed, calibrated, provenance-carrying claim published by an agent |
| MarketState | Continuously updated per-instrument market understanding object |
| TradePlan | Fully specified trade proposal (entry/stop/targets/size/reasoning) |
| DecisionRecord | Immutable, hash-chained record of a decision and all its inputs |
| POC / VAH / VAL / IB | Point of Control, Value Area High/Low, Initial Balance (market profile) |
| HVN / LVN | High / Low Volume Node (volume profile) |
| BOS / CHOCH | Break of Structure / Change of Character (market structure) |
| FVG | Fair Value Gap (3-bar displacement gap) |
| CVD | Cumulative Volume Delta |
| OI / PCR / IVR / IVP / GEX | Open Interest, Put-Call Ratio, IV Rank, IV Percentile, Gamma Exposure |
| MWPL / SPAN | Market-Wide Position Limit, exchange margin methodology (F&O) |
| EV / PF / ECE | Expected Value, Profit Factor, Expected Calibration Error |
| DSR / PSR | Deflated / Probabilistic Sharpe Ratio (multiple-testing-aware) |
| WFO | Walk-Forward Optimization |
| BOCPD / HMM | Bayesian Online Change-Point Detection, Hidden Markov Model |
| PIT | Point-In-Time correctness (no lookahead in features) |
| TCA / OMS | Transaction Cost Analysis, Order Management System |
| Digital Twin | Same production engine driven by replayed/simulated events |
| Dead-man switch | Broker-side protection that survives total platform failure |

## Change log

- **v0.1** (2026-07-11) — initial full design set (docs 00–08).
- **v0.2** (2026-07-11) — adversarial validation pass: internal audit (21 findings, 3 HIGH —
  stock-F&O physical-delivery guard, equity short-selling constraint, statistically-sound
  calibration gates) + external fact verification against July-2026 primary sources (SEBI algo
  framework mechanics incl. the 10-orders/sec threshold, verified expiry/lot/margin regime,
  crypto derivatives-first tax posture on FIU venues, broker API and data-vendor realities).
  Full findings, sources, and per-doc changes in [docs/09-VALIDATION-REVIEW.md](docs/09-VALIDATION-REVIEW.md).

## Code: volume-profile playbook

`src/atis/playbook` implements [docs/10](docs/10-VOLUME-PROFILE-PLAYBOOK.md) in dependency-free
Python (3.11+). It reads **current-month index futures bars** (spot has no volume), builds the
prior-day and developing volume/TPO profile (POC, VAH/VAL, HVN/LVN, IB, tails, poor extremes,
single prints, composite balance), classifies open type and day type, and runs the setup detectors
bar by bar. Each signal carries the futures entry/stop/targets, the option structure (ATM/ITM buy,
debit spread, credit spread, iron condor/fly with strikes beyond profile levels), lot sizing from the
risk rules, an exit-by time, and the reasons any setup was skipped. It never places orders.

```bash
pip install -e '.[dev]' && pytest
python -m atis.playbook demo --days 30 --backtest           # synthetic data
python -m atis.playbook run --csv nifty_fut_1m.csv --symbol NIFTY --iv 0.13 --basis 45 --backtest
```

**Real data (no account needed):** `--upstox` downloads 1-minute NIFTY / BANKNIFTY index bars from
Upstox's public historical API (from 2022-01-01), cached per month under `data/upstox/`:

```bash
python -m atis.playbook run --upstox --symbol BANKNIFTY --from 2025-10-01 --to 2026-10-01 --backtest
python -m atis.playbook fetch --symbol NIFTY --from 2025-10-01 --out nifty_1m.csv   # just save a CSV
```

Index bars carry no volume, so every minute is weighted equally (a time-at-price / TPO profile) and
order-flow confirmations read `n/a`. Exchange holidays are inferred from gaps in the data and short
special sessions are dropped. In the console, set **Settings → Data source = upstox** with a date range.

CSV columns: `timestamp,open,high,low,close,volume[,buy_volume,sell_volume]` (IST). Without
buy/sell volume, order flow is estimated with the tick rule and delta-divergence confirmation is
reported as `n/a`. Without `--iv`, option premiums are not priced and sizing falls back to an
assumed delta. The backtest scores futures R-multiples and condor containment — **not option P&L**.
Every threshold lives in `config.py` as a proposed default (P).

### Operator console (UI)

`src/atis/console` (FastAPI) runs the engine in a background **replay worker** and serves the
React + TypeScript UI from `console-ui/` (the documented ops-console stack, 01 §9):

| Page | What it shows / does |
|---|---|
| Dashboard | Engine state, replay progress, today's structure (open type, IB, day type, dPOC, VA), live mini-chart, recent signals, activity feed, plan warnings, last backtest equity |
| Market | Futures candles with prior VA/POC/H/L, IB, dPOC, HVN/LVN, single prints, composite balance overlays; today's and prior volume profile; signal markers; pre-market plan; skip reasons; any past session |
| Setups | All 13 setups with rules, today's status (fired / skipped + reason / watching), counts, backtest stats, and an on/off switch that applies on the next bar |
| Signals | Every signal with futures plan, option legs, sizing, confirmations; mark **taken / ignored** with a note (persisted journal); CSV export |
| Backtest | Run a backtest as a background job (progress, cancel), equity curve, per-setup table, trade list |
| Monitor | Replay worker health (thread, heartbeat, bars/s, position), background jobs, process/threads/memory, live event log with level filter |
| Settings | Every data, context, risk, playbook and session-time parameter with defaults and validation, persisted to `atis_console.json`; "live" fields apply at once, the rest on Reset |

Controls in the top bar: Start / Pause / Resume, Step 1 bar, +30 bars, Stop, Reset (reload data with
current settings), replay speed.

```bash
pip install -e '.[console]'
cd console-ui && npm install && npm run build && cd ..   # builds into src/atis/console/static
atis-console                                              # http://127.0.0.1:8765
```

For UI development run `atis-console` and `npm run dev` in `console-ui/` (Vite proxies `/api`).
The console binds to 127.0.0.1 and has no login, so do not expose it on a network. Data comes from
replaying CSV or synthetic sessions; a live broker feed is not wired in yet.

## After review

1. You review the docs and answer the **Open questions** (consolidated in 08 §14, plus the three
   new ones in 09 §7).
2. We amend the docs (v0.3) and freeze them as the build baseline.
3. Phase 0 implementation begins per [08-IMPLEMENTATION-ROADMAP](docs/08-IMPLEMENTATION-ROADMAP.md).
